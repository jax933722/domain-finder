"""Tests for the discovery orchestrator using a fake provider (no network)."""

import pytest

from app.services.search.discovery import discover_domain
from app.services.search.providers import BaseProvider, ProviderResponse, SearchResult


class FakeProvider(BaseProvider):
    def __init__(self, name: str, results: list[SearchResult]):
        self._name = name
        self._results = results

    @property
    def name(self) -> str:  # type: ignore[override]
        return self._name

    @property
    def available(self) -> bool:
        return True

    async def search(self, client, query: str) -> ProviderResponse:
        return ProviderResponse(
            provider=self._name,
            query=query,
            results=self._results,
            search_url=f"https://fake/{self._name}?q={query}",
            response_time_ms=1,
        )


@pytest.mark.asyncio
async def test_discovery_verifies_known_company():
    provider = FakeProvider("brave", [SearchResult("Google", "https://www.google.com", rank=1)])
    result = await discover_domain("Google", [provider], client=None)
    assert result.status == "VERIFIED"
    assert result.domain == "google.com"
    assert result.processing_time_ms >= 0


@pytest.mark.asyncio
async def test_discovery_returns_not_found_without_evidence():
    provider = FakeProvider("brave", [SearchResult("Blog", "https://randomblog.example", rank=1)])
    result = await discover_domain("Totally Unknown Startup XYZ", [provider], client=None)
    assert result.status == "NOT FOUND"
    assert result.domain is None
    assert result.reason


@pytest.mark.asyncio
async def test_discovery_stops_early_on_first_confident_provider():
    good = FakeProvider("brave", [SearchResult("Apple", "https://www.apple.com", rank=1)])
    # Second provider would never be consulted once the first is confident.
    bad = FakeProvider("bing", [SearchResult("Wrong", "https://wrong.example", rank=1)])
    result = await discover_domain("Apple", [good, bad], client=None)
    assert result.domain == "apple.com"
    # Only the first provider should have been attempted.
    assert len(result.attempts) == 1


@pytest.mark.asyncio
async def test_empty_name_is_not_found():
    provider = FakeProvider("brave", [])
    result = await discover_domain("", [provider], client=None)
    assert result.status == "NOT FOUND"
