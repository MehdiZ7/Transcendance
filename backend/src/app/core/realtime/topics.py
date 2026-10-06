"""Subscription key shared by the router, the broker and the session.

A topic is the pair (kind, id) carried by frames as `topic_kind` / `topic_id`.
"""

from typing import NamedTuple, Protocol


class _HasTopic(Protocol):
    topic_kind: str
    topic_id: str | None


class Topic(NamedTuple):
    kind: str
    id: str | None = None

    @classmethod
    def of(cls, frame: _HasTopic) -> "Topic":
        return cls(frame.topic_kind, frame.topic_id)

    def __str__(self):
        return self.kind if self.id is None else f"{self.kind}:{self.id}"
