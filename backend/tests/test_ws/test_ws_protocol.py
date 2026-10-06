"""Tests for the realtime wire format (protocol.py)."""

import json
import re

import pytest
from pydantic import ValidationError

from app.core.realtime.protocol import (
    ClientMessage,
    ErrorFrame,
    EventFrame,
    Ping,
    PongFrame,
    Resume,
    SessionFrame,
    Subscribe,
    Unsubscribe,
    dump_server_frame,
    parse_client_frame,
    parse_server_frame,
)

ISO_UTC_MS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")

# Client -> Server: valid frames


@pytest.mark.parametrize(
    ("raw", "expected_cls"),
    [
        (
            {"type": "subscribe", "topic_kind": "conversation", "topic_id": "42"},
            Subscribe,
        ),
        ({"type": "subscribe", "topic_kind": "presence"}, Subscribe),
        (
            {"type": "unsubscribe", "topic_kind": "conversation", "topic_id": "42"},
            Unsubscribe,
        ),
        ({"type": "resume", "session": "tok", "last_seq": 417}, Resume),
        ({"type": "resume", "session": "tok", "last_seq": 0}, Resume),
        ({"type": "ping"}, Ping),
        (
            {
                "type": "message.create",
                "topic_kind": "conversation",
                "topic_id": "42",
                "ref": "r1",
                "payload": {"text": "salut"},
            },
            ClientMessage,
        ),
    ],
)
def test_parse_client_frame_valid(raw, expected_cls):
    frame = parse_client_frame(json.dumps(raw))

    assert type(frame) is expected_cls
    dumped = frame.model_dump()
    assert {key: dumped[key] for key in raw} == raw


def test_parse_client_frame_accepts_bytes():
    frame = parse_client_frame(b'{"type": "ping"}')

    assert isinstance(frame, Ping)


def test_client_message_defaults():
    frame = parse_client_frame('{"type": "typing", "topic_kind": "conversation"}')

    assert isinstance(frame, ClientMessage)
    assert frame.topic_id is None
    assert frame.ref is None
    assert frame.payload == {}


# Client -> Server : Invalid Frames
@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("not json", id="invalid-json"),
        pytest.param("", id="empty"),
        pytest.param("[]", id="json-array"),
        pytest.param("null", id="json-null"),
        pytest.param("42", id="json-number"),
        pytest.param('{"topic_kind": "conversation"}', id="missing-type"),
        pytest.param('{"type": "", "topic_kind": "conversation"}', id="empty-type"),
        pytest.param('{"type": null, "topic_kind": "conversation"}', id="null-type"),
        pytest.param('{"type": "subscribe"}', id="subscribe-missing-topic"),
        pytest.param(
            '{"type": "subscribe", "topic_kind": ""}', id="subscribe-empty-topic"
        ),
        pytest.param('{"type": "unsubscribe"}', id="unsubscribe-missing-topic"),
        pytest.param('{"type": "resume", "last_seq": 1}', id="resume-missing-session"),
        pytest.param(
            '{"type": "resume", "session": "tok"}', id="resume-missing-last-seq"
        ),
        pytest.param(
            '{"type": "resume", "session": "tok", "last_seq": -1}',
            id="resume-negative-seq",
        ),
        pytest.param(
            '{"type": "resume", "session": "tok", "last_seq": "abc"}',
            id="resume-non-int-seq",
        ),
        # strict mode: no coercion
        pytest.param(
            '{"type": "resume", "session": "tok", "last_seq": true}',
            id="resume-bool-seq",
        ),
        pytest.param(
            '{"type": "resume", "session": "tok", "last_seq": "1"}',
            id="resume-str-seq",
        ),
        pytest.param(
            '{"type": "resume", "session": "tok", "last_seq": 1.0}',
            id="resume-float-seq",
        ),
        pytest.param('{"type": "ping", "extra": 1}', id="extra-field"),
        pytest.param('{"type": "message.create"}', id="message-missing-topic"),
        pytest.param(
            '{"type": "message.create", "topic_kind": "c", "payload": []}',
            id="message-payload-not-object",
        ),
    ],
)
def test_parse_client_frame_invalid_returns_bad_request(raw):
    frame = parse_client_frame(raw)

    assert isinstance(frame, ErrorFrame)
    assert frame.code == "bad_request"
    assert frame.detail


