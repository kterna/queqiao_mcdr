# QueQiao MCDR 插件使用说明

## 1. 插件介绍

QueQiao MCDR是QueQiao mod的mcdr移植[https://github.com/17TheWord/QueQiao]，支持跨服务器的消息传递和事件处理。

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

### 4.1 基础格式

**请求格式：**
```json
{
  "api": "API名称",
  "data": { "参数": "值" },
  "echo": "可选的回声标识"
}
```

**响应格式：**
```json
{
  "status": "ok",
  "message": "操作成功",
  "data": { "结果数据": "值" },
  "echo": "原样返回的回声标识"
}
```

### 4.2 消息发送 API

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

### 4.3 数据查询 API

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

### 4.4 消息格式功能

#### 🎨 颜色示例
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

#### ✨ 样式示例
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

#### 🖱️ 点击事件示例
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

#### 💬 悬浮提示示例
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

#### 🎯 组合功能示例
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