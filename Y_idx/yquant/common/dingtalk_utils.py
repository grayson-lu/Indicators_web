"""
钉钉推送工具类
支持文本、Markdown消息推送，以及@用户功能
"""
import requests
import json
import time
import hmac
import hashlib
import base64
import urllib.parse
from datetime import datetime
from typing import List, Dict, Optional, Any

class DingtalkBot:
    """钉钉机器人推送类"""
    
    def __init__(self, webhook_url: str, secret: str = ""):
        """
        初始化钉钉机器人
        
        Args:
            webhook_url: 钉钉机器人的 webhook 地址
            secret: 加签密钥（可选）
        """
        self.webhook_url = webhook_url
        self.secret = secret
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json;charset=utf-8',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def _get_signed_url(self) -> str:
        """
        获取加签后的URL（如果配置了secret）
        
        Returns:
            str: 签名后的webhook地址
        """
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
    
    def send_text(self, content: str, mentioned_list: List[str] = None,
                  mentioned_mobile_list: List[str] = None, is_at_all: bool = False) -> bool:
        """
        发送文本消息
        
        Args:
            content: 消息内容
            mentioned_list: @的用户id列表
            mentioned_mobile_list: @的用户手机号列表
            is_at_all: 是否@所有人
            
        Returns:
            bool: 发送是否成功
        """
        try:
            data = {
                "msgtype": "text",
                "text": {
                    "content": content
                },
                "at": {
                    "atUserIds": mentioned_list or [],
                    "atMobiles": mentioned_mobile_list or [],
                    "isAtAll": is_at_all
                }
            }
            
            url = self._get_signed_url()
            response = self.session.post(url, json=data, timeout=30)
            result = response.json()
            
            if result.get('errcode') == 0:
                print(f"钉钉文本消息发送成功: {content[:50]}...")
                return True
            else:
                print(f"钉钉文本消息发送失败: {result}")
                return False
                
        except Exception as e:
            print(f"发送钉钉文本消息异常: {e}")
            return False
    
    def send_markdown(self, title: str, content: str, mentioned_list: List[str] = None,
                      mentioned_mobile_list: List[str] = None, is_at_all: bool = False) -> bool:
        """
        发送Markdown消息
        
        Args:
            title: 消息标题
            content: Markdown格式的消息内容
            mentioned_list: @的用户id列表
            mentioned_mobile_list: @的用户手机号列表
            is_at_all: 是否@所有人
            
        Returns:
            bool: 发送是否成功
        """
        try:
            data = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": content
                },
                "at": {
                    "atUserIds": mentioned_list or [],
                    "atMobiles": mentioned_mobile_list or [],
                    "isAtAll": is_at_all
                }
            }
            
            url = self._get_signed_url()
            response = self.session.post(url, json=data, timeout=30)
            result = response.json()
            
            if result.get('errcode') == 0:
                print(f"钉钉Markdown消息发送成功: {title}")
                return True
            else:
                print(f"钉钉Markdown消息发送失败: {result}")
                return False
                
        except Exception as e:
            print(f"发送钉钉Markdown消息异常: {e}")
            return False
    
    def send_link(self, title: str, text: str, message_url: str, pic_url: str = "") -> bool:
        """
        发送链接消息
        
        Args:
            title: 消息标题
            text: 消息内容
            message_url: 点击消息跳转的URL
            pic_url: 图片URL
            
        Returns:
            bool: 发送是否成功
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
            response = self.session.post(url, json=data, timeout=30)
            result = response.json()
            
            if result.get('errcode') == 0:
                print(f"钉钉链接消息发送成功: {title}")
                return True
            else:
                print(f"钉钉链接消息发送失败: {result}")
                return False
                
        except Exception as e:
            print(f"发送钉钉链接消息异常: {e}")
            return False
    
    def send_action_card(self, title: str, text: str, single_title: str = "",
                        single_url: str = "", btn_orientation: str = "0",
                        hide_avatar: str = "0") -> bool:
        """
        发送ActionCard消息
        
        Args:
            title: 消息标题
            text: 消息内容（支持markdown）
            single_title: 单个按钮标题
            single_url: 单个按钮跳转链接
            btn_orientation: 按钮排列方向，0-按钮竖直排列，1-按钮横向排列
            hide_avatar: 是否隐藏发消息者头像，0-正常发消息者头像，1-隐藏发消息者头像
            
        Returns:
            bool: 发送是否成功
        """
        try:
            data = {
                "msgtype": "actionCard",
                "actionCard": {
                    "title": title,
                    "text": text,
                    "hideAvatar": hide_avatar,
                    "btnOrientation": btn_orientation,
                    "singleTitle": single_title,
                    "singleURL": single_url
                }
            }
            
            url = self._get_signed_url()
            response = self.session.post(url, json=data, timeout=30)
            result = response.json()
            
            if result.get('errcode') == 0:
                print(f"钉钉ActionCard消息发送成功: {title}")
                return True
            else:
                print(f"钉钉ActionCard消息发送失败: {result}")
                return False
                
        except Exception as e:
            print(f"发送钉钉ActionCard消息异常: {e}")
            return False

class DingtalkNotifier:
    """钉钉通知管理器"""
    
    def __init__(self, webhook_url: str, secret: str = "",
                 mentioned_users: List[str] = None, mentioned_mobiles: List[str] = None):
        """
        初始化钉钉通知管理器
        
        Args:
            webhook_url: 钉钉机器人webhook地址
            secret: 加签密钥
            mentioned_users: 默认@的用户ID列表
            mentioned_mobiles: 默认@的手机号列表
        """
        self.bot = DingtalkBot(webhook_url, secret)
        self.default_mentioned_users = mentioned_users or []
        self.default_mentioned_mobiles = mentioned_mobiles or []
    
    def send_market_summary(self, y_idx_value: float, latest_time: str, 
                          volatility_data: Dict, liquidity_data: Dict,
                          market_breadth_data: Dict, detailed_analysis: str = "") -> bool:
        """
        发送市场概况摘要
        
        Args:
            y_idx_value: Y指数值
            latest_time: 最新时间
            volatility_data: 波动率数据
            liquidity_data: 流动性数据
            market_breadth_data: 市场宽度数据
            detailed_analysis: 详细分析内容
            
        Returns:
            bool: 发送是否成功
        """
        try:
            title = "📊 Y指数市场概况报告"
            
            content = f"""# {title}

