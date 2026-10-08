"""Real ApiHandler payload behavior; MCDR host is a spy, network is loopback."""
import asyncio
import json
from types import SimpleNamespace

import pytest
import websockets

from queqiao_mcdr.api_handler import ApiHandler
from queqiao_mcdr.command_payload import component_json
from queqiao_mcdr.websocket_client import WebSocketClient


class Logger:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


def host():
    result = SimpleNamespace(logger=Logger(), commands=[])
    result.execute = result.commands.append
    return result


def configuration():
    return SimpleNamespace(server_name="Payload integration", access_token="test-only")


@pytest.mark.asyncio
@pytest.mark.parametrize("message", [
    42, True, [], {"translate": "unsupported"},
    {"text": "x", "bold": "false"},
    {"text": "x", "clickEvent": {"action": "unknown", "value": "x"}},
    {"text": "x", "hoverEvent": {"action": "show_text", "contents": "x", "value": "y"}},
    {"type": "image", "data": {"url": "http://example.invalid"}},
    "x" * 17000,
])
async def test_unsupported_or_oversized_components_never_reach_execute(message):
    server = host()
    api = ApiHandler(server, configuration())
    response = await api.handle_api_request("send_actionbar", {"message": message}, "bounded")
    assert response["status"] == "failed"
    assert response["echo"] == "bounded"
    assert server.commands == []


def test_component_depth_and_count_are_bounded():
    nested = {"text": "leaf"}
    for _ in range(10):
        nested = {"text": "", "extra": [nested]}
    with pytest.raises(ValueError):
        component_json(nested)
    with pytest.raises(ValueError):
        component_json(["x"] * 129)


@pytest.mark.asyncio
async def test_legacy_and_native_components_keep_supported_metadata_and_json_escaping():
    server = host()
    api = ApiHandler(server, configuration())
    legacy = {"type": "text", "data": {
        "text": 'say "hello"', "color": "green", "bold": True,
        "click_event": {"action": "suggest_command", "value": '/say "hi"'},
        "hover_event": {"action": "show_text", "value": {"text": "line\nnext"}},
    }}
    native = {"text": " extra", "extra": [{"text": "!"}]}
    response = await api.handle_api_request("send_actionbar", {"message": [legacy, native]}, "component")
    assert response["status"] == "ok"
    data = json.loads(server.commands[0].removeprefix("title @a actionbar "))
    assert data[0]["text"] == 'say "hello"'
    assert data[0]["bold"] is True and data[0]["color"] == "green"
    assert data[0]["clickEvent"]["value"] == '/say "hi"'
    assert data[0]["hoverEvent"]["value"]["text"] == "line\nnext"
    assert data[1]["extra"][0]["text"] == "!"
    assert "\n" not in server.commands[0]


@pytest.mark.asyncio
async def test_partial_submission_is_not_reported_as_atomic_execution_or_retried():
    server = host()
    attempts = []
    def execute(command):
        attempts.append(command)
        if len(attempts) == 2:
            raise RuntimeError("test transport rejected a submission")
        server.commands.append(command)
    server.execute = execute
    api = ApiHandler(server, configuration())
    result = await api.handle_api_request("send_title", {"title": "Hello", "subtitle": "World"}, "partial")
    assert result["status"] == "failed"
    assert result["data"] == {"submitted_commands": 1, "execution_confirmed": False, "partial_or_unknown": True}
    assert len(attempts) == 2 and len(server.commands) == 1
    assert list(api.command_audit)[-1]["status"] == "failed"


@pytest.mark.asyncio
async def test_audit_is_bounded_and_contains_no_message_body():
    server = host()
    api = ApiHandler(server, configuration())
    for _ in range(105):
        result = await api.send_actionbar({"message": "private synthetic message"}, "audit")
        assert result["status"] == "ok"
    assert len(api.command_audit) == 100
    assert "private synthetic message" not in json.dumps(list(api.command_audit))
    assert all(not item["execution_confirmed"] for item in api.command_audit)


@pytest.mark.asyncio
@pytest.mark.parametrize("name,data", [([], {}), ("send_title", []), ("execute", {"command": "list"})])
async def test_api_surface_remains_limited_and_invalid_envelopes_are_safe(name, data):
    server = host()
    api = ApiHandler(server, configuration())
    response = await api.handle_api_request(name, data, "envelope")
    assert response["status"] == "failed" and response["echo"] == "envelope"
    assert server.commands == []
    assert "execute" not in api.api_methods


@pytest.mark.asyncio
async def test_actual_websocket_client_dispatches_into_actual_api_handler():
    server = host()
    api = ApiHandler(server, configuration())
    responses = asyncio.Queue()
    async def peer(socket):
        await socket.send(json.dumps({"api": "send_title", "data": {"title": 'real "frame"\ntext', "stay": 0}, "echo": "valid"}))
        await responses.put(json.loads(await socket.recv()))
        await socket.send(json.dumps({"api": "send_title", "data": {"title": "bad", "fadein": "1\nstop"}, "echo": "invalid"}))
        await responses.put(json.loads(await socket.recv()))
        await socket.close()
    listener = await websockets.serve(peer, "127.0.0.1", 0)
    port = listener.sockets[0].getsockname()[1]
    client = WebSocketClient(server, f"ws://127.0.0.1:{port}/test", api, configuration(), reconnect_interval=30)
    task = asyncio.create_task(client.start())
    try:
        valid = await asyncio.wait_for(responses.get(), 3)
        invalid = await asyncio.wait_for(responses.get(), 3)
        assert valid["status"] == "ok" and valid["echo"] == "valid"
        assert invalid["status"] == "failed" and invalid["echo"] == "invalid"
        assert len(server.commands) == 2
        assert json.loads(server.commands[1].removeprefix("title @a title "))["text"] == 'real "frame"\ntext'
        assert all("\n" not in command for command in server.commands)
    finally:
        await client.stop()
        await asyncio.gather(task, return_exceptions=True)
        listener.close()
        await listener.wait_closed()
