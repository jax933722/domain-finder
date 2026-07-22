"""Tests for reachability-aware finalization of a verified domain."""

import httpx
import pytest

from app.core.config import settings
from app.services.search.discovery import _finalize_verified


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_reachable_keeps_domain_and_boosts(monkeypatch):
    monkeypatch.setattr(settings, "VERIFY_DOMAIN_REACHABLE", True)
    async with _client(lambda r: httpx.Response(200)) as client:
        result = await _finalize_verified(
            clean_company="Acme",
            domain="acme.com",
            confidence=0.8,
            source="web",
            authoritative=False,
            search_url="https://searx/q",
            query="Acme official website",
            start=0.0,
            attempts=[],
            client=client,
        )
    assert result.status == "VERIFIED"
    assert result.domain == "acme.com"
    assert result.confidence >= 0.8


@pytest.mark.asyncio
async def test_unreachable_nonauthoritative_drops_to_not_found(monkeypatch):
    monkeypatch.setattr(settings, "VERIFY_DOMAIN_REACHABLE", True)
    monkeypatch.setattr(settings, "REACHABILITY_PENALTY", 0.3)
    monkeypatch.setattr(settings, "CONFIDENCE_THRESHOLD", 0.6)
    async with _client(lambda r: httpx.Response(404)) as client:
        result = await _finalize_verified(
            clean_company="Acme",
            domain="acme.com",
            confidence=0.7,  # 0.7 - 0.3 = 0.4 < threshold
            source="web",
            authoritative=False,
            search_url="https://searx/q",
            query="Acme official website",
            start=0.0,
            attempts=[],
            client=client,
        )
    assert result.status == "NOT FOUND"
    assert result.domain is None
    assert "did not respond" in (result.reason or "")


@pytest.mark.asyncio
async def test_unreachable_authoritative_is_kept(monkeypatch):
    monkeypatch.setattr(settings, "VERIFY_DOMAIN_REACHABLE", True)
    async with _client(lambda r: httpx.Response(503)) as client:
        result = await _finalize_verified(
            clean_company="Reliance Industries",
            domain="ril.com",
            confidence=0.97,
            source="wikipedia (official website)",
            authoritative=True,
            search_url="https://wikidata",
            query="q",
            start=0.0,
            attempts=[],
            client=client,
        )
    # Authoritative answers are trusted even if a probe fails (firewall, HEAD block).
    assert result.status == "VERIFIED"
    assert result.domain == "ril.com"


@pytest.mark.asyncio
async def test_live_redirect_adopts_canonical_domain(monkeypatch):
    monkeypatch.setattr(settings, "VERIFY_DOMAIN_REACHABLE", True)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "acme.com":
            return httpx.Response(301, headers={"Location": "https://acme.io/"})
        return httpx.Response(200)

    async with _client(handler) as client:
        result = await _finalize_verified(
            clean_company="Acme",
            domain="acme.com",
            confidence=0.85,
            source="web",
            authoritative=False,
            search_url="https://searx/q",
            query="q",
            start=0.0,
            attempts=[],
            client=client,
        )
    assert result.status == "VERIFIED"
    assert result.domain == "acme.io"
    assert "canonical" in (result.reason or "")
