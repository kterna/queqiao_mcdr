"""
QueQiao MCDR插件入口文件

这个插件移植了QueQiao模组的功能，通过WebSocket协议连接不同的Minecraft服务器，
支持跨服务器的消息传递和事件处理。

支持两种连接模式：
- server（正向，默认）：MCDR 开 WebSocket Server，对接端主动连接
- client（反向）：MCDR 作为 Client 主动连接对接端，适合租赁服
"""

import os
import json
import asyncio
import threading
import time
from typing import Optional, Dict, Any, List, Union

from mcdreforged.api.all import *

from queqiao_mcdr.config import Config
from queqiao_mcdr.websocket_server import WebSocketServer
from queqiao_mcdr.websocket_client import WebSocketClient
from queqiao_mcdr.event_handler import EventHandler
from queqiao_mcdr.api_handler import ApiHandler
from queqiao_mcdr.command_handler import CommandHandler
from queqiao_mcdr.utils import get_server_version

# 插件元数据
PLUGIN_METADATA = {
    "id": "queqiao_mcdr",
    "version": "1.2.0",
    "name": "QueQiao MCDR",
    "description": "移植自QueQiao模组的MCDR插件，通过 WebSocket 实现跨服务器通信（支持正/反向）",
    "author": "kterna",
    "link": "https://github.com/kterna/QueQiao_MCDR",
    "dependencies": {
        "mcdreforged": ">=2.0.0",
    },
}

# 全局变量
config: Optional[Config] = None
websocket_server: Optional[WebSocketServer] = None
websocket_client: Optional[WebSocketClient] = None
event_handler: Optional[EventHandler] = None
api_handler: Optional[ApiHandler] = None
command_handler: Optional[CommandHandler] = None
ws_thread: Optional[threading.Thread] = None
loop: Optional[asyncio.AbstractEventLoop] = None


def on_load(server: PluginServerInterface, prev_module):
    """插件加载时调用"""
    global config, websocket_server, websocket_client, event_handler
    global api_handler, command_handler, ws_thread, loop

    # 创建数据文件夹
    data_folder = server.get_data_folder()
    if not os.path.exists(data_folder):
        os.makedirs(data_folder)

    # 加载配置
    config = Config(server)
    config.load_config()

    # 初始化各模块
    api_handler = ApiHandler(server, config)
    event_handler = EventHandler(server, config, api_handler)
    command_handler = CommandHandler(server, config)

    # 注册命令和事件监听器
    command_handler.register_commands()
    event_handler.register_events()

    # 如果配置了自动启动，则启动 WebSocket
    if config.auto_start:
        start_websocket(server)

    # 如果是从旧版本重载，尝试恢复状态
    if prev_module is not None:
        prev_running = False
        if getattr(prev_module, "websocket_server", None) is not None:
            prev_running = True
        if getattr(prev_module, "websocket_client", None) is not None:
            prev_running = True
        if prev_running and not (
            (websocket_server and websocket_server.is_running())
            or (websocket_client and websocket_client.is_running())
        ):
            server.logger.info("检测到插件重载，尝试恢复 WebSocket 状态")
            start_websocket(server)

    server.logger.info(
        f'QueQiao MCDR 插件已加载，版本 {PLUGIN_METADATA["version"]}，'
        f"模式={config.mode}"
    )


def on_unload(server: PluginServerInterface):
    """插件卸载时调用"""
    global websocket_server, websocket_client, ws_thread, loop

    server.logger.info("开始卸载 QueQiao MCDR 插件...")

    try:
        if (
            websocket_server is not None
            or websocket_client is not None
            or ws_thread is not None
            or loop is not None
        ):
            server.logger.info("发现 WebSocket 资源，正在停止...")
            stop_websocket(server)
        else:
            server.logger.info("未发现 WebSocket 资源")
    except Exception as e:
        server.logger.error(f"卸载时停止 WebSocket 失败: {e}")
        import traceback

        server.logger.error(traceback.format_exc())
        _force_cleanup()

    server.logger.info("QueQiao MCDR 插件已卸载")


def on_info(server: PluginServerInterface, info: Info):
    """接收到服务器信息时调用"""
    if info.is_user and info.content.startswith("!!queqiao"):
        command_handler.on_command(server, info)


