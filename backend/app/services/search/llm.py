"""Self-hosted LLM re-ranker (via Ollama).

Purpose and hard constraint
---------------------------
The LLM is **never** allowed to answer from its own knowledge or to invent a
domain. It is given the *real* candidate results already returned by our search
providers and asked only to **choose** which candidate is the company's official
website (or say "none"). Its choice is then re-validated against the same
guardrails used everywhere else:

* the chosen domain must be one of the candidate domains we actually extracted
  (any other value is treated as a hallucination and rejected);
* it must not be an aggregator/social/directory domain;
* the final confidence blends the model's own confidence with the deterministic
  name↔domain match, and must still clear ``CONFIDENCE_THRESHOLD``.

This lets a local model improve accuracy on ambiguous cases (e.g. picking
``aws.amazon.com`` for "Amazon Web Services", or the right same-name company)
without ever compromising the "never guess" promise.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import get_logger
from app.services.search.providers import ProviderResponse
from app.services.search.verifier import (
    VerificationOutcome,
    is_aggregator,
    name_domain_match,
    registrable_domain,
)

logger = get_logger(__name__)


@dataclass
class _Candidate:
    domain: str
    title: str
    snippet: str
    url: str


def _collect_candidates(responses: list[ProviderResponse]) -> list[_Candidate]:
    """Deduplicated, aggregator-free candidate domains from real search results."""
    seen: dict[str, _Candidate] = {}
    for resp in responses:
        for result in resp.results:
            domain = registrable_domain(result.url)
            if not domain or is_aggregator(domain) or domain in seen:
                continue
            seen[domain] = _Candidate(
                domain=domain,
                title=(result.title or "")[:160],
                snippet=(result.description or "")[:200],
                url=result.url,
            )
            if len(seen) >= settings.LLM_MAX_CANDIDATES:
                return list(seen.values())
    return list(seen.values())


def _build_prompt(clean_name: str, candidates: list[_Candidate]) -> str:
    lines = [
        f"{i + 1}. domain={c.domain} | title={c.title!r} | snippet={c.snippet!r}"
        for i, c in enumerate(candidates)
    ]
    candidate_block = "\n".join(lines)
    return (
        "You verify official company websites. Choose which candidate below is the "
        f"OFFICIAL website of the company named: \"{clean_name}\".\n\n"
        "STRICT RULES:\n"
        "- Choose ONLY from the candidate domains listed. Never invent a domain.\n"
        "- Pick the company's own official site, NOT a directory, marketplace, "
        "social network, news article, or reseller.\n"
        "- If none of the candidates is clearly the official website, return null.\n\n"
        f"CANDIDATES:\n{candidate_block}\n\n"
        'Respond with ONLY compact JSON: {"domain": <one candidate domain or null>, '
        '"confidence": <0..1>, "reason": <short string>}'
    )


async def llm_rerank(
    clean_name: str,
    responses: list[ProviderResponse],
    client: httpx.AsyncClient,
) -> VerificationOutcome | None:
    """Ask the local LLM to pick the official domain among real candidates.

    Returns a verified :class:`VerificationOutcome` if the model makes a valid,
    guardrail-passing choice; otherwise ``None`` (so discovery falls back to
    NOT FOUND). Any error is swallowed — the LLM is a best-effort enhancer.
    """
    if not settings.LLM_ENABLED or not settings.OLLAMA_URL:
        return None

    candidates = _collect_candidates(responses)
    if not candidates:
        return None

    candidate_domains = {c.domain for c in candidates}
    prompt = _build_prompt(clean_name, candidates)
    endpoint = f"{settings.OLLAMA_URL.rstrip('/')}/api/generate"
    payload = {
        "model": settings.LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }

    @retry(
        reraise=True,
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        retry=retry_if_exception_type(
            (httpx.TransportError, httpx.TimeoutException, httpx.HTTPStatusError)
        ),
    )
    async def _call() -> httpx.Response:
        resp = await client.post(endpoint, json=payload, timeout=settings.LLM_TIMEOUT_SECONDS)
        resp.raise_for_status()
        return resp

    try:
        resp = await _call()
        raw = resp.json().get("response", "")
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except Exception as exc:  # noqa: BLE001 - LLM is optional, never breaks a row
        logger.warning("LLM rerank failed for %r: %s", clean_name, exc)
        return None

    chosen = parsed.get("domain")
    if not chosen or not isinstance(chosen, str):
        return None
    chosen = chosen.strip().lower()

    # --- Guardrails: the model may only select a real, non-aggregator candidate.
    chosen_domain = registrable_domain(chosen) or chosen
    if chosen_domain not in candidate_domains:
        logger.info(
            "LLM proposed %r which is not among candidates %s — rejected as hallucination.",
            chosen_domain,
            candidate_domains,
        )
        return None
    if is_aggregator(chosen_domain):
        return None

    try:
        llm_conf = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        llm_conf = 0.0
    llm_conf = max(0.0, min(1.0, llm_conf))

    # Blend the model's confidence with the deterministic name match, and cap
    # below the authoritative-source ceiling (0.97) so Wikidata always outranks.
    match = name_domain_match(clean_name, chosen_domain)
    confidence = round(min(0.9, 0.5 * llm_conf + 0.4 * match + 0.1), 3)

    if confidence < settings.CONFIDENCE_THRESHOLD:
        return None

    reason = parsed.get("reason") if isinstance(parsed.get("reason"), str) else None
    return VerificationOutcome(
        domain=chosen_domain,
        confidence=confidence,
        source=f"LLM re-rank ({settings.LLM_MODEL})",
        reason=reason,
    )
