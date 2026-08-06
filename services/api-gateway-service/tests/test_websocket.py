"""The gateway's live event stream: the hub, and the WebSocket route.

The hub itself (``GatewayHub``/``GatewayStreamEvent``/``GatewaySubscriber``/
``frame_to_text``) is driven directly, entirely in-process -- no socket
needed to prove fan-out, the subscriber ceiling, or the slow-subscriber
drop.

**The route itself is driven by calling ``gateway_stream`` directly**,
against a duck-typed ``_FakeWebSocket``, rather than through a real
socket. ``httpx.ASGITransport`` buffers a response to completion (a
WebSocket stream has no natural end, so the async ``client``/``app``
fixtures would hang), and the usual alternative --
``starlette.testclient.TestClient`` -- is unusable in this repo's
current dependency lock: Starlette 1.3.1 emits
``StarletteDeprecationWarning: Using httpx with starlette.testclient is
deprecated; install httpx2 instead`` on import, and this project's own
``pyproject.toml`` turns every warning into a hard error
(``filterwarnings = ["error", ...]``) with no exemption for it, and
``httpx2`` is not one of this project's declared dependencies. Calling
the route function directly sidesteps both problems while still
exercising every one of its branches, including the one a real socket
cannot deterministically reach (an ASGI send failure that is *not* a
disconnect).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from shared_core.security.jwt import encode_token
from starlette.websockets import WebSocketDisconnect

from app.api.websocket_router import gateway_stream
from app.models.enums import GatewayStreamEventKind
from app.websocket.hub import GatewayHub, GatewayStreamEvent, frame_to_text

POLICY_VIOLATION = 1008
TRY_AGAIN_LATER = 1013


class TestGatewayStreamEvent:
    def test_as_dict_serialises_kind_org_and_timestamp(self) -> None:
        organization_id = uuid.uuid4()
        event = GatewayStreamEvent(
            kind=GatewayStreamEventKind.HEALTH_CHANGED,
            organization_id=organization_id,
            payload={"instance_url": "http://backend.test"},
        )
        as_dict = event.as_dict()
        assert as_dict["kind"] == "health_changed"
        assert as_dict["organization_id"] == str(organization_id)
        assert as_dict["payload"] == {"instance_url": "http://backend.test"}
        assert "T" in as_dict["at"]  # a real ISO-8601 timestamp

    def test_frame_to_text_renders_valid_json_matching_as_dict(self) -> None:
        event = GatewayStreamEvent(
            kind=GatewayStreamEventKind.HEARTBEAT, organization_id=uuid.uuid4()
        )
        assert json.loads(frame_to_text(event)) == event.as_dict()


class TestGatewayHub:
    def test_subscribe_tracks_counts_per_organization_and_overall(self) -> None:
        hub = GatewayHub()
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        hub.subscribe(org_a)
        hub.subscribe(org_a)
        hub.subscribe(org_b)

        assert hub.count_for(org_a) == 2
        assert hub.count_for(org_b) == 1
        assert hub.subscriber_count == 3

    def test_subscribe_carries_the_organization_and_user_id(self) -> None:
        hub = GatewayHub()
        org, user = uuid.uuid4(), uuid.uuid4()
        subscriber = hub.subscribe(org, user_id=user)
        assert subscriber.organization_id == org
        assert subscriber.user_id == user
        assert subscriber.subscriber_id

    def test_subscribe_refuses_once_the_ceiling_is_reached(self) -> None:
        hub = GatewayHub(max_subscribers=1)
        hub.subscribe(uuid.uuid4())
        with pytest.raises(RuntimeError, match="real-time subscriber limit"):
            hub.subscribe(uuid.uuid4())

    def test_unsubscribe_removes_and_is_safe_to_call_twice(self) -> None:
        hub = GatewayHub()
        org = uuid.uuid4()
        subscriber = hub.subscribe(org)
        hub.unsubscribe(subscriber)
        assert hub.count_for(org) == 0
        hub.unsubscribe(subscriber)  # does not raise
        assert hub.count_for(org) == 0

    def test_unsubscribing_one_of_several_leaves_the_others_in_place(self) -> None:
        # `unsubscribe`'s own `if not group:` only prunes the
        # organization's entry once its *last* subscriber leaves --
        # covered separately from `test_unsubscribe_removes_and_is_
        # safe_to_call_twice`, which only ever has one subscriber and so
        # always takes the "prune" branch.
        hub = GatewayHub()
        org = uuid.uuid4()
        first = hub.subscribe(org)
        hub.subscribe(org)
        hub.unsubscribe(first)
        assert hub.count_for(org) == 1

    def test_unsubscribe_of_an_unknown_organization_is_a_no_op(self) -> None:
        hub = GatewayHub()
        never_subscribed = hub.subscribe(uuid.uuid4())
        hub.unsubscribe(never_subscribed)
        # A second hub's own subscriber, unsubscribing from an org this
        # hub has never seen at all -- the `group is None` branch.
        other_hub = GatewayHub()
        other_hub.unsubscribe(never_subscribed)

    async def test_publish_delivers_only_to_the_matching_organization(self) -> None:
        hub = GatewayHub()
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        sub_a = hub.subscribe(org_a)
        hub.subscribe(org_b)

        delivered = await hub.publish(
            GatewayStreamEvent(kind=GatewayStreamEventKind.REQUEST_COMPLETED, organization_id=org_a)
        )
        assert delivered == 1
        assert sub_a.queue.qsize() == 1

    async def test_publish_to_an_organization_with_no_subscribers_delivers_to_none(self) -> None:
        hub = GatewayHub()
        delivered = await hub.publish(
            GatewayStreamEvent(kind=GatewayStreamEventKind.HEARTBEAT, organization_id=uuid.uuid4())
        )
        assert delivered == 0

    async def test_a_slow_subscriber_is_dropped_once_its_queue_is_full(self) -> None:
        hub = GatewayHub(queue_size=1)
        org = uuid.uuid4()
        hub.subscribe(org)
        assert hub.count_for(org) == 1

        event = GatewayStreamEvent(kind=GatewayStreamEventKind.QUOTA_EXCEEDED, organization_id=org)
        first = await hub.publish(event)
        assert first == 1
        assert hub.count_for(org) == 1  # still connected, just full

        second = await hub.publish(event)  # nothing has drained the queue
        assert second == 0
        assert hub.count_for(org) == 0  # dropped

    async def test_close_all_drops_every_subscriber_across_every_organization(self) -> None:
        hub = GatewayHub()
        hub.subscribe(uuid.uuid4())
        hub.subscribe(uuid.uuid4())
        await hub.close_all()
        assert hub.subscriber_count == 0

    async def test_stream_yields_a_real_event_before_its_heartbeat_timeout(self) -> None:
        hub = GatewayHub()
        org = uuid.uuid4()
        subscriber = hub.subscribe(org)
        event = GatewayStreamEvent(
            kind=GatewayStreamEventKind.CIRCUIT_BREAKER_OPENED, organization_id=org
        )
        await hub.publish(event)

        frames = hub.stream(subscriber, heartbeat_seconds=5)
        first = await asyncio.wait_for(anext(frames), timeout=5)
        assert first is event
        await frames.aclose()
        assert hub.count_for(org) == 0

    async def test_stream_emits_a_heartbeat_when_idle(self) -> None:
        hub = GatewayHub()
        subscriber = hub.subscribe(uuid.uuid4())
        frames = hub.stream(subscriber, heartbeat_seconds=0.05)
        first = await asyncio.wait_for(anext(frames), timeout=5)
        assert first.kind == GatewayStreamEventKind.HEARTBEAT
        assert first.payload["subscriber_id"] == subscriber.subscriber_id

        # Resuming past a heartbeat loops back to the top rather than
        # ending the stream -- a second consecutive idle period yields
        # a second heartbeat rather than closing.
        second = await asyncio.wait_for(anext(frames), timeout=5)
        assert second.kind == GatewayStreamEventKind.HEARTBEAT
        await frames.aclose()


def _token(user_id: uuid.UUID, jwt_keypair: tuple[str, str]) -> str:
    private_key, _public_key = jwt_keypair
    return encode_token({"sub": str(user_id)}, private_key=private_key)


class _FakeWebSocket:
    """A duck-typed stand-in for ``fastapi.WebSocket``.

    Exposes exactly what ``gateway_stream`` touches:
    ``query_params``/``app.state``, ``accept()``, ``send_text()``, and
    ``close()``. ``fail_after``/``fail_with`` let a test choose exactly
    which frame send fails and with what -- a real ``WebSocketDisconnect``
    (the client hung up) or anything else (the ASGI server itself
    misbehaving), the two branches ``gateway_stream`` tells apart.
    """

    def __init__(
        self,
        app: Any,
        token: str,
        *,
        fail_after: int | None = None,
        fail_with: type[BaseException] = RuntimeError,
    ) -> None:
        self.app = app
        self.query_params = {"token": token}
        self.sent: list[str] = []
        self.closed: tuple[int, str] | None = None
        self.accepted = False
        self._fail_after = fail_after
        self._fail_with = fail_with

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, text: str) -> None:
        self.sent.append(text)
        if self._fail_after is not None and len(self.sent) >= self._fail_after:
            raise self._fail_with()

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = (code, reason)


def _fake_app(
    hub: GatewayHub, public_key: str, *, heartbeat_seconds: float = 0.05
) -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(
            jwt_public_key=public_key,
            websocket_hub=hub,
            service_settings=SimpleNamespace(websocket_heartbeat_seconds=heartbeat_seconds),
        )
    )


class TestGatewayStreamRoute:
    async def test_no_token_is_closed_with_policy_violation(
        self, jwt_keypair: tuple[str, str]
    ) -> None:
        _private_key, public_key = jwt_keypair
        hub = GatewayHub()
        websocket = _FakeWebSocket(_fake_app(hub, public_key), "")

        await gateway_stream(websocket, uuid.uuid4())

        assert websocket.closed == (POLICY_VIOLATION, "Authentication required.")
        assert websocket.accepted is False
        assert hub.subscriber_count == 0

    async def test_a_forged_token_is_closed_with_policy_violation(
        self, jwt_keypair: tuple[str, str]
    ) -> None:
        _private_key, public_key = jwt_keypair
        hub = GatewayHub()
        websocket = _FakeWebSocket(_fake_app(hub, public_key), "forged")

        await gateway_stream(websocket, uuid.uuid4())

        assert websocket.closed == (POLICY_VIOLATION, "Authentication required.")

    async def test_the_subscriber_ceiling_refuses_the_handshake(
        self, jwt_keypair: tuple[str, str]
    ) -> None:
        private_key, public_key = jwt_keypair
        hub = GatewayHub(max_subscribers=0)
        token = _token(uuid.uuid4(), (private_key, public_key))
        websocket = _FakeWebSocket(_fake_app(hub, public_key), token)

        await gateway_stream(websocket, uuid.uuid4())

        assert websocket.closed is not None
        code, reason = websocket.closed
        assert code == TRY_AGAIN_LATER
        assert "subscriber limit" in reason
        assert websocket.accepted is False

    async def test_a_valid_connection_is_accepted_and_receives_a_heartbeat_frame(
        self, jwt_keypair: tuple[str, str]
    ) -> None:
        private_key, public_key = jwt_keypair
        hub = GatewayHub()
        organization_id = uuid.uuid4()
        token = _token(uuid.uuid4(), (private_key, public_key))
        # Fails after the first frame so the otherwise-endless stream
        # has somewhere to stop; the first frame itself, a genuine
        # successful `send_text`, is what this test is really checking.
        websocket = _FakeWebSocket(
            _fake_app(hub, public_key, heartbeat_seconds=0.02),
            token,
            fail_after=1,
            fail_with=WebSocketDisconnect,
        )

        await gateway_stream(websocket, organization_id)

        assert websocket.accepted is True
        frame = json.loads(websocket.sent[0])
        assert frame["kind"] == "heartbeat"
        assert frame["organization_id"] == str(organization_id)
        assert "at" in frame

    async def test_a_client_disconnect_is_handled_quietly_and_unsubscribes(
        self, jwt_keypair: tuple[str, str]
    ) -> None:
        private_key, public_key = jwt_keypair
        hub = GatewayHub()
        organization_id = uuid.uuid4()
        token = _token(uuid.uuid4(), (private_key, public_key))
        websocket = _FakeWebSocket(
            _fake_app(hub, public_key, heartbeat_seconds=0.02),
            token,
            fail_after=1,
            fail_with=WebSocketDisconnect,
        )

        await gateway_stream(websocket, organization_id)  # must not raise

        assert hub.count_for(organization_id) == 0
        assert websocket.closed is not None  # the `finally` still closes defensively

    async def test_a_non_disconnect_failure_is_logged_and_still_cleans_up(
        self, jwt_keypair: tuple[str, str]
    ) -> None:
        private_key, public_key = jwt_keypair
        hub = GatewayHub()
        organization_id = uuid.uuid4()
        token = _token(uuid.uuid4(), (private_key, public_key))
        websocket = _FakeWebSocket(
            _fake_app(hub, public_key, heartbeat_seconds=0.02),
            token,
            fail_after=1,
            fail_with=RuntimeError,
        )

        await gateway_stream(websocket, organization_id)  # must not raise

        assert websocket.accepted is True
        assert len(websocket.sent) == 1  # the heartbeat that triggered the failure
        assert hub.count_for(organization_id) == 0  # unsubscribed via the `finally`
        assert websocket.closed is not None  # `close()` in the `finally` succeeded
