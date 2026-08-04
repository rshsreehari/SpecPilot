from __future__ import annotations

from pathlib import Path

from src.eval.questions import Question, filter_split, load_questions

_YAML = """
questions:
  - id: q001
    split: dev
    category: answerable
    provider: test
    question: "How do I create a customer?"
    expected_endpoints:
      - method: POST
        path: /v1/customers
  - id: q002
    split: holdout
    category: unanswerable
    provider: test
    question: "How do I do the impossible?"
    expected_endpoints: []
"""


def _write(tmp_path: Path) -> None:
    (tmp_path / "test.yaml").write_text(_YAML)


def test_load_questions_parses_all_fields(tmp_path: Path) -> None:
    _write(tmp_path)

    questions = load_questions("test", base_dir=tmp_path)

    assert len(questions) == 2
    assert questions[0] == Question(
        id="q001",
        provider="test",
        split="dev",
        category="answerable",
        question="How do I create a customer?",
        expected_endpoints=frozenset({("POST", "/v1/customers")}),
    )
    assert questions[1].expected_endpoints == frozenset()


def test_filter_split_all_returns_everything(tmp_path: Path) -> None:
    _write(tmp_path)
    questions = load_questions("test", base_dir=tmp_path)

    assert filter_split(questions, "all") == questions


def test_filter_split_dev_only(tmp_path: Path) -> None:
    _write(tmp_path)
    questions = load_questions("test", base_dir=tmp_path)

    dev = filter_split(questions, "dev")

    assert [q.id for q in dev] == ["q001"]


def test_filter_split_holdout_only(tmp_path: Path) -> None:
    _write(tmp_path)
    questions = load_questions("test", base_dir=tmp_path)

    holdout = filter_split(questions, "holdout")

    assert [q.id for q in holdout] == ["q002"]


def test_load_questions_missing_provider_raises_a_clear_error(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(FileNotFoundError, match="no-such-provider"):
        load_questions("no-such-provider", base_dir=tmp_path)


def test_load_questions_default_path_reads_the_real_stripe_question_set() -> None:
    questions = load_questions("stripe")

    assert len(questions) == 50
    assert {q.split for q in questions} == {"dev", "holdout"}
    assert all(q.provider == "stripe" for q in questions)
