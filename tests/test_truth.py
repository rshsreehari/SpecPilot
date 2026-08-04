from __future__ import annotations

import json
from pathlib import Path

from src.eval.truth import build_truth, cached_truth, verify_endpoint, verify_parameter

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "small_spec.json"


def _load_spec() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def test_valid_endpoints_come_from_the_spec() -> None:
    truth = build_truth("test", _load_spec(), path_prefixes=None)

    assert ("GET", "/v1/widgets") in truth.valid_endpoints
    assert ("POST", "/v1/widgets") in truth.valid_endpoints
    assert ("DELETE", "/v1/widgets") not in truth.valid_endpoints


def test_endpoint_exists_with_known_method() -> None:
    truth = build_truth("test", _load_spec(), path_prefixes=None)

    assert truth.endpoint_exists("GET", "/v1/widgets") is True
    assert truth.endpoint_exists("DELETE", "/v1/widgets") is False
    assert truth.endpoint_exists("GET", "/v1/nonexistent") is False


def test_endpoint_exists_with_unknown_method_is_lenient_on_path() -> None:
    truth = build_truth("test", _load_spec(), path_prefixes=None)

    # Extractor couldn't determine the method; path exists under some method, so pass.
    assert truth.endpoint_exists(None, "/v1/widgets") is True
    assert truth.endpoint_exists(None, "/v1/nonexistent") is False


def test_valid_params_includes_both_query_and_body_parameters() -> None:
    truth = build_truth("test", _load_spec(), path_prefixes=None)

    get_params = truth.valid_params[("GET", "/v1/widgets")]
    assert get_params == frozenset({"limit"})

    post_params = truth.valid_params[("POST", "/v1/widgets")]
    assert post_params == frozenset({"name", "color"})


def test_parameter_exists_checks_a_single_named_parameter() -> None:
    truth = build_truth("test", _load_spec(), path_prefixes=None)

    assert truth.parameter_exists("GET", "/v1/widgets", "limit") is True
    assert truth.parameter_exists("GET", "/v1/widgets", "nonexistent") is False
    assert truth.parameter_exists("GET", "/v1/nonexistent", "limit") is False


def test_params_for_unions_across_multiple_endpoints() -> None:
    truth = build_truth("test", _load_spec(), path_prefixes=None)

    union = truth.params_for({("GET", "/v1/widgets"), ("POST", "/v1/widgets")})

    assert union == frozenset({"limit", "name", "color"})


def test_params_for_unknown_endpoint_is_empty() -> None:
    truth = build_truth("test", _load_spec(), path_prefixes=None)

    assert truth.params_for({("GET", "/v1/nonexistent")}) == frozenset()


def test_endpoint_exists_matches_concrete_example_ids_against_path_template() -> None:
    # Example code legitimately substitutes realistic IDs (cus_123) for {customer} -
    # that must still be recognized as the real, templated endpoint, not a hallucination.
    spec = {
        "paths": {
            "/v1/customers/{customer}": {
                "get": {"operationId": "GetCustomersCustomer", "parameters": []}
            }
        }
    }
    truth = build_truth("test", spec, path_prefixes=None)

    assert truth.endpoint_exists("GET", "/v1/customers/cus_123") is True
    assert truth.endpoint_exists("GET", "/v1/customers/{customer}") is True
    assert truth.endpoint_exists("GET", "/v1/customers/cus_123/extra") is False
    assert truth.endpoint_exists("POST", "/v1/customers/cus_123") is False


def test_params_for_resolves_concrete_ids_to_the_matching_template() -> None:
    spec = {
        "paths": {
            "/v1/customers/{customer}": {
                "get": {
                    "operationId": "GetCustomersCustomer",
                    "parameters": [
                        {"name": "expand", "in": "query", "schema": {"type": "array"}}
                    ],
                }
            }
        }
    }
    truth = build_truth("test", spec, path_prefixes=None)

    assert truth.params_for({("GET", "/v1/customers/cus_123")}) == frozenset({"expand"})


def test_cached_truth_returns_none_for_unconfigured_provider() -> None:
    assert cached_truth("does-not-exist-anywhere") is None


def test_verify_endpoint_is_unverified_not_an_error_for_unknown_provider() -> None:
    # A citation naming a provider that was never ingested must be treated as
    # unverified, not raise - per BUILD.md's live-verification contract.
    assert verify_endpoint("does-not-exist-anywhere", "GET", "/v1/widgets") is False
    assert verify_endpoint(None, "GET", "/v1/widgets") is False


def test_verify_parameter_is_unverified_not_an_error_for_unknown_provider() -> None:
    assert verify_parameter("does-not-exist-anywhere", "GET", "/v1/widgets", "limit") is False
