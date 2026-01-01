"""
钉钉推送模块
支持文本、Markdown、ActionCard等消息类型
"""
import requests
import json
import hashlib
import hmac
import base64
import urllib.parse
import time
import os
from datetime import datetime
from typing import List, Dict, Optional
from .notification_base import BaseNotificationBot, NotificationPlatform, NotificationResult

class DingtalkBot(BaseNotificationBot):
    """钉钉机器人推送类"""
    
    def _get_platform(self) -> NotificationPlatform:
        return NotificationPlatform.DINGTALK
    
    def _init_session(self):
        """初始化请求会话"""
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # 提取access_token和secret
        self.access_token = self._extract_access_token()
        self.secret = self.config.get('secret', '')
    
    def _extract_access_token(self) -> str:
        """从webhook URL中提取access_token"""
        try:
            if 'access_token=' in self.webhook_url:
                return self.webhook_url.split('access_token=')[1].split('&')[0]
            return ''
        except:
            return ''
    
    def _get_signed_url(self) -> str:
        """生成带签名的URL（如果配置了secret）"""
        if not self.secret:
            return self.webhook_url
        
        timestamp = str(round(time.time() * 1000))
        secret_enc = self.secret.encode('utf-8')
        string_to_sign = f'{timestamp}\n{self.secret}'
        string_to_sign_enc = string_to_sign.encode('utf-8')
        
        hmac_code = hmac.new(
            secret_enc, 
            string_to_sign_enc, 
            digestmod=hashlib.sha256
        ).digest()
        
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        
        return f"{self.webhook_url}&timestamp={timestamp}&sign={sign}"
    
    def send_text(self, content: str, at_mobiles: List[str] = None, 
                  at_all: bool = False) -> NotificationResult:
        """
        发送文本消息
        
        Args:
            content: 消息内容
            at_mobiles: @的手机号列表
            at_all: 是否@所有人
            
        Returns:
            NotificationResult: 发送结果
        """
        try:
            data = {
                "msgtype": "text",
                "text": {
                    "content": content
                },
                "at": {
                    "atMobiles": at_mobiles or [],
                    "isAtAll": at_all
                }
            }
            
            url = self._get_signed_url()
            response = self.session.post(url, json=data, timeout=self.timeout)
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
                    message=f"钉钉API错误: {result}",
                    data=result
                )
                
        except requests.exceptions.Timeout:
            return NotificationResult(False, "请求超时")
        except requests.exceptions.RequestException as e:
            return NotificationResult(False, f"网络请求失败: {str(e)}")
        except Exception as e:
            return NotificationResult(False, f"发送文本消息异常: {str(e)}")
    
    def send_markdown(self, content: str, title: str = "通知", 
                     at_mobiles: List[str] = None, at_all: bool = False) -> NotificationResult:
        """
        发送 Markdown 消息
        
        Args:
            content: Markdown 格式的消息内容
            title: 消息标题
            at_mobiles: @的手机号列表
            at_all: 是否@所有人
            
        Returns:
            NotificationResult: 发送结果
        """
        try:
            data = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": content
                },
                "at": {
                    "atMobiles": at_mobiles or [],
                    "isAtAll": at_all
                }
            }
            
            url = self._get_signed_url()
            response = self.session.post(url, json=data, timeout=self.timeout)
            result = response.json()
            
            if result.get('errcode') == 0:
                return NotificationResult(
                    success=True, 
                    message="Markdown消息发送成功"
                )
            else:
                return NotificationResult(
                    success=False, 
                    message=f"钉钉API错误: {result}",
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
        发送图片信息（钉钉不支持直接发送本地图片，发送图片信息）
        
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
            
            content = f"""## 📊 图表文件生成完成

**📁 文件名**: {filename}  
**📏 文件大小**: {file_size:,} bytes  
**⏰ 生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

> 图片已保存到本地，可通过Web界面查看"""
            
            return self.send_markdown(content, "图表生成通知")
            
        except Exception as e:
            return NotificationResult(False, f"发送图片信息异常: {str(e)}")
    
    def send_action_card(self, title: str, text: str, 
                        single_title: str = None, single_url: str = None,
                        buttons: List[Dict] = None) -> NotificationResult:
        """
        发送ActionCard消息
        
        Args:
            title: 标题
            text: 内容
            single_title: 单个按钮标题
            single_url: 单个按钮URL
            buttons: 多个按钮列表
            
        Returns:
            NotificationResult: 发送结果
        """
        try:
            data = {
                "msgtype": "actionCard",
                "actionCard": {
                    "title": title,
                    "text": text,
                    "hideAvatar": "0",
                    "btnOrientation": "0"
                }
            }
            
            if single_title and single_url:
                data["actionCard"]["singleTitle"] = single_title
                data["actionCard"]["singleURL"] = single_url
            elif buttons:
                data["actionCard"]["btns"] = buttons
            
            url = self._get_signed_url()
            response = self.session.post(url, json=data, timeout=self.timeout)
            result = response.json()
            
            if result.get('errcode') == 0:
                return NotificationResult(
                    success=True, 
                    message="ActionCard消息发送成功"
                )
            else:
                return NotificationResult(
                    success=False, 
                    message=f"钉钉API错误: {result}",
                    data=result
                )
                
        except Exception as e:
            return NotificationResult(False, f"发送ActionCard消息异常: {str(e)}")
    
    def send_link(self, title: str, text: str, message_url: str, 
                  pic_url: str = "") -> NotificationResult:
        """
        发送链接消息
        
        Args:
            title: 标题
            text: 内容
            message_url: 点击后跳转的URL
            pic_url: 图片URL
            
        Returns:
            NotificationResult: 发送结果
        """
        try:
            data = {
                "msgtype": "link",
                "link": {
                    "text": text,
                    "title": title,
                    "picUrl": pic_url,
                    "messageUrl": message_url
                }
            }
            
            url = self._get_signed_url()
            response = self.session.post(url, json=data, timeout=self.timeout)
            result = response.json()
            
            if result.get('errcode') == 0:
                return NotificationResult(
                    success=True, 
                    message="链接消息发送成功"
                )
            else:
                return NotificationResult(
                    success=False, 
                    message=f"钉钉API错误: {result}",
                    data=result
                )
                
        except Exception as e:
            return NotificationResult(False, f"发送链接消息异常: {str(e)}")