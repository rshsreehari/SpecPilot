from __future__ import annotations

import ast
import re
from dataclasses import dataclass

_METHOD = r"(GET|POST|PUT|PATCH|DELETE)"
# OpenAPI paths are not versioned or shaped consistently: `/pet`, `/v1/customers`, and
# `/repos/{owner}/{repo}/issues` are all equally valid. Stop at whitespace/quotes/code
# delimiters, then let `_strip_trailing_punct` remove prose punctuation.
_PATH = r"(?<![:/])(/[^\s\"'`?#<>]+)"
_METHOD_PATH_RE = re.compile(rf"{_METHOD}\s+{_PATH}", re.IGNORECASE)
_BARE_PATH_RE = re.compile(_PATH)
_CURL_METHOD_RE = re.compile(r"-X\s*(GET|POST|PUT|PATCH|DELETE)", re.IGNORECASE)
_CURL_DATA_RE = re.compile(
    r"""-d\s+["']?([A-Za-z_][A-Za-z0-9_]*)(?:\[[^\]]*])*["']?\s*="""
)
_JSON_KEY_RE = re.compile(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:')
_TRAILING_PUNCT = ".,;:)!?\"'`"


@dataclass(frozen=True)
class ExtractedEndpoint:
    method: str | None
    path: str


@dataclass(frozen=True)
class ExtractedEvidence:
    endpoints: list[ExtractedEndpoint]
    parameters: set[str]


def _strip_trailing_punct(path: str) -> str:
    return path.rstrip(_TRAILING_PUNCT)


def extract_endpoints(text: str) -> list[ExtractedEndpoint]:
    """Find every endpoint mentioned in free text (answer prose + code/curl snippet).

    Explicit "METHOD /path" pairs (prose citations, curl "-X POST ... /v1/x") are the
    reliable signal and always win. A bare path with no nearby method - e.g. inside a
    curl URL with no explicit -X - is paired with the snippet's single -X method if
    there is exactly one, else defaults to POST if the snippet uses curl's `-d` (curl
    sends POST when data is supplied), else left as method=None. SDK-style calls that
    do not literally contain a path string contribute nothing here - out of scope for
    this extractor, which only
    finds paths actually mentioned in the text.
    """
    found: dict[str, str | None] = {}

    for match in _METHOD_PATH_RE.finditer(text):
        method = match.group(1).upper()
        path = _strip_trailing_punct(match.group(2))
        found[path] = method

    all_paths = {_strip_trailing_punct(m.group(1)) for m in _BARE_PATH_RE.finditer(text)}
    unresolved = all_paths - found.keys()

    if unresolved:
        curl_methods = {m.upper() for m in _CURL_METHOD_RE.findall(text)}
        inferred_method: str | None
        if len(curl_methods) == 1:
            inferred_method = next(iter(curl_methods))
        elif _CURL_DATA_RE.search(text):
            inferred_method = "POST"
        else:
            inferred_method = None
        for path in unresolved:
            found[path] = inferred_method

    return [ExtractedEndpoint(method=method, path=path) for path, method in found.items()]


def _strip_code_fences(code: str) -> str:
    stripped = code.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines)


def _ast_parameter_names(code: str) -> set[str] | None:
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return None

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg is not None:
            names.add(node.arg)
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    names.add(key.value)
    return names


def _regex_parameter_names(code: str) -> set[str]:
    names = {m.group(1) for m in _CURL_DATA_RE.finditer(code)}
    names |= {m.group(1) for m in _JSON_KEY_RE.finditer(code)}
    return names


def extract_parameters(code_snippet: str | None) -> set[str]:
    """Parameter names used in a code snippet. AST parsing when the snippet is valid
    Python (covers both SDK-style calls' keyword args and JSON/dict-literal bodies'
    string keys, since both are valid Python syntax); regex fallback for curl and any
    snippet that doesn't parse (shell syntax, truncated code, etc).
    """
    if not code_snippet:
        return set()

    code = _strip_code_fences(code_snippet)
    ast_names = _ast_parameter_names(code)
    if ast_names is not None:
        return ast_names
    return _regex_parameter_names(code)


def extract_evidence(answer: str, code_snippet: str | None) -> ExtractedEvidence:
    combined = answer if code_snippet is None else f"{answer}\n{code_snippet}"
    return ExtractedEvidence(
        endpoints=extract_endpoints(combined),
        parameters=extract_parameters(code_snippet),
    )
