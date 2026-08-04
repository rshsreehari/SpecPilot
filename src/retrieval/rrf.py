from __future__ import annotations

from src.retrieval.base import RetrievedChunk


def reciprocal_rank_fusion(
    result_lists: list[list[RetrievedChunk]], k: int, top_k: int
) -> list[RetrievedChunk]:
    """RRF score(d) = sum over result lists L that contain d: 1 / (k + rank_L(d)).

    Fuses by rank position, not raw score, because the lists being combined can come from
    scoring methods on entirely different, incomparable scales (cosine similarity vs
    BM25), or from independently-scored corpora (one BM25 index per provider) where even
    the *same* scoring method isn't comparable across lists - document frequency
    statistics differ per corpus. Rank position needs no calibration between lists at
    all: "3rd most relevant in this list" means the same thing regardless of the raw
    score or which corpus it was computed against.

    Used both to fuse vector+BM25 results within one provider (HybridRetriever) and to
    fuse N providers' independently-built BM25 indices when no provider is specified
    (MultiProviderBM25Retriever) - the same fusion problem in both cases.
    """
    rrf_scores: dict[int, float] = {}
    chunks_by_id: dict[int, RetrievedChunk] = {}

    for results in result_lists:
        for rank, chunk in enumerate(results, start=1):
            rrf_scores[chunk.chunk_id] = rrf_scores.get(chunk.chunk_id, 0.0) + 1 / (k + rank)
            chunks_by_id.setdefault(chunk.chunk_id, chunk)

    ranked_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)
    return [
        chunks_by_id[chunk_id].model_copy(update={"score": rrf_scores[chunk_id]})
        for chunk_id in ranked_ids[:top_k]
    ]
