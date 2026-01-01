"""
统一推送通知基类
支持多平台推送（企业微信、钉钉等）
"""
import abc
import json
import time
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum

logger = logging.getLogger('notification')

class NotificationPlatform(Enum):
    """推送平台枚举"""
    WECHAT_WORK = "wechat_work"  # 企业微信
    DINGTALK = "dingtalk"        # 钉钉
    FEISHU = "feishu"           # 飞书

class MessageType(Enum):
    """消息类型枚举"""
    TEXT = "text"
    MARKDOWN = "markdown"
    IMAGE = "image"
    CARD = "card"
    FILE = "file"

class NotificationLevel(Enum):
    """通知级别枚举"""
    INFO = "info"        # 信息
    WARNING = "warning"  # 警告
    ERROR = "error"      # 错误
    SUCCESS = "success"  # 成功
    URGENT = "urgent"    # 紧急

class NotificationResult:
    """推送结果封装"""
    def __init__(self, success: bool, message: str = "", data: Dict = None):
        self.success = success
        self.message = message
        self.data = data or {}
        self.timestamp = datetime.now()
    
    def __str__(self):
        return f"NotificationResult(success={self.success}, message='{self.message}')"

class BaseNotificationBot(abc.ABC):
    """推送机器人基类"""
    
    def __init__(self, webhook_url: str, config: Dict = None):
        """
        初始化推送机器人
        
        Args:
            webhook_url: webhook地址
            config: 配置参数
        """
        self.webhook_url = webhook_url
        self.config = config or {}
        self.platform = self._get_platform()
        self.retry_count = self.config.get('retry_count', 3)
        self.retry_delay = self.config.get('retry_delay', 1)
        self.timeout = self.config.get('timeout', 30)
        self._init_session()
    
    @abc.abstractmethod
    def _get_platform(self) -> NotificationPlatform:
        """获取平台类型"""
        pass
    
    @abc.abstractmethod
    def _init_session(self):
        """初始化请求会话"""
        pass
    
    @abc.abstractmethod
    def send_text(self, content: str, **kwargs) -> NotificationResult:
        """发送文本消息"""
        pass
    
    @abc.abstractmethod
    def send_markdown(self, content: str, **kwargs) -> NotificationResult:
        """发送Markdown消息"""
        pass
    
    @abc.abstractmethod
    def send_image(self, image_path: str, **kwargs) -> NotificationResult:
        """发送图片消息"""
        pass
    
    def send_with_retry(self, send_func, *args, **kwargs) -> NotificationResult:
        """
        带重试机制的发送
        
        Args:
            send_func: 发送函数
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            NotificationResult: 发送结果
        """
        last_error = None
        
        for attempt in range(self.retry_count):
            try:
                result = send_func(*args, **kwargs)
                if result.success:
                    if attempt > 0:
                        logger.info(f"重试成功，尝试次数: {attempt + 1}")
                    return result
                else:
                    last_error = result.message
                    
            except Exception as e:
                last_error = str(e)
                logger.warning(f"发送失败 (尝试 {attempt + 1}/{self.retry_count}): {last_error}")
            
            if attempt < self.retry_count - 1:
                time.sleep(self.retry_delay * (attempt + 1))  # 递增延迟
        
        return NotificationResult(
            success=False, 
            message=f"重试失败，最后错误: {last_error}"
        )
    
    def validate_config(self) -> bool:
        """验证配置是否有效"""
        return bool(self.webhook_url)

