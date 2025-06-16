"""
工具函数模块

提供日志记录、消息格式化等通用功能
"""

import os
import json
import uuid
from typing import Dict, Any, Optional

def get_server_version() -> str:
    """
    获取服务器版本
    
    Returns:
        str: 服务器版本
    """
    try:
        # 此处应该通过MCDR API获取服务器版本
        # 由于需要服务器实例，此函数通常在事件处理器中调用
        return "unknown"
    except:
        return "unknown"

def generate_uuid() -> str:
    """
    生成UUID
    
    Returns:
        str: UUID字符串
    """
    return str(uuid.uuid4())

def safe_json_dumps(obj: Any) -> str:
    """
    安全地将对象转换为JSON字符串
    
    Args:
        obj: 要转换的对象
    
    Returns:
        str: JSON字符串
    """
    try:
        return json.dumps(obj, ensure_ascii=False)
    except:
        return "{}"

def safe_json_loads(json_str: str) -> Any:
    """
    安全地解析JSON字符串
    
    Args:
        json_str: JSON字符串
    
    Returns:
        Any: 解析后的对象，如果解析失败则返回None
    """
    try:
        return json.loads(json_str)
    except:
        return None

def escape_minecraft_formatting(text: str) -> str:
    """
    转义Minecraft格式化代码
    
    Args:
        text: 原始文本
    
    Returns:
        str: 转义后的文本
    """
    # 替换§符号为\\u00A7
    return text.replace('§', '\\u00A7')

def unescape_minecraft_formatting(text: str) -> str:
    """
    反转义Minecraft格式化代码
    
    Args:
        text: 转义后的文本
    
    Returns:
        str: 原始文本
    """
    # 替换\\u00A7为§符号
    return text.replace('\\u00A7', '§')
