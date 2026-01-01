# 统一推送系统 - 使用指南

## 📋 目录

- [系统概述](#系统概述)
- [功能特性](#功能特性)
- [快速开始](#快速开始)
- [详细配置](#详细配置)
- [使用示例](#使用示例)
- [API参考](#api参考)
- [Web管理界面](#web管理界面)
- [故障排除](#故障排除)
- [最佳实践](#最佳实践)

## 🎯 系统概述

统一推送系统是一个功能强大、易于使用的多平台消息推送解决方案，支持钉钉、企业微信、邮件和自定义Webhook等多种推送渠道。系统提供了丰富的功能，包括图片推送、内容优化、频率控制、定时推送、实时监控等。

### 🏗️ 系统架构

```
统一推送系统
├── 核心推送引擎 (unified_push_system.py)
├── 图片处理模块 (enhanced_image_push.py)
├── 内容优化器 (push_content_optimizer.py)
├── 推送管理器 (push_manager_enhanced.py)
├── 平台扩展 (platform_extensions.py)
├── 用户体验优化 (user_experience_optimizer.py)
├── Web界面 (push_ui_enhanced.py)
└── 配置管理 (push_config_template.json)
```

## ✨ 功能特性

### 🚀 核心功能
- **多平台支持**: 钉钉、企业微信、邮件、Webhook
- **多种推送模式**: 立即推送、定时推送、批量推送、智能推送
- **图片推送**: 支持批量图片、压缩优化、Base64编码
- **内容优化**: 自动格式化、模板支持、优先级管理
- **频率控制**: 防重复、限流、智能调度

### 📊 管理功能
- **实时监控**: 推送状态、系统性能、错误统计
- **历史记录**: 完整的推送历史和统计分析
- **Web界面**: 直观的管理界面和实时状态展示
- **重试机制**: 智能重试和降级策略
- **定时任务**: 灵活的定时推送和批处理

### 🔧 高级功能
- **内容预览**: 推送前预览效果
- **统计分析**: 详细的推送效果分析
- **性能优化**: 并发处理、连接池、缓存
- **安全保障**: 数据加密、请求验证、敏感信息保护

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install requests pillow matplotlib seaborn pandas numpy flask flask-socketio
```

### 2. 配置系统

复制配置模板并修改：

```bash
cp push_config_template.json notification_config.json
```

编辑 `notification_config.json`，配置你的推送平台信息：

```json
{
  "platforms": {
    "dingtalk": {
      "enabled": true,
      "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN",
      "secret": "YOUR_SECRET"
    },
    "wechat": {
      "enabled": true,
      "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"
    }
  }
}
```

### 3. 基本使用

```python
import asyncio
from yquant.common.unified_push_system import quick_push

# 快速推送
async def main():
    response = await quick_push(
        title="📈 市场提醒",
        content="BTC价格突破$50,000！",
        platforms=["dingtalk", "wechat"],
        priority="high"
    )
    print(f"推送结果: {response.status.value}")

asyncio.run(main())
```

### 4. 运行演示

```bash
# 快速演示
python push_system_example.py quick

# 完整功能演示
python push_system_example.py full

# 启动Web管理界面
python push_system_example.py web
```

## ⚙️ 详细配置

### 平台配置

#### 钉钉机器人配置

1. 在钉钉群中添加自定义机器人
2. 获取Webhook URL和加签密钥
3. 配置到系统中：

```json
{
  "dingtalk": {
    "enabled": true,
    "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN",
    "secret": "YOUR_SECRET",
    "timeout": 30,
    "retry_attempts": 3
  }
}
```

#### 企业微信机器人配置

1. 在企业微信群中添加机器人
2. 获取Webhook URL
3. 配置到系统中：

```json
{
  "wechat": {
    "enabled": true,
    "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY",
    "timeout": 30,
    "retry_attempts": 3
  }
}
```

#### 邮件配置

```json
{
  "email": {
    "enabled": true,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "username": "your_email@gmail.com",
    "password": "your_app_password",
    "use_tls": true,
    "default_recipients": ["recipient@example.com"]
  }
}
```

### 系统配置

#### 频率控制

```json
{
  "frequency_control": {
    "enabled": true,
    "global_limits": {
      "max_per_minute": 10,
      "max_per_hour": 100
    },
    "content_deduplication": {
      "enabled": true,
      "time_window": 300,
      "similarity_threshold": 0.8
    }
  }
}
```

#### 图片处理

```json
{
  "image_processing": {
    "enabled": true,
    "compression": {
      "enabled": true,
      "quality": 85,
      "max_width": 1920,
      "max_height": 1080
    },
    "thumbnail": {
      "enabled": true,
      "size": [300, 200]
    }
  }
}
```

## 📝 使用示例

### 基本推送

```python
from yquant.common.unified_push_system import UnifiedPushSystem, UnifiedPushRequest, PushMode

# 创建系统实例
system = UnifiedPushSystem()

# 创建推送请求
request = UnifiedPushRequest(
    title="📊 交易信号",
    content="检测到买入信号：BTC/USDT",
    platforms=["dingtalk", "wechat"],
    priority="high",
    mode=PushMode.IMMEDIATE
)

# 执行推送
response = await system.push(request)
print(f"推送状态: {response.status.value}")
```

### 图片推送

```python
request = UnifiedPushRequest(
    title="📈 市场分析图表",
    content="今日市场走势分析",
    platforms=["dingtalk"],
    message_type="image",
    images=[
        "chart1.png",
        "chart2.png",
        "report.jpg"
    ],
    mode=PushMode.IMMEDIATE
)

response = await system.push(request)
```

### 定时推送

```python
from datetime import datetime, timedelta

# 设置1小时后推送
scheduled_time = datetime.now() + timedelta(hours=1)

request = UnifiedPushRequest(
    title="⏰ 定时提醒",
    content="这是一条定时推送消息",
    platforms=["dingtalk"],
    mode=PushMode.SCHEDULED,
    scheduled_time=scheduled_time
)

response = await system.push(request)
```

### 批量推送

```python
request = UnifiedPushRequest(
    title="📢 重要通知",
    content="系统维护通知",
    platforms=["dingtalk", "wechat", "email"],
    mode=PushMode.BATCH,
    priority="high"
)

response = await system.push(request)
```

### 使用模板

```python
from yquant.common.push_content_optimizer import PushContentOptimizer

# 创建内容优化器
optimizer = PushContentOptimizer()

# 使用模板创建消息
message = optimizer.create_message_from_template(
    template_name="market_alert",
    data={
        "symbol": "BTC/USDT",
        "price": 50000,
        "change": 5.2,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
)

request = UnifiedPushRequest(
    title=message["title"],
    content=message["content"],
    platforms=["dingtalk"],
    priority=message["priority"]
)
```

## 🌐 Web管理界面

### 启动Web界面

```python
from yquant.common.unified_push_system import create_push_system

# 创建系统
system = create_push_system()

# 启动Web界面
system.start_web_interface(
    host='127.0.0.1',
    port=5000,
    debug=False
)
```

### 功能说明

- **实时监控**: 查看推送状态、活动任务、系统性能
- **推送历史**: 浏览历史推送记录，支持筛选和搜索
- **统计分析**: 查看推送统计图表和趋势分析
- **手动推送**: 通过Web界面创建和发送推送
- **内容预览**: 推送前预览在各平台的显示效果
- **系统设置**: 配置推送参数和平台设置

### 访问地址

启动后访问: `http://127.0.0.1:5000`

## 🔧 API参考

### UnifiedPushSystem 类

#### 主要方法

```python
# 推送消息
async def push(request: UnifiedPushRequest) -> UnifiedPushResponse

# 预览推送内容
def preview_push(request: UnifiedPushRequest) -> Dict[str, str]

# 获取系统状态
def get_system_status() -> Dict

# 获取推送统计
def get_statistics(days: int = 7) -> Dict

# 获取活动任务
def get_active_tasks() -> List[Dict]

# 启动Web界面
def start_web_interface(host: str = '127.0.0.1', port: int = 5000)
```

### UnifiedPushRequest 数据类

```python
@dataclass
class UnifiedPushRequest:
    title: str                    # 推送标题
    content: str                  # 推送内容
    platforms: List[str]          # 目标平台列表
    message_type: str = "text"    # 消息类型
    priority: str = "medium"      # 优先级
    mode: PushMode = PushMode.IMMEDIATE  # 推送模式
    images: List[str] = None      # 图片路径列表
    scheduled_time: datetime = None  # 定时推送时间
    tags: List[str] = None        # 标签
    custom_data: Dict = None      # 自定义数据
```

### 便捷函数

```python
# 快速推送
async def quick_push(title: str, content: str, platforms: List[str], 
                    priority: str = "medium") -> UnifiedPushResponse

# 创建推送系统
def create_push_system(config_path: str = None, db_path: str = None) -> UnifiedPushSystem
```

## 🔍 故障排除

### 常见问题

#### 1. 推送失败

**问题**: 推送返回失败状态

**解决方案**:
- 检查网络连接
- 验证Webhook URL和密钥
- 查看错误日志
- 检查平台限制（频率、内容长度等）

#### 2. 图片推送失败

**问题**: 图片无法正常推送

**解决方案**:
- 检查图片文件是否存在
- 验证图片格式是否支持
- 检查图片大小是否超限
- 确认平台是否支持图片推送

#### 3. Web界面无法访问

**问题**: 无法打开Web管理界面

**解决方案**:
- 检查端口是否被占用
- 确认防火墙设置
- 查看启动日志
- 尝试更换端口

### 调试模式

启用调试模式获取详细日志：

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# 或在配置文件中设置
{
  "system": {
    "debug": true,
    "log_level": "DEBUG"
  }
}
```

### 日志分析

系统会记录详细的操作日志，包括：
- 推送请求和响应
- 错误信息和堆栈跟踪
- 性能指标
- 系统状态变化

## 💡 最佳实践

### 1. 配置管理

- 使用环境变量存储敏感信息
- 定期备份配置文件
- 为不同环境使用不同配置

```python
import os

config = {
    "dingtalk": {
        "webhook_url": os.getenv("DINGTALK_WEBHOOK_URL"),
        "secret": os.getenv("DINGTALK_SECRET")
    }
}
```

### 2. 错误处理

- 始终检查推送结果
- 实现适当的重试逻辑
- 记录失败原因用于分析

```python
response = await system.push(request)

if response.status != SystemPushStatus.SUCCESS:
    logger.error(f"推送失败: {response.error_message}")
    # 实现降级策略
```

### 3. 性能优化

- 使用批量推送减少API调用
- 合理设置并发数量
- 启用缓存和连接池
- 定期清理历史数据

### 4. 安全考虑

- 定期更新API密钥
- 限制推送频率防止滥用
- 验证推送内容防止注入
- 加密存储敏感信息

### 5. 监控和维护

- 定期检查推送成功率
- 监控系统性能指标
- 及时处理错误告警
- 定期备份数据

## 📞 技术支持

如果遇到问题或需要帮助，请：

1. 查看本文档的故障排除部分
2. 检查系统日志获取详细错误信息
3. 运行演示程序验证系统功能
4. 查看配置文件确保设置正确

## 📄 更新日志

### v1.0.0 (2024-01-15)
- 初始版本发布
- 支持钉钉、企业微信推送
- 实现图片推送功能
- 添加Web管理界面
- 支持定时和批量推送
- 实现频率控制和重试机制

---

**注意**: 本系统仍在持续优化中，建议定期更新到最新版本以获得更好的功能和性能。