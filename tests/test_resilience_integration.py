"""Regression cases exercise real client/handler paths with a stub MCDR host."""
import asyncio
import json
import importlib
import random
import time
from types import SimpleNamespace

import pytest

from queqiao_mcdr.api_handler import ApiHandler
from queqiao_mcdr.reconnect_backoff import ReconnectBackoff
from queqiao_mcdr.websocket_client import WebSocketClient


class Logger:
    def __init__(self):
        self.messages = []

    def __getattr__(self, name):
        return lambda message, *args: self.messages.append(str(message))


def server():
    result = SimpleNamespace(logger=Logger(), commands=[])
    result.execute = result.commands.append
    return result


def config(**values):
    return SimpleNamespace(server_name="Local test", access_token="test-only", **values)


@pytest.mark.asyncio
async def test_stop_wakes_backoff_and_finishes_owned_client(monkeypatch):
    attempted = asyncio.Event()

    class FailedConnection:
        async def __aenter__(self):
            attempted.set()
            raise OSError("temporary failure")

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(importlib.import_module("queqiao_mcdr.websocket_client").websockets, "connect", lambda *a, **k: FailedConnection())
    client = WebSocketClient(server(), "ws://127.0.0.1:1", None, config(), reconnect_interval=30)
    task = asyncio.create_task(client.start())
    try:
        await asyncio.wait_for(attempted.wait(), 1)
        started = time.monotonic()
        await asyncio.wait_for(client.stop(), 0.5)
        assert task.done(), "stop returned while the client was still sleeping in backoff"
        assert time.monotonic() - started < 0.5
        await client.stop()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_normal_peer_close_is_paced_instead_of_a_tight_reconnect_loop(monkeypatch):
    calls = []

    class ClosedSocket:
        def __aiter__(self):
            async def empty():
                if False:
                    yield None
            return empty()

    class Connection:
        async def __aenter__(self):
            calls.append(time.monotonic())
            await asyncio.sleep(0)
            return ClosedSocket()

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(importlib.import_module("queqiao_mcdr.websocket_client").websockets, "connect", lambda *a, **k: Connection())
    client = WebSocketClient(server(), "ws://127.0.0.1:1", None, config(), reconnect_interval=30)
    task = asyncio.create_task(client.start())
    try:
        await asyncio.sleep(0.03)
        assert len(calls) == 1, "normal peer close must enter the configured retry policy"
    finally:
        await client.stop()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("fadein", "0\nstop"), ("stay", True), ("fadeout", -1)])
async def test_invalid_title_timing_has_zero_execution_side_effects(field, value):
    host = server()
    handler = ApiHandler(host, config())
    result = await handler.handle_api_request("send_title", {"title": "hello", field: value}, echo="timing")
    assert host.commands == []
    assert result["status"] == "failed"
    assert result["echo"] == "timing"


@pytest.mark.asyncio
async def test_plain_message_quotes_and_newlines_are_valid_json():
    host = server()
    handler = ApiHandler(host, config())
    text = 'hello "quoted"\nsecond line\\end'
    result = await handler.handle_api_request("send_actionbar", {"message": text}, echo="quoted")
    assert result["status"] == "ok"
    command = host.commands[0]
    assert command.startswith("title @a actionbar ")
    assert "\n" not in command
    assert json.loads(command.removeprefix("title @a actionbar "))["text"] == text


@pytest.mark.asyncio
async def test_invalid_subtitle_is_rejected_before_even_the_times_command():
    host = server()
    handler = ApiHandler(host, config())
    result = await handler.handle_api_request("send_title", {"title": "valid", "subtitle": {"unsupported": object()}}, echo="invalid")
    assert host.commands == []
    assert result["status"] == "failed"


def test_jitter_never_exceeds_the_configured_delay_cap(monkeypatch):
    monkeypatch.setattr(random, "random", lambda: 1.0)
    backoff = ReconnectBackoff(initial_delay=10, max_delay=10, jitter_ratio=0.1)
    assert backoff.next_delay() <= 10


@pytest.mark.parametrize("kwargs", [{"initial_delay": float("nan")}, {"initial_delay": 0}, {"multiplier": 0.5}, {"jitter_ratio": 2}])
def test_invalid_reconnect_policy_is_rejected(kwargs):
    with pytest.raises(ValueError):
        ReconnectBackoff(**kwargs)
