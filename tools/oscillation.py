"""Run the same solo load test many times over, and report the spread.

`Server_Design_EN.md` once claimed that two workloads on one thread oscillate rather than
degrade, on the strength of two runs that seated 410 and 998 players. Two runs is an
anecdote. This repeats one run — identical size, identical duration, identical starting
state — as many times as asked, and scrapes the server's own metrics every few seconds so
the *shape* of a run is visible and not just its total::

    python tools/oscillation.py 8 1000 60

What it found is in the design document: four runs in eight seated nobody, the login rate
was the same in all eight, and the tick loop in the failed runs did not run at all.

Each run gets its own throwaway SQLite accounts file — ``DATABASE_URL`` takes any path,
and anything that is not a DSN means SQLite — so no run inherits the previous run's
thousand accounts and the repository's ``users.db`` is never touched.
"""

from __future__ import annotations

import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OBS = "http://localhost:9100"


def scrape() -> str:
    """The metrics page as text, or raise if the server is not answering."""
    with urllib.request.urlopen(f"{OBS}/metrics", timeout=5) as response:
        return response.read().decode()


def value(text: str, name: str):
    """One counter or gauge out of a metrics page."""
    match = re.search(rf"^{re.escape(name)} (\S+)$", text, re.M)
    return float(match.group(1)) if match else None


def histogram(text: str, name: str):
    """One histogram's buckets, count and sum."""
    buckets = {}
    for bound, count in re.findall(rf'^{re.escape(name)}_bucket{{le="(\S+)"}} (\d+)$', text, re.M):
        buckets[float(bound)] = int(count)
    return buckets, value(text, f"{name}_count") or 0, value(text, f"{name}_sum") or 0


def percentile(buckets, total, fraction):
    """The bucket bound ``fraction`` of the observations fall within."""
    if not total:
        return None
    for bound in sorted(buckets):
        if buckets[bound] >= fraction * total:
            return bound
    return float("inf")


def sample(text: str, at: float) -> dict:
    """Everything worth keeping out of one scrape, stamped with when it was taken."""
    tick_buckets, tick_count, tick_sum = histogram(text, "kfc_game_tick_us")
    handling_buckets, handling_count, handling_sum = histogram(text, "kfc_move_handling_ms")
    return {
        "at": round(at, 1),
        "connections": value(text, "kfc_connections"),
        # Written once per tick, so a frozen value is itself the finding: the loop that
        # advances the games did not run between this sample and the last.
        "clients": value(text, "kfc_clients"),
        "active_games": value(text, "kfc_active_games"),
        "matches": value(text, "kfc_matches_total"),
        "logins": value(text, "kfc_logins_total"),
        "reaped": value(text, "kfc_games_reaped_total"),
        "bytes_out": value(text, "kfc_bytes_out_total"),
        "ticks": tick_count,
        "tick_mean_us": (tick_sum / tick_count) if tick_count else None,
        "tick_p99_us": percentile(tick_buckets, tick_count, 0.99),
        "handled_moves": handling_count,
        "handling_mean_ms": (handling_sum / handling_count) if handling_count else None,
        "handling_p99_ms": percentile(handling_buckets, handling_count, 0.99),
    }


