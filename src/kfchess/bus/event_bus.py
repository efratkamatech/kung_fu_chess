"""EventBus: a tiny publish/subscribe hub — the project's "announcement board".

Code that does something interesting *publishes* an event; code that cares *subscribes*
to a topic. Neither side knows about the other, so a new listener (a scoreboard, a
sound player, later a network broadcaster) joins by subscribing — no publisher changes.

Deliberately minimal: publishing is synchronous (each handler runs in turn, in
subscription order), an event with no subscribers is simply dropped, and there is no
ordering guarantee between topics. That is all the game needs; anything richer
(async delivery, priorities, unsubscribe) can be added when a caller actually requires
it.
"""

from __future__ import annotations

from typing import Callable, Dict, List

# A handler takes the published event object and returns nothing. The event is typed
# per topic (see ``bus/events.py``); ``object`` keeps the bus itself topic-agnostic.
Handler = Callable[[object], None]


class EventBus:
    """Routes published events to the handlers subscribed to their topic."""

    __slots__ = ("_handlers",)

    def __init__(self) -> None:
        # topic -> handlers, in the order they subscribed.
        self._handlers: Dict[str, List[Handler]] = {}

    def subscribe(self, topic: str, handler: Handler) -> None:
        """Register ``handler`` to be called for every event published on ``topic``."""
        self._handlers.setdefault(topic, []).append(handler)

    def publish(self, event) -> None:
        """Deliver ``event`` to each handler subscribed to ``event.topic``.

        The event carries its own topic (see ``bus/events.py``), so the caller never
        repeats the channel name. With no subscribers the event is silently dropped.
        """
        for handler in self._handlers.get(event.topic, ()):
            handler(event)
