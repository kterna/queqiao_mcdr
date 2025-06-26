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
        # 导入模块
        from queqiao_mcdr import start_websocket_server, websocket_server
        
        # 检查WebSocket服务器状态
        if websocket_server is not None and websocket_server.is_running():
            source.reply('WebSocket服务器已经在运行中')
            return
        
        # 启动WebSocket服务器
        start_websocket_server(self.server)
        source.reply('WebSocket服务器已启动')
    
    def on_command_stop(self, source: CommandSource):
        """
        处理stop命令
        
        Args:
            source: 命令源
        """
        # 导入模块
        from queqiao_mcdr import stop_websocket_server, websocket_server
        
        # 检查WebSocket服务器状态
        if websocket_server is None or not websocket_server.is_running():
            source.reply('WebSocket服务器未在运行')
            return
        
        # 停止WebSocket服务器
        stop_websocket_server(self.server)
        source.reply('WebSocket服务器已停止')
    
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
        # 导入模块
        from queqiao_mcdr import websocket_server
        
        # 获取WebSocket服务器状态
        is_running = websocket_server is not None and websocket_server.is_running()
        status = '运行中' if is_running else '已停止'
        
        # 获取连接数
        client_count = len(websocket_server.clients) if is_running else 0
        
        # 显示状态信息
        source.reply(f'WebSocket服务器状态: {status}')
        if is_running:
            source.reply(f'监听地址: {self.config.websocket_host}:{self.config.websocket_port}{self.config.websocket_path}')
            source.reply(f'当前连接数: {client_count}')
    
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
        source.reply(f'§7{self.prefix} status §f- 显示WebSocket服务器状态')
        
        # 只向有权限的用户显示管理命令
        if source.has_permission(self.permission['start']):
            source.reply(f'§7{self.prefix} start §f- 启动WebSocket服务器')
        if source.has_permission(self.permission['stop']):
            source.reply(f'§7{self.prefix} stop §f- 停止WebSocket服务器')
        if source.has_permission(self.permission['reload']):
            source.reply(f'§7{self.prefix} reload §f- 重新加载配置')
        if source.has_permission(self.permission['debug']):
            source.reply(f'§7{self.prefix} debug §f- 切换调试模式')
        
        source.reply('§6======================================')
