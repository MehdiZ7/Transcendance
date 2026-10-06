"""Wire format for the realtime channel

Client -> Server : Subscribe | Unsubscribe | Resume | Ping | ClientMessage
Server -> Client : SessionFrame | ErrorFrame | PongFrame | EventFrame

This module only describes and validated messages.
"""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    TypeAdapter,
    ValidationError,
    model_validator,
)
from pydantic_core import from_json

__all__ = [
    "AnyClientFrame",
    "AnyServerFrame",
    "ClientFrame",
    "ClientMessage",
    "ErrorCode",
    "ErrorFrame",
    "EventFrame",
    "Ping",
    "PongFrame",
    "Resume",
    "ServerFrame",
    "SessionFrame",
    "Subscribe",
    "Unsubscribe",
    "dump_server_frame",
    "parse_client_frame",
    "parse_server_frame",
]

# Helpers


def _now() -> str:
    """UTC timestamp in millisecond suffixed with Z"""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _type_of(value: Any) -> Any:
    """Read `type` from raw input or a model"""
    if isinstance(value, dict):
        t = value.get("type")
    else:
        t = getattr(value, "type", None)
    return t if isinstance(t, str) else None


class Frame(BaseModel):
    """Our base model for websocket frame"""

    # Forbids reassigning attributes but does not freeze the content
    # strict: no coercion (e.g. `true` is not accepted as an int)
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


# Client -> Server

CLIENT_CONTROL_TYPES = frozenset({"subscribe", "unsubscribe", "resume", "ping"})


class Subscribe(Frame):
    type: Literal["subscribe"] = "subscribe"
    topic_kind: str = Field(min_length=1)
    topic_id: str | None = None


class Unsubscribe(Frame):
    type: Literal["unsubscribe"] = "unsubscribe"
    topic_kind: str = Field(min_length=1)
    topic_id: str | None = None


class Resume(Frame):
    type: Literal["resume"] = "resume"
    session: str = Field(min_length=1)
    last_seq: int = Field(ge=0)


class Ping(Frame):
    type: Literal["ping"] = "ping"


class ClientMessage(Frame):
    """Business action sent by the client. `ref` is chosen by the client
    and echoed back in any ErrorFrame about this message"""

    type: str = Field(min_length=1)
    topic_kind: str = Field(min_length=1)
    topic_id: str | None = None
    ref: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _not_control(self) -> Self:
        if self.type in CLIENT_CONTROL_TYPES:
            raise ValueError(f"'{self.type}' is reserved for control frames")
        return self


def _client_tag(value: Any) -> str:
    t = _type_of(value)
    return t if t in CLIENT_CONTROL_TYPES else "message"


ClientFrame = Annotated[
    Annotated[Subscribe, Tag("subscribe")]
    | Annotated[Unsubscribe, Tag("unsubscribe")]
    | Annotated[Resume, Tag("resume")]
    | Annotated[Ping, Tag("ping")]
    | Annotated[ClientMessage, Tag("message")],
    Discriminator(_client_tag),
]


# Server -> Client

SERVER_CONTROL_TYPES = frozenset({"session", "error", "pong"})

ErrorCode = Literal[
    "forbidden",
    "unknown_topic",
    "unknown_type",
    "rate_limited",
    "too_many_topics",
    "bad_request",
]


class SessionFrame(Frame):
    """Always the first frame sent after the handshake."""

    type: Literal["session"] = "session"
    session: str = Field(min_length=1)
    resumed: bool
    from_seq: int | None = Field(default=None, ge=0)
    reason: Literal["expired", "gap", "new"] | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.resumed:
            if self.from_seq is None:
                raise ValueError("resumed session requires from_seq")
            if self.reason is not None:
                raise ValueError("resumed session must not carry a reason")
        else:
            if self.reason is None:
                raise ValueError("non-resumed session requires a reason")
            if self.from_seq is not None:
                raise ValueError("non-resumed session must not carry from_seq")
        return self