## 📊 核心指标
- **Y指数**: {y_idx_value:.2f}
- **更新时间**: {latest_time}

## 📈 波动率分析
- **7日波动率**: {volatility_data.get('7d', 'N/A')}
- **30日波动率**: {volatility_data.get('30d', 'N/A')}
- **90日波动率**: {volatility_data.get('90d', 'N/A')}

## 💧 流动性分析
- **30日流动性**: {liquidity_data.get('30d', 'N/A')}
- **90日流动性**: {liquidity_data.get('90d', 'N/A')}

## 📏 市场宽度分析
- **当前宽度**: {market_breadth_data.get('current', 'N/A')}
- **7日宽度**: {market_breadth_data.get('7d', 'N/A')}
- **30日宽度**: {market_breadth_data.get('30d', 'N/A')}

{detailed_analysis}

---
> 数据来源: Y指数量化系统 | 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
            
            return self.bot.send_markdown(
                title=title,
                content=content,
                mentioned_list=self.default_mentioned_users,
                mentioned_mobile_list=self.default_mentioned_mobiles
            )
            
        except Exception as e:
            print(f"钉钉发送市场概况失败: {e}")
            return False
    
    def send_error_notification(self, error_message: str, error_type: str = "系统错误",
                              error_module: str = "", is_urgent: bool = False) -> bool:
        """
        发送错误通知
        
        Args:
            error_message: 错误信息
            error_type: 错误类型
            error_module: 错误模块
            is_urgent: 是否紧急
            
        Returns:
            bool: 发送是否成功
        """
        try:
            title = f"⚠️ {error_type}"
            
            content = f"""# {title}

## 🕐 错误信息
- **发生时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **错误模块**: {error_module or '未知'}
- **错误详情**: {error_message}

## 🔧 处理建议
请检查系统状态并及时处理相关问题。

---
> 错误通知由Y指数量化系统自动发送"""
            
            # 紧急错误@所有人
            return self.bot.send_markdown(
                title=title,
                content=content,
                mentioned_list=self.default_mentioned_users,
                mentioned_mobile_list=self.default_mentioned_mobiles,
                is_at_all=is_urgent
            )
            
        except Exception as e:
            print(f"钉钉发送错误通知失败: {e}")
            return False
    
    def send_daily_report(self, report_data: Dict) -> bool:
        """
        发送每日报告
        
        Args:
            report_data: 报告数据字典
            
        Returns:
            bool: 发送是否成功
        """
        try:
            title = "📊 Y指数每日报告"
            
            content = f"""# {title}

## 📅 基本信息
- **报告日期**: {datetime.now().strftime('%Y年%m月%d日')}
- **Y指数**: {report_data.get('y_idx', 'N/A')}
- **市场状态**: {report_data.get('market_status', 'N/A')}

## 📊 技术指标
- **波动率**: {report_data.get('volatility', 'N/A')}
- **流动性**: {report_data.get('liquidity', 'N/A')}
- **市场宽度**: {report_data.get('market_breadth', 'N/A')}

## 💡 市场观察
{report_data.get('market_observation', '暂无特殊观察')}

## ⚠️ 风险提示
{report_data.get('risk_warning', '请关注市场风险，理性投资')}

---
> 报告由Y指数量化系统自动生成"""
            
            return self.bot.send_markdown(
                title=title,
                content=content,
                mentioned_list=self.default_mentioned_users,
                mentioned_mobile_list=self.default_mentioned_mobiles
            )
            
        except Exception as e:
            print(f"钉钉发送每日报告失败: {e}")
            return False
    
    def send_data_update_notification(self, update_summary: Dict) -> bool:
        """
        发送数据更新通知
        
        Args:
            update_summary: 更新摘要数据
            
        Returns:
            bool: 发送是否成功
        """
        try:
            title = "🔄 数据更新完成"
            
            processed_count = update_summary.get('processed_count', 0)
            processing_time = update_summary.get('processing_time', 0)
            success_rate = update_summary.get('success_rate', 0)
            
            content = f"""# {title}

## 📊 更新统计
- **更新时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **处理数据量**: {processed_count:,} 条
- **处理耗时**: {processing_time:.2f} 秒
- **成功率**: {success_rate:.1%}

## 📈 核心变化
{update_summary.get('core_changes', '数据已成功更新')}

---
> 数据更新由Y指数量化系统自动执行"""
            
            return self.bot.send_markdown(
                title=title,
                content=content
            )
            
        except Exception as e:
            print(f"钉钉发送更新通知失败: {e}")
            return False