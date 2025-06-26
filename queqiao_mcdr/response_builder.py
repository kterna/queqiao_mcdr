"""
响应构建器模块

提供统一的JSON响应格式构建方法，减少代码重复
"""

from typing import Dict, Any, Optional, List


class ResponseBuilder:
    """响应构建器类，提供统一的JSON响应格式"""
    
    @staticmethod
    def api_success(message: str, echo: Optional[str] = None, data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        创建API成功响应
        
        Args:
            message: 成功消息
            echo: 回显标识
            data: 附加数据
            
        Returns:
            Dict[str, Any]: 成功响应对象
        """
        response = {
            'status': 'ok',
            'message': message,
            'echo': echo
        }
        if data:
            response['data'] = data
        return response
    
    @staticmethod
    def api_error(message: str, echo: Optional[str] = None) -> Dict[str, Any]:
        """
        创建API错误响应
        
        Args:
            message: 错误消息
            echo: 回显标识
            
        Returns:
            Dict[str, Any]: 错误响应对象
        """
        return {
            'status': 'failed',
            'message': message,
            'echo': echo
        }
    
    @staticmethod
    def websocket_error(message: str) -> Dict[str, Any]:
        """
        创建WebSocket错误响应
        
        Args:
            message: 错误消息
            
        Returns:
            Dict[str, Any]: WebSocket错误响应对象
        """
        return {
            'type': 'error',
            'message': message
        }
    
    @staticmethod
    def websocket_echo(message: str, original_data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        创建WebSocket回显响应
        
        Args:
            message: 回显消息
            original_data: 原始数据
            
        Returns:
            Dict[str, Any]: WebSocket回显响应对象
        """
        response = {
            'type': 'echo',
            'message': message
        }
        if original_data:
            response['original'] = original_data
        return response
    
    @staticmethod
    def base_event(server_name: str, server_version: str, server_type: str, 
                   post_type: str, sub_type: Optional[str] = None) -> Dict[str, Any]:
        """
        创建基础事件结构
        
        Args:
            server_name: 服务器名称
            server_version: 服务器版本
            server_type: 服务器类型
            post_type: 事件类型
            sub_type: 事件子类型
            
        Returns:
            Dict[str, Any]: 基础事件对象
        """
        # 根据sub_type生成event_name，格式为MCDR + 首字母大写的sub_type
        event_name = ''
        if sub_type:
            if sub_type == 'player_command':
                event_name = 'MCDRPlayer_command'
            else:
                event_name = f'MCDR{sub_type.capitalize()}'
        
        return {
            'server_name': server_name,
            'server_version': server_version,
            'server_type': server_type,
            'post_type': post_type,
            'sub_type': sub_type,
            'event_name': event_name
        }
    
    @staticmethod
    def player_data(nickname: str, uuid: str = '', is_op: Optional[bool] = None, 
                    dimension: Optional[str] = None, coordinate: Optional[Dict] = None,
                    permission_level: int = 0) -> Dict[str, Any]:
        """
        创建玩家数据结构
        
        Args:
            nickname: 玩家昵称
            uuid: 玩家UUID
            is_op: 是否为OP
            dimension: 所在维度
            coordinate: 坐标信息
            permission_level: 权限等级
            
        Returns:
            Dict[str, Any]: 玩家数据对象
        """
        return {
            'nickname': nickname,
            'uuid': uuid,
            'is_op': is_op,
            'dimension': dimension,
            'coordinate': coordinate,
            'permission_level': permission_level,
        }
    
    @staticmethod
    def coordinate_data(x: Optional[float] = None, y: Optional[float] = None, 
                       z: Optional[float] = None) -> Dict[str, Any]:
        """
        创建坐标数据结构
        
        Args:
            x: X坐标
            y: Y坐标
            z: Z坐标
            
        Returns:
            Dict[str, Any]: 坐标数据对象
        """
        return {
            'x': x,
            'y': y,
            'z': z
        }
    
    @staticmethod
    def player_list_data(players: List[Dict], count: int, max_players: Optional[int] = None) -> Dict[str, Any]:
        """
        创建玩家列表数据结构
        
        Args:
            players: 玩家列表
            count: 玩家数量
            max_players: 最大玩家数
            
        Returns:
            Dict[str, Any]: 玩家列表数据对象
        """
        return {
            'players': players,
            'count': count,
            'max_players': max_players
        } 