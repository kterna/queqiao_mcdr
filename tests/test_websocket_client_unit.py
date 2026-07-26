"""
queqiao_mcdr WebSocketClient 单元/集成测试

不依赖完整 MCDR 运行时，用假对象模拟 server/api_handler。
"""

from __future__ import annotations

import asyncio
import json
import socket
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote_plus

import pytest
import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from queqiao_mcdr.websocket_client import WebSocketClient  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeLogger:
    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass

    def debug(self, *a, **k):
        pass


class FakeConfig:
    server_name = "FakeMCDR"
    access_token = "abc"


class FakeApiHandler:
    def __init__(self):
        self.calls = []

    async def handle_api_request(self, api_name, api_data, echo=None):
        self.calls.append((api_name, api_data, echo))
        return {
            "status": "success",
            "data": {"ok": True, "api": api_name},
            "echo": echo,
        }


@pytest.mark.asyncio
async def test_client_connects_and_handles_api():
    port = _free_port()
    path = "/minecraft/ws"
    events_from_client = asyncio.Queue()
    connected = asyncio.Event()

    async def server_handler(websocket):
        connected.set()
        # 先收一条客户端事件
        raw = await asyncio.wait_for(websocket.recv(), timeout=3)
        await events_from_client.put(json.loads(raw))
        # 再下发 API
        await websocket.send(
            json.dumps(
                {"api": "broadcast", "data": {"message": "ping"}, "echo": "9"}
            )
        )
        # 收响应
        resp = json.loads(await asyncio.wait_for(websocket.recv(), timeout=3))
        await events_from_client.put(resp)
        await websocket.close()

    server = await websockets.serve(
        server_handler, "127.0.0.1", port, process_request=None
    )

    fake_server = SimpleNamespace(logger=FakeLogger())
    api = FakeApiHandler()
    client = WebSocketClient(
        fake_server,
        f"ws://127.0.0.1:{port}{path}",
        api,
        FakeConfig(),
        reconnect_interval=1,
        reconnect_max_times=3,
    )

    # websockets.serve 默认接受任意 path；client 会带 headers
    # 注意：部分 websockets 版本 path 校验需要 process_request；这里不限制

    client_task = asyncio.create_task(client.start())
    try:
        await asyncio.wait_for(connected.wait(), timeout=5)
        # 等 client 标记 connected
        for _ in range(50):
            if client.is_connected():
                break
            await asyncio.sleep(0.05)
        assert client.is_connected()

        await client.broadcast_event(
            {
                "event_name": "PlayerChatEvent",
                "message": "from mcdr",
                "server_name": "FakeMCDR",
            }
        )

        event = await asyncio.wait_for(events_from_client.get(), timeout=5)
        assert event["message"] == "from mcdr"

        resp = await asyncio.wait_for(events_from_client.get(), timeout=5)
        assert resp["status"] == "success"
        assert resp["echo"] == "9"
        assert api.calls and api.calls[0][0] == "broadcast"
    finally:
        await client.stop()
        client_task.cancel()
        try:
            await client_task
        except (asyncio.CancelledError, Exception):
            pass
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_client_sends_correct_headers():
    """握手 headers 应包含 x-self-name / Authorization / x-client-origin。"""
    port = _free_port()
    got_headers = {}
    done = asyncio.Event()

    async def process_request(connection, request):
        headers = request.headers
        got_headers["x-self-name"] = headers.get("x-self-name")
        got_headers["Authorization"] = headers.get("Authorization")
        got_headers["x-client-origin"] = headers.get("x-client-origin")
        done.set()
        return None

    async def handler(websocket):
        await websocket.wait_closed()

    server = await websockets.serve(
        handler, "127.0.0.1", port, process_request=process_request
    )

    fake_server = SimpleNamespace(logger=FakeLogger())
    client = WebSocketClient(
        fake_server,
        f"ws://127.0.0.1:{port}/minecraft/ws",
        FakeApiHandler(),
        FakeConfig(),
        reconnect_interval=1,
        reconnect_max_times=1,
    )
    task = asyncio.create_task(client.start())
    try:
        await asyncio.wait_for(done.wait(), timeout=5)
        assert got_headers["x-self-name"] == quote_plus("FakeMCDR")
        assert got_headers["Authorization"] == "Bearer abc"
        assert got_headers["x-client-origin"] == "minecraft"
    finally:
        await client.stop()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        server.close()
        await server.wait_closed()
