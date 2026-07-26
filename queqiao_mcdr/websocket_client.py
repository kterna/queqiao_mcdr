"""
WebSocket 客户端模块（反向连接）

由 MC/MCDR 侧主动连接对接端（如 astrbot_plugin_mcqq）的 WebSocket Server，
适用于租赁服等无法自定义开放端口的场景。
"""

import asyncio
import json
from typing import Any, Dict, Optional
from urllib.parse import quote_plus

import websockets
from mcdreforged.api.all import *

from queqiao_mcdr.response_builder import ResponseBuilder


class WebSocketClient:
    """反向 WebSocket 客户端：主动连接对接端 Server。"""

    def __init__(
        self,
        server: PluginServerInterface,
        url: str,
        api_handler,
        config,  # Config
        reconnect_interval: int = 5,
        reconnect_max_times: int = 0,
    ):
        """
        Args:
            server: MCDR 服务器接口
            url: 对接端 WebSocket 地址，例如 ws://host:8080/minecraft/ws
            api_handler: API 处理器
            config: 配置对象
            reconnect_interval: 重连间隔（秒）
            reconnect_max_times: 最大重连次数，0 表示无限重连
        """
        self.server = server
        self.logger = server.logger
        self.url = url
        self.api_handler = api_handler
        self.config = config
        self.reconnect_interval = max(1, int(reconnect_interval))
        self.reconnect_max_times = max(0, int(reconnect_max_times))

        self.websocket = None
        self._running = False
        self._should_run = False
        self._send_lock = asyncio.Lock()
        self._total_retries = 0

    def is_running(self) -> bool:
        return self._running

    def is_connected(self) -> bool:
        return self.websocket is not None and self._running

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "x-self-name": quote_plus(self.config.server_name),
            "x-client-origin": "minecraft",
        }
        if self.config.access_token:
            headers["Authorization"] = f"Bearer {self.config.access_token}"
        return headers

    async def start(self):
        """启动客户端并维持重连循环。应在事件循环中被 await 一次。"""
        if self._should_run:
            self.logger.info("WebSocket 客户端已在运行中")
            return

        self._should_run = True
        self._total_retries = 0
        self.logger.info(f"WebSocket 客户端启动，目标: {self.url}")

        while self._should_run:
            try:
                headers = self._build_headers()
                # websockets 不同版本参数名可能不同
                connect_kwargs = {
                    "ping_interval": 30,
                    "ping_timeout": 10,
                }
                try:
                    async with websockets.connect(
                        self.url,
                        additional_headers=headers,
                        **connect_kwargs,
                    ) as ws:
                        await self._on_connected(ws)
                except TypeError:
                    # 兼容旧版 extra_headers
                    async with websockets.connect(
                        self.url,
                        extra_headers=headers,
                        **connect_kwargs,
                    ) as ws:
                        await self._on_connected(ws)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._running = False
                self.websocket = None
                if not self._should_run:
                    break

                self._total_retries += 1
                if (
                    self.reconnect_max_times > 0
                    and self._total_retries > self.reconnect_max_times
                ):
                    self.logger.error(
                        f"WebSocket 客户端重连次数已达上限 "
                        f"({self.reconnect_max_times})，停止重连"
                    )
                    self._should_run = False
                    break

                wait = min(
                    self.reconnect_interval * max(1, self._total_retries),
                    60,
                )
                self.logger.error(
                    f"WebSocket 客户端连接失败: {e}，"
                    f"{wait}s 后重试 (第{self._total_retries}次)"
                )
                try:
                    await asyncio.sleep(wait)
                except asyncio.CancelledError:
                    break

        self._running = False
        self.websocket = None
        self.logger.info("WebSocket 客户端已停止")

    async def _on_connected(self, ws):
        self.websocket = ws
        self._running = True
        self._total_retries = 0
        self.logger.info(f"WebSocket 客户端已连接到: {self.url}")

        try:
            async for message in ws:
                await self._process_message(message)
        except websockets.exceptions.ConnectionClosed as e:
            self.logger.warning(
                f"WebSocket 客户端连接关闭: code={getattr(e, 'code', '?')}, "
                f"reason={getattr(e, 'reason', '')}"
            )
        finally:
            self._running = False
            self.websocket = None

    async def stop(self):
        """停止客户端。"""
        self._should_run = False
        ws = self.websocket
        self.websocket = None
        self._running = False
        if ws is not None:
            try:
                await ws.close(code=1001, reason="Client shutting down")
            except Exception as e:
                self.logger.debug(f"关闭 WebSocket 客户端时出错: {e}")
        self.logger.info("WebSocket 客户端停止请求已发出")

    async def broadcast_event(self, event_data: Dict[str, Any]):
        """向对接端发送事件（与 Server 模式 API 一致）。"""
        if not self.is_connected():
            return
        try:
            message = json.dumps(event_data, ensure_ascii=False)
            async with self._send_lock:
                await self.websocket.send(message)
            self.logger.debug(f"客户端发送事件: {event_data}")
        except Exception as e:
            self.logger.error(f"客户端发送事件失败: {e}")

    async def _process_message(self, message):
        """处理对接端下发的 API 请求。"""
        try:
            data = json.loads(message)
            self.logger.debug(f"客户端收到消息: {data}")

            if "api" in data:
                response = await self.api_handler.handle_api_request(
                    data["api"],
                    data.get("data", {}),
                    data.get("echo"),
                )
            else:
                response = ResponseBuilder.websocket_echo(
                    message="收到你的消息",
                    original_data=data,
                )

            if self.websocket is not None:
                async with self._send_lock:
                    await self.websocket.send(
                        json.dumps(response, ensure_ascii=False)
                    )
        except json.JSONDecodeError:
            self.logger.warning(f"客户端收到无效 JSON: {message}")
            await self._send_error("无效的JSON格式，请发送有效的JSON消息")
        except Exception as e:
            self.logger.error(f"客户端处理消息出错: {e}")
            await self._send_error(f"消息处理错误: {str(e)}")

    async def _send_error(self, error_message: str):
        try:
            if self.websocket is None:
                return
            error_response = ResponseBuilder.websocket_error(message=error_message)
            async with self._send_lock:
                await self.websocket.send(
                    json.dumps(error_response, ensure_ascii=False)
                )
        except Exception:
            pass