class ErrorFrame(Frame):
    type: Literal["error"] = "error"
    code: ErrorCode
    topic_kind: str | None = None
    topic_id: str | None = None
    ref: str | None = None
    detail: str | None = None

    @model_validator(mode="after")
    def _check_topic(self) -> Self:
        if self.topic_id is not None and self.topic_kind is None:
            raise ValueError("topic_id requires topic_kind")
        return self


class PongFrame(Frame):
    """Answer to a client Ping."""

    type: Literal["pong"] = "pong"
    ts: str = Field(default_factory=_now)


class EventFrame(Frame):
    """Business event. `seq` is assigned by the session via `with_seq`
    not by the feature publishing the event"""

    type: str = Field(min_length=1)
    topic_kind: str = Field(min_length=1)
    topic_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    seq: int | None = Field(default=None, ge=0)
    ts: str = Field(default_factory=_now)

    @model_validator(mode="after")
    def _not_control(self) -> Self:
        if self.type in SERVER_CONTROL_TYPES:
            raise ValueError(f"'{self.type}' is reserved for control frame.")
        return self

    def with_seq(self, seq: int) -> Self:
        """Copy with `seq` set. Shallow copy: the payload is shared between
        copies, so it must not be mutated once the event is published"""
        if seq < 0:
            raise ValueError("seq must be >= 0")
        return self.model_copy(update={"seq": seq})


AnyServerFrame = SessionFrame | ErrorFrame | PongFrame | EventFrame
AnyClientFrame = Subscribe | Unsubscribe | Resume | Ping | ClientMessage


def _server_tag(value: Any) -> str:
    t = _type_of(value)
    return t if t in SERVER_CONTROL_TYPES else "event"


ServerFrame = Annotated[
    Annotated[SessionFrame, Tag("session")]
    | Annotated[ErrorFrame, Tag("error")]
    | Annotated[PongFrame, Tag("pong")]
    | Annotated[EventFrame, Tag("event")],
    Discriminator(_server_tag),
]


# Parsing / Serialization

_client_adapter: TypeAdapter[ClientFrame] = TypeAdapter(ClientFrame)
_server_adapter: TypeAdapter[ServerFrame] = TypeAdapter(ServerFrame)

# Fields echoed back from an invalid frame so the client can match the error
_ECHO_FIELDS = ("ref", "topic_kind", "topic_id")


def _echo_fields(raw: str | bytes) -> dict[str, str]:
    """Best effort: pull ref/topic_* out of an invalid frame.

    Only non-empty strings are kept, and topic_id only with topic_kind,
    so building the ErrorFrame can never fail"""
    try:
        data = from_json(raw)
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    fields = {k: v for k in _ECHO_FIELDS if isinstance(v := data.get(k), str) and v}
    if "topic_kind" not in fields:
        fields.pop("topic_id", None)
    return fields


def parse_client_frame(
    raw: str | bytes,
) -> Subscribe | Unsubscribe | Resume | Ping | ClientFrame | ErrorFrame:
    """Return the validated frame, or the ErrorFrame to send back.

    Never raises on bad input"""
    try:
        return _client_adapter.validate_json(raw)
    except ValidationError as exc:
        err = exc.errors(include_url=False, include_input=False)[0]
        loc = ".".join(str(part) for part in err["loc"])
        detail = f"{loc}: {err['msg']}" if loc else err["msg"]
        return ErrorFrame(code="bad_request", detail=detail, **_echo_fields(raw))


def parse_server_frame(
    raw: str | bytes,
) -> SessionFrame | ErrorFrame | PongFrame | EventFrame:
    """Validate a server frame for tests. Raises on bad input"""
    return _server_adapter.validate_json(raw)


def dump_server_frame(frame: SessionFrame | ErrorFrame | PongFrame | EventFrame) -> str:
    """Serialize a server frame for the wire.

    Raises if an EventFrame has no `seq`: it must go through `with_seq` first"""
    if isinstance(frame, EventFrame) and frame.seq is None:
        raise ValueError("EventFrame must have a seq before being sent")
    return frame.model_dump_json(exclude_none=True)
