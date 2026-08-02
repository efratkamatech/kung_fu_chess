"""Tests for the metrics registry: the counting, and the text a scraper reads.

The exposition format is tested character for character, because it is the one part of
this that has to satisfy somebody else. Everything else here can be judged by reading it;
whether Prometheus will accept the output cannot.
"""

from kfchess.obs.metrics import (
    DURATION_BUCKETS_US,
    Registry,
)


def test_a_counter_starts_at_nothing_and_goes_up():
    counter = Registry().counter("kfc_matches_total", "Matches made.")

    counter.inc()
    counter.inc(3)

    assert counter.value == 4


def test_a_gauge_is_told_what_it_is_rather_than_by_how_much_it_changed():
    """The caller knows how many games it is running; a delta would be it guessing."""
    gauge = Registry().gauge("kfc_active_games", "Games running.")

    gauge.set(17)
    gauge.set(16)

    assert gauge.value == 16


def test_a_histogram_counts_into_every_bucket_it_falls_within():
    """Cumulative, which is what makes a percentile readable straight off the counts."""
    registry = Registry()
    histogram = registry.histogram("kfc_move_latency_ms", "Latency.", buckets=(1, 10, 100))

    histogram.observe(5)

    assert registry.render().splitlines()[2:5] == [
        'kfc_move_latency_ms_bucket{le="1"} 0',
        'kfc_move_latency_ms_bucket{le="10"} 1',
        'kfc_move_latency_ms_bucket{le="100"} 1',
    ]


def test_a_histogram_keeps_its_sum_and_count():
    histogram = Registry().histogram("kfc_move_latency_ms", "Latency.")

    for value in (10, 20, 30):
        histogram.observe(value)

    assert (histogram.count, histogram.average) == (3, 20)


def test_an_empty_histogram_averages_to_nothing_rather_than_dividing_by_zero():
    assert Registry().histogram("kfc_move_latency_ms", "Latency.").average == 0.0


# --- percentiles: the number a load test is actually after ---------------------

def test_the_percentile_is_the_bucket_the_fraction_falls_in():
    histogram = Registry().histogram("kfc_x", "x.", buckets=(1, 10, 100, 1000))
    for _ in range(99):
        histogram.observe(5)
    histogram.observe(500)  # one slow one, in the hundredth

    assert histogram.percentile(0.5) == 10     # the fast crowd
    assert histogram.percentile(0.99) == 10    # still the fast crowd, just
    assert histogram.percentile(1.0) == 1000   # and the straggler


def test_a_percentile_of_nothing_is_nothing():
    assert Registry().histogram("kfc_x", "x.").percentile(0.99) == 0.0


def test_a_tail_beyond_the_last_bucket_is_reported_as_infinite():
    """Not clamped to the last bound: "worse than we thought to measure" is the finding."""
    histogram = Registry().histogram("kfc_x", "x.", buckets=(1, 10))
    histogram.observe(5)
    histogram.observe(99_999)

    assert histogram.percentile(0.99) == float("inf")


# --- the exposition format -----------------------------------------------------

def test_a_counter_renders_as_prometheus_expects():
    registry = Registry()
    registry.counter("kfc_matches_total", "Matches made since start.").inc(2)

    assert registry.render() == (
        "# HELP kfc_matches_total Matches made since start.\n"
        "# TYPE kfc_matches_total counter\n"
        "kfc_matches_total 2\n"
    )


def test_a_histogram_renders_with_its_buckets_sum_and_count():
    registry = Registry()
    registry.histogram("kfc_x", "An x.", buckets=(1, 10)).observe(5)

    assert registry.render() == (
        "# HELP kfc_x An x.\n"
        "# TYPE kfc_x histogram\n"
        'kfc_x_bucket{le="1"} 0\n'
        'kfc_x_bucket{le="10"} 1\n'
        'kfc_x_bucket{le="+Inf"} 1\n'
        "kfc_x_sum 5\n"
        "kfc_x_count 1\n"
    )


def test_metrics_are_separated_by_a_blank_line():
    registry = Registry()
    registry.counter("kfc_a", "A.").inc()
    registry.gauge("kfc_b", "B.").set(1)

    assert "\n\n" in registry.render()


def test_nothing_registered_renders_as_nothing():
    """An empty body, not a stray newline: a scraper reads this and must not be puzzled."""
    assert Registry().render() == ""


def test_whole_numbers_lose_their_decimal_point():
    registry = Registry()
    registry.gauge("kfc_games", "Games.").set(17.0)

    assert "kfc_games 17\n" in registry.render()


def test_a_fractional_value_keeps_its_decimals():
    registry = Registry()
    registry.gauge("kfc_load", "Load.").set(0.5)

    assert "kfc_load 0.5\n" in registry.render()


# --- registering ---------------------------------------------------------------

def test_asking_twice_for_the_same_metric_gives_the_same_one():
    """Modules ask at import time; nobody should have to sequence the imports."""
    registry = Registry()
    first = registry.counter("kfc_matches_total", "Matches.")
    first.inc()

    second = registry.counter("kfc_matches_total", "Matches.")

    assert second is first
    assert second.value == 1


def test_the_buckets_for_a_duration_are_the_small_ones():
    """The design assumes a tick resolves in about fifty microseconds. That needs bounds
    around fifty, not around a hundred milliseconds."""
    assert 50 in DURATION_BUCKETS_US
