"""
API处理模块

负责处理外部API调用请求
"""

import json
import asyncio
from typing import Dict, Any, Optional, Callable, Coroutine, List

from mcdreforged.api.all import *

from queqiao_mcdr.config import Config
from queqiao_mcdr.message_formatter import MessageFormatter
from queqiao_mcdr.response_builder import ResponseBuilder

class ApiHandler:
    """API处理器类"""
    
    def __init__(self, server: PluginServerInterface, config: Config):
        """
        初始化API处理器
        
        Args:
            server: MCDR服务器接口
            config: 配置对象
        """
        self.server = server
        self.logger = server.logger
        self.config = config
        
        # API方法映射
        self.api_methods = {
            'broadcast': self.broadcast,
            'send_msg': self.broadcast,
            'send_private_msg': self.send_private_msg,
            'send_title': self.send_title,
            'send_actionbar': self.send_actionbar,
            'get_player_list': self.get_player_list,
            'get_player_info': self.get_player_info
        }
    

    

    
    def _get_player_list_via_api(self) -> Dict:
        """通过minecraft_data_api获取玩家列表"""
        player_list_result = self._call_minecraft_data_api_safe('get_server_player_list', timeout=5.0)
        if not player_list_result:
            raise Exception("API返回空数据")
        
        players = []
        for player in player_list_result.players:
            player_name = player.name if hasattr(player, 'name') else str(player)
            player_uuid = str(player.uuid) if hasattr(player, 'uuid') else ''
            
            players.append(ResponseBuilder.player_data(
                nickname=player_name,
                uuid=player_uuid,
                permission_level=0,
            ))
        
        return ResponseBuilder.player_list_data(
            players=players, 
            count=len(players), 
            max_players=getattr(player_list_result, 'limit', None)
        )
    


    async def handle_api_request(self, api_name: str, api_data: Dict[str, Any], echo: Optional[str] = None) -> Dict[str, Any]:
        """处理API请求"""
        if api_name not in self.api_methods:
            return self._error_response(f'Unknown API: {api_name}', echo)
        
        try:
            method = self.api_methods[api_name]
            return await method(api_data, echo)
        except Exception as e:
            self.logger.error(f'处理API请求时出错: {e}')
            import traceback
            self.logger.error(traceback.format_exc())
            return self._error_response(f'API error: {str(e)}', echo)
    
    def _success_response(self, message: str, echo: Optional[str] = None, data: Optional[Dict] = None) -> Dict[str, Any]:
        """创建成功响应"""
        return ResponseBuilder.api_success(message=message, echo=echo, data=data)
    
    def _error_response(self, message: str, echo: Optional[str] = None) -> Dict[str, Any]:
        """创建错误响应"""
        return ResponseBuilder.api_error(message=message, echo=echo)
    
    def _find_player(self, uuid: Optional[str] = None, nickname: Optional[str] = None) -> Optional[str]:
        """查找玩家名称"""
        if nickname:
            return nickname
        if not uuid:
            return None

        # 通过 minecraft_data_api 的在线玩家列表从 UUID 反查玩家名
        try:
            player_list_result = self._call_minecraft_data_api_safe('get_server_player_list', timeout=3.0)
            if not player_list_result or not getattr(player_list_result, 'players', None):
                return None

            uuid_lower = str(uuid).lower()
            for player in player_list_result.players:
                player_uuid = getattr(player, 'uuid', None)
                if player_uuid is None:
                    continue
                if str(player_uuid).lower() == uuid_lower:
                    player_name = getattr(player, 'name', None)
                    return str(player_name) if player_name else None
        except Exception:
            return None

        return None
    
    def _format_message_for_command(self, message) -> str:
        """格式化消息用于命令"""
        formatted = MessageFormatter.format_message(message)
        if hasattr(formatted, 'to_json_str'):
            return formatted.to_json_str()
        return f'{{"text":"{formatted}"}}'
    
    def _get_player_detail_info(self, player_name: str) -> Dict[str, Any]:
        """获取玩家详细信息"""
        player_data = ResponseBuilder.player_data(nickname=player_name)
        
        # 获取权限信息
        try:
            # 获取MCDR权限等级
            mcdr_server = self.server.get_mcdr_server()
            permission_manager = mcdr_server.permission_manager
            permission_level = permission_manager.get_player_permission_level(player_name)
            player_data['permission_level'] = permission_level
            
        except:
            pass
        
        # 获取在线状态和位置信息
        try:
            player_list_result = self._call_minecraft_data_api_safe('get_server_player_list', timeout=3.0)
            if player_list_result:
                for p in player_list_result.players:
                    p_name = p.name if hasattr(p, 'name') else str(p)
                    if p_name == player_name:
                        player_data['uuid'] = str(p.uuid) if hasattr(p, 'uuid') else ''
                        self._get_player_location_info(player_name, player_data)
                        break
        except:
            pass
            
        return player_data
    
    def _get_player_location_info(self, player_name: str, player_data: Dict):
        """获取玩家位置信息"""
        # 获取维度
        dimension = self._call_minecraft_data_api_safe('get_player_dimension', player_name, timeout=2.0)
        if dimension is not None:
            player_data['dimension'] = dimension
            
        # 获取坐标
        coordinate = self._call_minecraft_data_api_safe('get_player_coordinate', player_name, timeout=2.0)
        if coordinate:
            player_data['coordinate'] = ResponseBuilder.coordinate_data(
                x=getattr(coordinate, 'x', None),
                y=getattr(coordinate, 'y', None),
                z=getattr(coordinate, 'z', None)
            )

    async def broadcast(self, data: Dict[str, Any], echo: Optional[str] = None) -> Dict[str, Any]:
        """广播消息"""
        message = data.get('message')
        if not message:
            return self._error_response('Missing message parameter', echo)
        
        try:
            formatted_message = MessageFormatter.format_message(message)
            self.server.broadcast(formatted_message)
            return self._success_response('Message broadcasted', echo)
        except Exception as e:
            return self._error_response(f'Failed to broadcast message: {str(e)}', echo)
    
    async def send_private_msg(self, data: Dict[str, Any], echo: Optional[str] = None) -> Dict[str, Any]:
        """发送私聊消息"""
        uuid = data.get('uuid')
        nickname = data.get('nickname')
        message = data.get('message')
        
        if not message:
            return self._error_response('Missing message parameter', echo)
        if not uuid and not nickname:
            return self._error_response('Missing player identifier (uuid or nickname)', echo)
        
        try:
            player = self._find_player(uuid, nickname)
            if not player:
                return self._error_response('Player not found', echo)
            
            formatted_message = MessageFormatter.format_message(message)
            self.server.tell(player, formatted_message)
            
            return self._success_response(
                'Private message sent',
                echo,
                {'player': ResponseBuilder.player_data(nickname=player, uuid=uuid or '')}
            )
        except Exception as e:
            return self._error_response(f'Failed to send private message: {str(e)}', echo)
    
    async def send_title(self, data: Dict[str, Any], echo: Optional[str] = None) -> Dict[str, Any]:
        """发送标题"""
        title = data.get('title')
        if not title:
            return self._error_response('Missing title parameter', echo)
        
        try:
            subtitle = data.get('subtitle', '')
            fadein = data.get('fadein', 10)
            stay = data.get('stay', 70)
            fadeout = data.get('fadeout', 20)
            
            # 设置标题时间
            self.server.execute(f'title @a times {fadein} {stay} {fadeout}')
            
            # 发送标题
            title_cmd = f'title @a title {self._format_message_for_command(title)}'
            self.server.execute(title_cmd)
            
            # 发送副标题（如果有）
            if subtitle:
                subtitle_cmd = f'title @a subtitle {self._format_message_for_command(subtitle)}'
                self.server.execute(subtitle_cmd)
            
            return self._success_response('Title displayed', echo)
        except Exception as e:
            return self._error_response(f'Failed to display title: {str(e)}', echo)
    
    async def send_actionbar(self, data: Dict[str, Any], echo: Optional[str] = None) -> Dict[str, Any]:
        """发送动作栏消息"""
        message = data.get('message')
        if not message:
            return self._error_response('Missing message parameter', echo)
        
        try:
            actionbar_cmd = f'title @a actionbar {self._format_message_for_command(message)}'
            self.server.execute(actionbar_cmd)
            return self._success_response('Actionbar message displayed', echo)
        except Exception as e:
            return self._error_response(f'Failed to display actionbar message: {str(e)}', echo)
    
    async def get_player_list(self, data: Dict[str, Any], echo: Optional[str] = None) -> Dict[str, Any]:
        """获取在线玩家列表"""
        try:
            result = self._get_player_list_via_api()
            return self._success_response('Player list retrieved', echo, result)
        except Exception as e:
            return self._error_response(f'Failed to get player list: {str(e)}', echo)
    
    async def get_player_info(self, data: Dict[str, Any], echo: Optional[str] = None) -> Dict[str, Any]:
        """获取特定玩家的详细信息"""
        player_name = data.get('player_name')
        if not player_name:
            return self._error_response('Missing player_name parameter', echo)
        
        try:
            player_data = self._get_player_detail_info(player_name)
            return self._success_response(
                'Player info retrieved',
                echo,
                {'player': player_data}
            )
        except Exception as e:
            return self._error_response(f'Failed to get player info: {str(e)}', echo)
    
    def _call_minecraft_data_api_safe(self, method_name: str, *args, **kwargs):
        """调用minecraft_data_api方法"""
        minecraft_data_api = self.server.get_plugin_instance('minecraft_data_api')
        method = getattr(minecraft_data_api, method_name)
        return method(*args, **kwargs)
    

