"""
命令处理模块

负责处理插件命令
"""

from typing import Dict, Any, List, Optional

from mcdreforged.api.all import *

from queqiao_mcdr.config import Config

class CommandHandler:
    """命令处理器类"""
    
    def __init__(self, server: PluginServerInterface, config: Config):
        """
        初始化命令处理器
        
        Args:
            server: MCDR服务器接口
            config: 配置对象
        """
        self.server = server
        self.logger = server.logger
        self.config = config
        
        # 命令前缀
        self.prefix = '!!queqiao'
        
        # 命令权限
        self.permission = {
            'help': 0,      # 所有人
            'status': 1,    # 玩家
            'start': 3,     # 管理员
            'stop': 3,      # 管理员
            'reload': 3,    # 管理员
            'debug': 3      # 管理员
        }
    
    def register_commands(self):
        """注册命令"""
        self.server.register_command(
            Literal(self.prefix).
            then(
                Literal('start').
                runs(lambda src: self.on_command_start(src)).
                requires(lambda src: src.has_permission(self.permission['start']))
            ).
            then(
                Literal('stop').
                runs(lambda src: self.on_command_stop(src)).
                requires(lambda src: src.has_permission(self.permission['stop']))
            ).
            then(
                Literal('reload').
                runs(lambda src: self.on_command_reload(src)).
                requires(lambda src: src.has_permission(self.permission['reload']))
            ).
            then(
                Literal('status').
                runs(lambda src: self.on_command_status(src)).
                requires(lambda src: src.has_permission(self.permission['status']))
            ).
            then(
                Literal('debug').
                then(
                    Literal('on').
                    runs(lambda src: self.on_command_debug(src, True))
                ).
                then(
                    Literal('off').
                    runs(lambda src: self.on_command_debug(src, False))
                ).
                runs(lambda src: self.on_command_debug_status(src)).
                requires(lambda src: src.has_permission(self.permission['debug']))
            ).

            then(
                Literal('help').
                runs(lambda src: self.on_command_help(src)).
                requires(lambda src: src.has_permission(self.permission['help']))
            ).
            runs(lambda src: self.on_command_help(src))
        )
    
    def on_command_start(self, source: CommandSource):
        """
        处理start命令
        
        Args:
            source: 命令源
        """
        from queqiao_mcdr import (
            start_websocket,
            websocket_server,
            websocket_client,
            config,
        )

        mode = config.mode if config else "server"
        if mode == "client":
            if websocket_client is not None and websocket_client.is_running():
                source.reply("WebSocket 客户端已经在运行中")
                return
            start_websocket(self.server)
            source.reply(f"WebSocket 客户端已启动 (mode=client, url={config.websocket_url})")
        else:
            if websocket_server is not None and websocket_server.is_running():
                source.reply("WebSocket 服务器已经在运行中")
                return
            start_websocket(self.server)
            source.reply("WebSocket 服务器已启动")

    def on_command_stop(self, source: CommandSource):
        """
        处理stop命令
        
        Args:
            source: 命令源
        """
        from queqiao_mcdr import (
            stop_websocket,
            websocket_server,
            websocket_client,
        )

        running = False
        if websocket_server is not None and websocket_server.is_running():
            running = True
        if websocket_client is not None and websocket_client.is_running():
            running = True

        if not running:
            source.reply("WebSocket 未在运行")
            return

        stop_websocket(self.server)
        source.reply("WebSocket 已停止")
    
    def on_command_reload(self, source: CommandSource):
        """
        处理reload命令
        
        Args:
            source: 命令源
        """
        # 重新加载配置
        if self.config.reload_config():
            source.reply('配置已重新加载')
        else:
            source.reply('重新加载配置失败，请检查日志')
    
    def on_command_status(self, source: CommandSource):
        """
        处理status命令
        
        Args:
            source: 命令源
        """
        from queqiao_mcdr import websocket_server, websocket_client

        mode = self.config.mode
        source.reply(f"连接模式: {mode}")

        if mode == "client":
            is_running = (
                websocket_client is not None and websocket_client.is_running()
            )
            is_connected = (
                websocket_client is not None and websocket_client.is_connected()
            )
            source.reply(f"WebSocket 客户端状态: {'运行中' if is_running else '已停止'}")
            source.reply(f"连接状态: {'已连接' if is_connected else '未连接'}")
            source.reply(f"目标地址: {self.config.websocket_url}")
            source.reply(f"server_name: {self.config.server_name}")
        else:
            is_running = (
                websocket_server is not None and websocket_server.is_running()
            )
            client_count = (
                len(websocket_server.clients) if is_running else 0
            )
            source.reply(f"WebSocket 服务器状态: {'运行中' if is_running else '已停止'}")
            if is_running:
                source.reply(
                    f"监听地址: {self.config.websocket_host}:"
                    f"{self.config.websocket_port}{self.config.websocket_path}"
                )
                source.reply(f"当前连接数: {client_count}")
    
    def on_command_debug(self, source: CommandSource, enable: bool):
        """
        处理debug命令
        
        Args:
            source: 命令源
            enable: 是否启用调试模式
        """
        source.reply(f'玩家数据调试功能已移除')
    
    def on_command_debug_status(self, source: CommandSource):
        """
        显示调试状态
        
        Args:
            source: 命令源
        """
        source.reply(f'玩家数据调试功能已移除')
    
    def on_command_help(self, source: CommandSource):
        """
        处理help命令
        
        Args:
            source: 命令源
        """
        # 显示帮助信息
        source.reply('§6========== QueQiao MCDR 帮助 ==========')
        source.reply(f'§7{self.prefix} help §f- 显示此帮助信息')
        source.reply(f'§7{self.prefix} status §f- 显示 WebSocket 状态（server/client）')

        # 只向有权限的用户显示管理命令
        if source.has_permission(self.permission['start']):
            source.reply(f'§7{self.prefix} start §f- 启动 WebSocket（按配置 mode）')
        if source.has_permission(self.permission['stop']):
            source.reply(f'§7{self.prefix} stop §f- 停止 WebSocket')
        if source.has_permission(self.permission['reload']):
            source.reply(f'§7{self.prefix} reload §f- 重新加载配置')
        if source.has_permission(self.permission['debug']):
            source.reply(f'§7{self.prefix} debug §f- 切换调试模式')

        source.reply('§6======================================')
