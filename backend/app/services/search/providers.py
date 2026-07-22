"""Search-provider abstraction.

Each provider wraps a *reliable* search API (Brave, Google Custom Search,
Bing) or an authoritative structured source (Wikidata / Wikipedia). We never
scrape a search engine's HTML — that is unreliable and easily blocked.

Every provider returns a normalized list of :class:`SearchResult`. Providers
whose credentials are not configured report ``available = False`` and are
skipped by the discovery orchestrator.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    description: str = ""
    rank: int = 0
    # For authoritative structured sources (Wikidata), the extracted official
    # website is trusted directly rather than merely being a candidate.
    authoritative: bool = False


@dataclass
class ProviderResponse:
    provider: str
    query: str
    results: list[SearchResult] = field(default_factory=list)
    search_url: str = ""
    response_time_ms: int = 0
    error: str | None = None


class BaseProvider:
    name: str = "base"

    @property
    def available(self) -> bool:  # pragma: no cover - trivial
        return True

    async def search(self, client: httpx.AsyncClient, query: str) -> ProviderResponse:
        raise NotImplementedError


def _retry():
    """Shared retry policy: exponential backoff on transient network errors."""
    return retry(
        reraise=True,
        stop=stop_after_attempt(settings.SEARCH_MAX_RETRIES),
        wait=wait_exponential(multiplier=settings.SEARCH_BACKOFF_BASE, min=0.5, max=8),
        retry=retry_if_exception_type(
            (httpx.TransportError, httpx.TimeoutException, httpx.HTTPStatusError)
        ),
    )


class BraveProvider(BaseProvider):
    name = "brave"
    ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

    @property
    def available(self) -> bool:
        return bool(settings.BRAVE_SEARCH_API_KEY)

    async def search(self, client: httpx.AsyncClient, query: str) -> ProviderResponse:
        start = time.perf_counter()
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": settings.BRAVE_SEARCH_API_KEY or "",
        }
        params = {"q": query, "count": 10, "safesearch": "off"}

        @_retry()
        async def _do() -> httpx.Response:
            resp = await client.get(self.ENDPOINT, headers=headers, params=params)
            resp.raise_for_status()
            return resp

        try:
            resp = await _do()
            data = resp.json()
            results = []
            for i, item in enumerate((data.get("web") or {}).get("results", [])):
                results.append(
                    SearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        description=item.get("description", ""),
                        rank=i + 1,
                    )
                )
            return ProviderResponse(
                provider=self.name,
                query=query,
                results=results,
                search_url=str(resp.request.url),
                response_time_ms=int((time.perf_counter() - start) * 1000),
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as error, never crashes job
            logger.warning("Brave search failed for %r: %s", query, exc)
            return ProviderResponse(
                provider=self.name,
                query=query,
                error=str(exc),
                response_time_ms=int((time.perf_counter() - start) * 1000),
            )


class GoogleCSEProvider(BaseProvider):
    name = "google"
    ENDPOINT = "https://www.googleapis.com/customsearch/v1"

    @property
    def available(self) -> bool:
        return bool(settings.GOOGLE_CSE_API_KEY and settings.GOOGLE_CSE_ENGINE_ID)

    async def search(self, client: httpx.AsyncClient, query: str) -> ProviderResponse:
        start = time.perf_counter()
        params = {
            "key": settings.GOOGLE_CSE_API_KEY,
            "cx": settings.GOOGLE_CSE_ENGINE_ID,
            "q": query,
            "num": 10,
        }

        @_retry()
        async def _do() -> httpx.Response:
            resp = await client.get(self.ENDPOINT, params=params)
            resp.raise_for_status()
            return resp

        try:
            resp = await _do()
            data = resp.json()
            results = []
            for i, item in enumerate(data.get("items", [])):
                results.append(
                    SearchResult(
                        title=item.get("title", ""),
                        url=item.get("link", ""),
                        description=item.get("snippet", ""),
                        rank=i + 1,
                    )
                )
            return ProviderResponse(
                provider=self.name,
                query=query,
                results=results,
                search_url=str(resp.request.url),
                response_time_ms=int((time.perf_counter() - start) * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Google CSE failed for %r: %s", query, exc)
            return ProviderResponse(
                provider=self.name,
                query=query,
                error=str(exc),
                response_time_ms=int((time.perf_counter() - start) * 1000),
            )


class BingProvider(BaseProvider):
    name = "bing"
    ENDPOINT = "https://api.bing.microsoft.com/v7.0/search"

    @property
    def available(self) -> bool:
        return bool(settings.BING_SEARCH_API_KEY)

    async def search(self, client: httpx.AsyncClient, query: str) -> ProviderResponse:
        start = time.perf_counter()
        headers = {"Ocp-Apim-Subscription-Key": settings.BING_SEARCH_API_KEY or ""}
        params = {"q": query, "count": 10, "responseFilter": "Webpages"}

        @_retry()
        async def _do() -> httpx.Response:
            resp = await client.get(self.ENDPOINT, headers=headers, params=params)
            resp.raise_for_status()
            return resp

        try:
            resp = await _do()
            data = resp.json()
            results = []
            for i, item in enumerate((data.get("webPages") or {}).get("value", [])):
                results.append(
                    SearchResult(
                        title=item.get("name", ""),
                        url=item.get("url", ""),
                        description=item.get("snippet", ""),
                        rank=i + 1,
                    )
                )
            return ProviderResponse(
                provider=self.name,
                query=query,
                results=results,
                search_url=str(resp.request.url),
                response_time_ms=int((time.perf_counter() - start) * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Bing search failed for %r: %s", query, exc)
            return ProviderResponse(
                provider=self.name,
                query=query,
                error=str(exc),
                response_time_ms=int((time.perf_counter() - start) * 1000),
            )


class SearxngProvider(BaseProvider):
    """Self-hosted SearXNG meta-search — no API key required.

    SearXNG aggregates results from many upstream engines (Google, Bing,
    DuckDuckGo, ...) behind a single JSON endpoint that *you* run, so there is
    no per-provider key and no risk of the app itself being blocked. The
    instance must have the ``json`` output format enabled (see the bundled
    ``searxng/settings.yml``).
    """

    name = "searxng"

    @property
    def available(self) -> bool:
        return bool(settings.SEARXNG_URL)

    async def search(self, client: httpx.AsyncClient, query: str) -> ProviderResponse:
        start = time.perf_counter()
        base = (settings.SEARXNG_URL or "").rstrip("/")
        endpoint = f"{base}/search"
        params = {
            "q": query,
            "format": "json",
            "categories": "general",
            "language": "en",
            "safesearch": 0,
        }

        @_retry()
        async def _do() -> httpx.Response:
            resp = await client.get(endpoint, params=params)
            resp.raise_for_status()
            return resp

        try:
            resp = await _do()
            data = resp.json()
            results = []
            for i, item in enumerate(data.get("results", [])[:10]):
                url = item.get("url", "")
                if not url:
                    continue
                results.append(
                    SearchResult(
                        title=item.get("title", ""),
                        url=url,
                        description=item.get("content", ""),
                        rank=i + 1,
                    )
                )
            return ProviderResponse(
                provider=self.name,
                query=query,
                results=results,
                search_url=str(resp.request.url),
                response_time_ms=int((time.perf_counter() - start) * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("SearXNG search failed for %r: %s", query, exc)
            return ProviderResponse(
                provider=self.name,
                query=query,
                error=str(exc),
                response_time_ms=int((time.perf_counter() - start) * 1000),
            )


class WikidataProvider(BaseProvider):
    """Authoritative source: Wikidata's *official website* property (P856).

    Wikidata/Wikipedia explicitly records a company's official website, so a
    match here is treated as verified rather than a mere candidate. No API key
    is required, which makes it a reliable free fallback.
    """

    name = "wikipedia"
    SEARCH_ENDPOINT = "https://www.wikidata.org/w/api.php"
    OFFICIAL_WEBSITE_PROP = "P856"
    INSTANCE_OF_PROP = "P31"
    # Wikidata QIDs that indicate a business/organization (reduces false hits).
    ORG_INSTANCE_QIDS = {
        "Q4830453",  # business enterprise
        "Q783794",  # company
        "Q6881511",  # enterprise
        "Q891723",  # public company
        "Q43229",  # organization
        "Q167037",  # corporation
        "Q4830453",
        "Q210167",  # technology company
        "Q1058914",  # software company
    }

    @property
    def available(self) -> bool:
        return True

    async def search(self, client: httpx.AsyncClient, query: str) -> ProviderResponse:
        start = time.perf_counter()
        try:
            entity_ids = await self._search_entities(client, query)
            for entity_id in entity_ids[:3]:
                website = await self._official_website(client, entity_id)
                if website:
                    return ProviderResponse(
                        provider=self.name,
                        query=query,
                        results=[
                            SearchResult(
                                title=f"Wikidata {entity_id}",
                                url=website,
                                description="Official website (Wikidata P856)",
                                rank=1,
                                authoritative=True,
                            )
                        ],
                        search_url=f"https://www.wikidata.org/wiki/{entity_id}",
                        response_time_ms=int((time.perf_counter() - start) * 1000),
                    )
            return ProviderResponse(
                provider=self.name,
                query=query,
                search_url=self.SEARCH_ENDPOINT,
                response_time_ms=int((time.perf_counter() - start) * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Wikidata lookup failed for %r: %s", query, exc)
            return ProviderResponse(
                provider=self.name,
                query=query,
                error=str(exc),
                response_time_ms=int((time.perf_counter() - start) * 1000),
            )

    async def _search_entities(self, client: httpx.AsyncClient, query: str) -> list[str]:
        params = {
            "action": "wbsearchentities",
            "search": query,
            "language": "en",
            "format": "json",
            "type": "item",
            "limit": 5,
        }

        @_retry()
        async def _do() -> httpx.Response:
            resp = await client.get(
                self.SEARCH_ENDPOINT,
                params=params,
                headers={"User-Agent": "DomainFinder/1.0 (contact: admin@example.com)"},
            )
            resp.raise_for_status()
            return resp

        resp = await _do()
        return [item["id"] for item in resp.json().get("search", [])]

    async def _official_website(self, client: httpx.AsyncClient, entity_id: str) -> str | None:
        params = {
            "action": "wbgetentities",
            "ids": entity_id,
            "props": "claims",
            "format": "json",
        }

        @_retry()
        async def _do() -> httpx.Response:
            resp = await client.get(
                self.SEARCH_ENDPOINT,
                params=params,
                headers={"User-Agent": "DomainFinder/1.0 (contact: admin@example.com)"},
            )
            resp.raise_for_status()
            return resp

        resp = await _do()
        entity = resp.json().get("entities", {}).get(entity_id, {})
        claims = entity.get("claims", {})

        if not self._is_organization(claims):
            return None

        website_claims = claims.get(self.OFFICIAL_WEBSITE_PROP, [])
        for claim in website_claims:
            value = (
                claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            )
            if isinstance(value, str) and value.startswith("http"):
                return value
        return None

    def _is_organization(self, claims: dict[str, Any]) -> bool:
        for claim in claims.get(self.INSTANCE_OF_PROP, []):
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
            if isinstance(value, dict) and value.get("id") in self.ORG_INSTANCE_QIDS:
                return True
        # If P31 is missing we don't hard-fail; the P856 field alone is a strong
        # signal. But an explicit non-org classification returns False above.
        return not claims.get(self.INSTANCE_OF_PROP)


PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {
    "brave": BraveProvider,
    "google": GoogleCSEProvider,
    "bing": BingProvider,
    "searxng": SearxngProvider,
    "wikipedia": WikidataProvider,
}


def build_providers() -> list[BaseProvider]:
    """Instantiate providers in the configured order, skipping unavailable ones."""
    providers: list[BaseProvider] = []
    for name in settings.SEARCH_PROVIDER_ORDER:
        cls = PROVIDER_REGISTRY.get(name)
        if cls is None:
            logger.warning("Unknown search provider configured: %s", name)
            continue
        provider = cls()
        if provider.available:
            providers.append(provider)
        else:
            logger.info("Search provider %s not configured; skipping", name)
    return providers
