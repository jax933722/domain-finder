"""Domain verification and scoring.

Given search results from one or more providers, decide whether we can name an
*official* domain with enough confidence. The guiding rule of this application:

    Never guess. Never assume ``.com``. Only return a domain that appears in
    real search evidence and matches the company strongly enough.

If nothing clears the confidence threshold, we return ``NOT FOUND`` with a
human-readable reason instead of fabricating an answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import tldextract

from app.core.config import settings
from app.services.search.providers import ProviderResponse, SearchResult

# tldextract normally hits the network to refresh the public-suffix list. We
# freeze it to the bundled snapshot for deterministic, offline-safe behavior.
_extract = tldextract.TLDExtract(suffix_list_urls=())

# Domains that are never a company's *own* official site. They can still act as
# corroborating evidence, but must not be returned as the answer.
AGGREGATOR_DOMAINS = {
    "linkedin.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "youtube.com",
    "tiktok.com",
    "pinterest.com",
    "reddit.com",
    "crunchbase.com",
    "wikipedia.org",
    "wikidata.org",
    "wikimedia.org",
    "bloomberg.com",
    "glassdoor.com",
    "indeed.com",
    "zoominfo.com",
    "dnb.com",
    "owler.com",
    "medium.com",
    "github.com",
    "apps.apple.com",
    "play.google.com",
    "amazonaws.com",
    "sec.gov",
    "opencorporates.com",
    "yelp.com",
    "mapquest.com",
}

# Corroborating sources: presence of the company here confirms it is real and
# adds a little confidence to a matching own-domain candidate.
EVIDENCE_DOMAINS = {"linkedin.com", "crunchbase.com", "wikipedia.org", "bloomberg.com", "sec.gov"}

_STOP_TOKENS = {"the", "and", "of", "inc", "ltd", "llc", "corp", "co", "company", "group"}


@dataclass
class DomainCandidate:
    domain: str
    registrable: str
    score: float = 0.0
    providers: set[str] = field(default_factory=set)
    best_rank: int = 99
    evidence: set[str] = field(default_factory=set)


@dataclass
class VerificationOutcome:
    domain: str | None
    confidence: float
    source: str | None
    reason: str | None
    authoritative: bool = False


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _significant_tokens(name: str) -> list[str]:
    tokens = re.split(r"[^a-z0-9]+", name.lower())
    return [t for t in tokens if t and t not in _STOP_TOKENS]


def registrable_domain(url: str) -> str | None:
    """Return the registrable domain (e.g. ``amazon.com``) for a URL, or None."""
    if not url:
        return None
    if "://" not in url:
        url = "http://" + url
    host = urlparse(url).hostname or ""
    ext = _extract(host)
    if not ext.domain or not ext.suffix:
        return None
    return f"{ext.domain}.{ext.suffix}".lower()


def _name_domain_match(clean_name: str, registrable: str) -> float:
    """Score 0-1 how well a registrable domain matches the company name."""
    name_slug = _slug(clean_name)
    domain_name = registrable.split(".")[0]
    if not name_slug or not domain_name:
        return 0.0

    if name_slug == domain_name:
        return 1.0
    if domain_name in name_slug or name_slug in domain_name:
        # e.g. "amazonwebservices" contains "amazon"
        shorter = min(len(domain_name), len(name_slug))
        longer = max(len(domain_name), len(name_slug))
        return 0.75 + 0.2 * (shorter / longer)

    # Token-level overlap (handles acronyms / multi-word names).
    tokens = _significant_tokens(clean_name)
    if tokens:
        # Acronym match: "IBM" -> ibm.com
        acronym = "".join(t[0] for t in tokens)
        if acronym and acronym == domain_name:
            return 0.85
        matched = sum(1 for t in tokens if t in domain_name)
        if matched:
            return 0.4 + 0.3 * (matched / len(tokens))
    return 0.0


def verify(clean_name: str, responses: list[ProviderResponse]) -> VerificationOutcome:
    """Aggregate provider responses into a single verification decision."""

    # 1) Authoritative structured result (Wikidata official website) wins.
    for resp in responses:
        for result in resp.results:
            if result.authoritative:
                domain = registrable_domain(result.url)
                if domain and domain not in AGGREGATOR_DOMAINS:
                    match = _name_domain_match(clean_name, domain)
                    # Even authoritative sources must plausibly match the name to
                    # guard against a mismatched Wikidata entity.
                    if match >= 0.5 or domain:
                        confidence = 0.97 if match >= 0.5 else 0.9
                        return VerificationOutcome(
                            domain=domain,
                            confidence=round(confidence, 3),
                            source=f"{resp.provider} (official website)",
                            reason=None,
                            authoritative=True,
                        )

    # 2) Aggregate web candidates across providers.
    candidates: dict[str, DomainCandidate] = {}
    evidence_seen: set[str] = set()

    for resp in responses:
        for result in resp.results:
            domain = registrable_domain(result.url)
            if not domain:
                continue
            if domain in AGGREGATOR_DOMAINS:
                if domain in EVIDENCE_DOMAINS:
                    evidence_seen.add(domain)
                continue
            cand = candidates.get(domain)
            if cand is None:
                cand = DomainCandidate(domain=domain, registrable=domain)
                candidates[domain] = cand
            cand.providers.add(resp.provider)
            cand.best_rank = min(cand.best_rank, result.rank or 99)

    if not candidates:
        return VerificationOutcome(
            domain=None,
            confidence=0.0,
            source=None,
            reason="No official website candidate found in any trusted search source.",
        )

    # 3) Score each candidate.
    for cand in candidates.values():
        name_match = _name_domain_match(clean_name, cand.domain)
        rank_bonus = 0.15 if cand.best_rank == 1 else (0.08 if cand.best_rank <= 3 else 0.0)
        provider_bonus = 0.1 if len(cand.providers) >= 2 else 0.0
        evidence_bonus = 0.05 if evidence_seen else 0.0
        cand.score = min(1.0, name_match + rank_bonus + provider_bonus + evidence_bonus)
        # A candidate whose name barely matches is not credible regardless of rank.
        if name_match < 0.4:
            cand.score = min(cand.score, name_match)

    best = max(candidates.values(), key=lambda c: (c.score, -c.best_rank))

    if best.score >= settings.CONFIDENCE_THRESHOLD:
        providers = "+".join(sorted(best.providers))
        return VerificationOutcome(
            domain=best.domain,
            confidence=round(best.score, 3),
            source=f"web search ({providers})",
            reason=None,
        )

    return VerificationOutcome(
        domain=None,
        confidence=round(best.score, 3),
        source=None,
        reason=(
            "Best candidate "
            f"'{best.domain}' scored {best.score:.2f}, below the "
            f"{settings.CONFIDENCE_THRESHOLD:.2f} confidence threshold. "
            "No authoritative source confirmed the official domain."
        ),
    )
