"""平台扩展支持模块
包含完善的钉钉推送、邮件推送和Webhook自定义推送功能
"""

import json
import smtplib
import ssl
import requests
import base64
import mimetypes
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication
from email.utils import formataddr
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from enum import Enum
import logging
from pathlib import Path
import time
import hashlib
import hmac
import urllib.parse
from datetime import datetime
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# 配置日志
logger = logging.getLogger(__name__)

class EmailSecurity(Enum):
    """邮件安全类型枚举"""
    NONE = "none"
    TLS = "tls"
    SSL = "ssl"

class WebhookMethod(Enum):
    """Webhook请求方法枚举"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"

@dataclass
class EmailConfig:
    """邮件配置数据类"""
    smtp_server: str
    smtp_port: int
    username: str
    password: str
    from_name: str = ""
    security: EmailSecurity = EmailSecurity.TLS
    timeout: int = 30
    max_recipients: int = 50
    
@dataclass
class WebhookConfig:
    """Webhook配置数据类"""
    url: str
    method: WebhookMethod = WebhookMethod.POST
    headers: Dict[str, str] = None
    auth_type: str = "none"  # none, basic, bearer, custom
    auth_token: str = ""
    timeout: int = 30
    retry_count: int = 3
    verify_ssl: bool = True
    
@dataclass
class DingtalkEnhancedConfig:
    """增强钉钉配置数据类"""
    webhook_url: str
    secret: str = ""
    at_mobiles: List[str] = None
    at_user_ids: List[str] = None
    is_at_all: bool = False
    enable_markdown: bool = True
    enable_actioncard: bool = True
    timeout: int = 30

class EnhancedDingtalkBot:
    """增强钉钉推送机器人"""
    
    def __init__(self, config: DingtalkEnhancedConfig):
        self.config = config
        self.session = requests.Session()
        self.session.timeout = config.timeout
        
    def _generate_sign(self, timestamp: str) -> str:
        """
        生成钉钉签名
        
        Args:
            timestamp: 时间戳
            
        Returns:
            str: 签名字符串
        """
        if not self.config.secret:
            return ""
            
        string_to_sign = f"{timestamp}\n{self.config.secret}"
        hmac_code = hmac.new(
            self.config.secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return sign
    
    def _get_signed_url(self) -> str:
        """
        获取带签名的URL
        
        Returns:
            str: 带签名的URL
        """
        if not self.config.secret:
            return self.config.webhook_url
            
        timestamp = str(round(time.time() * 1000))
        sign = self._generate_sign(timestamp)
        
        return f"{self.config.webhook_url}&timestamp={timestamp}&sign={sign}"
    
    def _build_at_config(self) -> Dict[str, Any]:
        """
        构建@配置
        
        Returns:
            Dict: @配置字典
        """
        at_config = {
            "isAtAll": self.config.is_at_all
        }
        
        if self.config.at_mobiles:
            at_config["atMobiles"] = self.config.at_mobiles
            
        if self.config.at_user_ids:
            at_config["atUserIds"] = self.config.at_user_ids
            
        return at_config
    
    def send_text_message(self, content: str, at_all: bool = None) -> Dict[str, Any]:
        """
        发送文本消息
        
        Args:
            content: 消息内容
            at_all: 是否@所有人
            
        Returns:
            Dict: 发送结果
        """
        try:
            url = self._get_signed_url()
            
            # 构建@配置
            at_config = self._build_at_config()
            if at_all is not None:
                at_config["isAtAll"] = at_all
            
            payload = {
                "msgtype": "text",
                "text": {
                    "content": content
                },
                "at": at_config
            }
            
            response = self.session.post(url, json=payload)
            result = response.json()
            
            if result.get('errcode') == 0:
                logger.info(f"钉钉文本消息发送成功")
                return {"success": True, "response": result}
            else:
                logger.error(f"钉钉文本消息发送失败: {result}")
                return {"success": False, "error": result.get('errmsg', '未知错误')}
                
        except Exception as e:
            logger.error(f"钉钉文本消息发送异常: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def send_markdown_message(self, title: str, content: str) -> Dict[str, Any]:
        """
        发送Markdown消息
        
        Args:
            title: 消息标题
            content: Markdown内容
            
        Returns:
            Dict: 发送结果
        """
        if not self.config.enable_markdown:
            return self.send_text_message(f"{title}\n{content}")
            
        try:
            url = self._get_signed_url()
            
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": content
                },
                "at": self._build_at_config()
            }
            
            response = self.session.post(url, json=payload)
            result = response.json()
            
            if result.get('errcode') == 0:
                logger.info(f"钉钉Markdown消息发送成功")
                return {"success": True, "response": result}
            else:
                logger.error(f"钉钉Markdown消息发送失败: {result}")
                return {"success": False, "error": result.get('errmsg', '未知错误')}
                
        except Exception as e:
            logger.error(f"钉钉Markdown消息发送异常: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def send_actioncard_message(self, title: str, content: str, 
                               buttons: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        发送ActionCard消息
        
        Args:
            title: 卡片标题
            content: 卡片内容
            buttons: 按钮列表 [{"title": "按钮名", "actionURL": "跳转链接"}]
            
        Returns:
            Dict: 发送结果
        """
        if not self.config.enable_actioncard:
            return self.send_markdown_message(title, content)
            
        try:
            url = self._get_signed_url()
            
            if len(buttons) == 1:
                # 单按钮模式
                payload = {
                    "msgtype": "actionCard",
                    "actionCard": {
                        "title": title,
                        "text": content,
                        "singleTitle": buttons[0]["title"],
                        "singleURL": buttons[0]["actionURL"]
                    }
                }
            else:
                # 多按钮模式
                payload = {
                    "msgtype": "actionCard",
                    "actionCard": {
                        "title": title,
                        "text": content,
                        "btns": buttons
                    }
                }
            
            response = self.session.post(url, json=payload)
            result = response.json()
            
            if result.get('errcode') == 0:
                logger.info(f"钉钉ActionCard消息发送成功")
                return {"success": True, "response": result}
            else:
                logger.error(f"钉钉ActionCard消息发送失败: {result}")
                return {"success": False, "error": result.get('errmsg', '未知错误')}
                
        except Exception as e:
            logger.error(f"钉钉ActionCard消息发送异常: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def send_link_message(self, title: str, text: str, message_url: str, 
                         pic_url: str = "") -> Dict[str, Any]:
        """
        发送链接消息
        
        Args:
            title: 消息标题
            text: 消息文本
            message_url: 点击消息跳转的URL
            pic_url: 图片URL
            
        Returns:
            Dict: 发送结果
        """
        try:
            url = self._get_signed_url()
            
            payload = {
                "msgtype": "link",
                "link": {
                    "text": text,
                    "title": title,
                    "picUrl": pic_url,
                    "messageUrl": message_url
                }
            }
            
            response = self.session.post(url, json=payload)
            result = response.json()
            
            if result.get('errcode') == 0:
                logger.info(f"钉钉链接消息发送成功")
                return {"success": True, "response": result}
            else:
                logger.error(f"钉钉链接消息发送失败: {result}")
                return {"success": False, "error": result.get('errmsg', '未知错误')}
                
        except Exception as e:
            logger.error(f"钉钉链接消息发送异常: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def send_feed_card_message(self, links: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        发送FeedCard消息
        
        Args:
            links: 链接列表 [{"title": "标题", "messageURL": "链接", "picURL": "图片"}]
            
        Returns:
            Dict: 发送结果
        """
        try:
            url = self._get_signed_url()
            
            payload = {
                "msgtype": "feedCard",
                "feedCard": {
                    "links": links
                }
            }
            
            response = self.session.post(url, json=payload)
            result = response.json()
            
            if result.get('errcode') == 0:
                logger.info(f"钉钉FeedCard消息发送成功")
                return {"success": True, "response": result}
            else:
                logger.error(f"钉钉FeedCard消息发送失败: {result}")
                return {"success": False, "error": result.get('errmsg', '未知错误')}
                
        except Exception as e:
            logger.error(f"钉钉FeedCard消息发送异常: {str(e)}")
            return {"success": False, "error": str(e)}

class EmailPushBot:
    """邮件推送机器人"""
    
    def __init__(self, config: EmailConfig):
        self.config = config
        self.smtp_server = None
        
    def _connect_smtp(self):
        """
        连接SMTP服务器
        
        Returns:
            smtplib.SMTP: SMTP连接对象
        """
        try:
            if self.config.security == EmailSecurity.SSL:
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(self.config.smtp_server, self.config.smtp_port, 
                                        timeout=self.config.timeout, context=context)
            else:
                server = smtplib.SMTP(self.config.smtp_server, self.config.smtp_port, 
                                    timeout=self.config.timeout)
                
                if self.config.security == EmailSecurity.TLS:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
            
            server.login(self.config.username, self.config.password)
            return server
            
        except Exception as e:
            logger.error(f"SMTP连接失败: {str(e)}")
            raise
    
    def send_text_email(self, to_emails: Union[str, List[str]], subject: str, 
                       content: str, cc_emails: List[str] = None) -> Dict[str, Any]:
        """
        发送文本邮件
        
        Args:
            to_emails: 收件人邮箱
            subject: 邮件主题
            content: 邮件内容
            cc_emails: 抄送邮箱列表
            
        Returns:
            Dict: 发送结果
        """
        try:
            # 处理收件人列表
            if isinstance(to_emails, str):
                to_emails = [to_emails]
            
            if len(to_emails) > self.config.max_recipients:
                return {"success": False, "error": f"收件人数量超过限制({self.config.max_recipients})"}
            
            # 创建邮件
            msg = MIMEText(content, 'plain', 'utf-8')
            msg['Subject'] = subject
            msg['From'] = formataddr((self.config.from_name, self.config.username))
            msg['To'] = ', '.join(to_emails)
            
            if cc_emails:
                msg['Cc'] = ', '.join(cc_emails)
                to_emails.extend(cc_emails)
            
            # 发送邮件
            with self._connect_smtp() as server:
                server.send_message(msg, to_addrs=to_emails)
            
            logger.info(f"文本邮件发送成功，收件人: {len(to_emails)}")
            return {"success": True, "recipients": len(to_emails)}
            
        except Exception as e:
            logger.error(f"文本邮件发送失败: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def send_html_email(self, to_emails: Union[str, List[str]], subject: str, 
                       html_content: str, text_content: str = "", 
                       cc_emails: List[str] = None) -> Dict[str, Any]:
        """
        发送HTML邮件
        
        Args:
            to_emails: 收件人邮箱
            subject: 邮件主题
            html_content: HTML内容
            text_content: 纯文本内容（备用）
            cc_emails: 抄送邮箱列表
            
        Returns:
            Dict: 发送结果
        """
        try:
            # 处理收件人列表
            if isinstance(to_emails, str):
                to_emails = [to_emails]
            
            if len(to_emails) > self.config.max_recipients:
                return {"success": False, "error": f"收件人数量超过限制({self.config.max_recipients})"}
            
            # 创建多部分邮件
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = formataddr((self.config.from_name, self.config.username))
            msg['To'] = ', '.join(to_emails)
            
            if cc_emails:
                msg['Cc'] = ', '.join(cc_emails)
                to_emails.extend(cc_emails)
            
            # 添加文本部分
            if text_content:
                text_part = MIMEText(text_content, 'plain', 'utf-8')
                msg.attach(text_part)
            
            # 添加HTML部分
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)
            
            # 发送邮件
            with self._connect_smtp() as server:
                server.send_message(msg, to_addrs=to_emails)
            
            logger.info(f"HTML邮件发送成功，收件人: {len(to_emails)}")
            return {"success": True, "recipients": len(to_emails)}
            
        except Exception as e:
            logger.error(f"HTML邮件发送失败: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def send_email_with_attachments(self, to_emails: Union[str, List[str]], subject: str,
                                   content: str, attachments: List[str], 
                                   is_html: bool = False, cc_emails: List[str] = None) -> Dict[str, Any]:
        """
        发送带附件的邮件
        
        Args:
            to_emails: 收件人邮箱
            subject: 邮件主题
            content: 邮件内容
            attachments: 附件文件路径列表
            is_html: 内容是否为HTML格式
            cc_emails: 抄送邮箱列表
            
        Returns:
            Dict: 发送结果
        """
        try:
            # 处理收件人列表
            if isinstance(to_emails, str):
                to_emails = [to_emails]
            
            if len(to_emails) > self.config.max_recipients:
                return {"success": False, "error": f"收件人数量超过限制({self.config.max_recipients})"}
            
            # 创建多部分邮件
            msg = MIMEMultipart()
            msg['Subject'] = subject
            msg['From'] = formataddr((self.config.from_name, self.config.username))
            msg['To'] = ', '.join(to_emails)
            
            if cc_emails:
                msg['Cc'] = ', '.join(cc_emails)
                to_emails.extend(cc_emails)
            
            # 添加邮件内容
            content_type = 'html' if is_html else 'plain'
            msg.attach(MIMEText(content, content_type, 'utf-8'))
            
            # 添加附件
            for attachment_path in attachments:
                if not Path(attachment_path).exists():
                    logger.warning(f"附件文件不存在: {attachment_path}")
                    continue
                
                try:
                    with open(attachment_path, 'rb') as f:
                        file_data = f.read()
                    
                    # 获取文件类型
                    content_type, encoding = mimetypes.guess_type(attachment_path)
                    
                    if content_type is None or encoding is not None:
                        content_type = 'application/octet-stream'
                    
                    main_type, sub_type = content_type.split('/', 1)
                    
                    if main_type == 'image':
                        attachment = MIMEImage(file_data, _subtype=sub_type)
                    else:
                        attachment = MIMEApplication(file_data, _subtype=sub_type)
                    
                    filename = Path(attachment_path).name
                    attachment.add_header('Content-Disposition', 'attachment', filename=filename)
                    msg.attach(attachment)
                    
                except Exception as e:
                    logger.error(f"添加附件失败 {attachment_path}: {str(e)}")
            
            # 发送邮件
            with self._connect_smtp() as server:
                server.send_message(msg, to_addrs=to_emails)
            
            logger.info(f"带附件邮件发送成功，收件人: {len(to_emails)}, 附件: {len(attachments)}")
            return {"success": True, "recipients": len(to_emails), "attachments": len(attachments)}
            
        except Exception as e:
            logger.error(f"带附件邮件发送失败: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def send_image_email(self, to_emails: Union[str, List[str]], subject: str,
                        content: str, image_paths: List[str], 
                        embed_images: bool = True) -> Dict[str, Any]:
        """
        发送包含图片的邮件
        
        Args:
            to_emails: 收件人邮箱
            subject: 邮件主题
            content: 邮件内容（HTML格式，可包含<img>标签）
            image_paths: 图片文件路径列表
            embed_images: 是否嵌入图片到邮件中
            
        Returns:
            Dict: 发送结果
        """
        if embed_images:
            return self._send_embedded_image_email(to_emails, subject, content, image_paths)
        else:
            return self.send_email_with_attachments(to_emails, subject, content, image_paths, is_html=True)
    
    def _send_embedded_image_email(self, to_emails: List[str], subject: str,
                                  content: str, image_paths: List[str]) -> Dict[str, Any]:
        """
        发送嵌入图片的邮件
        
        Args:
            to_emails: 收件人邮箱
            subject: 邮件主题
            content: HTML内容
            image_paths: 图片路径列表
            
        Returns:
            Dict: 发送结果
        """
        try:
            # 创建多部分邮件
            msg = MIMEMultipart('related')
            msg['Subject'] = subject
            msg['From'] = formataddr((self.config.from_name, self.config.username))
            msg['To'] = ', '.join(to_emails)
            
            # 创建HTML部分
            msg_alternative = MIMEMultipart('alternative')
            msg.attach(msg_alternative)
            
            # 处理嵌入图片
            processed_content = content
            for i, image_path in enumerate(image_paths):
                if not Path(image_path).exists():
                    continue
                
                try:
                    with open(image_path, 'rb') as f:
                        img_data = f.read()
                    
                    # 创建图片附件
                    img = MIMEImage(img_data)
                    img_id = f'image{i}'
                    img.add_header('Content-ID', f'<{img_id}>')
                    msg.attach(img)
                    
                    # 在HTML中引用图片
                    filename = Path(image_path).name
                    processed_content += f'<br><img src="cid:{img_id}" alt="{filename}" style="max-width:100%;height:auto;">'
                    
                except Exception as e:
                    logger.error(f"处理嵌入图片失败 {image_path}: {str(e)}")
            
            # 添加HTML内容
            html_part = MIMEText(processed_content, 'html', 'utf-8')
            msg_alternative.attach(html_part)
            
            # 发送邮件
            with self._connect_smtp() as server:
                server.send_message(msg, to_addrs=to_emails)
            
            logger.info(f"嵌入图片邮件发送成功，收件人: {len(to_emails)}, 图片: {len(image_paths)}")
            return {"success": True, "recipients": len(to_emails), "images": len(image_paths)}
            
        except Exception as e:
            logger.error(f"嵌入图片邮件发送失败: {str(e)}")
            return {"success": False, "error": str(e)}

class WebhookPushBot:
    """Webhook推送机器人"""
    
    def __init__(self, config: WebhookConfig):
        self.config = config
        self.session = requests.Session()
        self.session.timeout = config.timeout
        self.session.verify = config.verify_ssl
        
        # 设置认证
        self._setup_auth()
    
    def _setup_auth(self):
        """设置认证信息"""
        if self.config.auth_type == "basic" and self.config.auth_token:
            # Basic认证格式: username:password
            if ':' in self.config.auth_token:
                username, password = self.config.auth_token.split(':', 1)
                self.session.auth = (username, password)
        
        elif self.config.auth_type == "bearer" and self.config.auth_token:
            # Bearer Token认证
            self.session.headers.update({
                'Authorization': f'Bearer {self.config.auth_token}'
            })
        
        elif self.config.auth_type == "custom" and self.config.auth_token:
            # 自定义认证头
            self.session.headers.update({
                'Authorization': self.config.auth_token
            })
        
        # 添加自定义头
        if self.config.headers:
            self.session.headers.update(self.config.headers)
    
    def send_webhook(self, data: Dict[str, Any], 
                    custom_headers: Dict[str, str] = None) -> Dict[str, Any]:
        """
        发送Webhook请求
        
        Args:
            data: 要发送的数据
            custom_headers: 自定义请求头
            
        Returns:
            Dict: 发送结果
        """
        for attempt in range(self.config.retry_count + 1):
            try:
                headers = {}
                if custom_headers:
                    headers.update(custom_headers)
                
                # 根据请求方法发送
                if self.config.method == WebhookMethod.GET:
                    response = self.session.get(self.config.url, params=data, headers=headers)
                else:
                    # POST, PUT, PATCH
                    response = self.session.request(
                        self.config.method.value, 
                        self.config.url, 
                        json=data, 
                        headers=headers
                    )
                
                # 检查响应状态
                if response.status_code < 400:
                    logger.info(f"Webhook发送成功: {self.config.url} (状态码: {response.status_code})")
                    
                    try:
                        response_data = response.json()
                    except:
                        response_data = response.text
                    
                    return {
                        "success": True, 
                        "status_code": response.status_code,
                        "response": response_data,
                        "attempt": attempt + 1
                    }
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                    logger.warning(f"Webhook发送失败 (尝试 {attempt + 1}): {error_msg}")
                    
                    if attempt == self.config.retry_count:
                        return {
                            "success": False, 
                            "error": error_msg,
                            "status_code": response.status_code,
                            "attempts": attempt + 1
                        }
                    
                    # 重试前等待
                    time.sleep(2 ** attempt)
                    
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Webhook发送异常 (尝试 {attempt + 1}): {error_msg}")
                
                if attempt == self.config.retry_count:
                    return {
                        "success": False, 
                        "error": error_msg,
                        "attempts": attempt + 1
                    }
                
                # 重试前等待
                time.sleep(2 ** attempt)
        
        return {"success": False, "error": "未知错误"}
    
    def send_text_webhook(self, title: str, content: str, 
                         extra_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        发送文本Webhook
        
        Args:
            title: 标题
            content: 内容
            extra_data: 额外数据
            
        Returns:
            Dict: 发送结果
        """
        data = {
            "type": "text",
            "title": title,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        
        if extra_data:
            data.update(extra_data)
        
        return self.send_webhook(data)
    
    def send_markdown_webhook(self, title: str, markdown_content: str,
                             extra_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        发送Markdown Webhook
        
        Args:
            title: 标题
            markdown_content: Markdown内容
            extra_data: 额外数据
            
        Returns:
            Dict: 发送结果
        """
        data = {
            "type": "markdown",
            "title": title,
            "content": markdown_content,
            "timestamp": datetime.now().isoformat()
        }
        
        if extra_data:
            data.update(extra_data)
        
        return self.send_webhook(data)
    
    def send_image_webhook(self, title: str, image_paths: List[str],
                          description: str = "", extra_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        发送图片Webhook（Base64编码）
        
        Args:
            title: 标题
            image_paths: 图片路径列表
            description: 描述
            extra_data: 额外数据
            
        Returns:
            Dict: 发送结果
        """
        images_data = []
        
        for image_path in image_paths:
            if not Path(image_path).exists():
                logger.warning(f"图片文件不存在: {image_path}")
                continue
            
            try:
                with open(image_path, 'rb') as f:
                    image_data = f.read()
                
                # Base64编码
                encoded_image = base64.b64encode(image_data).decode('utf-8')
                
                # 获取文件信息
                file_info = {
                    "filename": Path(image_path).name,
                    "size": len(image_data),
                    "data": encoded_image,
                    "mime_type": mimetypes.guess_type(image_path)[0] or "image/jpeg"
                }
                
                images_data.append(file_info)
                
            except Exception as e:
                logger.error(f"处理图片失败 {image_path}: {str(e)}")
        
        data = {
            "type": "image",
            "title": title,
            "description": description,
            "images": images_data,
            "timestamp": datetime.now().isoformat()
        }
        
        if extra_data:
            data.update(extra_data)
        
        return self.send_webhook(data)

class PlatformExtensionManager:
    """平台扩展管理器"""
    
    def __init__(self):
        self.dingtalk_bots: Dict[str, EnhancedDingtalkBot] = {}
        self.email_bots: Dict[str, EmailPushBot] = {}
        self.webhook_bots: Dict[str, WebhookPushBot] = {}
        self.executor = ThreadPoolExecutor(max_workers=10)
    
    def add_dingtalk_bot(self, name: str, config: DingtalkEnhancedConfig):
        """添加钉钉机器人"""
        self.dingtalk_bots[name] = EnhancedDingtalkBot(config)
        logger.info(f"添加钉钉机器人: {name}")
    
    def add_email_bot(self, name: str, config: EmailConfig):
        """添加邮件机器人"""
        self.email_bots[name] = EmailPushBot(config)
        logger.info(f"添加邮件机器人: {name}")
    
    def add_webhook_bot(self, name: str, config: WebhookConfig):
        """添加Webhook机器人"""
        self.webhook_bots[name] = WebhookPushBot(config)
        logger.info(f"添加Webhook机器人: {name}")
    
    def broadcast_message(self, title: str, content: str, 
                         platforms: List[str] = None, 
                         message_type: str = "text") -> Dict[str, Any]:
        """
        广播消息到多个平台
        
        Args:
            title: 消息标题
            content: 消息内容
            platforms: 指定平台列表，None表示所有平台
            message_type: 消息类型
            
        Returns:
            Dict: 广播结果
        """
        results = {}
        futures = []
        
        # 钉钉平台
        for name, bot in self.dingtalk_bots.items():
            if platforms is None or f"dingtalk_{name}" in platforms:
                if message_type == "markdown":
                    future = self.executor.submit(bot.send_markdown_message, title, content)
                else:
                    future = self.executor.submit(bot.send_text_message, f"{title}\n{content}")
                futures.append((f"dingtalk_{name}", future))
        
        # 邮件平台
        for name, bot in self.email_bots.items():
            if platforms is None or f"email_{name}" in platforms:
                # 这里需要配置收件人列表
                recipients = self._get_email_recipients(name)
                if recipients:
                    if message_type == "html":
                        future = self.executor.submit(bot.send_html_email, recipients, title, content)
                    else:
                        future = self.executor.submit(bot.send_text_email, recipients, title, content)
                    futures.append((f"email_{name}", future))
        
        # Webhook平台
        for name, bot in self.webhook_bots.items():
            if platforms is None or f"webhook_{name}" in platforms:
                if message_type == "markdown":
                    future = self.executor.submit(bot.send_markdown_webhook, title, content)
                else:
                    future = self.executor.submit(bot.send_text_webhook, title, content)
                futures.append((f"webhook_{name}", future))
        
        # 收集结果
        for platform_name, future in futures:
            try:
                result = future.result(timeout=30)
                results[platform_name] = result
            except Exception as e:
                results[platform_name] = {"success": False, "error": str(e)}
        
        return results
    
    def _get_email_recipients(self, bot_name: str) -> List[str]:
        """
        获取邮件收件人列表（需要根据实际配置实现）
        
        Args:
            bot_name: 机器人名称
            
        Returns:
            List[str]: 收件人列表
        """
        # 这里应该从配置文件或数据库中获取收件人列表
        # 示例实现
        default_recipients = {
            "admin": ["admin@example.com"],
            "alert": ["alert@example.com", "monitor@example.com"],
            "report": ["report@example.com"]
        }
        
        return default_recipients.get(bot_name, [])
    
    def get_platform_status(self) -> Dict[str, Any]:
        """
        获取所有平台状态
        
        Returns:
            Dict: 平台状态信息
        """
        return {
            "dingtalk_bots": list(self.dingtalk_bots.keys()),
            "email_bots": list(self.email_bots.keys()),
            "webhook_bots": list(self.webhook_bots.keys()),
            "total_platforms": len(self.dingtalk_bots) + len(self.email_bots) + len(self.webhook_bots)
        }
    
    def shutdown(self):
        """关闭管理器"""
        self.executor.shutdown(wait=True)
        logger.info("平台扩展管理器已关闭")