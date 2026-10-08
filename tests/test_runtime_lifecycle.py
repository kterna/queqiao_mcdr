"""Ownership, retry policy and configuration integration on real event loops/threads."""
import asyncio
import copy
import importlib
import json
import socket
import threading
from types import SimpleNamespace

import pytest
import websockets

from queqiao_mcdr.api_handler import ApiHandler
from queqiao_mcdr.config import Config
from queqiao_mcdr.endpoint_runtime import EndpointRuntime
from queqiao_mcdr.event_handler import EventHandler
from queqiao_mcdr.websocket_client import WebSocketClient

plugin = importlib.import_module("queqiao_mcdr")
client_module = importlib.import_module("queqiao_mcdr.websocket_client")


class Logger:
    def __init__(self):
        self.messages = []

    def __getattr__(self, name):
        return lambda message, *args, **kwargs: self.messages.append(str(message))


def host(tmp_path=None):
    result = SimpleNamespace(logger=Logger(), commands=[])
    result.execute = result.commands.append
    if tmp_path is not None:
        result.get_data_folder = lambda: str(tmp_path)
    return result


def settings(**values):
    return SimpleNamespace(server_name="Lifecycle test", access_token="test-only", **values)


@pytest.fixture
def isolated_plugin(tmp_path, monkeypatch):
    server = host(tmp_path)
    cfg = Config(server)
    pending_peer = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    pending_peer.bind(("127.0.0.1", 0))
    pending_peer.listen(8)
    candidate = copy.deepcopy(cfg.config)
    candidate["mode"] = "client"
    candidate["websocket"].update(
        url=f"ws://127.0.0.1:{pending_peer.getsockname()[1]}/owned-fixture",
        auto_start=False, reconnect_interval=30,
    )
    cfg.install(candidate)
    api = ApiHandler(server, cfg)
    handler = EventHandler(server, cfg, api)
    for key, value in {
        "_runtime": None, "websocket_server": None, "websocket_client": None,
        "ws_thread": None, "loop": None, "config": cfg, "api_handler": api,
        "event_handler": handler, "command_handler": None,
    }.items():
        monkeypatch.setattr(plugin, key, value)
    try:
        yield server, cfg, handler
    finally:
        assert plugin.on_unload(server)
        pending_peer.close()


def test_plugin_repeated_start_stop_owns_and_closes_each_loop(isolated_plugin):
    server, _, _ = isolated_plugin
    assert plugin.start_websocket(server)
    first = plugin.get_websocket_runtime()
    assert first and first.is_alive() and first.endpoint.is_running()
    assert plugin.start_websocket(server)
    assert plugin.get_websocket_runtime() is first
    assert plugin.stop_websocket(server)
    assert not first.thread.is_alive() and first.loop.is_closed()
    assert plugin.stop_websocket(server)
    assert plugin.start_websocket(server)
    second = plugin.get_websocket_runtime()
    assert second is not first and second.loop is not first.loop
    assert first.submit_event({"event_name": "old"}) is None
    assert plugin.stop_websocket(server)
    assert not second.thread.is_alive() and second.loop.is_closed()


def test_invalid_reload_keeps_current_endpoint_and_configuration(isolated_plugin):
    server, cfg, _ = isolated_plugin
    assert plugin.start_websocket(server)
    original_runtime = plugin.get_websocket_runtime()
    original = copy.deepcopy(cfg.config)
    malformed = copy.deepcopy(original)
    malformed["websocket"]["reconnect_interval"] = -1
    with open(cfg.config_path, "w", encoding="utf-8") as stream:
        json.dump(malformed, stream)
    assert plugin.reload_configuration(server) is False
    assert plugin.get_websocket_runtime() is original_runtime
    assert original_runtime.is_alive() and cfg.config == original
    assert cfg.reconnect_interval == 30


def test_valid_reload_replaces_one_generation_and_closes_previous_loop(isolated_plugin):
    server, cfg, _ = isolated_plugin
    assert plugin.start_websocket(server)
    original = plugin.get_websocket_runtime()
    changed = copy.deepcopy(cfg.config)
    changed["websocket"]["reconnect_interval"] = 10
    with open(cfg.config_path, "w", encoding="utf-8") as stream:
        json.dump(changed, stream)
    assert plugin.reload_configuration(server)
    replacement = plugin.get_websocket_runtime()
    assert replacement is not original
    assert not original.thread.is_alive() and original.loop.is_closed()
    assert replacement.endpoint.reconnect_interval == 10
    assert cfg.reconnect_interval == 10