def start_websocket(server: PluginServerInterface):
    """根据配置启动 WebSocket Server 或 Client"""
    if config is None:
        server.logger.error("配置未加载，无法启动 WebSocket")
        return

    if config.mode == "client":
        start_websocket_client(server)
    else:
        start_websocket_server(server)


def stop_websocket(server: PluginServerInterface):
    """停止当前运行的 WebSocket（Server 或 Client）"""
    global websocket_server, websocket_client

    # 两者都尝试停，兼容异常状态
    if websocket_client is not None:
        stop_websocket_client(server)
    if websocket_server is not None:
        stop_websocket_server(server)
    # 若都为空，仍做清理
    if websocket_client is None and websocket_server is None:
        if ws_thread is not None or loop is not None:
            _force_cleanup()


# 兼容旧 API 名称
def start_websocket_server(server: PluginServerInterface):
    """启动 WebSocket 服务器（正向）"""
    global websocket_server, websocket_client, ws_thread, loop, api_handler

    if websocket_client is not None and websocket_client.is_running():
        server.logger.warning("当前为 client 模式且正在运行，请先 stop 再切换")
        return

    if websocket_server is not None and websocket_server.is_running():
        server.logger.info("WebSocket 服务器已经在运行中")
        return

    try:
        websocket_server = WebSocketServer(
            server,
            config.websocket_host,
            config.websocket_port,
            config.websocket_path,
            api_handler,
            config,
        )

        def run_websocket_server():
            global loop
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(websocket_server.start())
                loop.run_forever()
            except Exception as e:
                server.logger.error(f"WebSocket 服务器线程异常: {e}")
                import traceback

                server.logger.error(traceback.format_exc())
            finally:
                try:
                    if loop and not loop.is_closed():
                        loop.close()
                except Exception as e:
                    server.logger.error(f"关闭事件循环时出错: {e}")
                finally:
                    loop = None

        ws_thread = threading.Thread(
            target=run_websocket_server, daemon=True, name="QueQiao-WebSocket-Server"
        )
        ws_thread.start()
        time.sleep(0.1)

        server.logger.info(
            f"WebSocket 服务器已启动，监听地址: "
            f"{config.websocket_host}:{config.websocket_port}{config.websocket_path}"
        )
    except Exception as e:
        server.logger.error(f"启动 WebSocket 服务器失败: {e}")
        import traceback

        server.logger.error(traceback.format_exc())


def start_websocket_client(server: PluginServerInterface):
    """启动 WebSocket 客户端（反向）"""
    global websocket_client, websocket_server, ws_thread, loop, api_handler

    if websocket_server is not None and websocket_server.is_running():
        server.logger.warning("当前为 server 模式且正在运行，请先 stop 再切换")
        return

    if websocket_client is not None and websocket_client.is_running():
        server.logger.info("WebSocket 客户端已经在运行中")
        return

    try:
        websocket_client = WebSocketClient(
            server,
            config.websocket_url,
            api_handler,
            config,
            reconnect_interval=config.reconnect_interval,
            reconnect_max_times=config.reconnect_max_times,
        )

        def run_websocket_client():
            global loop
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(websocket_client.start())
            except Exception as e:
                server.logger.error(f"WebSocket 客户端线程异常: {e}")
                import traceback

                server.logger.error(traceback.format_exc())
            finally:
                try:
                    if loop and not loop.is_closed():
                        # start() 返回后循环已结束
                        if loop.is_running():
                            loop.stop()
                        loop.close()
                except Exception as e:
                    server.logger.error(f"关闭事件循环时出错: {e}")
                finally:
                    loop = None

        ws_thread = threading.Thread(
            target=run_websocket_client, daemon=True, name="QueQiao-WebSocket-Client"
        )
        ws_thread.start()
        time.sleep(0.1)

        server.logger.info(
            f"WebSocket 客户端已启动，目标: {config.websocket_url} "
            f"(server_name={config.server_name})"
        )
    except Exception as e:
        server.logger.error(f"启动 WebSocket 客户端失败: {e}")
        import traceback

        server.logger.error(traceback.format_exc())


