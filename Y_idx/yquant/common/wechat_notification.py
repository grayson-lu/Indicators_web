"""
优化的企业微信推送模块
增强错误处理和重试机制
"""
import requests
import json
import base64
import os
from datetime import datetime
from typing import List, Dict, Optional
from .notification_base import BaseNotificationBot, NotificationPlatform, NotificationResult

class WechatWorkBot(BaseNotificationBot):
    """增强的企业微信机器人推送类"""
    
    def _get_platform(self) -> NotificationPlatform:
        return NotificationPlatform.WECHAT_WORK
    
    def _init_session(self):
        """初始化请求会话"""
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def send_text(self, content: str, mentioned_list: List[str] = None, 
                  mentioned_mobile_list: List[str] = None) -> NotificationResult:
        """
        发送文本消息
        
        Args:
            content: 消息内容
            mentioned_list: @的用户列表（userid）
            mentioned_mobile_list: @的用户手机号列表
            
        Returns:
            NotificationResult: 发送结果
        """
        try:
            data = {
                "msgtype": "text",
                "text": {
                    "content": content
                }
            }
            
            # 添加@用户
            if mentioned_list or mentioned_mobile_list:
                data["text"]["mentioned_list"] = mentioned_list or []
                data["text"]["mentioned_mobile_list"] = mentioned_mobile_list or []
            
            response = self.session.post(
                self.webhook_url, 
                json=data, 
                timeout=self.timeout
            )
            result = response.json()
            
            if result.get('errcode') == 0:
                return NotificationResult(
                    success=True, 
                    message="文本消息发送成功",
                    data={"content_preview": content[:50] + "..." if len(content) > 50 else content}
                )
            else:
                return NotificationResult(
                    success=False, 
                    message=f"企业微信API错误: {result}",
                    data=result
                )
                
        except requests.exceptions.Timeout:
            return NotificationResult(False, "请求超时")
        except requests.exceptions.RequestException as e:
            return NotificationResult(False, f"网络请求失败: {str(e)}")
        except Exception as e:
            return NotificationResult(False, f"发送文本消息异常: {str(e)}")
    
    def send_markdown(self, content: str) -> NotificationResult:
        """
        发送 Markdown 消息
        
        Args:
            content: Markdown 格式的消息内容
            
        Returns:
            NotificationResult: 发送结果
        """
        try:
            data = {
                "msgtype": "markdown",
                "markdown": {
                    "content": content
                }
            }
            
            response = self.session.post(
                self.webhook_url, 
                json=data, 
                timeout=self.timeout
            )
            result = response.json()
            
            if result.get('errcode') == 0:
                return NotificationResult(
                    success=True, 
                    message="Markdown消息发送成功"
                )
            else:
                return NotificationResult(
                    success=False, 
                    message=f"企业微信API错误: {result}",
                    data=result
                )
                
        except requests.exceptions.Timeout:
            return NotificationResult(False, "请求超时")
        except requests.exceptions.RequestException as e:
            return NotificationResult(False, f"网络请求失败: {str(e)}")
        except Exception as e:
            return NotificationResult(False, f"发送Markdown消息异常: {str(e)}")
    
    def send_image(self, image_path: str) -> NotificationResult:
        """
        发送图片信息（企业微信机器人不支持直接上传，发送文件信息）
        
        Args:
            image_path: 图片路径
            
        Returns:
            NotificationResult: 发送结果
        """
        try:
            if not os.path.exists(image_path):
                return NotificationResult(False, f"图片文件不存在: {image_path}")
            
            filename = os.path.basename(image_path)
            file_size = os.path.getsize(image_path)
            
            content = f"""📊 **图表文件生成完成**

📁 **文件名**: {filename}
📏 **文件大小**: {file_size:,} bytes
⏰ **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

*注: 图片已保存到本地，可通过Web界面查看*"""
            
            return self.send_markdown(content)
            
        except Exception as e:
            return NotificationResult(False, f"发送图片信息异常: {str(e)}")
    
    def send_news_card(self, articles: List[Dict]) -> NotificationResult:
        """
        发送图文消息（企业微信支持）
        
        Args:
            articles: 图文列表，每个元素包含title, description, url, picurl
            
        Returns:
            NotificationResult: 发送结果
        """
        try:
            data = {
                "msgtype": "news",
                "news": {
                    "articles": articles
                }
            }
            
            response = self.session.post(
                self.webhook_url, 
                json=data, 
                timeout=self.timeout
            )
            result = response.json()
            
            if result.get('errcode') == 0:
                return NotificationResult(
                    success=True, 
                    message="图文消息发送成功"
                )
            else:
                return NotificationResult(
                    success=False, 
                    message=f"企业微信API错误: {result}",
                    data=result
                )
                
        except Exception as e:
            return NotificationResult(False, f"发送图文消息异常: {str(e)}")