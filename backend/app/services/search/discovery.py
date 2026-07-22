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
from app.services.search.llm import llm_rerank
from app.services.search.providers import BaseProvider, ProviderResponse
from app.services.search.reachability import check_domain
from app.services.search.verifier import is_aggregator, name_domain_match, verify

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


async def _finalize_verified(
    clean_company: str,
    domain: str,
    confidence: float,
    source: str | None,
    authoritative: bool,
    search_url: str | None,
    query: str,
    start: float,
    attempts: list[SearchAttempt],
    client: httpx.AsyncClient,
) -> DiscoveryResult:
    """Confirm a found domain is live before returning it.

    Reachability never invents a domain — it validates one already identified.
    A non-authoritative domain that fails to respond is penalized and may drop
    to NOT FOUND; a live redirect to a better-matching own-domain is adopted.
    """
    final_domain = domain
    final_confidence = confidence
    reason: str | None = None

    if settings.VERIFY_DOMAIN_REACHABLE and client is not None:
        reach = await check_domain(domain, client)
        if reach.checked:
            attempts.append(
                SearchAttempt(
                    provider="reachability",
                    query=query,
                    search_url=f"https://{domain}",
                    result_domain=reach.final_domain,
                    success=reach.reachable,
                    response_time_ms=0,
                    error=reach.error,
                )
            )
            if reach.reachable:
                # Follow a live cross-domain redirect to the canonical own-site
                # when it matches the company at least as well (e.g. .com -> .io).
                if (
                    reach.redirected
                    and reach.final_domain
                    and not is_aggregator(reach.final_domain)
                    and name_domain_match(clean_company, reach.final_domain)
                    >= name_domain_match(clean_company, domain)
                ):
                    final_domain = reach.final_domain
                    reason = f"Redirected from {domain} to canonical {final_domain}."
                final_confidence = min(1.0, final_confidence + 0.03)
            elif not authoritative:
                final_confidence = round(final_confidence - settings.REACHABILITY_PENALTY, 3)
                if final_confidence < settings.CONFIDENCE_THRESHOLD:
                    elapsed = int((time.perf_counter() - start) * 1000)
                    return DiscoveryResult(
                        clean_company=clean_company,
                        domain=None,
                        status="NOT FOUND",
                        confidence=final_confidence,
                        source=None,
                        search_url=search_url,
                        query=query,
                        reason=(
                            f"Identified domain '{domain}' did not respond, and "
                            "confidence fell below the threshold after that penalty."
                        ),
                        processing_time_ms=elapsed,
                        attempts=attempts,
                    )
                reason = f"Identified domain '{domain}' did not respond; confidence reduced."
            else:
                reason = f"Authoritative domain '{domain}' did not respond to a probe."

    elapsed = int((time.perf_counter() - start) * 1000)
    return DiscoveryResult(
        clean_company=clean_company,
        domain=final_domain,
        status="VERIFIED",
        confidence=round(final_confidence, 3),
        source=source,
        search_url=search_url,
        query=query,
        reason=reason,
        processing_time_ms=elapsed,
        attempts=attempts,
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
            logger.info(
                "Resolved %r -> %s (%.2f) via %s",
                clean_company,
                outcome.domain,
                outcome.confidence,
                outcome.source,
            )
            return await _finalize_verified(
                clean_company=clean_company,
                domain=outcome.domain,
                confidence=outcome.confidence,
                source=outcome.source,
                authoritative=outcome.authoritative,
                search_url=resp.search_url,
                query=query,
                start=start,
                attempts=attempts,
                client=client,
            )

    # Deterministic verification did not clear the bar. If a self-hosted LLM is
    # enabled, let it disambiguate among the *real* candidates we collected. It
    # can only pick an already-seen domain — it never invents one.
    llm_outcome = await llm_rerank(clean_company, responses, client)
    if llm_outcome and llm_outcome.domain:
        attempts.append(
            SearchAttempt(
                provider="llm-rerank",
                query=query,
                search_url="",
                result_domain=llm_outcome.domain,
                success=True,
                response_time_ms=0,
            )
        )
        logger.info(
            "LLM resolved %r -> %s (%.2f)",
            clean_company,
            llm_outcome.domain,
            llm_outcome.confidence,
        )
        last_url = next((a.search_url for a in reversed(attempts) if a.search_url), None)
        return await _finalize_verified(
            clean_company=clean_company,
            domain=llm_outcome.domain,
            confidence=llm_outcome.confidence,
            source=llm_outcome.source,
            authoritative=False,
            search_url=last_url,
            query=query,
            start=start,
            attempts=attempts,
            client=client,
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