def stop_websocket_server(server: PluginServerInterface):
    """停止 WebSocket 服务器"""
    global websocket_server, ws_thread, loop

    if websocket_server is None:
        server.logger.info("WebSocket 服务器未初始化")
        if websocket_client is None:
            _force_cleanup()
        return

    try:
        server.logger.info("开始停止 WebSocket 服务器...")

        if loop is not None and not loop.is_closed():
            try:
                future = asyncio.run_coroutine_threadsafe(
                    websocket_server.stop(), loop
                )
                future.result(timeout=8)
            except asyncio.TimeoutError:
                server.logger.warning("停止 WebSocket 服务器超时，继续强制停止")
            except Exception as e:
                server.logger.warning(f"停止 WebSocket 服务器时出错: {e}")

            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception as e:
                server.logger.warning(f"停止事件循环时出错: {e}")

        if ws_thread is not None and ws_thread.is_alive():
            ws_thread.join(timeout=12)
            if ws_thread.is_alive():
                server.logger.warning(
                    "WebSocket 服务器线程未能正常结束，可能需要重启 MCDR"
                )

        websocket_server = None
        if websocket_client is None:
            _force_cleanup()
        server.logger.info("WebSocket 服务器已完全停止")
    except Exception as e:
        server.logger.error(f"停止 WebSocket 服务器失败: {e}")
        import traceback

        server.logger.error(traceback.format_exc())
        server.logger.warning("尝试强制清理 WebSocket 服务器资源")
        websocket_server = None
        if websocket_client is None:
            _force_cleanup()


def stop_websocket_client(server: PluginServerInterface):
    """停止 WebSocket 客户端"""
    global websocket_client, ws_thread, loop

    if websocket_client is None:
        server.logger.info("WebSocket 客户端未初始化")
        if websocket_server is None:
            _force_cleanup()
        return

    try:
        server.logger.info("开始停止 WebSocket 客户端...")

        if loop is not None and not loop.is_closed():
            try:
                future = asyncio.run_coroutine_threadsafe(
                    websocket_client.stop(), loop
                )
                future.result(timeout=8)
            except asyncio.TimeoutError:
                server.logger.warning("停止 WebSocket 客户端超时，继续强制停止")
            except Exception as e:
                server.logger.warning(f"停止 WebSocket 客户端时出错: {e}")

            try:
                # client 的 start() 循环会因 _should_run=False 退出
                # 若仍在 sleep，需要中断
                if loop.is_running():
                    loop.call_soon_threadsafe(loop.stop)
            except Exception as e:
                server.logger.warning(f"停止事件循环时出错: {e}")

        if ws_thread is not None and ws_thread.is_alive():
            ws_thread.join(timeout=12)
            if ws_thread.is_alive():
                server.logger.warning(
                    "WebSocket 客户端线程未能正常结束，可能需要重启 MCDR"
                )

        websocket_client = None
        if websocket_server is None:
            _force_cleanup()
        server.logger.info("WebSocket 客户端已完全停止")
    except Exception as e:
        server.logger.error(f"停止 WebSocket 客户端失败: {e}")
        import traceback

        server.logger.error(traceback.format_exc())
        websocket_client = None
        if websocket_server is None:
            _force_cleanup()


def _force_cleanup():
    """强制清理所有 WebSocket 相关资源"""
    global websocket_server, websocket_client, ws_thread, loop

    websocket_server = None
    websocket_client = None
    ws_thread = None
    loop = None


def get_websocket_server() -> Optional[WebSocketServer]:
    """获取 WebSocket 服务器实例（兼容旧接口）"""
    return websocket_server


def get_websocket_client() -> Optional[WebSocketClient]:
    """获取 WebSocket 客户端实例"""
    return websocket_client


def get_websocket_endpoint() -> Optional[Union[WebSocketServer, WebSocketClient]]:
    """获取当前活跃的 WebSocket 端点（Server 或 Client）"""
    if websocket_client is not None and websocket_client.is_running():
        return websocket_client
    if websocket_server is not None and websocket_server.is_running():
        return websocket_server
    if websocket_client is not None:
        return websocket_client
    return websocket_server
