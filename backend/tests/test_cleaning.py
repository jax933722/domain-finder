"""Tests for the company-name cleaning rules."""

import pytest

from app.services.cleaning import cache_key_for, clean_company_name


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("CEO at Microsoft", "Microsoft"),
        ("Founder @ Google", "Google"),
        ("CTO - Amazon Web Services", "Amazon Web Services"),
        ("Working at Apple Inc.", "Apple"),
        ("Director @ Reliance Industries Limited", "Reliance Industries"),
        ("Founder & CEO - OpenAI", "OpenAI"),
        ("Google LLC", "Google"),
        ("Meta Platforms", "Meta Platforms"),
        ("Infosys Ltd", "Infosys"),
        ("IBM India", "IBM"),
        ("Owner, ABC Traders", "ABC Traders"),
        ("Managing Director | Tata Consultancy Services", "Tata Consultancy Services"),
        ("Co-Founder @ Stripe, Inc.", "Stripe"),
    ],
)
def test_clean_company_name(raw, expected):
    assert clean_company_name(raw) == expected


def test_empty_and_whitespace():
    assert clean_company_name("") == ""
    assert clean_company_name("   ") == ""


def test_cache_key_is_normalized():
    assert cache_key_for("Amazon Web Services") == "amazonwebservices"
    assert cache_key_for("Google LLC") == cache_key_for("google llc")
    assert cache_key_for("IBM") == "ibm"


def test_accented_names_are_folded():
    assert clean_company_name("Nestlé S.A.") == "Nestle"
