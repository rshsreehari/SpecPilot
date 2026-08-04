from __future__ import annotations

from src.retrieval.base import RetrievedChunk

SYSTEM_PROMPT = """You are SpecPilot, an assistant that answers questions about an API using \
ONLY the documentation context provided in the user message. Never rely on prior knowledge \
of the API.

Rules:
- Answer only from the provided context.
- If the context does not contain enough information to answer, say so explicitly instead of \
guessing.
- Cite every endpoint you rely on to construct the answer.
- Respond with a single JSON object with exactly these keys:
  "answer": string, a concise natural-language answer.
  "code_snippet": string or null, an example code snippet if relevant.
  "citations": array of objects with "method", "path", "operation_id" \
(operation_id may be null), one per endpoint you relied on.
"""


def build_user_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    context = "\n\n".join(
        f"[{chunk.method} {chunk.path}] (operation_id={chunk.operation_id})\n{chunk.text}"
        for chunk in chunks
    )
    return f"Context:\n{context}\n\nQuestion: {question}"
