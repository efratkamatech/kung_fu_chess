"""MessageBus: publish/subscribe between the gateway and the shard, near or far.

:class:`~kfchess.bus.event_bus.EventBus` carries typed events between objects inside one
process. This carries text between *services* — the gateway that holds the sockets and
the shard that runs the games. They share a name and a shape and nothing else: an event
is a Python object delivered to a function in the same interpreter, and a message is a
string that may have to cross a network to a process on another machine.

Two implementations. **Which one is in play is a deployment decision, not a test
decision** — that is the point of there being two:

- :class:`InProcessMessageBus` delivers synchronously, in the calling thread, in the
  order things were published. It runs the solo server, where one process holds both
  ends and a message is a function call; and it runs the tests, which wire a whole
  gateway to a whole shard, play a move, and assert on what came back — no sockets, no
  event loop, no waiting. The same trick the ``Lobby`` tests use with their ``send``
  callbacks, one layer further out.
- :class:`NatsMessageBus` is the one for the split deployment: a thin skin over
  ``nats-py``, kept thin enough that "this is only I/O" is an honest claim rather than
  an excuse.

Neither is the "real" one. A game played over the first is played by the same shard,
under the same rules, as a game played over the second.

Subject matching follows NATS: ``*`` matches exactly one token and ``>`` matches the rest
of the subject, both only on whole dot-separated tokens. Both implementations use the
same :func:`matches`, so a subscription that works in one process works over NATS.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

# A subscriber is handed the concrete subject a message arrived on as well as the
# payload: a wildcard subscription such as ``conn.gw1.>`` is answered by many subjects,
# and which one it was is usually the routing information the handler needs.
Handler = Callable[[str, str], None]

_MATCH_ONE = "*"
_MATCH_REST = ">"


def matches(pattern: str, subject: str) -> bool:
    """Whether ``subject`` is delivered to a subscription on ``pattern``.

    ``*`` stands for exactly one token, ``>`` for one or more tokens and only at the end.
    A pattern with no wildcards matches only itself.
    """
    pattern_tokens = pattern.split(".")
    subject_tokens = subject.split(".")
    for index, token in enumerate(pattern_tokens):
        if token == _MATCH_REST:
            return index < len(subject_tokens)  # ">" needs something left to match
        if index >= len(subject_tokens):
            return False
        if token != _MATCH_ONE and token != subject_tokens[index]:
            return False
    return len(pattern_tokens) == len(subject_tokens)


class InProcessMessageBus:
    """A message bus for one process: same interface, delivered inline, no network.

    Handlers run during :meth:`publish`, in subscription order, so a chain of services
    wired through one of these behaves like a single synchronous call — which makes a
    test of the whole path deterministic and instant, and makes the solo server a
    gateway and a shard talking to each other at the speed of a function call.
    """

    def __init__(self) -> None:
        self._subscriptions: List[Tuple[str, Handler, Optional[str]]] = []
        # Everything ever published, in order, for a test that wants to assert on the
        # wire itself rather than on what some handler did with it.
        self.published: List[Tuple[str, str]] = []
        # Which member of each queue group is next in turn, so the same group does not
        # hand everything to whoever subscribed first.
        self._next_in_group: Dict[str, int] = {}

    def publish(self, subject: str, payload: str) -> None:
        """Deliver ``payload`` to every matching subscription, one per queue group."""
        self.published.append((subject, payload))
        for _, handler, _ in self._chosen(subject):
            handler(subject, payload)

    def _chosen(self, subject: str):
        """Who receives this message: everyone matching, but one member per queue group.

        Whose turn it is rotates. Always calling the first member would make "they share
        the work" a claim no test could catch out — one shard would answer everything and
        the second would look idle rather than broken.
        """
        matching = [
            subscription
            for subscription in self._subscriptions
            if matches(subscription[0], subject)
        ]
        for group in {sub[2] for sub in matching if sub[2] is not None}:
            members = [sub for sub in matching if sub[2] == group]
            turn = self._next_in_group.get(group, 0) % len(members)
            self._next_in_group[group] = turn + 1
            matching = [sub for sub in matching if sub[2] != group]
            matching.insert(0, members[turn])
        return matching

    def subscribe(
        self, pattern: str, handler: Handler, queue_group: Optional[str] = None
    ) -> None:
        """Call ``handler(subject, payload)`` for every message matching ``pattern``.

        Subscriptions sharing a ``queue_group`` share the *work* instead of each getting
        a copy: exactly one of them is called per message. That is what lets a second
        shard exist at all — every shard subscribes to the same "somebody deal with this
        connection" subject, and without a group each would run its own copy of every
        game that followed.
        """
        self._subscriptions.append((pattern, handler, queue_group))

    def unsubscribe(self, pattern: str) -> None:
        """Drop every subscription on ``pattern``; unknown patterns are ignored.

        A gateway calls this when the last connection it held in a room goes away: with
        nobody left to forward that room's traffic to, continuing to receive it would be
        pure waste — and at ten thousand rooms per shard, waste that adds up.
        """
        self._subscriptions = [
            subscription
            for subscription in self._subscriptions
            if subscription[0] != pattern
        ]

    def sent_to(self, pattern: str) -> List[str]:
        """Every payload published to a subject matching ``pattern`` (a test helper)."""
        return [
            payload for subject, payload in self.published if matches(pattern, subject)
        ]


class NatsMessageBus:  # pragma: no cover  (a live NATS server; the in-process one stands in)
    """The real bus: publish and subscribe over NATS, and nothing else.

    **The interface stays synchronous**, which is the whole point. ``nats-py`` is
    coroutine-based, and if that leaked out then the gateway and the shard would have to
    be written in ``async def`` and could no longer be driven by a test that just calls
    them — the thin-async-shell split this repository's coverage depends on would be
    gone. So every call here only *records* what to do, and one coroutine, :meth:`run`,
    performs them in the order they were asked for. It is the same shape as the
    per-connection queue in ``gateway.app.serve``, one layer further out.

    Deliberately the thinnest possible skin: everything that decides *what* to publish
    and *what to do* with a message lives in the gateway and the shard, and both of those
    are tested against :class:`InProcessMessageBus`.
    """

    def __init__(self, connection, pending) -> None:
        """Wrap a connected ``nats-py`` client and an ``asyncio.Queue`` (see
        :func:`connect`); the queue is taken as an argument so that nothing here has to
        import asyncio to be constructed."""
        self._connection = connection
        self._pending = pending
        self._handlers: Dict[str, Handler] = {}
        self._subscriptions: Dict[str, list] = {}

    def publish(self, subject: str, payload: str) -> None:
        self._pending.put_nowait(("publish", subject, payload))

    def subscribe(
        self, pattern: str, handler: Handler, queue_group: Optional[str] = None
    ) -> None:
        self._handlers[pattern] = handler
        self._pending.put_nowait(("subscribe", pattern, queue_group or ""))

    def unsubscribe(self, pattern: str) -> None:
        self._pending.put_nowait(("unsubscribe", pattern, ""))

    async def run(self) -> None:
        """Perform the queued operations, forever and in order."""
        while True:
            operation, subject, payload = await self._pending.get()
            if operation == "publish":
                await self._connection.publish(subject, payload.encode("utf-8"))
            elif operation == "subscribe":
                await self._open(subject, payload)
            else:
                for subscription in self._subscriptions.pop(subject, []):
                    await subscription.unsubscribe()

    async def _open(self, pattern: str, queue_group: str) -> None:
        handler = self._handlers[pattern]

        async def deliver(message) -> None:
            handler(message.subject, message.data.decode("utf-8"))

        # NATS calls it `queue`; an empty one means an ordinary fan-out subscription.
        subscription = await self._connection.subscribe(
            pattern, queue=queue_group, cb=deliver
        )
        self._subscriptions.setdefault(pattern, []).append(subscription)


async def connect(url: str) -> NatsMessageBus:  # pragma: no cover  (opens a socket)
    """Connect to the NATS server at ``url`` and wrap it as a bus.

    ``nats`` is imported here rather than at module scope so that everything else —
    including every test — imports and runs without the client library installed.
    """
    import asyncio

    import nats

    return NatsMessageBus(await nats.connect(url), asyncio.Queue())