def start_server(db_path: Path):
    """A fresh ``--solo`` server on its own accounts file, once it answers /healthz."""
    environment = dict(os.environ, DATABASE_URL=str(db_path))
    process = subprocess.Popen(
        [sys.executable, "server_main.py", "--solo"],
        cwd=REPO, env=environment,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(75):
        try:
            urllib.request.urlopen(f"{OBS}/healthz", timeout=1)
            return process
        except OSError:
            time.sleep(0.2)
    process.terminate()
    raise RuntimeError("the server never became healthy")


def sampler(samples, stop, started, every):
    """Scrape every ``every`` seconds until ``stop`` is set, ignoring a missed scrape."""
    while not stop.wait(every):
        try:
            samples.append(sample(scrape(), time.monotonic() - started))
        except OSError:
            pass


def bot_field(output: str, label: str):
    """One of the load bot's reported numbers, by the label it prints it under."""
    match = re.search(rf"^{re.escape(label)}\s+([\d.,]+)", output, re.M)
    return float(match.group(1).replace(",", "")) if match else None


def latency(output: str, label: str):
    """One of the load bot's latency percentiles."""
    match = re.search(rf"^\s+{re.escape(label)}\s+<?=?\s*([\d.]+)", output, re.M)
    return float(match.group(1)) if match else None


def one_run(index: int, connections: int, seconds: float, move_every: float, every: float):
    """Start a server, drive the bots at it, and take the server's pulse throughout."""
    db_path = Path(tempfile.gettempdir()) / f"kfc-osc-{index}-{int(time.time())}.db"
    server = start_server(db_path)
    samples, stop = [], threading.Event()
    started = time.monotonic()
    thread = threading.Thread(target=sampler, args=(samples, stop, started, every), daemon=True)
    try:
        bot = subprocess.Popen(
            [sys.executable, "tools/loadbot.py",
             "--connections", str(connections), "--seconds", str(seconds),
             "--move-every", str(move_every)],
            cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        thread.start()
        output = bot.communicate(timeout=seconds * 3 + 120)[0]
        stop.set()
        thread.join(timeout=10)
        try:
            final = sample(scrape(), time.monotonic() - started)
        except OSError:
            final = None
    finally:
        stop.set()
        server.terminate()
        try:
            server.wait(timeout=20)
        except subprocess.TimeoutExpired:  # pragma: no cover  (a wedged server)
            server.kill()
        db_path.unlink(missing_ok=True)

    peak = max(samples, key=lambda one: one["ticks"] or 0) if samples else {}
    refused = re.search(r"\((\d+) refused\)", output)
    return {
        "run": index,
        "seated": bot_field(output, "seated in a game"),
        "games": bot_field(output, "games"),
        "moves": bot_field(output, "moves played"),
        "moves_per_s": bot_field(output, "moves per second"),
        "refused": float(refused.group(1)) if refused else None,
        "p50_ms": latency(output, "p50"),
        "p90_ms": latency(output, "p90"),
        "p99_ms": latency(output, "p99"),
        "mean_ms": latency(output, "mean"),
        "bytes_per_conn_per_s": bot_field(output, "  per connection per second"),
        "ticks": peak.get("ticks"),
        "tick_mean_us": peak.get("tick_mean_us"),
        "final": final,
        "samples": samples,
        "bot": output,
    }


def spread(name: str, values) -> str:
    """One row of the summary: the range, and then every run that made it."""
    values = [one for one in values if one is not None]
    if not values:
        return f"{name:<24}—"
    low, high = min(values), max(values)
    ratio = f"{high / low:.1f}x" if low else "inf"
    return (f"{name:<24}{low:>10,.0f}{statistics.median(values):>10,.0f}{high:>10,.0f}"
            f"{ratio:>10}   " + " ".join(f"{one:,.0f}" for one in values))


def main() -> None:
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    connections = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
    seconds = float(sys.argv[3]) if len(sys.argv) > 3 else 60
    move_every = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0
    every = float(sys.argv[5]) if len(sys.argv) > 5 else 5.0

    results = []
    for index in range(1, runs + 1):
        print(f"\n{'=' * 72}\nrun {index}/{runs} — {connections} connections, {seconds:g}s"
              f"\n{'=' * 72}", flush=True)
        result = one_run(index, connections, seconds, move_every, every)
        print(result["bot"], flush=True)
        results.append(result)
        Path("oscillation.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(f"\n{'=' * 72}\nthe spread over {runs} runs\n{'=' * 72}")
    print(f"{'':<24}{'min':>10}{'median':>10}{'max':>10}{'max/min':>10}   every run")
    for name, key in (("seated", "seated"), ("moves", "moves"), ("ticks", "ticks"),
                      ("move p50 ms", "p50_ms"), ("move mean ms", "mean_ms"),
                      ("games (seated/2)", "games"), ("tick mean us", "tick_mean_us")):
        print(spread(name, [result[key] for result in results]))


if __name__ == "__main__":
    main()
