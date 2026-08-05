"""Fill the cluster up and watch it grow, then stop and watch it shrink.

    python tools/k8s_autoscale.py [connections] [seconds] [after]

S6's third exit criterion — *the HPA scales shards up under load and back down
afterwards*. ``after`` has to be longer than the autoscaler's scale-down stabilisation
window (300 s in ``k8s/60-autoscale.yaml``) or the answer is always "it did not scale
down"; it is deliberately slow, because removing a shard means draining it.

The autoscalers read ``kfc_active_games`` and ``kfc_connections`` through
``custom.metrics.k8s.io``, so this is also the end-to-end test of the metrics adapter: a
column of question marks means the adapter is not serving, not that nothing happened.

Needs the cluster from ``k8s/README.md`` up.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GATEWAY = "ws://localhost:30765"

COLUMNS = ("NAME:.metadata.name,"
           "NOW:.status.currentMetrics[0].pods.current.averageValue,"
           "TARGET:.spec.metrics[0].pods.target.averageValue,"
           "REPLICAS:.status.currentReplicas,"
           "DESIRED:.status.desiredReplicas")


def autoscalers():
    """Both HorizontalPodAutoscalers, as Kubernetes reports them."""
    out = subprocess.run(
        ["kubectl", "get", "hpa", "-n", "kfchess", "--no-headers", "-o",
         f"custom-columns={COLUMNS}"],
        capture_output=True, text=True,
    )
    return {parts[0]: parts[1:] for parts in
            (line.split() for line in out.stdout.strip().splitlines() if line)}


def pods(label: str) -> str:
    """How many pods of one kind are running, out of how many exist."""
    out = subprocess.run(
        ["kubectl", "get", "pods", "-n", "kfchess", "-l", f"app={label}", "--no-headers"],
        capture_output=True, text=True,
    )
    lines = [line for line in out.stdout.strip().splitlines() if line]
    return f"{sum(1 for line in lines if ' Running ' in f' {line} ')}/{len(lines)}"


def line(label: str) -> None:
    """One line of the record, for both autoscalers at once."""
    reported = autoscalers()
    shard = reported.get("shard", ["?"] * 4)
    gateway = reported.get("gateway", ["?"] * 4)
    print(f"{label:<14} shard: {shard[0]:>7}/{shard[1]:<5} "
          f"replicas {shard[2]}->{shard[3]:<3} pods {pods('shard'):<6} | "
          f"gateway: {gateway[0]:>6}/{gateway[1]:<5} "
          f"replicas {gateway[2]}->{gateway[3]:<3} pods {pods('gateway')}", flush=True)


def main() -> None:
    connections = int(sys.argv[1]) if len(sys.argv) > 1 else 800
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 240
    after = int(sys.argv[3]) if len(sys.argv) > 3 else 420

    print(f"load: {connections} connections for {seconds}s, then {after}s of watching\n")
    line("before")

    bot = subprocess.Popen(
        [sys.executable, "tools/loadbot.py", "--connections", str(connections),
         "--seconds", str(seconds), "--url", GATEWAY],
        cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    started = time.monotonic()
    while time.monotonic() - started < seconds:
        time.sleep(15)
        line(f"load t+{time.monotonic() - started:.0f}s")

    print("\n--- the load bot's own report ---")
    print(bot.communicate()[0], flush=True)

    print("--- and now, with nobody playing ---", flush=True)
    started = time.monotonic()
    while time.monotonic() - started < after:
        time.sleep(20)
        line(f"idle t+{time.monotonic() - started:.0f}s")


if __name__ == "__main__":
    main()
