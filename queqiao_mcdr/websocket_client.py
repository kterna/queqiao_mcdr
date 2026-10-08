"""Reverse WebSocket client with owned tasks and interruptible reconnect policy."""
import asyncio
import inspect
import json
import time
from typing import Any, Dict
from urllib.parse import quote_plus, urlsplit

import websockets

from queqiao_mcdr.reconnect_backoff import ReconnectBackoff, finite_number
from queqiao_mcdr.response_builder import ResponseBuilder


def safe_websocket_target(url):
    """Logs/status never expose URL user-info, query, fragment or private path."""
    try:
        parts = urlsplit(url)
        host = parts.hostname or "<invalid>"
        host = f"[{host}]" if ":" in host else host
        port = f":{parts.port}" if parts.port else ""
        return f"{parts.scheme}://{host}{port}"
    except (TypeError, ValueError):
        return "<invalid WebSocket target>"


class WebSocketClient:
    """One start task owns one connection task and its retry wait at a time."""

    def __init__(self, server, url, api_handler, config,
                 reconnect_interval=5, reconnect_max_times=0, *, clock=None):
        self.server, self.logger = server, server.logger
        self.url, self.api_handler, self.config = url, api_handler, config
        if type(reconnect_max_times) is not int or reconnect_max_times < 0:
            raise ValueError("reconnect_max_times must be a nonnegative integer")
        self.backoff = ReconnectBackoff(
            initial_delay=reconnect_interval,
            max_delay=getattr(config, "reconnect_max_delay", 60),
            multiplier=getattr(config, "reconnect_multiplier", 2),
            jitter_ratio=getattr(config, "reconnect_jitter_ratio", 0.1),
        )
        self.reconnect_interval = self.backoff.initial_delay
        self.reconnect_max_times = reconnect_max_times
        self.reset_after = finite_number(
            getattr(config, "reconnect_reset_after", 30), "reconnect_reset_after", 0, 3600
        )
        self._clock = clock or time.monotonic
        self.websocket = None
        self._running = False
        self._should_run = False
        self._run_task = None
        self._connection_task = None
        self._stop_event = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._total_retries = 0
        self._last_connection_duration = 0.0
        self.metrics = {
            "connection_attempts": 0, "connected_sessions": 0,
            "normal_closes": 0, "transport_failures": 0,
            "authentication_failures": 0, "messages_received": 0,
            "send_failures": 0, "last_retry_delay": None, "last_error": None,
        }

    def is_running(self):
        """True during connecting/backoff as well as a connected session."""
        return self._running

    def is_connected(self):
        return self._running and self.websocket is not None

    def _build_headers(self):
        headers = {
            "x-self-name": quote_plus(self.config.server_name),
            "x-client-origin": "minecraft",
        }
        if self.config.access_token:
            headers["Authorization"] = f"Bearer {self.config.access_token}"
        return headers

    async def start(self):
        if self._run_task is not None and not self._run_task.done():
            self.logger.info("WebSocket client is already running")
            return
        owner = asyncio.current_task()
        self._run_task = owner
        self._stop_event = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._should_run = self._running = True
        self._total_retries = 0
        self.backoff.reset()
        self.logger.info(f"WebSocket client starting: {safe_websocket_target(self.url)}")
        try:
            while self._should_run:
                self._last_connection_duration = 0.0
                self.metrics["connection_attempts"] += 1
                connection = asyncio.create_task(self._connect_once(), name="QueQiao-connection")
                self._connection_task = connection
                try:
                    await connection
                    self.metrics["normal_closes"] += 1
                    self.metrics["last_error"] = "peer_closed"
                except asyncio.CancelledError:
                    if self._should_run:
                        raise
                    break
                except Exception as exc:
                    self.metrics["transport_failures"] += 1
                    self.metrics["last_error"] = type(exc).__name__
                    response = getattr(exc, "response", None)
                    status = getattr(response, "status_code", getattr(exc, "status_code", None))
                    if status in (401, 403):
                        self.metrics["authentication_failures"] += 1
                        self._should_run = False
                        self.logger.error(f"WebSocket authentication rejected (HTTP {status}); restart after correcting configuration")
                        break
                    self.logger.warning(f"WebSocket connection ended: {type(exc).__name__}")
                finally:
                    if self._connection_task is connection:
                        self._connection_task = None
                if not self._should_run:
                    break
                # A completed handshake alone must not reset a flapping peer's budget.
                if self._last_connection_duration >= self.reset_after:
                    self._total_retries = 0
                    self.backoff.reset()
                self._total_retries += 1
                if self.reconnect_max_times and self._total_retries > self.reconnect_max_times:
                    self.metrics["last_error"] = "retry_exhausted"
                    self.logger.error("WebSocket reconnect limit reached")
                    break
                delay = self.backoff.next_delay()
                self.metrics["last_retry_delay"] = delay
                await self._wait_retry(delay)
        finally:
            self._should_run = False
            self._stop_event.set()
            child = self._connection_task
            if child is not None and not child.done():
                child.cancel()
                await asyncio.gather(child, return_exceptions=True)
            self._connection_task = None
            self.websocket = None
            self._running = False
            if self._run_task is owner:
                self._run_task = None
            self.logger.info("WebSocket client stopped")

    async def _wait_retry(self, delay):
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

    async def _connect_once(self):
        connector = websockets.connect
        # Select the supported header parameter before dialing. A TypeError in
        # application handling must never trigger a second connection attempt.
        try:
            parameters = inspect.signature(connector).parameters
        except (TypeError, ValueError):
            parameters = {}
        header_key = "extra_headers" if "extra_headers" in parameters and "additional_headers" not in parameters else "additional_headers"
        options = {
            header_key: self._build_headers(), "ping_interval": 30,
            "ping_timeout": 10, "open_timeout": 10, "close_timeout": 1,
        }
        async with connector(self.url, **options) as ws:
            await self._on_connected(ws)

    async def _on_connected(self, ws):
        self.websocket = ws
        started = self._clock()
        self.metrics["connected_sessions"] += 1
        self.logger.info(f"WebSocket connected: {safe_websocket_target(self.url)}")
        try:
            async for message in ws:
                self.metrics["messages_received"] += 1
                await self._process_message(message)
        finally:
            self._last_connection_duration = max(0.0, self._clock() - started)
            if self.websocket is ws:
                self.websocket = None

    async def stop(self):
        owner = self._run_task
        self._should_run = False
        self._stop_event.set()
        child = self._connection_task
        if child is not None and not child.done():
            child.cancel()
        if owner is not None and owner is not asyncio.current_task():
            try:
                await asyncio.wait_for(asyncio.shield(owner), timeout=3)
            except asyncio.CancelledError:
                if not owner.cancelled():
                    raise
            except asyncio.TimeoutError:
                # Keep ownership references so another start cannot orphan it.
                raise RuntimeError("WebSocket client did not finish shutdown") from None

    async def _send_json(self, payload):
        ws = self.websocket
        if ws is None or not self._running:
            return False
        try:
            message = json.dumps(payload, ensure_ascii=False, allow_nan=False)
            async with self._send_lock:
                if self.websocket is not ws or not self._running:
                    return False
                await ws.send(message)
            return True
        except Exception as exc:
            self.metrics["send_failures"] += 1
            self.logger.warning(f"WebSocket send failed: {type(exc).__name__}")
            return False

    async def broadcast_event(self, event_data: Dict[str, Any]):
        return await self._send_json(event_data)

    async def _process_message(self, message):
        try:
            data = json.loads(message)
            if not isinstance(data, dict):
                await self._send_error("WebSocket request must be a JSON object")
                return
            if "api" in data:
                response = await self.api_handler.handle_api_request(
                    data["api"], data.get("data", {}), data.get("echo")
                )
            else:
                response = ResponseBuilder.websocket_echo(
                    message="收到你的消息", original_data=data
                )
            await self._send_json(response)
        except json.JSONDecodeError:
            self.logger.warning("WebSocket received invalid JSON")
            await self._send_error("无效的JSON格式，请发送有效的JSON消息")
        except Exception as exc:
            self.logger.error(f"WebSocket request handling failed: {type(exc).__name__}")
            await self._send_error("消息处理失败")

    async def _send_error(self, error_message):
        await self._send_json(ResponseBuilder.websocket_error(message=error_message))
