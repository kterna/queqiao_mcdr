"""
消息格式转换模块

负责在MCDR和QueQiao消息格式之间转换
"""

import json
import re
from typing import Dict, Any, List, Union, Optional

from mcdreforged.api.rtext import RText, RTextList, RColor, RStyle, RAction

class MessageFormatter:
    """消息格式转换器类"""
    
    @staticmethod
    def format_message(message) -> Union[str, RText, RTextList]:
        """
        将QueQiao消息格式转换为MCDR可用的格式
        
        Args:
            message: QueQiao消息对象或字符串
        
        Returns:
            Union[str, RText, RTextList]: 格式化后的消息
        """
        # 如果是字符串，直接返回
        if isinstance(message, str):
            return message
        
        # 如果是列表，处理每个元素并连接
        if isinstance(message, list):
            result = RTextList()
            for item in message:
                MessageFormatter._append_component(result, MessageFormatter._format_component(item))
            return result
        
        # 如果是字典，处理为组件
        if isinstance(message, dict):
            return MessageFormatter._format_component(message)
        
        # 其他类型，转为字符串
        return str(message)
    
    @staticmethod
    def _format_component(component: Dict[str, Any]) -> Union[RText, RTextList, str]:
        """
        格式化单个消息组件
        
        Args:
            component: 消息组件
        
        Returns:
            Union[RText, str]: 格式化后的组件
        """
        # 检查组件类型
        if not isinstance(component, dict):
            return str(component)

        # 兼容两种格式：
        # 1) 旧版 QueQiao: {"type": "text", "data": {...}}
        # 2) Queqiao V2 / 原生 Minecraft JSON 组件: {"text": "...", "color": "...", ...}
        is_wrapped_component = 'type' in component and 'data' in component
        comp_type = component.get('type', 'text') if is_wrapped_component else 'text'
        comp_data = component.get('data', {}) if is_wrapped_component else component
        
        # 处理文本组件
        if comp_type == 'text':
            text = comp_data.get('text', '')

            # 创建RText对象
            rtext = RText(text)
            
            # 设置颜色
            color = comp_data.get('color')
            if color:
                try:
                    rtext.set_color(MessageFormatter._parse_color(color))
                except:
                    pass
            
            # 设置样式
            styles = []
            if comp_data.get('bold'):
                styles.append(RStyle.bold)
            if comp_data.get('italic'):
                styles.append(RStyle.italic)
            if comp_data.get('underlined'):
                styles.append(RStyle.underlined)
            if comp_data.get('strikethrough'):
                styles.append(RStyle.strikethrough)
            if comp_data.get('obfuscated'):
                styles.append(RStyle.obfuscated)
            
            if styles:
                rtext.set_styles(styles)
            
            # 设置点击事件
            click_event = comp_data.get('click_event') or comp_data.get('clickEvent')
            if click_event and isinstance(click_event, dict):
                action = click_event.get('action')
                value = click_event.get('value')
                if action and value is not None:
                    rtext.set_click_event(MessageFormatter._parse_click_action(str(action)), str(value))
            
            # 设置悬浮事件
            hover_event = comp_data.get('hover_event') or comp_data.get('hoverEvent')
            if hover_event and isinstance(hover_event, dict):
                action = hover_event.get('action')
                action = action.lower() if isinstance(action, str) else action
                # v1 使用 value；v2 使用 contents（MessageBuilder 会规范化为 contents）
                hover_contents = None
                if 'contents' in hover_event:
                    hover_contents = hover_event.get('contents')
                elif 'value' in hover_event:
                    hover_contents = hover_event.get('value')
                elif 'text' in hover_event:
                    hover_contents = hover_event.get('text')

                if action == 'show_text' and hover_contents:
                    if isinstance(hover_contents, list):
                        hover_text = RTextList()
                        for item in hover_contents:
                            MessageFormatter._append_component(hover_text, MessageFormatter._format_component(item))
                        rtext.set_hover_text(hover_text)
                    elif isinstance(hover_contents, dict):
                        rtext.set_hover_text(MessageFormatter._format_component(hover_contents))
                    else:
                        rtext.set_hover_text(str(hover_contents))

            # 处理原生组件的 extra 字段
            extra = comp_data.get('extra')
            if isinstance(extra, list) and extra:
                result = RTextList()
                MessageFormatter._append_component(result, rtext)
                for item in extra:
                    MessageFormatter._append_component(result, MessageFormatter._format_component(item))
                return result

            return rtext
        
        # 其他类型，转为字符串
        return str(component)

    @staticmethod
    def _append_component(target: RTextList, component: Union[RText, RTextList, str]) -> None:
        """将组件安全追加到 RTextList，自动展开 RTextList"""
        if isinstance(component, RTextList):
            try:
                for item in component:
                    target.append(item)
            except Exception:
                target.append(component)
            return
        target.append(component)
    
    @staticmethod
    def _parse_color(color_name: str) -> RColor:
        """
        解析颜色名称为RColor
        
        Args:
            color_name: 颜色名称
        
        Returns:
            RColor: 对应的RColor
        """
        color_map = {
            'black': RColor.black,
            'dark_blue': RColor.dark_blue,
            'dark_green': RColor.dark_green,
            'dark_aqua': RColor.dark_aqua,
            'dark_red': RColor.dark_red,
            'dark_purple': RColor.dark_purple,
            'gold': RColor.gold,
            'gray': RColor.gray,
            'dark_gray': RColor.dark_gray,
            'blue': RColor.blue,
            'green': RColor.green,
            'aqua': RColor.aqua,
            'red': RColor.red,
            'light_purple': RColor.light_purple,
            'yellow': RColor.yellow,
            'white': RColor.white,
            
            # 别名
            'dark_grey': RColor.dark_gray,
            'grey': RColor.gray,
            'purple': RColor.light_purple,
            'magenta': RColor.light_purple
        }
        
        return color_map.get(color_name.lower(), RColor.white)
    
    @staticmethod
    def _parse_click_action(action_name: str) -> RAction:
        """
        解析点击动作名称为RAction
        
        Args:
            action_name: 动作名称
        
        Returns:
            RAction: 对应的RAction
        """
        action_map = {
            'open_url': RAction.open_url,
            'run_command': RAction.run_command,
            'suggest_command': RAction.suggest_command,
            'copy_to_clipboard': RAction.copy_to_clipboard
        }
        
        return action_map.get(action_name.lower(), RAction.suggest_command)
    
    @staticmethod
    def parse_message(message_str: str) -> Union[str, Dict[str, Any], List[Dict[str, Any]]]:
        """
        将字符串解析为QueQiao消息格式
        
        Args:
            message_str: 消息字符串
        
        Returns:
            Union[str, Dict[str, Any], List[Dict[str, Any]]]: 解析后的消息
        """
        # 检查是否为JSON格式
        try:
            data = json.loads(message_str)
            if isinstance(data, dict) and 'type' in data and 'data' in data:
                return data
            if isinstance(data, list):
                for item in data:
                    if not (isinstance(item, dict) and 'type' in item and 'data' in item):
                        return message_str
                return data
        except:
            pass
        
        # 简单文本，不需要特殊处理
        return message_str
