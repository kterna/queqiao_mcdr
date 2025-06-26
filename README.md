# QueQiao MCDR 插件使用说明

## 1. 插件介绍

QueQiao MCDR是[QueQiao mod](https://github.com/17TheWord/QueQiao)的mcdr移植，支持跨服务器的消息传递和事件处理。

## 2. 安装配置

### 2.1 依赖要求

- MCDReforged >= 2.0.0
- Python >= 3.8
- websockets >= 15.0.0

### 2.2 安装步骤

1. 将插件文件放入 `plugins` 目录
2. 重启或重载 MCDR
3. 编辑生成的配置文件
4. 重载插件或重启 MCDR

### 2.3 配置文件

插件会在 `config/queqiao_mcdr/config.json` 生成配置文件：

```json
{
  "websocket": {
    "host": "0.0.0.0",
    "port": 8080,
    "path": "/ws",
    "auto_start": true
  },
  "server": {
    "name": "MyServer",
    "type": "mcdr"
  },
  "security": {
    "access_token": ""
  }
}
```

#### 配置项说明

- **websocket**：WebSocket服务器配置
  - `host`：监听地址，默认为 `0.0.0.0`
  - `port`：监听端口，默认为 `8080`
  - `path`：WebSocket路径，默认为 `/ws`
  - `auto_start`：是否自动启动WebSocket服务器，默认为 `true`

- **server**：服务器信息配置
  - `name`：服务器名称，用于事件数据
  - `type`：服务器类型，默认为 `mcdr`

- **security**：安全配置
  - `access_token`：访问令牌，为空则不验证

## 3. 命令系统

| 命令                     | 权限等级 | 说明                    |
| ------------------------ | -------- | ----------------------- |
| `!!queqiao help`         | 0        | 显示帮助信息            |
| `!!queqiao status`       | 1        | 显示WebSocket服务器状态 |
| `!!queqiao start`        | 3        | 启动WebSocket服务器     |
| `!!queqiao stop`         | 3        | 停止WebSocket服务器     |
| `!!queqiao reload`       | 3        | 重新加载配置            |
| `!!queqiao debug on/off` | 3        | 切换调试模式            |

## 4. API 接口完整指南

### 4.1 消息发送 API

#### 📢 broadcast / send_msg - 广播消息
```json
{
  "api": "broadcast",
  "data": {
    "message": "Hello everyone!"
  }
}
```

#### 💬 send_private_msg - 私聊消息
```json
{
  "api": "send_private_msg",
  "data": {
    "nickname": "PlayerName",
    "message": "Hello player!"
  }
}
```

#### 🎯 send_title - 显示标题
```json
{
  "api": "send_title",
  "data": {
    "title": "主标题",
    "subtitle": "副标题",
    "fadein": 10,
    "stay": 70,
    "fadeout": 20
  }
}
```

#### ⚡ send_actionbar - 动作栏消息
```json
{
  "api": "send_actionbar",
  "data": {
    "message": "Action bar message"
  }
}
```

### 4.2 数据查询 API

#### 👥 get_player_list - 获取玩家列表
```json
{
  "api": "get_player_list",
  "data": {}
}
```

**响应示例：**
```json
{
  "status": "ok",
  "data": {
    "players": [
      {
        "nickname": "PlayerA",
        "uuid": "123e4567-e89b-12d3-a456-426614174000",
        "online": true,
        "dimension": "0",
        "coordinate": {"x": 100, "y": 64, "z": -200}
      }
    ],
    "count": 1,
    "max_players": 20
  }
}
```

#### 👤 get_player_info - 获取玩家信息
```json
{
  "api": "get_player_info",
  "data": {
    "player_name": "PlayerName"
  }
}
```

**响应示例：**
```json
{
  "status": "ok",
  "data": {
    "player": {
      "nickname": "PlayerName",
      "uuid": "123e4567-e89b-12d3-a456-426614174000",
      "online": true,
      "is_op": false,
      "permission_level": 1,
      "dimension": "0",
      "coordinate": {"x": 100, "y": 64, "z": -200}
    }
  }
}
```



## 5. 事件监听

插件会自动广播以下事件给所有已连接的客户端：

### 5.1 玩家加入事件
```json
{
  "server_name": "MyServer",
  "server_version": "1.21.1",
  "server_type": "mcdr",
  "post_type": "notice",
  "sub_type": "join",
  "event_name": "MCDRJoin",
  "player": {
    "nickname": "PlayerName",
    "uuid": "123e4567-e89b-12d3-a456-426614174000",
    "is_op": false,
    "dimension": "0",
    "coordinate": {"x": 100, "y": 64, "z": -200}
  }
}
```

### 5.2 玩家离开事件
```json
{
  "server_name": "MyServer",
  "server_version": "1.21.1",
  "server_type": "mcdr",
  "post_type": "notice",
  "sub_type": "quit",
  "event_name": "MCDRQuit",
  "player": {
    "nickname": "PlayerName",
    "uuid": "",
    "is_op": false
  }
}
```

### 5.3 聊天消息事件
```json
{
  "server_name": "MyServer",
  "server_version": "1.21.1", 
  "server_type": "mcdr",
  "post_type": "message",
  "sub_type": "chat",
  "event_name": "MCDRChat",
  "player": {
    "nickname": "PlayerName",
    "uuid": "123e4567-e89b-12d3-a456-426614174000",
    "is_op": false,
    "dimension": "0",
    "coordinate": {"x": 100, "y": 64, "z": -200}
  },
  "message": "Hello world!"
}
```

### 5.4 玩家命令事件
```json
{
  "server_name": "MyServer",
  "server_version": "1.21.1",
  "server_type": "mcdr", 
  "post_type": "message",
  "sub_type": "player_command",
  "event_name": "MCDRPlayer_command",
  "player": {
    "nickname": "PlayerName",
    "uuid": "123e4567-e89b-12d3-a456-426614174000",
    "is_op": false,
    "dimension": "0",
    "coordinate": {"x": 100, "y": 64, "z": -200}
  },
  "message": "/tp 0 64 0"
}
```

### 5.5 玩家死亡事件
```json
{
  "server_name": "MyServer",
  "server_version": "1.21.1",
  "server_type": "mcdr",
  "post_type": "message", 
  "sub_type": "death",
  "event_name": "MCDRDeath",
  "player": {
    "nickname": "PlayerName",
    "uuid": "123e4567-e89b-12d3-a456-426614174000",
    "is_op": false,
    "dimension": "0",
    "coordinate": {"x": 100, "y": 64, "z": -200}
  },
  "message": "PlayerName was slain by Zombie"
}
```

## 6. 消息格式功能

### 6.1 颜色示例
```json
{
  "api": "broadcast",
  "data": {
    "message": [
      {
        "type": "text",
        "data": {
          "text": "红色文字",
          "color": "red"
        }
      },
      {
        "type": "text", 
        "data": {
          "text": "蓝色文字",
          "color": "blue"
        }
      }
    ]
  }
}
```

### 6.2 样式示例
```json
{
  "api": "broadcast",
  "data": {
    "message": [
      {
        "type": "text",
        "data": {
          "text": "粗体",
          "bold": true
        }
      },
      {
        "type": "text",
        "data": {
          "text": "斜体",
          "italic": true
        }
      },
      {
        "type": "text",
        "data": {
          "text": "下划线",
          "underlined": true
        }
      }
    ]
  }
}
```

### 6.3 点击事件示例
```json
{
  "api": "broadcast",
  "data": {
    "message": [
      {
        "type": "text",
        "data": {
          "text": "点击执行命令",
          "color": "green",
          "click_event": {
            "action": "run_command",
            "value": "/spawn"
          }
        }
      },
      {
        "type": "text",
        "data": {
          "text": "点击打开网页",
          "color": "blue",
          "click_event": {
            "action": "open_url",
            "value": "https://minecraft.net"
          }
        }
      }
    ]
  }
}
```

### 6.4 悬浮提示示例
```json
{
  "api": "broadcast",
  "data": {
    "message": [
      {
        "type": "text",
        "data": {
          "text": "悬浮查看详情",
          "color": "yellow",
          "hover_event": {
            "action": "show_text",
            "value": "这是详细信息"
          }
        }
      }
    ]
  }
}
```

### 6.5 组合功能示例
```json
{
  "api": "send_private_msg",
  "data": {
    "nickname": "PlayerName",
    "message": [
      {
        "type": "text",
        "data": {
          "text": "[重要] ",
          "color": "red",
          "bold": true
        }
      },
      {
        "type": "text",
        "data": {
          "text": "点击加入QQ群",
          "color": "blue",
          "underlined": true,
          "click_event": {
            "action": "open_url",
            "value": "https://qm.qq.com/xxx"
          },
          "hover_event": {
            "action": "show_text",
            "value": "点击打开QQ群链接"
          }
        }
      }
    ]
  }
}
```