"""Tests that metrics are defined and exportable."""

from prometheus_client import generate_latest

from app.core import metrics


def test_counters_increment_and_export():
    metrics.LOOKUPS_TOTAL.labels(outcome="verified").inc()
    metrics.PROVIDER_REQUESTS.labels(provider="searxng", outcome="success").inc()
    metrics.JOBS_TOTAL.labels(status="completed").inc()
    metrics.JOB_ROWS.inc(5)

    exported = generate_latest()
    assert b"df_domain_lookups_total" in exported
    assert b"df_provider_requests_total" in exported
    assert b"df_jobs_total" in exported
    assert b"df_job_rows_total" in exported


def test_histograms_observe():
    metrics.LOOKUP_LATENCY.observe(0.5)
    metrics.PROVIDER_LATENCY.labels(provider="brave").observe(0.2)
    metrics.HTTP_LATENCY.labels("GET", "/health").observe(0.01)
    exported = generate_latest()
    assert b"df_domain_lookup_duration_seconds" in exported
    assert b"df_http_request_duration_seconds" in exported
