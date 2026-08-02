"""Counters, gauges and histograms, and the text a scraper reads them out of.

Three kinds of number, and which one a measurement is says what may be done with it:

- a **counter** only goes up (matches made, ever). Its value alone is uninteresting; the
  *rate* of it is the measurement, and a scraper works that out from two readings.
- a **gauge** is whatever it is right now (games running, sockets held). Reading it twice
  tells you nothing extra.
- a **histogram** is a distribution, and it exists because an average latency is a number
  that can look excellent while a tenth of the players are having a terrible time. What
  matters is the ninety-ninth percentile, and the only way to have one at the end is to
  have counted into buckets all along.

**No labels.** A metrics library would let a value carry dimensions — which shard, which
room — and it is genuinely the first thing to reach for. It is not needed here: each
process exposes only its own numbers, and the scraper stamps them with which process it
got them from. A label set would let one shard report per-room latency, which at ten
thousand rooms is ten thousand time series from one process, and that is a well-known way
to take a monitoring system down with the thing it is monitoring.

Everything is guarded by one lock. Values are written from the loop that runs the games
and read from the thread serving ``/metrics``, and while a torn *counter* would not matter
much, a histogram read halfway through an update would report a sum that never happened.
The lock is held for microseconds, a scrape happens every fifteen seconds, and the
alternative is a class of bug nobody would ever reproduce.
"""

from __future__ import annotations

import threading
from typing import Dict, Iterable, List, Sequence, Tuple

# Where a latency histogram's buckets sit, in milliseconds. Dense where the answer is
# expected and sparse after it, because "how much worse than 100 ms" stops being a
# question once the answer is "much".
LATENCY_BUCKETS_MS: Tuple[float, ...] = (1, 2, 5, 10, 25, 50, 100, 250, 500, 1000)
# And in microseconds, for the one measurement small enough to need them: the design
# assumes a tick resolves in about fifty.
DURATION_BUCKETS_US: Tuple[float, ...] = (10, 25, 50, 100, 250, 500, 1_000, 5_000)
# Bytes, for what one connection is sent per second. The claim to beat is ~325.
SIZE_BUCKETS_B: Tuple[float, ...] = (64, 128, 256, 512, 1_024, 2_048, 4_096, 16_384)


class _Metric:
    """What every metric has: a name, a sentence saying what it is, and a lock."""

    kind = ""

    def __init__(self, name: str, description: str, lock: threading.Lock) -> None:
        self.name = name
        self.description = description
        self._lock = lock

    def lines(self) -> Iterable[str]:  # pragma: no cover  (each subclass overrides it)
        raise NotImplementedError


class Counter(_Metric):
    """A number that only ever goes up. Read it twice to learn a rate."""

    kind = "counter"

    def __init__(self, name: str, description: str, lock: threading.Lock) -> None:
        super().__init__(name, description, lock)
        self._value = 0.0

    def inc(self, amount: float = 1.0) -> None:
        """Add ``amount`` (one by default) to the count."""
        with self._lock:
            self._value += amount

    @property
    def value(self) -> float:
        """The count so far — for a test, and for anything reading its own numbers."""
        with self._lock:
            return self._value

    def lines(self) -> Iterable[str]:
        yield f"{self.name} {_number(self._value)}"


class Gauge(_Metric):
    """A number that is whatever it is right now, and may go either way."""

    kind = "gauge"

    def __init__(self, name: str, description: str, lock: threading.Lock) -> None:
        super().__init__(name, description, lock)
        self._value = 0.0

    def set(self, value: float) -> None:
        """Say what the number is now. Not a delta: the caller knows the whole truth."""
        with self._lock:
            self._value = value

    @property
    def value(self) -> float:
        with self._lock:
            return self._value

    def lines(self) -> Iterable[str]:
        yield f"{self.name} {_number(self._value)}"


