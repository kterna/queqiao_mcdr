"""
配置管理模块

负责加载、保存和管理插件配置
"""

import os
import json
from typing import Dict, Any, List, Optional

from mcdreforged.api.all import *

class Config:
    """配置管理类"""
    
    DEFAULT_CONFIG = {
        "websocket": {
            "host": "0.0.0.0",
            "port": 8080,
            "path": "/ws",
            "auto_start": True
        },
        "server": {
            "name": "MCDR Server",
            "type": "mcdr"
        },
        "security": {
            "access_token": ""
        }
    }
    
    def __init__(self, server: PluginServerInterface):
        """
        初始化配置管理器
        
        Args:
            server: MCDR服务器接口
        """
        self.server = server
        self.logger = server.logger
        self.config_path = os.path.join(server.get_data_folder(), 'config.json')
        self.config = self.DEFAULT_CONFIG.copy()
        
        # 配置属性
        self.websocket_host = "0.0.0.0"
        self.websocket_port = 8080
        self.websocket_path = "/ws"
        self.auto_start = True
        
        self.server_name = "MCDR Server"
        self.server_type = "mcdr"
        
        self.access_token = ""
    
    def load_config(self) -> bool:
        """
        加载配置文件
        
        Returns:
            bool: 是否成功加载配置
        """
        if not os.path.exists(self.config_path):
            self.logger.info('配置文件不存在，创建默认配置')
            self.save_config()
            self._apply_config()
            return True
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
            
            # 更新配置，保留默认值
            self._update_dict(self.config, loaded_config)
            self._apply_config()
            
            self.logger.info('配置文件加载成功')
            return True
        except Exception as e:
            self.logger.error(f'加载配置文件失败: {e}')
            self.logger.error('使用默认配置')
            self._apply_config()
            return False
    
    def save_config(self) -> bool:
        """
        保存配置文件
        
        Returns:
            bool: 是否成功保存配置
        """
        try:
            # 确保数据文件夹存在
            data_folder = self.server.get_data_folder()
            if not os.path.exists(data_folder):
                os.makedirs(data_folder)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            
            self.logger.info('配置文件保存成功')
            return True
        except Exception as e:
            self.logger.error(f'保存配置文件失败: {e}')
            return False
    
    def reload_config(self) -> bool:
        """
        重新加载配置文件
        
        Returns:
            bool: 是否成功重新加载配置
        """
        return self.load_config()
    
    def _apply_config(self):
        """应用配置到属性"""
        # WebSocket配置
        websocket_config = self.config.get('websocket', {})
        self.websocket_host = websocket_config.get('host', "0.0.0.0")
        self.websocket_port = websocket_config.get('port', 8080)
        self.websocket_path = websocket_config.get('path', "/ws")
        self.auto_start = websocket_config.get('auto_start', True)
        
        # 服务器配置
        server_config = self.config.get('server', {})
        self.server_name = server_config.get('name', "MCDR Server")
        self.server_type = server_config.get('type', "mcdr")
        
        # 安全配置
        security_config = self.config.get('security', {})
        self.access_token = security_config.get('access_token', "")
    
    def _update_dict(self, target: Dict[str, Any], source: Dict[str, Any]):
        """
        递归更新字典，保留默认值
        
        Args:
            target: 目标字典
            source: 源字典
        """
        for key, value in source.items():
            if key in target:
                if isinstance(value, dict) and isinstance(target[key], dict):
                    self._update_dict(target[key], value)
                else:
                    target[key] = value