def test_bad_request_detail_points_to_field():
    frame = parse_client_frame('{"type": "subscribe"}')

    assert isinstance(frame, ErrorFrame)
    assert "topic_kind" in frame.detail


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # ref and topic are echoed back when the frame is invalid elsewhere
        (
            (
                '{"type": "chat.send", "topic_kind": "conversation", "topic_id": "42",'
                ' "ref": "r1", "payload": 1}'
            ),
            {"ref": "r1", "topic_kind": "conversation", "topic_id": "42"},
        ),
        (
            '{"type": "subscribe", "topic_kind": "conversation", "topic_id": 42}',
            {"ref": None, "topic_kind": "conversation", "topic_id": None},
        ),
        # topic_id alone would break ErrorFrame's own validator
        (
            '{"type": "chat.send", "topic_id": "42", "ref": "r1"}',
            {"ref": "r1", "topic_kind": None, "topic_id": None},
        ),
        # non-string or empty values are not echoed
        (
            '{"type": "chat.send", "topic_kind": "", "ref": 5}',
            {"ref": None, "topic_kind": None, "topic_id": None},
        ),
        ("not json", {"ref": None, "topic_kind": None, "topic_id": None}),
        ('["r1"]', {"ref": None, "topic_kind": None, "topic_id": None}),
    ],
)
def test_bad_request_echoes_ref_and_topic(raw, expected):
    frame = parse_client_frame(raw)

    assert isinstance(frame, ErrorFrame)
    assert frame.code == "bad_request"
    assert {k: getattr(frame, k) for k in expected} == expected


@pytest.mark.parametrize("reserved", ["subscribe", "unsubscribe", "resume", "ping"])
def test_client_message_rejects_control_types(reserved):
    with pytest.raises(ValidationError, match="reserved"):
        ClientMessage(type=reserved, topic_kind="conversation")


# Server -> Client : SessionFrame


@pytest.mark.parametrize(
    "kwargs",
    [
        {"resumed": True, "from_seq": 418},
        {"resumed": True, "from_seq": 0},
        {"resumed": False, "reason": "expired"},
        {"resumed": False, "reason": "gap"},
        {"resumed": False, "reason": "new"},
    ],
)
def test_session_frame_valid(kwargs):
    frame = SessionFrame(session="tok", **kwargs)

    assert frame.type == "session"


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"resumed": True}, id="resumed-without-from-seq"),
        pytest.param(
            {"resumed": True, "from_seq": 1, "reason": "gap"},
            id="resumed-with-reason",
        ),
        pytest.param({"resumed": False}, id="not-resumed-without-reason"),
        pytest.param(
            {"resumed": False, "reason": "gap", "from_seq": 1},
            id="not-resumed-with-from-seq",
        ),
        pytest.param({"resumed": False, "reason": "other"}, id="unknown-reason"),
        pytest.param({"resumed": True, "from_seq": -1}, id="negative-from-seq"),
    ],
)
def test_session_frame_invalid(kwargs):
    with pytest.raises(ValidationError):
        SessionFrame(session="tok", **kwargs)


def test_session_frame_requires_non_empty_session():
    with pytest.raises(ValidationError):
        SessionFrame(session="", resumed=False, reason="new")


# Server -> Client : ErrorFrame


@pytest.mark.parametrize(
    "code",
    ["forbidden", "unknown_topic", "unknown_type", "rate_limited", "bad_request"],
)
def test_error_frame_known_codes(code):
    assert ErrorFrame(code=code).code == code


def test_error_frame_unknown_code():
    with pytest.raises(ValidationError):
        ErrorFrame(code="teapot")


def test_error_frame_topic_id_requires_topic_kind():
    with pytest.raises(ValidationError, match="topic_kind"):
        ErrorFrame(code="forbidden", topic_id="42")


