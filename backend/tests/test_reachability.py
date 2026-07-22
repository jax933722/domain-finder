"""Tests for live domain reachability confirmation."""

import httpx
import pytest

from app.core.config import settings
from app.services.search.reachability import check_domain


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_disabled_skips_check(monkeypatch):
    monkeypatch.setattr(settings, "VERIFY_DOMAIN_REACHABLE", False)
    async with _client(lambda r: httpx.Response(200)) as client:
        result = await check_domain("example.com", client)
    assert result.checked is False


@pytest.mark.asyncio
async def test_reachable_domain(monkeypatch):
    monkeypatch.setattr(settings, "VERIFY_DOMAIN_REACHABLE", True)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    async with _client(handler) as client:
        result = await check_domain("example.com", client)
    assert result.checked is True
    assert result.reachable is True
    assert result.final_domain == "example.com"
    assert result.redirected is False


@pytest.mark.asyncio
async def test_unreachable_domain(monkeypatch):
    monkeypatch.setattr(settings, "VERIFY_DOMAIN_REACHABLE", True)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    async with _client(handler) as client:
        result = await check_domain("dead-domain.example", client)
    assert result.checked is True
    assert result.reachable is False


@pytest.mark.asyncio
async def test_follows_cross_domain_redirect(monkeypatch):
    monkeypatch.setattr(settings, "VERIFY_DOMAIN_REACHABLE", True)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.com":
            return httpx.Response(301, headers={"Location": "https://example.org/"})
        return httpx.Response(200)

    async with _client(handler) as client:
        result = await check_domain("example.com", client)
    assert result.reachable is True
    assert result.final_domain == "example.org"
    assert result.redirected is True


@pytest.mark.asyncio
async def test_head_405_falls_back_to_get(monkeypatch):
    monkeypatch.setattr(settings, "VERIFY_DOMAIN_REACHABLE", True)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(405)
        return httpx.Response(200)

    async with _client(handler) as client:
        result = await check_domain("example.com", client)
    assert result.reachable is True


@pytest.mark.asyncio
async def test_connection_error_is_unreachable(monkeypatch):
    monkeypatch.setattr(settings, "VERIFY_DOMAIN_REACHABLE", True)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    async with _client(handler) as client:
        result = await check_domain("nowhere.example", client)
    assert result.checked is True
    assert result.reachable is False
    assert result.error is not None