class Histogram(_Metric):
    """A distribution, kept as cumulative buckets, a sum and a count.

    Cumulative is the format Prometheus expects and is also the useful one: each bucket
    answers "how many were at most this", so a percentile is read straight off the counts
    without keeping a single observation around. A million measurements cost the same
    handful of numbers as ten.
    """

    kind = "histogram"

    def __init__(
        self,
        name: str,
        description: str,
        lock: threading.Lock,
        buckets: Sequence[float] = LATENCY_BUCKETS_MS,
    ) -> None:
        super().__init__(name, description, lock)
        self._bounds = tuple(sorted(buckets))
        self._counts: List[int] = [0] * len(self._bounds)
        self._sum = 0.0
        self._count = 0

    def observe(self, value: float) -> None:
        """Record one measurement."""
        with self._lock:
            self._sum += value
            self._count += 1
            for index, bound in enumerate(self._bounds):
                if value <= bound:
                    self._counts[index] += 1

    def percentile(self, fraction: float) -> float:
        """The bucket bound at or below which ``fraction`` of measurements fell.

        The answer a load test is actually after, without a Prometheus in the room. It is
        the *bucket*, not an interpolated value: saying p99 is "at most 100 ms" is what
        the data supports, and inventing 87.3 from it would be a decimal point of
        precision the measurement never had. ``inf`` means the tail ran off the end of
        the buckets, which is itself the finding.
        """
        with self._lock:
            if self._count == 0:
                return 0.0
            wanted = fraction * self._count
            for bound, count in zip(self._bounds, self._counts):
                if count >= wanted:
                    return bound
            return float("inf")

    @property
    def count(self) -> int:
        with self._lock:
            return self._count

    @property
    def average(self) -> float:
        """The mean — worth having beside a percentile, never instead of one."""
        with self._lock:
            return self._sum / self._count if self._count else 0.0

    def lines(self) -> Iterable[str]:
        for bound, count in zip(self._bounds, self._counts):
            yield f'{self.name}_bucket{{le="{_number(bound)}"}} {count}'
        yield f'{self.name}_bucket{{le="+Inf"}} {self._count}'
        yield f"{self.name}_sum {_number(self._sum)}"
        yield f"{self.name}_count {self._count}"


class Registry:
    """Every metric one process publishes, and the text a scraper reads them out of."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._metrics: Dict[str, _Metric] = {}

    def counter(self, name: str, description: str) -> Counter:
        """Register a counter, or return the one already registered under that name.

        Returning the existing one rather than refusing is what lets a module ask for its
        own metric at import time without anybody having to sequence the imports.
        """
        return self._register(Counter(name, description, self._lock))

    def gauge(self, name: str, description: str) -> Gauge:
        return self._register(Gauge(name, description, self._lock))

    def histogram(
        self, name: str, description: str, buckets: Sequence[float] = LATENCY_BUCKETS_MS
    ) -> Histogram:
        return self._register(Histogram(name, description, self._lock, buckets))

    def _register(self, metric: _Metric):
        existing = self._metrics.get(metric.name)
        if existing is not None:
            return existing
        self._metrics[metric.name] = metric
        return metric

    def render(self) -> str:
        """Every metric in the Prometheus text exposition format.

        Four kinds of line and a blank one between metrics. Written out here rather than
        imported because that is genuinely all of it — and because a format this small,
        implemented in the open, cannot drift from what the scraper expects without a
        test noticing.
        """
        blocks = []
        with self._lock:
            for metric in self._metrics.values():
                lines = [
                    f"# HELP {metric.name} {metric.description}",
                    f"# TYPE {metric.name} {metric.kind}",
                    *metric.lines(),
                ]
                blocks.append("\n".join(lines))
        return "\n\n".join(blocks) + "\n" if blocks else ""


def _number(value: float) -> str:
    """A number as Prometheus wants it: no trailing ``.0`` on whole values."""
    return str(int(value)) if float(value).is_integer() else repr(float(value))


# The one registry a process publishes. A module asks it for its own metrics at import
# time; nothing has to be passed down through six constructors to reach the place a
# number is actually known. It is a global because a process has exactly one set of
# numbers about itself, which is the case where a global is the honest answer.
REGISTRY = Registry()
