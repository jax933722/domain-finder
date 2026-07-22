"""Tests for search providers that need no external network (mocked transport)."""

import httpx
import pytest

from app.core.config import settings
from app.services.search.providers import SearxngProvider


@pytest.mark.asyncio
async def test_searxng_parses_json_results(monkeypatch):
    monkeypatch.setattr(settings, "SEARXNG_URL", "http://searxng:8080")
    provider = SearxngProvider()
    assert provider.available is True

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("format") == "json"
        assert "Microsoft" in request.url.params.get("q", "")
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "Microsoft", "url": "https://www.microsoft.com", "content": "official"},
                    {"title": "MS on LinkedIn", "url": "https://linkedin.com/company/microsoft", "content": ""},
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        resp = await provider.search(client, "Microsoft official website")

    assert resp.error is None
    assert resp.results[0].url == "https://www.microsoft.com"
    assert resp.results[0].rank == 1
    assert len(resp.results) == 2


@pytest.mark.asyncio
async def test_searxng_unavailable_without_url(monkeypatch):
    monkeypatch.setattr(settings, "SEARXNG_URL", None)
    assert SearxngProvider().available is False


@pytest.mark.asyncio
async def test_searxng_handles_http_error(monkeypatch):
    monkeypatch.setattr(settings, "SEARXNG_URL", "http://searxng:8080")
    provider = SearxngProvider()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        resp = await provider.search(client, "Anything")

    # Failure is reported, never raised — the job keeps going.
    assert resp.error is not None
    assert resp.results == []
