"""``/metrics`` and ``/healthz``, on a thread, from the standard library.

The shard was built with no listener at all — "no ``websockets`` import anywhere beneath
it" was the point of splitting it off. Prometheus *pulls*, though, so something has to be
willing to answer, and the alternatives were worse: pushing metrics onto NATS would mean
inventing a collector, and a collector is a service that has to be up in order for anyone
to find out that a service is down.

So: :mod:`http.server` on a daemon thread. No dependency, nothing that could be mistaken
for the game's own traffic, and the same twenty lines serve the gateway and the solo
server as well. It is deliberately unable to do anything but answer two paths — the
handler has no route table to extend and no reference to the game — which is what keeps
"the shard has no API" true in every sense that mattered.

The two paths answer two different questions, and conflating them is a classic mistake:

- ``/healthz`` asks *are you alive* — is this process still able to answer at all. It is
  what an orchestrator restarts on, so it must not fail because something else is down.
  A liveness check that goes and asks the database is a liveness check that will
  eventually restart every healthy process in the cluster at the same moment.
- ``/metrics`` asks *how are you doing*. Nobody restarts anything over it.
"""

from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from kfchess.obs.metrics import REGISTRY

_log = logging.getLogger(__name__)  # silent until configure_logging runs

_METRICS_TYPE = "text/plain; version=0.0.4; charset=utf-8"


def answer(path: str):
    """What to reply to ``path``: ``(status, body, content type)``.

    The whole of the decision, as a function of a string, so it is tested by calling it.
    What is left in the handler below is a socket and the shape of an HTTP response —
    the same split every other listener in this repository is written to.
    """
    if path == "/healthz":
        # Nothing is consulted. This answers "is this process able to answer", and a
        # liveness check that asks the database is one that restarts the whole cluster
        # the moment the database hiccups.
        return 200, "ok\n", "text/plain; charset=utf-8"
    if path == "/metrics":
        return 200, REGISTRY.render(), _METRICS_TYPE
    return 404, "not found\n", "text/plain; charset=utf-8"


class _Handler(BaseHTTPRequestHandler):  # pragma: no cover  (a socket; see `answer`)
    """Two paths, no state, and no way to reach the game from here."""

    def do_GET(self) -> None:  # noqa: N802  (BaseHTTPRequestHandler's spelling)
        self._respond(*answer(self.path))

    def _respond(self, status: int, body: str, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, fmt, *args) -> None:
        """Swallow the default per-request line to stderr.

        A scrape every fifteen seconds from every replica would otherwise be most of what
        the log contains, and it says nothing: that monitoring is working is not news.
        """


def serve_observability(port: int) -> ThreadingHTTPServer:  # pragma: no cover (a socket)
    """Answer ``/metrics`` and ``/healthz`` on ``port``, on a thread, until the process ends.

    A daemon thread, so it cannot be the reason a shutdown hangs — there is nothing here
    worth finishing before exiting. Returns the server so a caller could close it; none
    does, because every caller runs until it is killed.
    """
    server = ThreadingHTTPServer(("", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True, name="obs").start()
    _log.info("observability listening", extra={"port": port})
    return server
