"""Live domain reachability confirmation.

This does **not** discover or invent domains — it only confirms that a domain
*already identified* by search actually responds, and reports where it
redirects. That lets discovery catch dead, parked, or mis-identified domains and
adjust confidence accordingly, which makes results materially more trustworthy.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.search.verifier import registrable_domain

logger = get_logger(__name__)


@dataclass
class ReachabilityResult:
    checked: bool
    reachable: bool
    status_code: int | None = None
    final_domain: str | None = None
    redirected: bool = False
    error: str | None = None


async def check_domain(domain: str, client: httpx.AsyncClient) -> ReachabilityResult:
    """Probe ``https://{domain}`` (then ``http://``), following redirects.

    A domain is considered reachable when the final response status is < 400.
    Never raises — any failure is reported as ``reachable=False``.
    """
    if not settings.VERIFY_DOMAIN_REACHABLE or not domain:
        return ReachabilityResult(checked=False, reachable=False)

    timeout = httpx.Timeout(settings.REACHABILITY_TIMEOUT_SECONDS)
    headers = {"User-Agent": "DomainFinder/1.0 (+reachability-check)"}

    for scheme in ("https", "http"):
        url = f"{scheme}://{domain}"
        try:
            # Prefer a cheap HEAD; some servers reject it, so fall back to GET.
            resp = await client.head(
                url, timeout=timeout, follow_redirects=True, headers=headers
            )
            if resp.status_code >= 400 or resp.status_code == 405:
                resp = await client.get(
                    url, timeout=timeout, follow_redirects=True, headers=headers
                )
            final_domain = registrable_domain(str(resp.url)) or domain
            reachable = resp.status_code < 400
            return ReachabilityResult(
                checked=True,
                reachable=reachable,
                status_code=resp.status_code,
                final_domain=final_domain,
                redirected=final_domain != domain,
            )
        except Exception as exc:  # noqa: BLE001 - try next scheme, then give up
            last_error = str(exc)
            continue

    return ReachabilityResult(checked=True, reachable=False, error=last_error)
