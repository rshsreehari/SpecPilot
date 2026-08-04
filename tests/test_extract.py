from __future__ import annotations

from src.eval.extract import ExtractedEndpoint, extract_endpoints, extract_evidence

# Six hand-checked (answer, code_snippet) examples covering the shapes Mistral actually
# produces: curl (non-Python, regex fallback), SDK-style calls (valid Python, AST),
# a bare JSON body (also valid Python), no code at all, an ambiguous bare path mention,
# and multiple distinct endpoints in one answer.


def test_curl_snippet_uses_regex_fallback_for_parameters() -> None:
    answer = "To create a subscription with a 14-day trial, use POST /v1/subscriptions."
    code = (
        "```\ncurl https://api.stripe.com/v1/subscriptions \\\n"
        '  -u "sk_test_...": \\\n'
        '  -d customer="cus_123" \\\n'
        '  -d "items[0][price]"="price_123" \\\n'
        "  -d trial_period_days=14\n```"
    )

    evidence = extract_evidence(answer, code)

    assert ExtractedEndpoint(method="POST", path="/v1/subscriptions") in evidence.endpoints
    assert evidence.parameters == {"customer", "items", "trial_period_days"}


def test_sdk_style_snippet_uses_ast_and_finds_nested_dict_keys() -> None:
    answer = "Create a subscription with POST /v1/subscriptions, e.g.:"
    code = (
        'stripe.Subscription.create(customer="cus_123", '
        'items=[{"price": "price_123"}], trial_period_days=14)'
    )

    evidence = extract_evidence(answer, code)

    assert ExtractedEndpoint(method="POST", path="/v1/subscriptions") in evidence.endpoints
    assert evidence.parameters == {"customer", "items", "trial_period_days", "price"}


def test_json_body_snippet_is_also_valid_python_and_parsed_via_ast() -> None:
    answer = "Send a request to POST /v1/customers with the following body:"
    code = '{"email": "test@example.com", "name": "Jane Doe", "metadata": {"plan": "gold"}}'

    evidence = extract_evidence(answer, code)

    assert ExtractedEndpoint(method="POST", path="/v1/customers") in evidence.endpoints
    assert evidence.parameters == {"email", "name", "metadata", "plan"}


def test_refusal_answer_with_no_code_extracts_nothing() -> None:
    answer = "The documentation does not cover converting a subscription into an NFT."

    evidence = extract_evidence(answer, None)

    assert evidence.endpoints == []
    assert evidence.parameters == set()


def test_bare_path_mention_with_no_method_context_is_method_none() -> None:
    answer = "You can find details about a price at /v1/prices/{price}."

    evidence = extract_evidence(answer, None)

    assert evidence.endpoints == [ExtractedEndpoint(method=None, path="/v1/prices/{price}")]


def test_multiple_distinct_endpoints_are_all_extracted() -> None:
    answer = (
        "First call POST /v1/customers to create a customer, then POST /v1/subscriptions "
        "to subscribe them."
    )

    endpoints = extract_endpoints(answer)

    assert set(endpoints) == {
        ExtractedEndpoint(method="POST", path="/v1/customers"),
        ExtractedEndpoint(method="POST", path="/v1/subscriptions"),
    }


def test_trailing_punctuation_is_stripped_from_extracted_path() -> None:
    answer = "You can void an invoice (POST /v1/invoices/{invoice}/void)."

    endpoints = extract_endpoints(answer)

    assert ExtractedEndpoint(method="POST", path="/v1/invoices/{invoice}/void") in endpoints


def test_paths_without_v1_prefix_are_extracted_for_any_provider() -> None:
    answer = (
        "Create the pet with POST /pet, then inspect it with "
        "GET /repos/{owner}/{repo}/issues/{issue_number}."
    )

    endpoints = extract_endpoints(answer)

    assert set(endpoints) == {
        ExtractedEndpoint(method="POST", path="/pet"),
        ExtractedEndpoint(method="GET", path="/repos/{owner}/{repo}/issues/{issue_number}"),
    }


def test_generic_path_matcher_does_not_capture_the_url_hostname() -> None:
    code = "curl https://petstore.example.com/pet -d name=Fido"

    endpoints = extract_endpoints(code)

    assert endpoints == [ExtractedEndpoint(method="POST", path="/pet")]
