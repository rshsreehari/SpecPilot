from __future__ import annotations

import pytest

from src.retrieval.bm25 import BM25Index, tokenize

# Hand-computed fixture. Three tiny "chunks":
#   1: "create a subscription with trial period"   (6 tokens)
#   2: "cancel a subscription immediately"          (4 tokens)
#   3: "list all customer invoices"                 (4 tokens, no query terms)
# avgdl = (6+4+4)/3 = 4.6667
#
# query "subscription trial", k1=1.5, b=0.75:
#   IDF(subscription) = ln(1 + (3-2+0.5)/(2+0.5)) = ln(1.6)    ~ 0.4700
#   IDF(trial)        = ln(1 + (3-1+0.5)/(1+0.5)) = ln(2.6667) ~ 0.9808
#   doc1 matches both terms (f=1 each)   -> score ~ 1.28555
#   doc2 matches "subscription" only     -> score ~ 0.50229
#   doc3 matches neither                 -> not returned at all
_CHUNKS = [
    (1, 100, "GET", "/v1/subscriptions", "GetSubscriptions", "create a subscription with trial period"),
    (2, 100, "DELETE", "/v1/subscriptions/{id}", "DeleteSubscription", "cancel a subscription immediately"),
    (3, 200, "GET", "/v1/customers", "GetCustomers", "list all customer invoices"),
]


def test_tokenize_lowercases_and_keeps_underscores() -> None:
    assert tokenize("Trial_Period Days!") == ["trial_period", "days"]


def test_bm25_scores_match_hand_computed_values() -> None:
    index = BM25Index.build("stripe", _CHUNKS, k1=1.5, b=0.75)

    ranked = index.score("subscription trial", top_k=10)
    scores = dict(ranked)

    assert scores[1] == pytest.approx(1.2855481235192703, rel=1e-9)
    assert scores[2] == pytest.approx(0.5022939549191067, rel=1e-9)
    assert 3 not in scores


def test_bm25_ranks_by_score_descending() -> None:
    index = BM25Index.build("stripe", _CHUNKS, k1=1.5, b=0.75)

    ranked = index.score("subscription trial", top_k=10)

    assert [chunk_id for chunk_id, _ in ranked] == [1, 2]


def test_bm25_respects_top_k() -> None:
    index = BM25Index.build("stripe", _CHUNKS, k1=1.5, b=0.75)

    ranked = index.score("subscription trial", top_k=1)

    assert [chunk_id for chunk_id, _ in ranked] == [1]


def test_bm25_query_with_no_matching_terms_returns_empty() -> None:
    index = BM25Index.build("stripe", _CHUNKS, k1=1.5, b=0.75)

    assert index.score("nonexistent gibberish", top_k=10) == []


async def test_bm25_retriever_returns_retrieved_chunks_with_metadata() -> None:
    from src.retrieval.bm25 import BM25Retriever

    index = BM25Index.build("stripe", _CHUNKS, k1=1.5, b=0.75)
    retriever = BM25Retriever(index)

    results = await retriever.search("subscription trial", top_k=10)

    assert [r.chunk_id for r in results] == [1, 2]
    assert results[0].method == "GET"
    assert results[0].path == "/v1/subscriptions"
    assert results[0].endpoint_id == 100
    assert results[0].provider_id == "stripe"


async def test_multi_provider_retriever_fuses_independently_scored_indices() -> None:
    from src.retrieval.bm25 import BM25Retriever, MultiProviderBM25Retriever

    # A second, tiny "provider" corpus where "subscription" is not rare (appears in
    # every doc) - if the two corpora were ever pooled before scoring, this term's IDF
    # would be computed across both and corrupt the stripe-side ranking above. Fusing
    # two independently-built indices must not do that.
    other_chunks = [
        (10, 900, "GET", "/v2/items", "GetItems", "subscription subscription subscription"),
        (11, 900, "GET", "/v2/other", "GetOther", "subscription unrelated words here"),
    ]
    stripe_index = BM25Index.build("stripe", _CHUNKS, k1=1.5, b=0.75)
    other_index = BM25Index.build("other", other_chunks, k1=1.5, b=0.75)

    multi = MultiProviderBM25Retriever([stripe_index, other_index], k=60)
    results = await multi.search("subscription trial", top_k=10)

    provider_ids = {r.provider_id for r in results}
    assert provider_ids == {"stripe", "other"}
    # Same ranking within the stripe corpus as querying it alone - each index still
    # scores independently, using only its own document-frequency statistics.
    solo = await BM25Retriever(stripe_index).search("subscription trial", top_k=10)
    assert [r.chunk_id for r in results if r.provider_id == "stripe"] == [r.chunk_id for r in solo]
