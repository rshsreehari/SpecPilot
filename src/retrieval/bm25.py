from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass

from src.retrieval.base import RetrievedChunk
from src.retrieval.rrf import reciprocal_rank_fusion

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def tokenize(text: str) -> list[str]:
    """Lowercase, split on anything that isn't alphanumeric or underscore. Underscores
    are kept because parameter names commonly use them (e.g. trial_period_days)."""
    return _TOKEN_RE.findall(text.lower())


@dataclass(frozen=True)
class _ChunkDoc:
    chunk_id: int
    endpoint_id: int
    provider_id: str
    method: str
    path: str
    operation_id: str | None
    text: str
    length: int


class BM25Index:
    """Hand-implemented Okapi BM25, held entirely in memory, always built from exactly
    one provider's chunks.

    This is a deliberate, load-bearing design constraint, not an implementation detail:
    IDF - inverse document frequency - is a per-corpus statistic (how rare is this term
    *in this collection*). Building one shared index across multiple providers' chunks
    and filtering by provider only after scoring does not fix this - the damage happens
    at scoring time, when document-frequency counts (and therefore every IDF value) are
    computed across a corpus that mixes unrelated APIs' vocabularies. A term that's rare
    in Stripe's docs but common in GitHub's would get an inflated IDF for GitHub
    documents and a distorted one for Stripe's, in both directions, silently - the
    results would still look plausible, which is exactly what makes this class of bug
    dangerous. See retrieval/factory.py for how one BM25Index per provider is built and
    cached, and MultiProviderBM25Retriever below for how "search all providers" is
    implemented instead: N single-provider indices queried independently and fused by
    rank (RRF), never one pooled index.

    Time complexity:
      - Build: O(T) where T is the total token count across the provider's chunks - one
        pass to tokenize every document and populate the inverted index.
      - Query: O(Q * P_avg) where Q is the number of unique query terms and P_avg is the
        average posting-list length per term - for each query term we only walk the
        chunks that actually contain it, never the full corpus.

    IDF uses ln(1 + (N - n + 0.5) / (n + 0.5)) rather than the classic Robertson form
    ln((N - n + 0.5) / (n + 0.5)), which can go negative when a term appears in more than
    half the corpus - a real risk in a small provider's corpus.
    """

    def __init__(self, provider_id: str, k1: float = 1.5, b: float = 0.75) -> None:
        self.provider_id = provider_id
        self.k1 = k1
        self.b = b
        self._docs: dict[int, _ChunkDoc] = {}
        self._postings: dict[str, dict[int, int]] = defaultdict(dict)
        self._avgdl = 0.0

    @classmethod
    def build(
        cls,
        provider_id: str,
        chunks: list[tuple[int, int, str, str, str | None, str]],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> BM25Index:
        """chunks: (chunk_id, endpoint_id, method, path, operation_id, text), all
        belonging to `provider_id` - the caller is responsible for that scoping (see
        retrieval/factory.py::load_bm25_index)."""
        index = cls(provider_id=provider_id, k1=k1, b=b)
        total_length = 0

        for chunk_id, endpoint_id, method, path, operation_id, text in chunks:
            tokens = tokenize(text)
            doc = _ChunkDoc(
                chunk_id=chunk_id,
                endpoint_id=endpoint_id,
                provider_id=provider_id,
                method=method,
                path=path,
                operation_id=operation_id,
                text=text,
                length=len(tokens),
            )
            index._docs[chunk_id] = doc
            total_length += len(tokens)

            term_counts: dict[str, int] = defaultdict(int)
            for token in tokens:
                term_counts[token] += 1
            for term, count in term_counts.items():
                index._postings[term][chunk_id] = count

        index._avgdl = total_length / len(index._docs) if index._docs else 0.0
        return index

    def _idf(self, term: str) -> float:
        n_docs = len(self._docs)
        n_containing = len(self._postings.get(term, {}))
        if n_containing == 0:
            return 0.0
        return math.log(1 + (n_docs - n_containing + 0.5) / (n_containing + 0.5))

    def score(self, query: str, top_k: int) -> list[tuple[int, float]]:
        """Returns (chunk_id, score) pairs, highest first, for chunks matching at least
        one query term. Chunks matching zero query terms are never scored or returned."""
        scores: dict[int, float] = defaultdict(float)

        for term in set(tokenize(query)):
            postings = self._postings.get(term)
            if not postings:
                continue
            idf = self._idf(term)
            for chunk_id, freq in postings.items():
                doc_length = self._docs[chunk_id].length
                denom = freq + self.k1 * (1 - self.b + self.b * doc_length / self._avgdl)
                scores[chunk_id] += idf * (freq * (self.k1 + 1)) / denom

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return ranked[:top_k]

    def chunk(self, chunk_id: int) -> _ChunkDoc:
        return self._docs[chunk_id]

    def __len__(self) -> int:
        return len(self._docs)


class BM25Retriever:
    def __init__(self, index: BM25Index) -> None:
        self._index = index

    async def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        ranked = self._index.score(query, top_k)
        return [
            RetrievedChunk(
                chunk_id=chunk_id,
                endpoint_id=self._index.chunk(chunk_id).endpoint_id,
                provider_id=self._index.chunk(chunk_id).provider_id,
                text=self._index.chunk(chunk_id).text,
                method=self._index.chunk(chunk_id).method,
                path=self._index.chunk(chunk_id).path,
                operation_id=self._index.chunk(chunk_id).operation_id,
                score=score,
            )
            for chunk_id, score in ranked
        ]


class MultiProviderBM25Retriever:
    """The "search all providers" case for BM25. Queries each provider's own BM25Index
    independently (each with its own, uncorrupted IDF statistics) and fuses the rankings
    with Reciprocal Rank Fusion - the same fusion HybridRetriever uses to combine vector
    and BM25 results, applied here across providers instead of across strategies. Never
    builds one pooled index across providers; see BM25Index's docstring for why that
    would be wrong, not just different."""

    def __init__(self, indices: list[BM25Index], k: int = 60) -> None:
        self._retrievers = [BM25Retriever(index) for index in indices]
        self._k = k

    async def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        if not self._retrievers:
            return []
        result_lists = [await retriever.search(query, top_k) for retriever in self._retrievers]
        return reciprocal_rank_fusion(result_lists, self._k, top_k)
