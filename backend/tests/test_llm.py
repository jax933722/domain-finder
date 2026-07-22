"""Tests for the self-hosted LLM re-ranker, including hallucination guardrails."""

import json

import httpx
import pytest

from app.core.config import settings
from app.services.search.llm import llm_rerank
from app.services.search.providers import ProviderResponse, SearchResult


def _responses() -> list[ProviderResponse]:
    return [
        ProviderResponse(
            provider="searxng",
            query="Amazon Web Services official website",
            results=[
                SearchResult("AWS", "https://aws.amazon.com/", rank=1),
                SearchResult("AWS on LinkedIn", "https://linkedin.com/company/aws", rank=2),
                SearchResult("Some reseller", "https://cloudreseller.example/aws", rank=3),
            ],
        )
    ]


def _client_returning(payload: dict) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": json.dumps(payload)})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_llm_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "LLM_ENABLED", False)
    async with _client_returning({"domain": "amazon.com", "confidence": 0.9}) as client:
        assert await llm_rerank("Amazon Web Services", _responses(), client) is None


@pytest.mark.asyncio
async def test_llm_picks_valid_candidate(monkeypatch):
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_URL", "http://ollama:11434")
    async with _client_returning(
        {"domain": "aws.amazon.com", "confidence": 0.95, "reason": "official AWS site"}
    ) as client:
        outcome = await llm_rerank("Amazon Web Services", _responses(), client)
    assert outcome is not None
    # aws.amazon.com collapses to the registrable amazon.com (a real candidate).
    assert outcome.domain == "amazon.com"
    assert outcome.confidence >= settings.CONFIDENCE_THRESHOLD
    assert "LLM" in (outcome.source or "")


@pytest.mark.asyncio
async def test_llm_hallucination_is_rejected(monkeypatch):
    """A domain the model invents (not among real candidates) must be dropped."""
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_URL", "http://ollama:11434")
    async with _client_returning({"domain": "amazonwebservices.io", "confidence": 0.99}) as client:
        outcome = await llm_rerank("Amazon Web Services", _responses(), client)
    assert outcome is None


@pytest.mark.asyncio
async def test_llm_null_choice_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_URL", "http://ollama:11434")
    async with _client_returning({"domain": None, "confidence": 0.0}) as client:
        outcome = await llm_rerank("Totally Unknown Co", _responses(), client)
    assert outcome is None


@pytest.mark.asyncio
async def test_llm_never_returns_aggregator(monkeypatch):
    """Even if the model names an aggregator, it is never returned."""
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_URL", "http://ollama:11434")
    # LinkedIn is filtered out of candidates, so selecting it fails the guard.
    async with _client_returning({"domain": "linkedin.com", "confidence": 0.9}) as client:
        outcome = await llm_rerank("Amazon Web Services", _responses(), client)
    assert outcome is None


@pytest.mark.asyncio
async def test_llm_no_candidates_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_URL", "http://ollama:11434")
    empty = [ProviderResponse(provider="searxng", query="q", results=[])]
    async with _client_returning({"domain": "x.com", "confidence": 0.9}) as client:
        assert await llm_rerank("Anything", empty, client) is None