def test_reload_publishes_candidate_after_replacement_starts(isolated_plugin, monkeypatch):
    server, cfg, _ = isolated_plugin
    assert plugin.start_websocket(server)
    previous = copy.deepcopy(cfg.config)
    candidate = copy.deepcopy(previous)
    candidate["websocket"]["reconnect_interval"] = 11
    monkeypatch.setattr(cfg, "load_candidate", lambda: copy.deepcopy(candidate))
    observed_durable_states = []

    def start_replacement(_server):
        with open(cfg.config_path, "r", encoding="utf-8") as stream:
            observed_durable_states.append(json.load(stream))
        return True

    monkeypatch.setattr(plugin, "start_websocket", start_replacement)
    assert plugin.reload_configuration(server)
    assert observed_durable_states == [previous]
    assert cfg.config == candidate
    with open(cfg.config_path, "r", encoding="utf-8") as stream:
        assert json.load(stream) == candidate


def test_failed_replacement_rolls_back_to_previous_client_configuration(isolated_plugin):
    server, cfg, _ = isolated_plugin
    assert plugin.start_websocket(server)
    original = plugin.get_websocket_runtime()
    previous = copy.deepcopy(cfg.config)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        invalid_replacement = copy.deepcopy(previous)
        invalid_replacement["mode"] = "server"
        invalid_replacement["websocket"].update(host="127.0.0.1", port=occupied.getsockname()[1])
        with open(cfg.config_path, "w", encoding="utf-8") as stream:
            json.dump(invalid_replacement, stream)
        assert plugin.reload_configuration(server) is False
    recovered = plugin.get_websocket_runtime()
    assert recovered and recovered.mode == "client" and recovered.is_alive()
    assert cfg.config == previous
    assert not original.is_alive() and original.loop.is_closed()


def test_plugin_reload_handover_stops_previous_owner(isolated_plugin, monkeypatch):
    server, _, old_handler = isolated_plugin
    assert plugin.start_websocket(server)
    previous = plugin.get_websocket_runtime()
    previous_module = SimpleNamespace(_runtime=previous, ws_thread=previous.thread, event_handler=old_handler)
    monkeypatch.setattr(plugin.CommandHandler, "register_commands", lambda self: None)
    monkeypatch.setattr(plugin.EventHandler, "register_events", lambda self: None)
    plugin.on_load(server, previous_module)
    current = plugin.get_websocket_runtime()
    assert current is not previous and current.is_alive()
    assert not previous.is_alive() and previous.loop.is_closed()
    assert old_handler._closed.is_set()


def test_incomplete_shutdown_retains_ownership_and_blocks_replacement(isolated_plugin, monkeypatch):
    server, _, _ = isolated_plugin
    retained = SimpleNamespace(mode="client", is_alive=lambda: True, stop=lambda: False)
    monkeypatch.setattr(plugin, "_runtime", retained)
    try:
        assert plugin.stop_websocket(server) is False
        assert plugin._runtime is retained
        assert plugin._force_cleanup() is False
        assert plugin.start_websocket_server(server) is False
        assert plugin._runtime is retained
    finally:
        monkeypatch.setattr(plugin, "_runtime", None)


@pytest.mark.asyncio
async def test_external_cancellation_closes_the_owned_connection_task(monkeypatch):
    entered, cancelled = asyncio.Event(), asyncio.Event()
    class Hanging:
        async def __aenter__(self):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        async def __aexit__(self, *args):
            pass
    monkeypatch.setattr(client_module.websockets, "connect", lambda *a, **k: Hanging())
    client = WebSocketClient(host(), "ws://127.0.0.1:1", None, settings())
    task = asyncio.create_task(client.start())
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()
    assert not client.is_running() and client._connection_task is None
    assert client._run_task is None


@pytest.mark.asyncio
async def test_retry_budget_and_progression_use_actual_client_loop(monkeypatch):
    calls, delays = [], []
    class Failed:
        async def __aenter__(self):
            calls.append(1)
            raise OSError("fixture failure")
        async def __aexit__(self, *args):
            pass
    monkeypatch.setattr(client_module.websockets, "connect", lambda *a, **k: Failed())
    client = WebSocketClient(host(), "ws://127.0.0.1:1", None,
        settings(reconnect_jitter_ratio=0, reconnect_max_delay=8),
        reconnect_interval=1, reconnect_max_times=3)
    async def controlled_wait(delay):
        delays.append(delay)
    client._wait_retry = controlled_wait
    await client.start()
    assert len(calls) == 4 and delays == [1, 2, 4]
    assert client.metrics["last_error"] == "retry_exhausted"
    assert not client.is_running()


