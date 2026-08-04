from __future__ import annotations

from src.ingest.parse import ParsedEndpoint


def build_chunk_text(endpoint: ParsedEndpoint) -> str:
    lines = [f"{endpoint.method} {endpoint.path}"]

    if endpoint.summary:
        lines.append(endpoint.summary)
    if endpoint.description:
        lines.append(endpoint.description)

    if endpoint.parameters:
        lines.append("Parameters:")
        for param in endpoint.parameters:
            required = " (required)" if param.required else ""
            description = f": {param.description}" if param.description else ""
            lines.append(f"- {param.name}{required}{description}")

    return "\n".join(lines)
