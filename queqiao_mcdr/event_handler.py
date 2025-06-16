"""
事件处理模块

负责监听MCDR事件并转换为QueQiao格式
"""

import json
import threading
from typing import Dict, Any, Optional, List
import asyncio

from mcdreforged.api.all import *

from queqiao_mcdr.config import Config
from queqiao_mcdr.message_formatter import MessageFormatter

class EventHandler:
    """事件处理器类"""
    
    def __init__(self, server: PluginServerInterface, config: Config, api_handler):
        """
        初始化事件处理器
        
        Args:
            server: MCDR服务器接口
            config: 配置对象
            api_handler: API处理器
        """
        self.server = server
        self.logger = server.logger
        self.config = config
        self.api_handler = api_handler
    
    def register_events(self):
        """注册MCDR事件监听器"""
        self.server.register_event_listener(MCDRPluginEvents.PLAYER_JOINED, self.on_player_joined)
        self.server.register_event_listener(MCDRPluginEvents.PLAYER_LEFT, self.on_player_left)
        self.server.register_event_listener(MCDRPluginEvents.USER_INFO, self.on_user_info)
        self.server.register_event_listener(MCDRPluginEvents.GENERAL_INFO, self.on_server_info)
    
    def on_player_joined(self, server: PluginServerInterface, player: str, info: Info):
        """
        处理玩家加入事件
        
        Args:
            server: MCDR服务器接口
            player: 玩家名称
            info: 信息对象
        """
        try:
            # 创建BaseJoinEvent
            event_data = self.create_base_event('notice', 'join')
            
            # 获取玩家对象
            player_obj = None
            try:
                minecraft_data_api = server.get_plugin_instance('minecraft_data_api')
                if minecraft_data_api is not None:
                    player_obj = minecraft_data_api.get_player_info(player)
            except:
                pass  # minecraft_data_api插件不存在或方法不存在
            
            player_data = self.create_player_data(player, player_obj)
            
            # 添加玩家信息
            event_data['player'] = player_data
            
            # 异步获取位置信息后再发送完整事件
            self._send_event_with_location(event_data, player)
            
            self.logger.debug(f'玩家加入事件: {player}')
        except Exception as e:
            self.logger.error(f'处理玩家加入事件时出错: {e}')
            import traceback
            self.logger.error(traceback.format_exc())
    
    def on_player_left(self, server: PluginServerInterface, player: str):
        """
        处理玩家离开事件
        
        Args:
            server: MCDR服务器接口
            player: 玩家名称
        """
        try:
            # 创建BaseQuitEvent
            event_data = self.create_base_event('notice', 'quit')
            
            # 创建玩家数据（玩家已离开，可能无法获取完整信息）
            player_data = {
                'nickname': player,
                'uuid': '',  # 玩家已离开，可能无法获取UUID
                'is_op': False  # 默认值
            }
            
            # 添加玩家信息
            event_data['player'] = player_data
            
            # 广播事件
            self.broadcast_event(event_data)
            
            self.logger.debug(f'玩家离开事件: {player}')
        except Exception as e:
            self.logger.error(f'处理玩家离开事件时出错: {e}')
            import traceback
            self.logger.error(traceback.format_exc())
    
    def on_user_info(self, server: PluginServerInterface, info: Info):
        """
        处理用户消息事件
        
        Args:
            server: MCDR服务器接口
            info: 信息对象
        """
        try:
            # 忽略MCDR命令
            if info.content.startswith('!!'):
                return
            
            # 判断是否为命令
            is_command = info.content.startswith('/')
            
            # 创建事件数据
            if is_command:
                # 创建BasePlayerCommandEvent
                event_data = self.create_base_event('message', 'player_command')
                sub_type = 'player_command'
            else:
                # 创建BaseChatEvent
                event_data = self.create_base_event('message', 'chat')
                sub_type = 'chat'
            
            # 获取玩家对象
            player_obj = None
            try:
                minecraft_data_api = server.get_plugin_instance('minecraft_data_api')
                if minecraft_data_api is not None:
                    player_obj = minecraft_data_api.get_player_info(info.player)
            except:
                pass  # minecraft_data_api插件不存在或方法不存在
            
            player_data = self.create_player_data(info.player, player_obj)
            
            # 添加玩家信息和消息内容
            event_data['player'] = player_data
            event_data['message'] = info.content
            
            # 异步获取位置信息后再发送完整事件
            self._send_event_with_location(event_data, info.player)
            
            self.logger.debug(f'用户{sub_type}事件: {info.player} - {info.content}')
        except Exception as e:
            self.logger.error(f'处理用户消息事件时出错: {e}')
            import traceback
            self.logger.error(traceback.format_exc())
    
    def on_server_info(self, server: PluginServerInterface, info: Info):
        """
        处理服务器消息事件
        
        Args:
            server: MCDR服务器接口
            info: 信息对象
        """
        try:
            # 检查是否为死亡消息
            if self.is_death_message(info.content):
                # 解析死亡消息
                player_name = self.extract_player_from_death_message(info.content)
                if player_name:
                    # 创建BaseDeathEvent
                    event_data = self.create_base_event('message', 'death')
                    
                    # 获取玩家对象
                    player_obj = None
                    try:
                        minecraft_data_api = server.get_plugin_instance('minecraft_data_api')
                        if minecraft_data_api is not None:
                            player_obj = minecraft_data_api.get_player_info(player_name)
                    except:
                        pass  # minecraft_data_api插件不存在或方法不存在
                    
                    player_data = self.create_player_data(player_name, player_obj)
                    
                    # 添加玩家信息和死亡消息
                    event_data['player'] = player_data
                    event_data['message'] = info.content
                    
                    # 异步获取位置信息后再发送完整事件
                    self._send_event_with_location(event_data, player_name)
                    
                    self.logger.debug(f'玩家死亡事件: {player_name} - {info.content}')
        except Exception as e:
            self.logger.error(f'处理服务器消息事件时出错: {e}')
            import traceback
            self.logger.error(traceback.format_exc())
    
    def create_base_event(self, post_type: str, sub_type: Optional[str] = None) -> Dict[str, Any]:
        """创建基础事件结构"""
        # 根据sub_type生成event_name，格式为MCDR + 首字母大写的sub_type
        event_name = ''
        if sub_type:
            if sub_type == 'player_command':
                event_name = 'MCDRPlayer_command'
            else:
                event_name = f'MCDR{sub_type.capitalize()}'
        
        return {
            'server_name': self.config.server_name,
            'server_version': self.get_server_version(),
            'server_type': self.config.server_type,
            'post_type': post_type,
            'sub_type': sub_type,
            'event_name': event_name
        }
    
    def create_player_data(self, player_name: str, player_obj: Optional[Any] = None) -> Dict[str, Any]:
        """创建玩家数据"""
        player_data = {
            'nickname': player_name,
            'uuid': '',
            'is_op': False,
            'dimension': None,
            'coordinate': None
        }
        
        # 获取UUID（只从玩家对象获取，不自动生成）
        if player_obj and hasattr(player_obj, 'uuid'):
            player_data['uuid'] = str(player_obj.uuid)
        elif player_obj and hasattr(player_obj, 'UUID'):
            player_data['uuid'] = str(player_obj.UUID)
        
        player_data['is_op'] = None
        
        return player_data
    
    def get_server_version(self) -> str:
        """获取服务器版本"""
        try:
            version_api = self.server.get_plugin_instance('minecraft_data_api')
            if version_api:
                return version_api.get_server_version()
        except:
            pass
        return "unknown"
    
    def is_death_message(self, message: str) -> bool:
        """检查是否为死亡消息"""
        death_keywords = [
            "was slain", "was shot", "was killed", "drowned", "blew up", 
            "hit the ground", "fell from", "burned to death", "tried to swim in lava",
            "fell out of the world", "withered away", "suffocated"
        ]
        
        return any(keyword in message for keyword in death_keywords)
    
    def extract_player_from_death_message(self, message: str) -> Optional[str]:
        """从死亡消息中提取玩家名称"""
        parts = message.split(' ')
        return parts[0] if len(parts) > 1 else None
    
    def broadcast_event(self, event_data: Dict[str, Any]):
        """广播事件"""
        def async_runner():
            try:
                from queqiao_mcdr import get_websocket_server
                ws_server = get_websocket_server()
                if ws_server and ws_server.is_running():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(ws_server.broadcast_event(event_data))
                    finally:
                        loop.close()
            except:
                pass
        
        import threading
        threading.Thread(target=async_runner, daemon=True).start()
    
    def _send_event_with_location(self, event_data: Dict[str, Any], player_name: str):
        """发送包含位置信息的完整事件"""
        def send_complete_event():
            try:
                minecraft_data_api = self.server.get_plugin_instance('minecraft_data_api')
                if minecraft_data_api:
                    # 获取维度
                    try:
                        dimension = minecraft_data_api.get_player_dimension(player_name, timeout=1.5)
                        if dimension is not None:
                            event_data['player']['dimension'] = dimension
                    except Exception as e:
                        self.logger.error(f'获取玩家 {player_name} 维度信息失败: {e}')
                    
                    # 获取坐标
                    try:
                        coordinate = minecraft_data_api.get_player_coordinate(player_name, timeout=1.5)
                        if coordinate:
                            event_data['player']['coordinate'] = {
                                'x': getattr(coordinate, 'x', None),
                                'y': getattr(coordinate, 'y', None),
                                'z': getattr(coordinate, 'z', None)
                            }
                    except Exception as e:
                        self.logger.error(f'获取玩家 {player_name} 坐标信息失败: {e}')
                else:
                    self.logger.warning('minecraft_data_api 插件实例获取失败')
                
                self.broadcast_event(event_data)
            except Exception as e:
                self.logger.error(f'发送事件时出错: {e}')
                import traceback
                self.logger.error(traceback.format_exc())
                self.broadcast_event(event_data)
        
        # 在新线程中异步执行
        import threading
        threading.Thread(target=send_complete_event, daemon=True).start()


