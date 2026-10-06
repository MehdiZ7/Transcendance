import logging
import time
from collections import deque
from collections.abc import Iterable
from typing import Callable


from app.core.config import settings
from app.core.realtime.broker import Broker
from app.core.realtime.protocol import (
    ClientMessage,
    ErrorFrame,
    EventFrame,
    Ping,
    PongFrame,
    Resume,
    AnyServerFrame,
    SessionFrame,
    Subscribe,
    Unsubscribe,
    dump_server_frame,
)
from app.core.realtime.router import Router
from app.core.realtime.topics import Topic

__all__ = ["Session", "SessionState"]

logger = logging.getLogger(__name__)

DEFAULT_QUEUE_LIMIT = settings.ws_send_queue_max
DEFAULT_REPLAY_LIMIT = settings.ws_replay_max
DEFAULT_MAX_TOPICS = settings.ws_max_topics_per_session

Limiter = Callable[[str, object], bool]
Clock = Callable[[], float]
Listener = Callable[[], None]


class SessionState:
    ATTACHED = "attached"
    DETACHED = "detached"
    CLOSED = "closed"


class Session:
    def __init__(
        self,
        id: str,
        principal: str,
        router: Router,
        broker: Broker,
        *,
        queue_limit: int = DEFAULT_QUEUE_LIMIT,
        replay_limit: int = DEFAULT_REPLAY_LIMIT,
        clock: Clock = time.monotonic,
        limiter: Limiter | None = None,
        max_topics: int = DEFAULT_MAX_TOPICS,
    ) -> None:
        self._id = id
        self.principal = principal
        self._router = router
        self._broker = broker
        self._queue_limit = queue_limit
        self._clock = clock
        self._limiter = limiter
        self._max_topics = max_topics

        self._queue: deque[AnyServerFrame] = deque()
        self._replay: deque[EventFrame] = deque(maxlen=replay_limit)
        self._seq = 0
        self._state = SessionState.DETACHED
        self._gapped = False
        self._last_seen = clock()
        self._listener: Listener | None = None
        self._epoch = 0

    # Identity and State

    @property
    def id(self) -> str:
        return self._id

    @property
    def state(self) -> str:
        return self._state

    @property
    def attached(self) -> bool:
        return self._state == SessionState.ATTACHED

    @property
    def closed(self) -> bool:
        return self._state == SessionState.CLOSED

    @property
    def gapped(self) -> bool:
        return self._gapped

    @property
    def last_seq(self) -> int:
        return self._seq

    @property
    def epoch(self) -> int:
        """Bumped on every attach (hello or resume). A connection remembers
        the epoch it attached with: once it differs, the session belongs to
        another connection."""
        return self._epoch

    @property
    def should_close(self) -> bool:
        """The transport hangs up on a gapped session"""
        return self._gapped

    def idle_for(self) -> float:
        """Seconds since the last client activity."""
        return self._clock() - self._last_seen

    def touch(self) -> None:
        self._last_seen = self._clock()

    # Lifecycle

    def hello(self, reason: str = "new") -> None:
        """First frame of a brand new session."""
        self._require_open()
        self._state = SessionState.ATTACHED
        self._epoch += 1
        self.touch()
        self._enqueue(SessionFrame(session=self._id, resumed=False, reason=reason))

    def resume(self, last_seq: int) -> bool:
        """Reattach an existing session and replay what follows `last_seq`.

        Handshake only: the transport picks the session by id, then calls this
        on a detached session."""
        self._require_open()
        if self.attached:
            raise RuntimeError(f"session {self._id} is already attached")
        self._epoch += 1
        self.touch()
        reason = self._resume_refusal(last_seq)
        if reason is not None:
            self._reset()
            self._state = SessionState.ATTACHED
            self._enqueue(SessionFrame(session=self._id, resumed=False, reason=reason))
            return False

        self._state = SessionState.ATTACHED
        self._enqueue(
            SessionFrame(session=self._id, resumed=True, from_seq=last_seq + 1)
        )
        for event in self._replay:
            if event.seq is not None and event.seq > last_seq:
                self._enqueue(event)
        return True

    def _resume_refusal(self, last_seq: int) -> str | None:
        if self._gapped:
            return "gap"
        if last_seq > self._seq:
            return "gap"
        missing = self._seq - last_seq
        if missing > len(self._replay):
            return "gap"
        # The session frame plus the replay must fit, or it would gap mid-replay
        if missing + 1 > self._queue_limit - len(self._queue):
            return "gap"
        return None

    def detach(self) -> None:
        """Socket lost, or taken over by another connection. The listener is
        woken so a connection still running notices it lost the session."""
        if self.closed:
            return
        self._state = SessionState.DETACHED
        self._queue.clear()
        self._notify()

    def close(self) -> None:
        """Definitive, drops every subscription in the broker.
        The attached connection, if any, is woken so it hangs up."""
        if self.closed:
            return
        self._state = SessionState.CLOSED
        self._broker.disconnect(self)
        self._queue.clear()
        self._replay.clear()
        self._notify()

    def _reset(self) -> None:
        self._broker.disconnect(self)
        self._queue.clear()
        self._replay.clear()
        self._seq = 0
        self._gapped = False

    def _require_open(self) -> None:
        if self.closed:
            raise RuntimeError(f"session {self._id} is closed")

    # Call by the broker
    def deliver(self, event: EventFrame) -> None:
        """Number the event, keep it for replay, queue it when attached."""
        if self.closed or self._gapped:
            return
        self._seq += 1
        numbered = event.with_seq(self._seq)
        self._replay.append(numbered)
        if self.attached:
            self._enqueue(numbered)

    # Queue

    def listen(self, listener: Listener) -> None:
        """Called whenever the transport has something to do: a frame was
        queued or the session gapped. One listener, the attached transport.
        Must not block or raise."""
        self._listener = listener

    def unlisten(self, listener: Listener) -> None:
        """Remove `listener` only if it is still the current one, so a
        connection that lost a takeover cannot mute its successor."""
        if self._listener == listener:
            self._listener = None

    def _notify(self) -> None:
        if self._listener is not None:
            self._listener()

    def _enqueue(self, frame: AnyServerFrame) -> None:
        if len(self._queue) >= self._queue_limit:
            self._mark_gap()
            return
        self._queue.append(frame)
        self._notify()

    def _mark_gap(self) -> None:
        if self._gapped:
            return
        self._gapped = True
        logger.warning(
            "session %s outbound queue full (%d), marking gap",
            self._id,
            self._queue_limit,
        )
        self._notify()

    def drain(self) -> list[AnyServerFrame]:
        frames = list(self._queue)
        self._queue.clear()
        return frames

    def drain_json(self) -> list[str]:
        return [dump_server_frame(frame) for frame in self.drain()]

    @property
    def pending(self) -> int:
        return len(self._queue)

    # Inbound frames
    def handle(self, frame: object) -> None:
        """Apply one already-parsed client frame."""
        self._require_open()
        self.touch()

        # Invalid frames count too, or they would be a free way around the limit
        if not self._allowed(frame):
            return self._enqueue(self._rate_limited(frame))
        if isinstance(frame, ErrorFrame):
            return self._enqueue(frame)
        if isinstance(frame, Ping):
            return self._enqueue(PongFrame())
        if isinstance(frame, Resume):
            # Resuming is the transport's job at handshake, never mid-stream
            return self._enqueue(
                ErrorFrame(code="bad_request", detail="resume only at handshake")
            )
        if isinstance(frame, Subscribe):
            return self._subscribe(frame)
        if isinstance(frame, Unsubscribe):
            return self._unsubscribe(frame)
        if isinstance(frame, ClientMessage):
            return self._message(frame)
        raise TypeError(f"unsupported frame: {type(frame).__name__}")

    def _allowed(self, frame: object) -> bool:
        return self._limiter is None or self._limiter(self.principal, frame)

    @staticmethod
    def _rate_limited(frame: object) -> ErrorFrame:
        # A subscribe has no ref: its topic tells the client which one failed
        if isinstance(frame, Subscribe):
            return ErrorFrame(
                code="rate_limited", topic_kind=frame.topic_kind, topic_id=frame.topic_id
            )
        return ErrorFrame(code="rate_limited", ref=getattr(frame, "ref", None))

    def _subscribe(self, frame: Subscribe) -> None:
        topic = Topic.of(frame)
        error = self._authorize(topic)
        if error is not None:
            return self._enqueue(error)

        current = self._broker.topics(self)
        if topic not in current and len(current) >= self._max_topics:
            return self._enqueue(
                ErrorFrame(
                    code="too_many_topics",
                    topic_kind=topic.kind,
                    topic_id=topic.id,
                    detail=f"at most {self._max_topics} topics per session",
                )
            )

        if not self._broker.subscribe(topic, self):
            return None  # already subscribed

        hook = self._router.on_subscribe_for(topic)
        if hook is None:
            return None
        for event in self._initial_events(hook, topic):
            self.deliver(event)
        return None

    def _initial_events(self, hook: Callable, topic: Topic) -> Iterable[EventFrame]:
        try:
            return list(hook(self, topic) or ())
        except Exception:
            logger.exception("on_subscribe failed for %s", topic)
            return ()

    def _unsubscribe(self, frame: Unsubscribe) -> None:
        self._broker.unsubscribe(Topic.of(frame), self)

    def _message(self, frame: ClientMessage) -> None:
        handler = self._router.handler_for(frame.type)
        if handler is None:
            return self._enqueue(
                ErrorFrame(
                    code="unknown_type",
                    topic_kind=frame.topic_kind,
                    topic_id=frame.topic_id,
                    ref=frame.ref,
                    detail=f"no handler for {frame.type}",
                )
            )

        error = self._authorize(Topic.of(frame))
        if error is not None:
            return self._enqueue(error.model_copy(update={"ref": frame.ref}))

        try:
            handler(self, frame)
        except Exception:
            logger.exception("handler %s failed", frame.type)
            self._enqueue(
                ErrorFrame(
                    code="bad_request",
                    topic_kind=frame.topic_kind,
                    topic_id=frame.topic_id,
                    ref=frame.ref,
                    detail="handler error",
                )
            )
        return None

    def _authorize(self, topic: Topic) -> ErrorFrame | None:
        authorizer = self._router.authorizer_for(topic)
        if authorizer is None:
            return ErrorFrame(
                code="unknown_topic", topic_kind=topic.kind, topic_id=topic.id
            )
        if not authorizer(self.principal, topic):
            return ErrorFrame(
                code="forbidden", topic_kind=topic.kind, topic_id=topic.id
            )
        return None

    def topics(self) -> frozenset[Topic]:
        return self._broker.topics(self)

    def __repr__(self) -> str:
        return (
            f"<Session {self._id} {self._state} seq={self._seq} "
            f"pending={len(self._queue)}{' gapped' if self._gapped else ''}>"
        )
