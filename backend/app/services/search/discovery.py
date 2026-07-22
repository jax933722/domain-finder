"""Domain-discovery orchestration.

Ties providers and the verifier together for a single company. Implements the
sequential search strategy: authoritative structured sources first, then
reliable search APIs, stopping as soon as a confident answer emerges.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.search.providers import BaseProvider, ProviderResponse
from app.services.search.verifier import verify

logger = get_logger(__name__)


@dataclass
class SearchAttempt:
    provider: str
    query: str
    search_url: str
    result_domain: str | None
    success: bool
    response_time_ms: int
    error: str | None = None


@dataclass
class DiscoveryResult:
    clean_company: str
    domain: str | None
    status: str  # "VERIFIED" | "NOT FOUND" | "ERROR"
    confidence: float
    source: str | None
    search_url: str | None
    query: str
    reason: str | None
    processing_time_ms: int
    attempts: list[SearchAttempt] = field(default_factory=list)


def create_http_client() -> httpx.AsyncClient:
    """Shared async client with connection pooling and sane timeouts."""
    limits = httpx.Limits(
        max_connections=settings.HTTP_MAX_CONNECTIONS,
        max_keepalive_connections=settings.HTTP_MAX_KEEPALIVE,
    )
    timeout = httpx.Timeout(settings.SEARCH_TIMEOUT_SECONDS)
    return httpx.AsyncClient(
        limits=limits,
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": "DomainFinder/1.0"},
    )


async def discover_domain(
    clean_company: str,
    providers: list[BaseProvider],
    client: httpx.AsyncClient,
) -> DiscoveryResult:
    """Resolve the official domain for a cleaned company name.

    Never fabricates a domain: if no provider yields verifiable evidence, the
    result status is ``NOT FOUND``.
    """
    start = time.perf_counter()
    query = f"{clean_company} official website"

    if not clean_company.strip():
        return DiscoveryResult(
            clean_company=clean_company,
            domain=None,
            status="NOT FOUND",
            confidence=0.0,
            source=None,
            search_url=None,
            query=query,
            reason="Empty company name after cleaning.",
            processing_time_ms=0,
        )

    responses: list[ProviderResponse] = []
    attempts: list[SearchAttempt] = []

    for provider in providers:
        resp = await provider.search(client, query)
        responses.append(resp)

        result_domain = resp.results[0].url if resp.results else None
        attempts.append(
            SearchAttempt(
                provider=provider.name,
                query=query,
                search_url=resp.search_url,
                result_domain=result_domain,
                success=bool(resp.results),
                response_time_ms=resp.response_time_ms,
                error=resp.error,
            )
        )

        # Verify with everything gathered so far; stop early once confident.
        outcome = verify(clean_company, responses)
        if outcome.domain and outcome.confidence >= settings.CONFIDENCE_THRESHOLD:
            elapsed = int((time.perf_counter() - start) * 1000)
            logger.info(
                "Resolved %r -> %s (%.2f) via %s",
                clean_company,
                outcome.domain,
                outcome.confidence,
                outcome.source,
            )
            return DiscoveryResult(
                clean_company=clean_company,
                domain=outcome.domain,
                status="VERIFIED",
                confidence=outcome.confidence,
                source=outcome.source,
                search_url=resp.search_url,
                query=query,
                reason=None,
                processing_time_ms=elapsed,
                attempts=attempts,
            )

    # Nothing cleared the bar — return an honest NOT FOUND with the last reason.
    final = verify(clean_company, responses)
    elapsed = int((time.perf_counter() - start) * 1000)
    last_url = next((a.search_url for a in reversed(attempts) if a.search_url), None)
    return DiscoveryResult(
        clean_company=clean_company,
        domain=None,
        status="NOT FOUND",
        confidence=final.confidence,
        source=None,
        search_url=last_url,
        query=query,
        reason=final.reason or "No authoritative source identified the official domain.",
        processing_time_ms=elapsed,
        attempts=attempts,
    )