@pytest.mark.asyncio
async def test_stable_connection_duration_resets_budget_not_a_brief_handshake(monkeypatch):
    clock = iter([0, 0.1, 1, 20, 21, 21.1])
    delays = []
    class Closed:
        def __aiter__(self):
            async def empty():
                if False:
                    yield None
            return empty()
    class Connection:
        async def __aenter__(self):
            return Closed()
        async def __aexit__(self, *args):
            pass
    monkeypatch.setattr(client_module.websockets, "connect", lambda *a, **k: Connection())
    client = WebSocketClient(host(), "ws://127.0.0.1:1", None,
        settings(reconnect_jitter_ratio=0, reconnect_reset_after=10), reconnect_interval=1,
        clock=lambda: next(clock))
    async def controlled_wait(delay):
        delays.append(delay)
        if len(delays) == 3:
            await client.stop()
    client._wait_retry = controlled_wait
    await client.start()
    assert delays == [1, 1, 2]


@pytest.mark.asyncio
async def test_legacy_header_signature_does_not_mask_application_typeerror(monkeypatch):
    calls, entered = [], asyncio.Event()
    class Connection:
        async def __aenter__(self):
            entered.set()
            return object()
        async def __aexit__(self, *args):
            pass
    def legacy_connect(url, *, extra_headers, **kwargs):
        calls.append(extra_headers)
        return Connection()
    monkeypatch.setattr(client_module.websockets, "connect", legacy_connect)
    client = WebSocketClient(host(), "ws://127.0.0.1:1", None, settings(), reconnect_interval=30)
    async def broken_handler(ws):
        raise TypeError("application error")
    client._on_connected = broken_handler
    task = asyncio.create_task(client.start())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.sleep(0)
        assert len(calls) == 1
        assert calls[0]["Authorization"] == "Bearer test-only"
        assert client.metrics["last_error"] == "TypeError"
    finally:
        await client.stop()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_real_auth_rejection_stops_retries_and_redacts_target():
    server = host()
    def reject(connection, request):
        return connection.respond(401, "Rejected")
    listener = await websockets.serve(lambda ws: ws.wait_closed(), "127.0.0.1", 0, process_request=reject)
    port = listener.sockets[0].getsockname()[1]
    client = WebSocketClient(server, f"ws://127.0.0.1:{port}/private-path?secret=url-secret", None,
        settings(), reconnect_interval=0.01)
    try:
        await asyncio.wait_for(client.start(), 3)
        assert client.metrics["connection_attempts"] == 1
        assert client.metrics["authentication_failures"] == 1
        assert not client.is_running()
        logs = "\n".join(server.logger.messages)
        assert "url-secret" not in logs and "private-path" not in logs and "test-only" not in logs
    finally:
        await client.stop()
        listener.close()
        await listener.wait_closed()


def test_optional_event_enrichment_is_bounded_and_closes_without_dispatching_to_new_owner(monkeypatch):
    server = host()
    entered = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    counts = {"running": 0, "peak": 0}
    def dimension(player, timeout):
        with lock:
            counts["running"] += 1
            counts["peak"] = max(counts["peak"], counts["running"])
            if counts["running"] == 2:
                entered.set()
        release.wait(2)
        with lock:
            counts["running"] -= 1
        return "test_dimension"
    server.get_plugin_instance = lambda name: SimpleNamespace(
        get_player_dimension=dimension, get_player_coordinate=lambda *a, **k: None)
    class Runtime:
        def __init__(self):
            self.alive = True
            self.events = []
        def submit_event(self, event):
            if self.alive:
                self.events.append(event)
            return None
    first, replacement = Runtime(), Runtime()
    current = [first]
    monkeypatch.setattr(plugin, "get_websocket_runtime", lambda: current[0])
    handler = EventHandler(server, settings(), None)
    try:
        handler._send_event_with_location({"player": {}}, "first")
        handler._send_event_with_location({"player": {}}, "second")
        assert entered.wait(1)
        handler._send_event_with_location({"player": {}, "fallback": True}, "third")
        assert len(first.events) == 1 and first.events[0]["fallback"]
        assert counts["peak"] == 2
        first.alive = False
        current[0] = replacement
    finally:
        release.set()
        assert handler.close()
    assert replacement.events == []
    assert not handler._workers
    handler.broadcast_event({"after_close": True})
    assert replacement.events == []
