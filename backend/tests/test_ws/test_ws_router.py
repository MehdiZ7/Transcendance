"""Tests for the static registry (router.py)."""

import pytest

from app.core.realtime.router import Router, RouterError
from app.core.realtime.topics import Topic

CONVERSATION = Topic("conversation", "42")


# ── registration and resolution ───────────────────────────────────


def test_topic_authorizer_is_resolved(router: Router):
    @router.topic("conversation")
    def allow(principal, topic):
        return True

    assert router.authorizer_for(CONVERSATION) is allow
    assert router.knows_topic(CONVERSATION)


def test_authorizer_is_shared_by_every_id_of_the_kind(router: Router):
    @router.topic("conversation")
    def allow(principal, topic):
        return True

    assert router.authorizer_for(Topic("conversation", "1")) is allow
    assert router.authorizer_for(Topic("conversation", "999")) is allow
    assert router.authorizer_for(Topic("conversation")) is allow


def test_message_handler_is_resolved(router: Router):
    @router.message("message.create")
    def handle(context, frame):
        return None

    assert router.handler_for("message.create") is handle
    assert router.knows_type("message.create")


def test_on_subscribe_is_resolved(router: Router):
    @router.topic("conversation")
    def allow(principal, topic):
        return True

    @router.on_subscribe("conversation")
    def initial(context, topic):
        return []

    assert router.on_subscribe_for(CONVERSATION) is initial


def test_decorator_returns_the_function_untouched(router: Router):
    def allow(principal, topic):
        return True

    assert router.topic("conversation")(allow) is allow


def test_tables_are_independent(router: Router):
    @router.topic("conversation")
    def allow(principal, topic):
        return True

    @router.message("conversation")
    def handle(context, frame):
        return None

    assert router.authorizer_for(CONVERSATION) is allow
    assert router.handler_for("conversation") is handle
    assert router.on_subscribe_for(CONVERSATION) is None


# ── unknown keys default to refusal ───────────────────────────────


def test_unknown_kind_resolves_to_none(router: Router):
    assert router.authorizer_for(Topic("secret", "1")) is None
    assert not router.knows_topic(Topic("secret", "1"))


def test_unknown_type_resolves_to_none(router: Router):
    assert router.handler_for("message.nope") is None
    assert not router.knows_type("message.nope")


def test_on_subscribe_is_optional(router: Router):
    @router.topic("conversation")
    def allow(principal, topic):
        return True

    assert router.on_subscribe_for(CONVERSATION) is None


def test_known_kinds_and_types(router: Router):
    router.topic("conversation")(lambda p, t: True)
    router.topic("presence")(lambda p, t: True)
    router.message("message.create")(lambda c, f: None)

    assert router.known_kinds() == {"conversation", "presence"}
    assert router.known_types() == {"message.create"}


# ── registration mistakes ─────────────────────────────────────────


def test_duplicate_authorizer_raises(router: Router):
    router.topic("conversation")(lambda p, t: True)

    with pytest.raises(RouterError, match="duplicate"):
        router.topic("conversation")(lambda p, t: False)


def test_duplicate_handler_raises(router: Router):
    router.message("message.create")(lambda c, f: None)

    with pytest.raises(RouterError, match="duplicate"):
        router.message("message.create")(lambda c, f: None)


def test_duplicate_on_subscribe_raises(router: Router):
    router.on_subscribe("conversation")(lambda c, t: [])

    with pytest.raises(RouterError, match="duplicate"):
        router.on_subscribe("conversation")(lambda c, t: [])


def test_duplicate_error_names_the_existing_function(router: Router):
    def first(principal, topic):
        return True

    router.topic("conversation")(first)

    with pytest.raises(RouterError, match="first"):
        router.topic("conversation")(lambda p, t: True)


@pytest.mark.parametrize("reserved", ["subscribe", "unsubscribe", "resume", "ping"])
def test_control_types_cannot_be_registered_as_messages(router: Router, reserved: str):
    with pytest.raises(RouterError, match="control frame"):
        router.message(reserved)(lambda c, f: None)


@pytest.mark.parametrize("register", ["topic", "on_subscribe", "message"])
def test_async_callables_are_rejected(router: Router, register: str):
    async def callback(a, b):
        return True

    with pytest.raises(RouterError, match="synchronous"):
        getattr(router, register)("conversation")(callback)


def test_rejected_async_callable_is_not_registered(router: Router):
    async def allow(principal, topic):
        return True

    with pytest.raises(RouterError):
        router.topic("conversation")(allow)

    assert router.authorizer_for(CONVERSATION) is None


def test_empty_keys_are_rejected(router: Router):
    with pytest.raises(RouterError):
        router.topic("")(lambda p, t: True)
    with pytest.raises(RouterError):
        router.message("")(lambda c, f: None)


# ── freeze ────────────────────────────────────────────────────────


def test_freeze_blocks_registration(router: Router):
    router.topic("conversation")(lambda p, t: True)
    router.freeze()

    with pytest.raises(RouterError, match="frozen"):
        router.topic("presence")(lambda p, t: True)
    with pytest.raises(RouterError, match="frozen"):
        router.message("message.create")(lambda c, f: None)


def test_freeze_keeps_resolution_working(router: Router):
    allow = lambda p, t: True  # noqa: E731
    router.topic("conversation")(allow)
    router.freeze()

    assert router.frozen
    assert router.authorizer_for(CONVERSATION) is allow


def test_freeze_is_idempotent(router: Router):
    router.freeze()
    router.freeze()

    assert router.frozen


# ── startup check ─────────────────────────────────────────────────


def test_check_passes_on_a_consistent_router(router: Router):
    router.topic("conversation")(lambda p, t: True)
    router.on_subscribe("conversation")(lambda c, t: [])

    router.check()


def test_check_catches_a_hook_without_authorizer(router: Router):
    router.on_subscribe("conversation")(lambda c, t: [])

    with pytest.raises(RouterError, match="conversation"):
        router.check()


# ── isolation between instances ───────────────────────────────────


def test_routers_do_not_share_state():
    a, b = Router(), Router()
    a.topic("conversation")(lambda p, t: True)

    assert b.authorizer_for(CONVERSATION) is None
    assert b.known_kinds() == frozenset()


# ── Topic ─────────────────────────────────────────────────────────


def test_topic_is_hashable_and_comparable():
    assert Topic("conversation", "42") == Topic("conversation", "42")
    assert Topic("conversation", "42") != Topic("conversation", "43")
    assert len({Topic("c", "1"), Topic("c", "1"), Topic("c", "2")}) == 2


def test_topic_str_is_readable():
    assert str(Topic("conversation", "42")) == "conversation:42"
    assert str(Topic("presence")) == "presence"