"""Tests for the observability endpoint: what it answers, and what it refuses to.

The routing is a function of a string, so it is tested by calling it. The socket and the
shape of an HTTP response are the irreducible part, excluded from coverage exactly like
every other listener here.
"""

from kfchess.obs.endpoint import answer
from kfchess.obs.metrics import REGISTRY


def test_health_is_answered_without_consulting_anything():
    """A liveness check that asks the database restarts the cluster when it hiccups."""
    status, body, _ = answer("/healthz")

    assert (status, body) == (200, "ok\n")


def test_metrics_are_answered_in_the_format_a_scraper_expects():
    REGISTRY.counter("kfc_test_endpoint_total", "A test counter.").inc()

    status, body, content_type = answer("/metrics")

    assert status == 200
    assert "kfc_test_endpoint_total" in body
    assert content_type.startswith("text/plain; version=0.0.4")


def test_anything_else_is_not_found():
    """There is no route table to extend, which is the point: this is not an API."""
    assert answer("/games")[0] == 404
    assert answer("/")[0] == 404
