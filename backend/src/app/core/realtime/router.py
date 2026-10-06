"""Static registry: which callable answers for a topic kind or a message type.

Filled by decorators at import time, frozen at startup, never mutated afterwards.
"""

import inspect
from typing import Any, Callable, TypeVar

from app.core.realtime.protocol import CLIENT_CONTROL_TYPES
from app.core.realtime.topics import Topic


__all__ = ["Authorizer", "Handler", "OnSubscribe", "Router", "RouterError"]

Authorizer = Callable[..., Any]
OnSubscribe = Callable[..., Any]
Handler = Callable[..., Any]


F = TypeVar("F", bound=Callable[..., Any])


class RouterError(RuntimeError):
    """Registration mistake. Always raised at import or startup, never after"""


class Router:
    def __init__(self) -> None:
        self._authorizers: dict[str, Authorizer] = {}
        self._on_subscribe: dict[str, OnSubscribe] = {}
        self._handlers: dict[str, Handler] = {}
        self._frozen = False

    def topic(self, kind: str) -> Callable[[F], F]:
        """Register the authorizer for a topic kind."""
        return self._register(self._authorizers, "authorizer", kind, self._check_kind)

    def on_subscribe(self, kind: str) -> Callable[[F], F]:
        """Register the hook returning the events to send right after a successful subscribe (initial state). Optional."""
        return self._register(
            self._on_subscribe, "on_subscribe", kind, self._check_kind
        )

    def message(self, type_: str) -> Callable[[F], F]:
        """Register the handler for a business message type."""
        return self._register(self._handlers, "handler", type_, self._check_type)

    def _register(
        self, table: dict[str, Any], label: str, key: str, check: Callable[[str], None]
    ) -> Callable[[F], F]:
        if self._frozen:
            raise RouterError(f"router is frozen, cannot register {label} {key!r}")
        check(key)
        if key in table:
            existing = getattr(table[key], "__qualname__", table[key])
            raise RouterError(f"duplicate {label} for {key!r} (already {existing})")

        def decorator(func: F) -> F:
            # An async authorizer would return a coroutine, which is always truthy
            if inspect.iscoroutinefunction(func):
                raise RouterError(f"{label} for {key!r} must be synchronous")
            table[key] = func
            return func

        return decorator

    @staticmethod
    def _check_kind(kind: str) -> None:
        if not kind:
            raise RouterError("topic kind must not be empty")

    @staticmethod
    def _check_type(type_: str) -> None:
        if not type_:
            raise RouterError("message type must not be empty")
        if type_ in CLIENT_CONTROL_TYPES:
            raise RouterError(f"{type_!r} is a control frame, not a business message")

    def freeze(self) -> None:
        self._frozen = True

    @property
    def frozen(self) -> bool:
        return self._frozen

    # Resolution

    def authorizer_for(self, topic: Topic) -> Authorizer | None:
        return self._authorizers.get(topic.kind)

    def on_subscribe_for(self, topic: Topic) -> OnSubscribe | None:
        return self._on_subscribe.get(topic.kind)

    def handler_for(self, type_: str) -> Handler | None:
        return self._handlers.get(type_)

    def knows_topic(self, topic: Topic) -> bool:
        return topic.kind in self._authorizers

    def knows_type(self, type_: str) -> bool:
        return type_ in self._handlers

    def known_kinds(self) -> frozenset[str]:
        return frozenset(self._authorizers)

    def known_types(self) -> frozenset[str]:
        return frozenset(self._handlers)

    def check(self) -> None:
        orphans = sorted(set(self._on_subscribe) - set(self._authorizers))
        if orphans:
            raise RouterError(
                "on_subscribe without authorizer for: " + ", ".join(orphans)
            )
