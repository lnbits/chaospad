import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from .. import teleprompter, views_api
from ..teleprompter import FRAME_TELEPROMPTER, TeleprompterState


def receive_state(ws):
    frame = ws.receive_bytes()
    assert frame[0] == FRAME_TELEPROMPTER
    return json.loads(frame[1:])


def command(ws, action):
    ws.send_bytes(bytes([FRAME_TELEPROMPTER]) + action.encode())


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(teleprompter.time, "monotonic", lambda: now[0])
    return now


@pytest.fixture
def client(monkeypatch):
    async def pad_exists(_pads_id):
        return True

    monkeypatch.setattr(views_api, "get_pads_by_id", pad_exists)
    app = FastAPI()
    app.include_router(views_api.chaospad_generic_router, prefix="/chaospad")
    with TestClient(app) as test_client:
        yield test_client
    assert not views_api.ROOMS
    assert not views_api.TELEPROMPTERS


def test_position_is_continuous_across_pause_resume_and_speed(clock):
    state = TeleprompterState()
    assert state.command(b"open")
    assert not state.running
    assert state.speed == 140
    state.command(b"play")
    clock[0] += 30
    assert state.current_position() == 70
    state.command(b"faster")
    assert state.current_position() == 70
    clock[0] += 30
    assert state.current_position() == 150
    state.command(b"pause")
    clock[0] += 600
    assert state.current_position() == 150
    state.command(b"play")
    clock[0] += 30
    assert state.current_position() == 230
    state.command(b"restart")
    assert state.current_position() == 0
    assert state.running
    state.command(b"cancel")
    assert not state.active
    assert not state.running
    assert state.current_position() == 0


def test_commands_are_bounded_and_cannot_set_arbitrary_state():
    state = TeleprompterState()
    assert not state.command(b"play")
    state.command(b"open")
    assert not state.command(b'{"position": -100, "speed": 99999}')
    for _ in range(30):
        state.command(b"faster")
    assert state.speed == 300
    for _ in range(30):
        state.command(b"slower")
    assert state.speed == 40


def test_shared_controls_join_reconnect_and_document_frames(client, clock):
    with client.websocket_connect("/chaospad/ws/pad") as desktop:
        assert not receive_state(desktop)["active"]
        command(desktop, "open")
        assert receive_state(desktop)["active"]
        command(desktop, "play")
        assert receive_state(desktop)["running"]
        clock[0] += 30
        with client.websocket_connect("/chaospad/ws/pad") as phone:
            joined = receive_state(phone)
            assert joined["running"]
            assert joined["position"] == 70
            command(desktop, "pause")
            assert receive_state(desktop) == receive_state(phone)
            clock[0] += 60
            command(phone, "sync")
            assert receive_state(phone)["position"] == 70
            command(phone, "slower")
            assert receive_state(desktop) == receive_state(phone)
            command(desktop, "play")
            assert receive_state(desktop) == receive_state(phone)
            document_frame = b"\x01unchanged-yjs-update"
            desktop.send_bytes(document_frame)
            assert phone.receive_bytes() == document_frame
        with client.websocket_connect("/chaospad/ws/pad") as reconnected:
            assert receive_state(reconnected)["speed"] == 120
            command(desktop, "cancel")
            cancelled = receive_state(desktop)
            assert cancelled == receive_state(reconnected)
            assert not cancelled["active"]


def test_rooms_are_isolated_and_sessions_end_when_everyone_leaves(client):
    with client.websocket_connect("/chaospad/ws/first") as first:
        receive_state(first)
        with client.websocket_connect("/chaospad/ws/second") as second:
            receive_state(second)
            command(first, "open")
            assert receive_state(first)["active"]
            command(second, "sync")
            assert not receive_state(second)["active"]
            command(first, "invalid")
            command(first, "sync")
            assert not receive_state(first)["running"]
    with client.websocket_connect("/chaospad/ws/first") as fresh:
        assert not receive_state(fresh)["active"]
