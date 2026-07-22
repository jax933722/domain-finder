"""Company-name cleaning.

Turns messy input such as ``"CEO at Microsoft"`` or ``"Founder & CEO - OpenAI"``
into a normalized brand name (``"Microsoft"`` / ``"OpenAI"``) that can be used as
a search query and a stable cache key.

The cleaning is deliberately conservative: it strips well-known job-title
prefixes and legal-entity suffixes but preserves the actual brand. It never
invents or rewrites the core name.
"""

from __future__ import annotations

import re
import unicodedata

# Job titles / relationship prefixes that may precede a company name.
# Longest phrases first so multi-word titles are matched before single words.
JOB_TITLE_PREFIXES = [
    "managing director",
    "co-founder & ceo",
    "founder & ceo",
    "co founder",
    "co-founder",
    "vice president",
    "employee at",
    "working at",
    "works at",
    "consultant at",
    "consultant",
    "president",
    "director",
    "founder",
    "partner",
    "owner",
    "manager",
    "ceo",
    "cto",
    "coo",
    "cfo",
    "cmo",
    "vp",
    "svp",
    "evp",
    "head",
    "lead",
    "at",
]

# Connector tokens that separate a title from the company.
SEPARATOR_PATTERN = re.compile(r"\s*[@|/\-–—:,]\s*|\s+at\s+", re.IGNORECASE)

# Legal / entity suffixes to drop. Order matters (longest first).
COMPANY_SUFFIXES = [
    "private limited",
    "pvt. ltd.",
    "pvt ltd",
    "pte. ltd.",
    "pte ltd",
    "co., ltd.",
    "co. ltd",
    "s.a.s.",
    "s.a.",
    "s.r.l.",
    "b.v.",
    "n.v.",
    "plc.",
    "plc",
    "llc.",
    "llc",
    "l.l.c.",
    "ltd.",
    "ltd",
    "limited",
    "inc.",
    "inc",
    "incorporated",
    "corporation",
    "corp.",
    "corp",
    "gmbh",
    "ag",
    "bv",
    "nv",
    "sa",
    "srl",
    "oyj",
    "ab",
    "as",
    "kk",
    "co.",
    "company",
    "holdings",
    "group",
    "technologies",
    "solutions",
]

# Regional qualifiers frequently appended to a global brand (e.g. "IBM India").
REGION_QUALIFIERS = {
    "india",
    "usa",
    "us",
    "uk",
    "emea",
    "apac",
    "europe",
    "asia",
    "global",
    "international",
    "worldwide",
}

_TITLE_PREFIX_RE = re.compile(
    r"^(?:%s)\b" % "|".join(re.escape(p) for p in JOB_TITLE_PREFIXES),
    re.IGNORECASE,
)


def _normalize_unicode(text: str) -> str:
    """Fold accents to ASCII-ish equivalents while keeping letters intact."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def _strip_leading_titles(text: str) -> str:
    """Repeatedly remove leading job titles and stray separators."""
    previous = None
    current = text.strip()
    # Loop because inputs may stack several titles: "Founder & CEO - OpenAI".
    while current and current != previous:
        previous = current
        current = _TITLE_PREFIX_RE.sub("", current).strip()
        # Trim any leftover leading separators/conjunctions.
        current = re.sub(r"^(?:[&,/@|\-–—:]|and|\s)+", "", current, flags=re.IGNORECASE).strip()
    return current


def _remove_suffixes(text: str) -> str:
    """Drop trailing legal/entity suffixes, one layer at a time."""
    changed = True
    while changed:
        changed = False
        for suffix in COMPANY_SUFFIXES:
            # Match the suffix as trailing whole word(s), tolerating a comma.
            pattern = re.compile(r"[\s,]+" + re.escape(suffix) + r"\.?$", re.IGNORECASE)
            if pattern.search(text):
                stripped = pattern.sub("", text).strip(" ,.-")
                # Never let suffix removal delete the entire name.
                if stripped:
                    text = stripped
                    changed = True
                break
    return text


def _remove_region_qualifier(text: str) -> str:
    """Strip a single trailing region qualifier (e.g. "IBM India" -> "IBM")."""
    parts = text.split()
    if len(parts) >= 2 and parts[-1].lower().strip(".,") in REGION_QUALIFIERS:
        return " ".join(parts[:-1]).strip()
    return text


def clean_company_name(raw: str) -> str:
    """Extract the brand name from a raw company/role string.

    Returns an empty string if nothing meaningful remains.
    """
    if not raw or not raw.strip():
        return ""

    text = _normalize_unicode(raw).strip()

    # Collapse whitespace early.
    text = re.sub(r"\s+", " ", text)

    # If a clear separator exists, the company usually follows the last one
    # (e.g. "CTO - Amazon Web Services", "Working at Apple Inc.").
    candidate = text
    stripped = _strip_leading_titles(text)
    if stripped:
        candidate = stripped
    else:
        # Whole string was titles/separators; fall back to the segment after
        # the final separator.
        segments = [s for s in SEPARATOR_PATTERN.split(text) if s and s.strip()]
        candidate = segments[-1].strip() if segments else text

    # Remove any residual separators that survived.
    candidate = candidate.strip(" ,-|/@").strip()

    candidate = _remove_suffixes(candidate)
    candidate = _remove_region_qualifier(candidate)

    # Final tidy: collapse whitespace and trim punctuation noise.
    candidate = re.sub(r"\s+", " ", candidate).strip(" ,.-&")

    return candidate


def cache_key_for(clean_name: str) -> str:
    """Stable, case-insensitive key for caching/deduplication."""
    return re.sub(r"[^a-z0-9]+", "", clean_name.lower())
