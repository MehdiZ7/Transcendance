# Realtime

Server → browser push over one WebSocket per tab. Business code publishes an
event on a **topic**. Every session subscribed to that topic receives the
event, numbered, and can pick up where it left off after a reconnection. The
same socket carries the few messages the browser sends to the server, such as
typing indicators.

This package (`app/core/realtime/`) is the **generic core**: it knows nothing
about listings or users. The rest lives elsewhere:

| What | Where |
|---|---|
| The application's topics and message handlers | [`app/realtime_topics.py`](../../realtime_topics.py) |
| The application's single `router` and `hub` | [`app/realtime.py`](../../realtime.py) |
| The endpoint (`/api/ws`) and its authentication | [`app/api/ws.py`](../../api/ws.py) |
| The browser client | [`front/src/lib/realtime/`](../../../../../front/src/lib/realtime/README.md) |
| Backend overview, SSE stream, endpoint table | [`backend/README.md`](../../../../README.md#real-time) |

Everything described here is tested: `tests/test_ws/` covers the core and the
endpoint, and `tests/test_realtime_topics.py` covers the application topics.

## Contents

- [In this application](#in-this-application)
- [Layers](#layers)
- [Concurrency rule](#concurrency-rule)
- [Declaring a feature](#declaring-a-feature)
- [Publishing from business code](#publishing-from-business-code)
- [Wiring](#wiring)
- [Wire protocol (for the front)](#wire-protocol-for-the-front)
- [Delivery guarantees](#delivery-guarantees)
- [Settings](#settings)
- [Testing](#testing)

## In this application

### Topics

| Topic | Who may subscribe | Events |
|---|---|---|
| `user:<public_id>` | that user only | `message.created`, `friend_message.created`, `typing`, `friend_typing` |
| `presence` (no id) | any signed-in user | `presence.snapshot` on subscribe, `presence.changed` |

- **`message.created` and `friend_message.created`** are published by
  `POST /api/v1/conversations/{id}/messages` and
  `POST /api/v1/friends/{public_id}/messages`, after the commit, to **both**
  participants' `user:` topics. The sender is included so that their other
  tabs stay in sync. The payload is the same object the route returns.
- **`presence.snapshot`** carries `{"online": [<public_id>, …]}`: the users
  who currently have at least one socket open.
- **`presence.changed`** carries
  `{"user_id": "<public_id>", "status": "online" | "offline"}`. It is sent
  when a user's first socket opens and when their last one closes.
- **Presence and blocks.** Presence does not filter blocked users.

### Client messages

The client sends a message on its **own** `user:<public_id>` topic, which is
the only topic its authorizer allows.

| Type | Payload | Relayed to |
|---|---|---|
| `typing` | `{"conversation_id": int, "is_typing": bool}` | The other participant, if the sender takes part in the conversation, it is open, and neither side blocked the other |
| `friend_typing` | `{"friend_id": int, "is_typing": bool}` | The friend, if the friendship is accepted, the sender is in it, and neither side blocked the other |

- **Delivery.** The recipient gets the payload plus `user_id`, the sender's
  `public_id`, as an event of the same type on their own `user:` topic.
- **Silent drops.** A relay that fails its check is dropped silently, like an
  unknown conversation.
- **Invalid payloads.** A payload with the wrong types answers `bad_request`.
- **Why two types.** Friendship ids and conversation ids overlap, hence the
  separate `friend_*` names.

### Server-side revocation

`hub.registry.close_principal(public_id)` closes every session of a user.
Attached sockets are closed with `4001 revoked`, and detached sessions can no
longer be resumed. It is called by:

- `POST /api/auth/logout`;
- moderation, when a report is resolved by suspending or removing a user;
- the admin deletion of an account (`DELETE /api/v1/users/{public_id}`).

## Layers

```
 feature code ──publish──▶ Publisher ─▶ Backend ─▶ Broker ─▶ Session(s) ─▶ Connection ─▶ socket
                                                    ▲            │
                         Router (who may read what,  └─subscribe──┘
                         who handles which message)      Registry (sessions by token)
```

| Module | Role |
|---|---|
| `protocol.py` | Wire format: every frame is a strict Pydantic model |
| `topics.py` | `Topic(kind, id)`, the subscription key |
| `router.py` | Authorizers, `on_subscribe` hooks and message handlers, registered by decorator |
| `broker.py` | In-memory pub/sub: topic → sessions |
| `session.py` | One client: numbering, outbound queue, replay buffer, gap detection |
| `registry.py` | Live sessions by token: TTL, resume, takeover, per-user cap, revocation |
| `publisher.py` | The only entry point for feature code. `Backend` is the swappable transport (`LocalBackend` today) |
| `transport.py` | Drives one socket (asyncio), through the `Socket` port |
| `limiter.py` | Sliding-window rate limit per user, shared by all of the user's tabs |
| `hub.py` | Assembles the stack, and starts and stops the sweeper task |

Everything except `transport.py` and the hub's sweeper task is plain
synchronous Python, with no I/O.

## Concurrency rule

Everything runs on the event loop thread. The broker, the sessions and the
registry never `await`, so each call is atomic and nothing needs a lock. In
return:

- **Publish from the loop thread only.** An `async def` route or a background
  task is fine. From a sync `def` route, which runs in a worker thread, or
  from any other thread, go through
  `loop.call_soon_threadsafe(publisher.publish, ...)`.
- **Authorizers, `on_subscribe` hooks and handlers are synchronous.** The
  router refuses coroutines. They must be fast, with no database round trip,
  because they block every connection while they run. Check against data
  already in memory.
- **Checks that need the database.** Validate the payload synchronously, then
  start a task that does the lookup and publishes only if allowed. The
  `typing` and `friend_typing` handlers in `app/realtime_topics.py` follow
  this pattern.

## Declaring a feature

A topic kind needs an authorizer. `on_subscribe` hooks and message handlers
are optional. The application's real registrations are in
[`app/realtime_topics.py`](../../realtime_topics.py). The module that
registers them must be imported before the app starts, because `hub.start()`
freezes the router.

```python
from app.core.realtime.protocol import ClientMessage, EventFrame
from app.core.realtime.session import Session
from app.core.realtime.topics import Topic
from app.realtime import hub, router  # the app's single router

# `principal` is the user's public_id, as a string


@router.topic("user")
def own_topic_only(principal: str, topic: Topic) -> bool:
    """Called on every subscribe, and before every client message on this kind."""
    return topic.id == principal


@router.on_subscribe("presence")
def presence_snapshot(session: Session, topic: Topic) -> list[EventFrame]:
    """Initial state, sent right after a successful subscribe."""
    return [
        EventFrame(
            type="presence.snapshot",
            topic_kind=topic.kind,
            payload={"online": sorted(online_users)},
        )
    ]


@router.message("wave")
def wave(session: Session, frame: ClientMessage) -> None:
    """Business message from the client. Its topic is authorized first."""
    hub.publisher.publish("waved", Topic.of(frame), {"by": session.principal})
```

The router enforces these rules at import time, raising `RouterError`:

- one authorizer, hook or handler per key, with no duplicates;
- no async functions;
- message types cannot reuse a control type (`subscribe`, `unsubscribe`,
  `resume`, `ping`);
- `router.check()` refuses an `on_subscribe` hook without an authorizer;
- after `router.freeze()`, nothing more can be registered.

A handler that raises is logged, and the client receives
`{"type": "error", "code": "bad_request", "detail": "handler error", "ref": ...}`.
Handlers answer by publishing: there is no direct reply channel.

## Publishing from business code

Take the hub as a dependency, so that tests can swap it. For the usual case,
one event to a set of users, use the application helper `publish_to_users`,
which publishes on each user's `user:<public_id>` topic:

```python
from fastapi import Depends

from app.core.realtime.hub import Hub
from app.realtime import get_hub
from app.realtime_topics import publish_to_users


@router.post("/conversations/{conversation_id}/messages", status_code=201)
async def send_message(..., hub: Hub = Depends(get_hub)) -> MessageRead:
    ...
    await session.commit()
    read = _to_message_read(message, current_user.public_id)
    publish_to_users(
        hub,
        "message.created",                  # event type, free-form
        (str(buyer), str(seller)),          # recipients' public_ids
        read.model_dump(mode="json"),       # JSON-serializable payload
    )
    return read
```

The lower-level call is
`hub.publisher.publish(type, Topic(kind, id), payload)`.

- Call it **after** the database commit, so that a client never sees an event
  for data that was rolled back.
- A backend failure, or a payload that does not serialize to JSON, is logged
  and returns `0`: the request does not fail because of it. Programming
  errors do raise `ValueError`: a reserved event type (`session`, `error`,
  `pong`) or a preset `seq`.
- The return value is the number of local sessions reached. Don't build logic
  on it: with a multi-process backend, it would count only local sessions.
- Every recipient shares the same payload: never mutate it after publishing.
- Don't set `seq`: each session numbers events itself.

## Wiring

`app/main.py` starts the hub in the application lifespan:

- `hub.start()` checks and freezes the router, then sweeps expired sessions
  every `ws_session_ttl` seconds;
- `hub.stop()` stops the sweeper and closes every session.

`app/main.py` also mounts `app/api/ws.py` on `/api/ws`, **outside**
`/api/v1`, because nginx upgrades only `location /api/ws`.

### Authentication

Nothing reaches the realtime core unauthenticated. Before `accept()`, the
endpoint requires:

1. **An allowed `Origin`**: one of `ws_allowed_origins`, which defaults to the
   origin nginx serves, `https://SERVER_NAME[:HTTPS_PORT]`. A missing `Origin`
   is refused. This blocks cross-site WebSocket hijacking: the browser
   attaches the session cookie to any page's handshake.
2. **A valid session cookie**, decoded by the same code as the REST routes
   (`core/security.py`), naming an active user who is not deleted.

A refusal is a close before accept, so the client sees a `403` on the
handshake. The principal handed to the core is the user's `public_id`.

Once open, a socket:

- lives no longer than the JWT that opened it, and is closed with
  `4001 expired` when the JWT expires;
- is closed with `4001 revoked` when its user's sessions are revoked server
  side (see [Server-side revocation](#server-side-revocation)).

Every new socket authenticates again, so resuming a session needs a valid
cookie for the same user.

Not covered yet:

- **Authorizers** run when subscribing and before each client message, not on
  every event, so a right revoked later does not remove an existing
  subscription. In this application every per-user topic is one's own, so no
  such right exists today.
- **Other deactivations.** An account deactivated by any path other than the
  ones above (for example directly in the database) keeps its open sockets
  until the JWT expires.

## Wire protocol (for the front)

Frames are JSON text. Unknown fields are rejected, and types are strict:
`"1"` is not an int.

### Client → server

| Frame | Shape |
|---|---|
| Subscribe | `{"type": "subscribe", "topic_kind": "user", "topic_id": "<own public_id>"}` |
| Unsubscribe | `{"type": "unsubscribe", "topic_kind": "presence"}` |
| Resume | `{"type": "resume", "session": "<token>", "last_seq": 17}`, **first frame only** |
| Ping | `{"type": "ping"}` |
| Message | `{"type": "typing", "topic_kind": "user", "topic_id": "<own public_id>", "ref": "c-7", "payload": {"conversation_id": 42, "is_typing": true}}` |

- `topic_id` is optional, for global kinds such as `presence`.
- `ref` is chosen by the client and echoed in any error about that message.
- Subscribing twice to the same topic is a no-op, and does not send a second
  snapshot.
- Unsubscribing is silent.

### Server → client

| Frame | Shape |
|---|---|
| Session | `{"type": "session", "session": "<token>", "resumed": false, "reason": "new"}` or `{"type": "session", "session": "<token>", "resumed": true, "from_seq": 18}` |
| Event | `{"type": "message.created", "topic_kind": "user", "topic_id": "<public_id>", "payload": {...}, "seq": 18, "ts": "2026-09-24T10:00:00.000Z"}` |
| Error | `{"type": "error", "code": "forbidden", "topic_kind": "user", "topic_id": "<another user>", "ref": "c-7"}` |
| Pong | `{"type": "pong", "ts": "..."}` |

| Error code | Cause |
|---|---|
| `bad_request` | Invalid frame (`detail` names the field), a `resume` after the first frame, or a handler that raised |
| `forbidden` | The authorizer refused the topic |
| `unknown_topic` | No authorizer is registered for this topic kind |
| `unknown_type` | No handler is registered for this message type |
| `rate_limited` | More than `ws_rate_limit_per_10s` frames from this user in 10 seconds |
| `too_many_topics` | The session already holds `ws_max_topics_per_session` subscriptions |

- An error never closes the connection.
- Invalid frames count toward the rate limit.
- For an invalid frame, `ref`, `topic_kind` and `topic_id` are echoed on a
  best-effort basis.

### Client lifecycle

1. **Open.** Open the socket and send a first frame within
   `ws_handshake_timeout` seconds: a `resume` if you hold a token, otherwise
   anything (typically a `subscribe` or a `ping`).
2. **Store the token.** The first server frame is always `session`: store its
   token.
3. **Track `seq`.** Keep the last `seq` received. It counts **all events of
   the session**, not per topic, and has no holes.
4. **Keep the socket alive.** Send something at least every
   `ws_session_ttl` seconds (60), or the socket is closed as idle. The front
   sends a `ping` every 25 seconds (`heartbeatMs` in
   `front/src/lib/realtime/client.ts`).
5. **On a drop**, reconnect and send
   `{"type": "resume", "session": token, "last_seq": n}`:
   - `resumed: true`: the missed events follow, starting at `from_seq`.
     Subscriptions are still in place.
   - `resumed: false`: you got a fresh stream. `reason` is `expired` (token
     unknown, too old, or not yours) or `gap` (events were lost). Store the
     token from the frame, reset `seq`, **resubscribe**, and reload state over
     HTTP.
6. **One token per tab.** Keep the token per tab, in memory:
   `front/src/lib/realtime` keeps it for the page's lifetime.
   - Resuming a session that is still attached is a **takeover**: the new
     socket gets the session, and the old one is closed with `4000`. That is
     what makes a quick reconnect work when the server hasn't noticed yet
     that the old socket died.
   - Two tabs sharing a token would keep stealing it from each other.

### Close codes

| Code | Reason | Client should |
|---|---|---|
| 1000 | normal | stop |
| 1001 | `idle` (no client frame for `ws_session_ttl` seconds), or peer gone | reconnect and resume (after an idle close, resume usually answers `expired`) |
| 403 on the handshake | not logged in, or foreign `Origin` | log in again |
| 1008 | `no handshake`: no first frame within `ws_handshake_timeout` | fix the client: send a first frame right after opening |
| 1009 | frame larger than `ws_max_frame_bytes` | fix the client |
| 1011 | `internal error` | reconnect with backoff, and resume |
| 1012 | server restarting (sent by Uvicorn on shutdown) | reconnect with backoff. Sessions live in process memory, so resume answers `expired` |
| 1013 | `gap`: the client read too slowly and the queue overflowed | reconnect; resume will answer `gap` |
| 1013 | `too many sessions`: the user already has `ws_max_sessions_per_user` sockets open | retry later, with backoff |
| 4000 | `replaced`: another connection resumed this session | **stop**, don't reconnect (it would steal the session back) |
| 4001 | `revoked`: the user's sessions were closed server side (logout, suspension or removal by a moderator, deletion by an admin); or `expired`: the JWT expired | check the login (`/users/me`). Logged out: log in again. Still logged in: reconnect (resume answers `expired`: resubscribe and reload) |

## Delivery guarantees

- **Ordering.** Events on a session arrive in order, numbered `1, 2, 3…`,
  with no holes.
- **Detached sessions.** A detached session keeps collecting events until
  `ws_session_ttl` seconds after the client's **last frame**, not after the
  drop. With the front's 25-second heartbeat, that leaves at least 35 seconds
  to resume. A resume replays up to `ws_replay_max` missed events. Beyond
  that, it answers `gap`.
- **Slow clients.** A client that doesn't read fast enough overflows its
  queue (`ws_send_queue_max` frames). The connection is then closed with
  `1013` rather than delivering a stream with holes. Other clients are not
  slowed down.
- **Authorization** is checked when subscribing, not on every event. See
  [Authentication](#authentication).
- **Single process only** (`LocalBackend`): keep `UVICORN_WORKERS=1`. With
  several workers, swap the `Backend` (Redis pub/sub…); call sites don't
  change. Sessions, presence and replay buffers are lost on restart.

## Settings

From `app.core.config` (environment variables in upper case):

| Setting | Default | Used by |
|---|---|---|
| `ws_send_queue_max` | 100 | Session outbound queue |
| `ws_replay_max` | 100 | Session replay buffer (`0` = no replay) |
| `ws_session_ttl` | 60 | Detached-session lifetime (counted from the last client frame), idle timeout of an attached socket, sweeper period |
| `ws_handshake_timeout` | 10 | Delay for the first client frame |
| `ws_heartbeat_interval` | 25 | **Not read by the server.** Documents the front's ping period, which must stay below `ws_session_ttl` |
| `ws_rate_limit_per_10s` | 1000 | Client frames per user, all tabs together (`WindowLimiter` in the hub; `0` = no limit) |
| `ws_max_sessions_per_user` | 8 | Registry: the longest-idle detached session is evicted, otherwise `1013` |
| `ws_max_topics_per_session` | 50 | Session: `too_many_topics` error |
| `ws_max_frame_bytes` | 4096 | Uvicorn `--ws-max-size` (entrypoint) and the endpoint; close `1009` |
| `ws_allowed_origins` | `""` | Endpoint. Empty means `https://SERVER_NAME[:HTTPS_PORT]` |

## Testing

```bash
make test_ws                                        # from the repository root
POSTGRES_PASSWORD=x uv run pytest tests/test_ws     # the same, from backend/
```

The core and endpoint tests need no database. `POSTGRES_PASSWORD` is set only
because the settings refuse to build a database URL without one.
`tests/test_realtime_topics.py` does use the database, and runs with the
whole suite under `make test`.

`test_ws_endpoint.py` goes through the real app with Starlette's
`TestClient` (httpx's ASGI transport has no WebSocket support). It swaps the
user lookup (`get_user_loader`) and the hub (`get_hub`), so it needs no
database, while the Origin, cookie and JWT checks run for real.

`tests/test_ws/conftest.py` provides the test doubles:

- `RecordingSink` stands in for a session in broker tests;
- `FakeSocket` is an in-memory socket:
  - `feed(raw)` sends a client frame;
  - `hang_up()` drops the peer;
  - `gate.clear()` stalls sends, like a client that stopped reading;
- `settle()` lets every connection task run until it blocks again.

For a feature:

1. test the authorizer and the handlers directly, since they are plain
   functions;
2. add a case to `test_ws_stack_integration.py` if the flow matters end to
   end.

### Live bench

The live bench is a browser page against the real stack, with a demo router
and **no authentication**: the user comes from the query string, so it is for
**development only**.

```bash
make test_ws_live            # http://127.0.0.1:8765
make test_ws_live_shutdown   # stop it
```

Each card on the page is one tab: connect, subscribe, chat, drop and resume,
take over a session, flood the rate limiter, send raw frames. The side panel
publishes like business code would, sends bursts of events to force a gap,
and shows the registry and broker live.

The queue is small on purpose, so that a burst of 50 events gaps every
subscriber. The environment variables `PORT` (8765), `LIVE_QUEUE` (20),
`LIVE_REPLAY` (50) and `LIVE_TTL` (30 s) change the bench's limits.
