"""The Auth service: take a password off the bus, check it, and answer the shard.

Deliberately almost nothing. It has no session, no cache and no memory of who asked it
what a moment ago — the whole design rests on that, because a service that remembered
something could not be replicated by starting another one.

It reaches into :mod:`kfchess.server.user_store` rather than owning its own accounts
table, and that is on purpose: there is exactly one accounts database, and the shard
still reads it to record a result and write a new rating. Two spellings of the same
schema is how they come to disagree. What moved here is the *hashing*, not the data.
"""

from __future__ import annotations

import logging
from time import perf_counter

from kfchess.bus import subjects
from kfchess.bus.envelope import AuthResult, decode_auth_request, encode
from kfchess.bus.message_bus import MessageBus
from kfchess.obs.measures import LOGIN_MS, LOGINS
from kfchess.server.user_store import UserStore

_log = logging.getLogger(__name__)  # silent until configure_logging runs


class AuthService:
    """Answers "is this her, and what is she rated" — and holds nothing in between."""

    def __init__(self, bus: MessageBus, users: UserStore) -> None:
        self._bus = bus
        self._users = users
        # A queue group, so a login is answered once however many replicas are listening.
        # Without it every replica would hash every password: the cost would be shared by
        # nobody and multiplied by everybody.
        self._bus.subscribe(
            subjects.AUTH_REQUEST, self._on_request, queue_group=subjects.AUTH_GROUP
        )

    def _on_request(self, subject: str, payload: str) -> None:
        """One password to check, from a shard that is not waiting for the answer."""
        request = decode_auth_request(payload)
        started = perf_counter()
        rating = self._users.register_or_login(request.username, request.password)
        LOGIN_MS.observe((perf_counter() - started) * 1000)
        LOGINS.inc()
        _log.info(
            "login %s", "accepted" if rating is not None else "refused",
            extra={"user": request.username, "shard": request.shard_id},
        )
        self._bus.publish(
            subjects.shard_auth(request.shard_id),
            encode(AuthResult(request.conn_id, request.username, rating)),
        )


async def serve(nats_url: str = None) -> None:  # pragma: no cover  (NATS + a listener)
    """Answer logins until cancelled. The thinnest shell in the repository.

    There is no clock here and no games to advance: the whole service is one subscription
    and the coroutine that pumps it.
    """
    from kfchess.bus.message_bus import connect
    from kfchess.config import NATS_URL, OBS_PORT
    from kfchess.obs.endpoint import serve_observability

    serve_observability(OBS_PORT)
    bus = await connect(nats_url or NATS_URL)
    AuthService(bus, UserStore())
    await bus.run()
