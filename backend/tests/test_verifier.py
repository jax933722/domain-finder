"""Tests for domain verification/scoring."""

from app.services.search.providers import ProviderResponse, SearchResult
from app.services.search.verifier import (
    registrable_domain,
    verify,
)


def test_registrable_domain():
    assert registrable_domain("https://www.microsoft.com/en-us/") == "microsoft.com"
    assert registrable_domain("http://aws.amazon.com") == "amazon.com"
    assert registrable_domain("openai.com") == "openai.com"
    assert registrable_domain("") is None


def test_exact_match_is_verified():
    resp = ProviderResponse(
        provider="brave",
        query="Microsoft official website",
        results=[
            SearchResult(title="Microsoft", url="https://www.microsoft.com", rank=1),
            SearchResult(title="LinkedIn", url="https://linkedin.com/company/microsoft", rank=2),
        ],
    )
    outcome = verify("Microsoft", [resp])
    assert outcome.domain == "microsoft.com"
    assert outcome.confidence >= 0.6


def test_authoritative_source_wins():
    resp = ProviderResponse(
        provider="wikipedia",
        query="Reliance Industries official website",
        results=[
            SearchResult(
                title="Wikidata Q1",
                url="https://www.ril.com",
                rank=1,
                authoritative=True,
            )
        ],
    )
    outcome = verify("Reliance Industries", [resp])
    assert outcome.domain == "ril.com"
    assert outcome.authoritative is True
    assert outcome.confidence >= 0.9


def test_no_match_returns_not_found():
    resp = ProviderResponse(
        provider="brave",
        query="Nonexistent Fake Company official website",
        results=[
            SearchResult(title="Some blog", url="https://randomblog.example/post", rank=1),
            SearchResult(title="Wikipedia", url="https://en.wikipedia.org/wiki/None", rank=2),
        ],
    )
    outcome = verify("Nonexistent Fake Company", [resp])
    assert outcome.domain is None
    assert outcome.reason is not None


def test_aggregator_only_is_not_returned():
    resp = ProviderResponse(
        provider="brave",
        query="Acme official website",
        results=[
            SearchResult(title="Acme on LinkedIn", url="https://linkedin.com/company/acme", rank=1),
            SearchResult(title="Acme on Crunchbase", url="https://crunchbase.com/org/acme", rank=2),
        ],
    )
    outcome = verify("Acme", [resp])
    # Aggregators must never be returned as the official domain.
    assert outcome.domain is None


def test_substring_match_scores():
    resp = ProviderResponse(
        provider="brave",
        query="Amazon Web Services official website",
        results=[SearchResult(title="AWS", url="https://aws.amazon.com", rank=1)],
    )
    outcome = verify("Amazon Web Services", [resp])
    assert outcome.domain == "amazon.com"