class UnifiedNotificationManager:
    """统一通知管理器"""
    
    def __init__(self, config: Dict = None):
        """
        初始化通知管理器
        
        Args:
            config: 配置字典，包含各平台的配置信息
        """
        self.config = config or {}
        self.bots: Dict[NotificationPlatform, BaseNotificationBot] = {}
        self.enabled_platforms = set()
        self._initialize_bots()
    
    def _initialize_bots(self):
        """初始化各平台机器人"""
        for platform_name, platform_config in self.config.items():
            if not platform_config.get('enabled', False):
                continue

            try:
                platform = self._resolve_platform(platform_name)
                if platform is None:
                    logger.warning(f"不支持的平台配置: {platform_name}")
                    continue

                bot = self._create_bot(platform, platform_config)

                if bot and bot.validate_config():
                    self.bots[platform] = bot
                    self.enabled_platforms.add(platform)
                    logger.info(f"{platform.value} 推送已启用")
                else:
                    logger.warning(f"{platform.value} 配置无效，已跳过")

            except (ValueError, Exception) as e:
                logger.error(f"初始化 {platform_name} 推送失败: {e}")

    @staticmethod
    def _resolve_platform(platform_name: str) -> Optional[NotificationPlatform]:
        """兼容平台名称别名"""
        if not platform_name:
            return None
        key = platform_name.lower().strip()
        mapping = {
            "wechat": NotificationPlatform.WECHAT_WORK,
            "wechat_work": NotificationPlatform.WECHAT_WORK,
            "wecom": NotificationPlatform.WECHAT_WORK,
            "dingtalk": NotificationPlatform.DINGTALK,
            "feishu": NotificationPlatform.FEISHU,
        }
        return mapping.get(key)
    
    def _create_bot(self, platform: NotificationPlatform, config: Dict) -> Optional[BaseNotificationBot]:
        """创建指定平台的机器人"""
        webhook_url = config.get('webhook_url', '')
        
        if platform == NotificationPlatform.WECHAT_WORK:
            from .wechat_notification import WechatWorkBot
            return WechatWorkBot(webhook_url, config)
        elif platform == NotificationPlatform.DINGTALK:
            from .dingtalk_notification import DingtalkBot
            return DingtalkBot(webhook_url, config)
        else:
            logger.warning(f"不支持的平台: {platform.value}")
            return None
    
    def send_to_all(self, message_type: MessageType, content: str, 
                   level: NotificationLevel = NotificationLevel.INFO, 
                   **kwargs) -> Dict[NotificationPlatform, NotificationResult]:
        """
        向所有启用的平台发送消息
        
        Args:
            message_type: 消息类型
            content: 消息内容
            level: 通知级别
            **kwargs: 其他参数
            
        Returns:
            Dict: 各平台发送结果
        """
        results = {}
        
        for platform, bot in self.bots.items():
            try:
                # 根据消息类型调用对应方法
                if message_type == MessageType.TEXT:
                    result = bot.send_with_retry(bot.send_text, content, **kwargs)
                elif message_type == MessageType.MARKDOWN:
                    result = bot.send_with_retry(bot.send_markdown, content, **kwargs)
                elif message_type == MessageType.IMAGE:
                    result = bot.send_with_retry(bot.send_image, content, **kwargs)
                else:
                    result = NotificationResult(False, f"不支持的消息类型: {message_type.value}")
                
                results[platform] = result
                
                if result.success:
                    logger.info(f"{platform.value} 发送成功")
                else:
                    logger.error(f"{platform.value} 发送失败: {result.message}")
                    
            except Exception as e:
                error_msg = f"{platform.value} 发送异常: {str(e)}"
                logger.error(error_msg)
                results[platform] = NotificationResult(False, error_msg)
        
        return results
    
    def send_to_platform(self, platform: NotificationPlatform, 
                         message_type: MessageType, content: str, 
                         **kwargs) -> NotificationResult:
        """
        向指定平台发送消息
        
        Args:
            platform: 目标平台
            message_type: 消息类型
            content: 消息内容
            **kwargs: 其他参数
            
        Returns:
            NotificationResult: 发送结果
        """
        if platform not in self.bots:
            return NotificationResult(False, f"平台 {platform.value} 未启用或配置无效")
        
        bot = self.bots[platform]
        
        try:
            if message_type == MessageType.TEXT:
                return bot.send_with_retry(bot.send_text, content, **kwargs)
            elif message_type == MessageType.MARKDOWN:
                return bot.send_with_retry(bot.send_markdown, content, **kwargs)
            elif message_type == MessageType.IMAGE:
                return bot.send_with_retry(bot.send_image, content, **kwargs)
            else:
                return NotificationResult(False, f"不支持的消息类型: {message_type.value}")
                
        except Exception as e:
            return NotificationResult(False, f"发送异常: {str(e)}")
    
    def is_enabled(self, platform: NotificationPlatform = None) -> bool:
        """
        检查平台是否启用
        
        Args:
            platform: 平台类型，为None时检查是否有任何平台启用
            
        Returns:
            bool: 是否启用
        """
        if platform is None:
            return len(self.enabled_platforms) > 0
        return platform in self.enabled_platforms
    
    def get_enabled_platforms(self) -> List[NotificationPlatform]:
        """获取已启用的平台列表"""
        return list(self.enabled_platforms)
