"""
QueQiao MCDR插件入口文件

这个插件移植了QueQiao模组的功能，通过WebSocket协议连接不同的Minecraft服务器，
支持跨服务器的消息传递和事件处理。
"""

import os
import json
import asyncio
import threading
import time
from typing import Optional, Dict, Any, List

from mcdreforged.api.all import *

from queqiao_mcdr.config import Config
from queqiao_mcdr.websocket_server import WebSocketServer
from queqiao_mcdr.event_handler import EventHandler
from queqiao_mcdr.api_handler import ApiHandler
from queqiao_mcdr.command_handler import CommandHandler
from queqiao_mcdr.utils import get_server_version

# 插件元数据
PLUGIN_METADATA = {
    'id': 'queqiao_mcdr',
    'version': '1.1.0',
    'name': 'QueQiao MCDR',
    'description': '移植自QueQiao模组的MCDR插件，通过 WebSocket 实现跨服务器通信',
    'author': 'kterna',
    'link': 'https://github.com/kterna/QueQiao_MCDR',
    'dependencies': {
        'mcdreforged': '>=2.0.0'
    }
}

# 全局变量
config: Optional[Config] = None
websocket_server: Optional[WebSocketServer] = None
event_handler: Optional[EventHandler] = None
api_handler: Optional[ApiHandler] = None
command_handler: Optional[CommandHandler] = None
ws_thread: Optional[threading.Thread] = None
loop: Optional[asyncio.AbstractEventLoop] = None

def on_load(server: PluginServerInterface, prev_module):
    """
    插件加载时调用
    """
    global config, websocket_server, event_handler, api_handler, command_handler, ws_thread, loop
    
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
    
    # 如果配置了自动启动，则启动WebSocket服务器
    if config.auto_start:
        start_websocket_server(server)
    
    # 如果是从旧版本重载，尝试恢复状态
    if prev_module is not None and hasattr(prev_module, 'websocket_server') and prev_module.websocket_server is not None:
        server.logger.info('检测到插件重载，尝试恢复WebSocket服务器状态')
        start_websocket_server(server)
    
    server.logger.info(f'QueQiao MCDR 插件已加载，版本 {PLUGIN_METADATA["version"]}')

def on_unload(server: PluginServerInterface):
    """
    插件卸载时调用
    """
    global websocket_server, ws_thread, loop
    
    server.logger.info('开始卸载QueQiao MCDR插件...')
    
    # 总是尝试停止WebSocket服务器，无论状态如何
    try:
        if websocket_server is not None or ws_thread is not None or loop is not None:
            server.logger.info('发现WebSocket服务器资源，正在停止...')
            stop_websocket_server(server)
        else:
            server.logger.info('未发现WebSocket服务器资源')
    except Exception as e:
        server.logger.error(f'卸载时停止WebSocket服务器失败: {e}')
        import traceback
        server.logger.error(traceback.format_exc())
        # 强制清理
        _force_cleanup()
    
    server.logger.info('QueQiao MCDR 插件已卸载')

def on_info(server: PluginServerInterface, info: Info):
    """
    接收到服务器信息时调用
    """
    # 命令处理由CommandHandler负责
    if info.is_user and info.content.startswith('!!queqiao'):
        command_handler.on_command(server, info)

def start_websocket_server(server: PluginServerInterface):
    """
    启动WebSocket服务器
    """
    global websocket_server, ws_thread, loop, api_handler
    
    if websocket_server is not None and websocket_server.is_running():
        server.logger.info('WebSocket服务器已经在运行中')
        return
    
    try:
        # 创建WebSocket服务器
        websocket_server = WebSocketServer(
            server, 
            config.websocket_host, 
            config.websocket_port, 
            config.websocket_path,
            api_handler,
            config
        )
        
        # 在新线程中启动WebSocket服务器
        def run_websocket_server():
            global loop
            try:
                # 创建新的事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # 启动WebSocket服务器
                loop.run_until_complete(websocket_server.start())
                
                # 运行事件循环直到被停止
                loop.run_forever()
            except Exception as e:
                server.logger.error(f'WebSocket服务器线程异常: {e}')
                import traceback
                server.logger.error(traceback.format_exc())
            finally:
                # 清理事件循环
                try:
                    if loop and not loop.is_closed():
                        loop.close()
                except Exception as e:
                    server.logger.error(f'关闭事件循环时出错: {e}')
                finally:
                    loop = None
        
        ws_thread = threading.Thread(target=run_websocket_server, daemon=True, name="QueQiao-WebSocket")
        ws_thread.start()
        
        # 等待一小段时间确保服务器启动
        time.sleep(0.1)
        
        server.logger.info(f'WebSocket服务器已启动，监听地址: {config.websocket_host}:{config.websocket_port}{config.websocket_path}')
    except Exception as e:
        server.logger.error(f'启动WebSocket服务器失败: {e}')
        import traceback
        server.logger.error(traceback.format_exc())

def stop_websocket_server(server: PluginServerInterface):
    """
    停止WebSocket服务器
    """
    global websocket_server, ws_thread, loop
    
    if websocket_server is None:
        server.logger.info('WebSocket服务器未初始化')
        # 清理可能残留的线程和循环
        if ws_thread is not None and ws_thread.is_alive():
            server.logger.info('发现残留的WebSocket线程，正在清理...')
        if loop is not None:
            server.logger.info('发现残留的事件循环，正在清理...')
        _force_cleanup()
        return
    
    try:
        server.logger.info('开始停止WebSocket服务器...')
        
        # 1. 首先停止WebSocket服务器
        if loop is not None and not loop.is_closed():
            try:
                # 在事件循环中安全地停止服务器
                server.logger.debug('正在停止WebSocket服务器...')
                future = asyncio.run_coroutine_threadsafe(websocket_server.stop(), loop)
                future.result(timeout=8)  # 等待最多8秒
                server.logger.debug('WebSocket服务器已停止')
            except asyncio.TimeoutError:
                server.logger.warning('停止WebSocket服务器超时，继续强制停止')
            except Exception as e:
                server.logger.warning(f'停止WebSocket服务器时出错: {e}')
            
            # 2. 停止事件循环
            try:
                server.logger.debug('正在停止事件循环...')
                loop.call_soon_threadsafe(loop.stop)
            except Exception as e:
                server.logger.warning(f'停止事件循环时出错: {e}')
        
        # 3. 等待线程结束
        if ws_thread is not None and ws_thread.is_alive():
            server.logger.debug('等待WebSocket线程结束...')
            ws_thread.join(timeout=12)  # 等待最多12秒
            if ws_thread.is_alive():
                server.logger.warning('WebSocket服务器线程未能正常结束，可能需要重启MCDR')
        
        # 4. 清理全局变量
        _force_cleanup()
        
        server.logger.info('WebSocket服务器已完全停止')
    except Exception as e:
        server.logger.error(f'停止WebSocket服务器失败: {e}')
        import traceback
        server.logger.error(traceback.format_exc())
        
        # 强制清理
        server.logger.warning('尝试强制清理WebSocket服务器资源')
        _force_cleanup()

def _force_cleanup():
    """强制清理所有WebSocket相关资源"""
    global websocket_server, ws_thread, loop
    
    websocket_server = None
    ws_thread = None
    loop = None

def get_websocket_server() -> Optional[WebSocketServer]:
    """
    获取WebSocket服务器实例
    
    Returns:
        Optional[WebSocketServer]: WebSocket服务器实例，如果不存在则返回None
    """
    global websocket_server
    return websocket_server