# Server -> Client : EventFrame


def test_event_frame_defaults():
    event = EventFrame(type="message.created", topic_kind="conversation")

    assert event.seq is None
    assert event.payload == {}
    assert ISO_UTC_MS.match(event.ts)


@pytest.mark.parametrize("reserved", ["session", "error", "pong"])
def test_event_frame_rejects_control_types(reserved):
    with pytest.raises(ValidationError, match="reserved"):
        EventFrame(type=reserved, topic_kind="conversation")


def test_with_seq_returns_copy_with_seq():
    event = EventFrame(type="message.created", topic_kind="conversation")

    numbered = event.with_seq(418)

    assert numbered.seq == 418
    assert event.seq is None
    assert numbered is not event
    assert numbered.ts == event.ts


def test_with_seq_shares_payload():
    event = EventFrame(
        type="message.created",
        topic_kind="conversation",
        payload={"items": [1]},
    )

    numbered = event.with_seq(1)

    # Shallow copy on purpose: one copy per subscriber must stay cheap
    assert numbered.payload is event.payload


def test_with_seq_rejects_negative():
    event = EventFrame(type="message.created", topic_kind="conversation")

    with pytest.raises(ValueError):
        event.with_seq(-1)


def test_pong_frame_has_timestamp():
    assert ISO_UTC_MS.match(PongFrame().ts)


# Immutability


@pytest.mark.parametrize(
    ("frame", "field", "value"),
    [
        (Subscribe(topic_kind="conversation"), "topic_kind", "other"),
        (EventFrame(type="x", topic_kind="c"), "seq", 1),
        (ErrorFrame(code="forbidden"), "code", "bad_request"),
    ],
)
def test_frames_are_frozen(frame, field, value):
    with pytest.raises(ValidationError):
        setattr(frame, field, value)


# Serialization && Deserialization


def test_dump_omits_none_fields():
    frame = SessionFrame(session="tok", resumed=True, from_seq=418)

    assert json.loads(dump_server_frame(frame)) == {
        "type": "session",
        "session": "tok",
        "resumed": True,
        "from_seq": 418,
    }


def test_dump_event_frame_shape():
    event = EventFrame(
        type="message.created",
        topic_kind="conversation",
        topic_id="42",
        payload={"text": "salut"},
    ).with_seq(418)

    data = json.loads(dump_server_frame(event))

    assert data == {
        "type": "message.created",
        "topic_kind": "conversation",
        "topic_id": "42",
        "payload": {"text": "salut"},
        "seq": 418,
        "ts": event.ts,
    }


def test_dump_event_frame_requires_seq():
    event = EventFrame(type="message.created", topic_kind="conversation")

    with pytest.raises(ValueError, match="seq"):
        dump_server_frame(event)


@pytest.mark.parametrize(
    "frame",
    [
        pytest.param(
            SessionFrame(session="tok", resumed=True, from_seq=418),
            id="session-resumed",
        ),
        pytest.param(
            SessionFrame(session="tok", resumed=False, reason="expired"),
            id="session-new",
        ),
        pytest.param(
            ErrorFrame(
                code="forbidden",
                topic_kind="conversation",
                topic_id="42",
                ref="r1",
                detail="nope",
            ),
            id="error",
        ),
        pytest.param(PongFrame(), id="pong"),
        pytest.param(
            EventFrame(
                type="message.created",
                topic_kind="conversation",
                topic_id="42",
                payload={"text": "salut"},
            ).with_seq(418),
            id="event",
        ),
    ],
)
def test_server_frame_roundtrip(frame):
    parsed = parse_server_frame(dump_server_frame(frame))

    assert type(parsed) is type(frame)
    assert parsed == frame


def test_parse_server_frame_raises_on_invalid():
    with pytest.raises(ValidationError):
        parse_server_frame('{"type": "session", "session": "tok"}')


def test_error_frame_from_client_is_serializable():
    error = parse_client_frame("not json")

    data = json.loads(dump_server_frame(error))

    assert data["type"] == "error"
    assert data["code"] == "bad_request"
