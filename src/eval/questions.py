from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

QUESTIONS_DIR = Path("eval/questions")


@dataclass(frozen=True)
class Question:
    id: str
    provider: str
    split: str
    category: str
    question: str
    expected_endpoints: frozenset[tuple[str, str]]


def _questions_path(provider_id: str, base_dir: Path = QUESTIONS_DIR) -> Path:
    return base_dir / f"{provider_id}.yaml"


def load_questions(provider_id: str, base_dir: Path = QUESTIONS_DIR) -> list[Question]:
    path = _questions_path(provider_id, base_dir)
    if not path.is_file():
        raise FileNotFoundError(
            f"no eval questions for provider {provider_id!r} at {path} - "
            f"write eval/questions/{provider_id}.yaml first"
        )
    raw: dict[str, Any] = yaml.safe_load(path.read_text())
    questions = []
    for item in raw["questions"]:
        endpoints = frozenset(
            (e["method"], e["path"]) for e in item.get("expected_endpoints", [])
        )
        questions.append(
            Question(
                id=item["id"],
                provider=item.get("provider", provider_id),
                split=item["split"],
                category=item["category"],
                question=item["question"],
                expected_endpoints=endpoints,
            )
        )
    return questions


def filter_split(questions: list[Question], split: str) -> list[Question]:
    if split == "all":
        return questions
    return [q for q in questions if q.split == split]
