"""
WebSocket服务器模块

负责建立WebSocket服务器，处理连接和消息
"""

import asyncio
import json
import websockets
from typing import Dict, Any, Set, Optional

from mcdreforged.api.all import *

from queqiao_mcdr.config import Config

class WebSocketServer:
    """WebSocket服务器类"""
    
    def __init__(self, server: PluginServerInterface, host: str, port: int, path: str, api_handler, config: Config):
        """初始化WebSocket服务器"""
        self.server = server
        self.logger = server.logger
        self.host = host
        self.port = port
        self.path = path
        self.api_handler = api_handler
        self.config = config
        
        self.ws_server = None
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.authenticated_clients: Set[websockets.WebSocketServerProtocol] = set()
        self._running = False
    
    async def start(self):
        """启动WebSocket服务器"""
        if self._running:
            self.logger.info('WebSocket服务器已经在运行中')
            return
        
        try:
            # 使用自定义的连接处理器来处理认证
            self.ws_server = await websockets.serve(
                self.handle_client, 
                self.host, 
                self.port,
                process_request=self.process_request
            )
            self._running = True
            self.logger.info(f'WebSocket服务器已启动: ws://{self.host}:{self.port}{self.path}')
        except Exception as e:
            self.logger.error(f'启动WebSocket服务器失败: {e}')
            import traceback
            self.logger.error(traceback.format_exc())
    
    async def stop(self):
        """停止WebSocket服务器"""
        if not self._running:
            self.logger.debug('WebSocket服务器未在运行')
            return
        
        self.logger.info('开始停止WebSocket服务器...')
        
        try:
            self._running = False
            
            # 关闭所有客户端
            if self.clients:
                self.logger.debug(f'正在关闭 {len(self.clients)} 个客户端连接...')
                await asyncio.gather(
                    *[self._close_client_safe(client) for client in list(self.clients)],
                    return_exceptions=True
                )
                self.clients.clear()
                self.authenticated_clients.clear()
                self.logger.debug('所有客户端连接已关闭')
            
            # 关闭WebSocket服务器
            if self.ws_server:
                self.logger.debug('正在关闭WebSocket服务器...')
                self.ws_server.close()
                
                try:
                    await asyncio.wait_for(self.ws_server.wait_closed(), timeout=5.0)
                    self.logger.debug('WebSocket服务器已完全关闭')
                except asyncio.TimeoutError:
                    self.logger.warning('等待WebSocket服务器关闭超时')
                
                self.ws_server = None
            
            self.logger.info('WebSocket服务器已停止')
        except Exception as e:
            self.logger.error(f'停止WebSocket服务器失败: {e}')
            self._force_cleanup()
    
    async def _close_client_safe(self, client):
        """安全关闭客户端连接"""
        try:
            if not client.closed:
                await client.close(code=1001, reason='Server shutting down')
        except Exception as e:
            self.logger.debug(f'关闭客户端连接时出错: {e}')
    
    def _force_cleanup(self):
        """强制清理资源"""
        self._running = False
        self.ws_server = None
        self.clients.clear()
        self.authenticated_clients.clear()
    
    def is_running(self) -> bool:
        """检查WebSocket服务器是否正在运行"""
        return self._running
    
    async def process_request(self, connection, request):
        """处理WebSocket连接请求，在握手阶段进行认证"""
        client_info = f'{connection.remote_address[0]}:{connection.remote_address[1]}'
        
        # 检查路径
        if request.path != self.path:
            self.logger.warning(f'客户端路径不匹配，期望: {self.path}, 实际: {request.path}')
            return connection.respond(
                status=400,
                headers=[],
                body=b'Invalid path'
            )
        
        # 如果没有配置访问令牌，则跳过认证
        if not self.config.access_token:
            self.logger.debug(f'未配置访问令牌，跳过客户端认证: {client_info}')
            return None  # 允许连接
        
        # 获取Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            self.logger.warning(f'客户端未提供Authorization header: {client_info}')
            return connection.respond(
                status=401,
                headers=[('WWW-Authenticate', 'Bearer')],
                body=b'Missing Authorization header'
            )
        
        # 解析Bearer token
        if not auth_header.startswith('Bearer '):
            self.logger.warning(f'客户端Authorization header格式错误: {client_info}')
            return connection.respond(
                status=401,
                headers=[('WWW-Authenticate', 'Bearer')],
                body=b'Invalid Authorization header format'
            )
        
        token = auth_header[7:]  # 移除'Bearer '前缀
        
        # 验证访问令牌
        if token == self.config.access_token:
            self.logger.debug(f'客户端认证成功: {client_info}')
            return None  # 允许连接
        else:
            self.logger.warning(f'客户端访问令牌无效: {client_info}')
            return connection.respond(
                status=401,
                headers=[('WWW-Authenticate', 'Bearer')],
                body=b'Invalid access token'
            )
    
    async def broadcast_event(self, event_data: Dict[str, Any]):
        """广播事件给所有已认证的客户端"""
        if not self.authenticated_clients:
            return
        
        try:
            message = json.dumps(event_data)
            await asyncio.gather(
                *[client.send(message) for client in self.authenticated_clients], 
                return_exceptions=True
            )
            
            self.logger.debug(f'广播事件: {event_data}')
        except Exception as e:
            self.logger.error(f'广播事件失败: {e}')
    
    async def handle_client(self, websocket):
        """处理WebSocket客户端连接"""
        client_info = f'{websocket.remote_address[0]}:{websocket.remote_address[1]}'
        
        # 添加客户端到列表（认证已在握手阶段完成）
        self.clients.add(websocket)
        self.authenticated_clients.add(websocket)
        self.logger.info(f'客户端已连接并认证: {client_info}，当前连接数: {len(self.clients)}')
        
        try:
            # 开始处理消息
            async for message in websocket:
                await self.process_message(websocket, message)
                
        except websockets.exceptions.ConnectionClosed:
            self.logger.info(f'客户端连接已关闭: {client_info}')
        except websockets.exceptions.ConnectionClosedError:
            self.logger.info(f'客户端连接异常关闭: {client_info}')
        except Exception as e:
            self.logger.error(f'处理客户端连接时出错: {e}')
        finally:
            # 清理客户端
            if websocket in self.clients:
                self.clients.remove(websocket)
            if websocket in self.authenticated_clients:
                self.authenticated_clients.remove(websocket)
            self.logger.info(f'客户端已断开: {client_info}，当前连接数: {len(self.clients)}，已认证连接数: {len(self.authenticated_clients)}')
    

    
    async def process_message(self, websocket, message):
        """处理接收到的消息"""
        try:
            data = json.loads(message)
            
            self.logger.debug(f'收到消息: {data}')
            
            # 路由消息到处理器
            response = await self._route_message(data)
            await websocket.send(json.dumps(response))
                
        except json.JSONDecodeError:
            self.logger.warning(f'收到无效的JSON消息: {message}')
            await self._send_error_response(websocket, '无效的JSON格式，请发送有效的JSON消息')
        except Exception as e:
            self.logger.error(f'处理消息时出错: {e}')
            await self._send_error_response(websocket, f'消息处理错误: {str(e)}')
    
    async def _route_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """路由消息到相应的处理器"""
        if 'api' in data:
            return await self._handle_api_request(data)
        else:
            return self._handle_echo(data)
    

    
    async def _handle_api_request(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理API请求"""
        api_name = data['api']
        api_data = data.get('data', {})
        echo = data.get('echo')
        
        return await self.api_handler.handle_api_request(api_name, api_data, echo)
    
    def _handle_echo(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理回显消息"""
        return {
            'type': 'echo',
            'message': '收到你的消息',
            'original': data
        }
    
    async def _send_error_response(self, websocket, error_message: str):
        """发送错误响应"""
        try:
            error_response = {
                'type': 'error',
                'message': error_message
            }
            await websocket.send(json.dumps(error_response))
        except:
            pass  # 如果发送失败，忽略错误
