"""Roll the shards while people are playing, and see whether anybody lost a game.

    python tools/k8s_rolling.py [connections] [seconds] [warmup]

This is how S6's second exit criterion — *a rolling deploy completes with zero games
interrupted* — was measured. It starts a load against the cluster, waits for the games to
be running, restarts the shard Deployment, and prints what the cluster says while it
happens: how many games are live, how many sockets and clients (they must be equal), which
shard pods exist, and whether the safety net ever caught anything.

**``warmup`` is not a detail.** `loadbot.py` shuttles a knight back and forth for ever, so
its games never *end* — and a shard drains by finishing its games. Start the rollout with
more than the grace period of load still to run and the draining pods are killed at the
ceiling with their games live, which looks exactly like a failure and is not one. Real
games last thirty to ninety seconds; leaving less than the grace period after the rollout
is how that is imitated. The default leaves 110 seconds against a 120-second grace.

Needs the cluster from ``k8s/README.md`` up, with Prometheus on its NodePort.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROM = "http://localhost:30090/api/v1/query"
GATEWAY = "ws://localhost:30765"


def query(expression: str):
    """One instant PromQL query, summed, or ``None`` if nothing answered."""
    url = f"{PROM}?query={urllib.parse.quote(expression)}"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            result = json.load(response)["data"]["result"]
    except OSError:
        return None
    return sum(float(one["value"][1]) for one in result) if result else None


def shard_pods():
    """The shard pods and their phases, as short names."""
    out = subprocess.run(
        ["kubectl", "get", "pods", "-n", "kfchess", "-l", "app=shard", "--no-headers",
         "-o", "custom-columns=NAME:.metadata.name,STATUS:.status.phase"],
        capture_output=True, text=True,
    )
    return [line.split() for line in out.stdout.strip().splitlines() if line]


def snapshot(label: str) -> None:
    """One line of the record: what is live, and which pods are holding it."""
    names = ",".join(f"{name.split('-')[-1]}:{status}" for name, status in shard_pods())
    print(f"{label:<22} games={query('sum(kfc_active_games)')!s:<8} "
          f"clients={query('sum(kfc_clients)')!s:<8} "
          f"conns={query('sum(kfc_connections)')!s:<8} "
          f"reaped={query('sum(kfc_games_reaped_total)')!s:<6} pods=[{names}]", flush=True)


def main() -> None:
    connections = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 240
    warmup = int(sys.argv[3]) if len(sys.argv) > 3 else 150

    bot = subprocess.Popen(
        [sys.executable, "tools/loadbot.py", "--connections", str(connections),
         "--seconds", str(seconds), "--url", GATEWAY],
        cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    print(f"load: {connections} connections for {seconds}s, rolling at {warmup}s\n")
    for _ in range(warmup // 10):
        time.sleep(10)
        snapshot("warming up")

    print(f"\n--- restarting the shards, with {query('sum(kfc_active_games)')} games live "
          f"---\n", flush=True)
    subprocess.run(["kubectl", "rollout", "restart", "deployment/shard", "-n", "kfchess"],
                   check=True)

    started = time.monotonic()
    while time.monotonic() - started < seconds - warmup - 5:
        time.sleep(5)
        snapshot(f"t+{time.monotonic() - started:.0f}s")

    print("\n--- the rollout, as Kubernetes saw it ---", flush=True)
    subprocess.run(["kubectl", "rollout", "status", "deployment/shard", "-n", "kfchess",
                    "--timeout=180s"])

    output = bot.communicate()[0]
    print(output)
    seated = re.search(r"^seated in a game\s+(\d+)", output, re.M)
    moves = re.search(r"^moves played\s+(\d+)", output, re.M)
    print(f"seated {seated.group(1) if seated else '?'}, "
          f"moves {moves.group(1) if moves else '?'}, "
          f"games reaped {query('sum(kfc_games_reaped_total)')}")


if __name__ == "__main__":
    main()
