"""
企业微信推送工具类
支持文本消息和图片推送
"""
import requests
import json
import os
import base64
from datetime import datetime
import time
from typing import List, Dict, Optional

class WechatWorkBot:
    """企业微信机器人推送类"""
    
    def __init__(self, webhook_url: str):
        """
        初始化企业微信机器人
        
        Args:
            webhook_url: 企业微信机器人的 webhook 地址
        """
        self.webhook_url = webhook_url
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def send_text(self, content: str, mentioned_list: List[str] = None, 
                  mentioned_mobile_list: List[str] = None) -> bool:
        """
        发送文本消息
        
        Args:
            content: 消息内容
            mentioned_list: @的用户列表（userid）
            mentioned_mobile_list: @的用户手机号列表
            
        Returns:
            bool: 发送是否成功
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
            
            response = self.session.post(self.webhook_url, json=data, timeout=30)
            result = response.json()
            
            if result.get('errcode') == 0:
                print(f"文本消息发送成功: {content[:50]}...")
                return True
            else:
                print(f"文本消息发送失败: {result}")
                return False
                
        except Exception as e:
            print(f"发送文本消息异常: {e}")
            return False
    
    def send_markdown(self, content: str) -> bool:
        """
        发送 Markdown 消息
        
        Args:
            content: Markdown 格式的消息内容
            
        Returns:
            bool: 发送是否成功
        """
        try:
            data = {
                "msgtype": "markdown",
                "markdown": {
                    "content": content
                }
            }
            
            response = self.session.post(self.webhook_url, json=data, timeout=30)
            result = response.json()
            
            if result.get('errcode') == 0:
                print(f"Markdown消息发送成功")
                return True
            else:
                print(f"Markdown消息发送失败: {result}")
                return False
                
        except Exception as e:
            print(f"发送Markdown消息异常: {e}")
            return False
    
    def upload_media(self, file_path: str, media_type: str = "file") -> Optional[str]:
        """
        上传媒体文件到企业微信
        
        Args:
            file_path: 文件路径
            media_type: 媒体类型 (image/file)
            
        Returns:
            str: 媒体ID，失败返回None
        """
        try:
            # 注意：企业微信机器人不支持直接上传媒体文件
            # 这里提供一个占位实现，实际需要通过企业微信API上传
            print(f"企业微信机器人不支持直接上传媒体文件: {file_path}")
            return None
            
        except Exception as e:
            print(f"上传媒体文件异常: {e}")
            return None
    
    def send_image_as_base64(self, image_path: str) -> bool:
        """
        将图片转换为base64并通过文本消息发送（受限方案）
        
        Args:
            image_path: 图片路径
            
        Returns:
            bool: 发送是否成功
        """
        try:
            if not os.path.exists(image_path):
                print(f"图片文件不存在: {image_path}")
                return False
            
            # 读取图片并转换为base64
            with open(image_path, 'rb') as f:
                image_data = f.read()
                base64_data = base64.b64encode(image_data).decode('utf-8')
            
            # 由于企业微信机器人限制，这里只能发送文件名信息
            filename = os.path.basename(image_path)
            file_size = len(image_data)
            
            content = f"📊 图表文件: {filename}\n📏 文件大小: {file_size} bytes\n⏰ 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            return self.send_text(content)
            
        except Exception as e:
            print(f"发送图片异常: {e}")
            return False

class WechatWorkNotifier:
    """企业微信通知管理器"""
    
    def __init__(self, webhook_url: str):
        """
        初始化通知管理器
        
        Args:
            webhook_url: 企业微信机器人webhook地址
        """
        self.bot = WechatWorkBot(webhook_url)
        self.image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp'}
    
    def send_market_summary(self, y_idx_value: float, latest_time: str, 
                          volatility_data: Dict, liquidity_data: Dict,
                          market_breadth_data: Dict) -> bool:
        """
        发送市场概况摘要
        
        Args:
            y_idx_value: Y指数值
            latest_time: 最新时间
            volatility_data: 波动率数据
            liquidity_data: 流动性数据
            market_breadth_data: 市场宽度数据
            
        Returns:
            bool: 发送是否成功
        """
        try:
            # 构建市场概况消息
            content = f"""📈 **Y指数市场概况报告**
            
🕐 **更新时间**: {latest_time}
📊 **Y指数**: {y_idx_value:.2f}

📉 **波动率指标**:
• 7日波动率: {volatility_data.get('7d', 'N/A')}
• 30日波动率: {volatility_data.get('30d', 'N/A')}
• 90日波动率: {volatility_data.get('90d', 'N/A')}

💧 **流动性指标**:
• 30日流动性: {liquidity_data.get('30d', 'N/A')}
• 90日流动性: {liquidity_data.get('90d', 'N/A')}

📏 **市场宽度**:
• 当日宽度: {market_breadth_data.get('current', 'N/A')}
• 7日宽度: {market_breadth_data.get('7d', 'N/A')}
• 30日宽度: {market_breadth_data.get('30d', 'N/A')}

---
*数据来源: Y指数量化系统*"""
            
            return self.bot.send_markdown(content)
            
        except Exception as e:
            print(f"发送市场概况失败: {e}")
            return False
    
    def send_chart_notifications(self, chart_files: List[str]) -> bool:
        """
        发送图表通知
        
        Args:
            chart_files: 图表文件路径列表
            
        Returns:
            bool: 发送是否成功
        """
        try:
            success_count = 0
            total_count = len(chart_files)
            
            # 发送图表列表概览
            chart_list = "\n".join([f"• {os.path.basename(f)}" for f in chart_files])
            overview_content = f"""📊 **今日图表更新完成**

📈 **生成的图表文件** ({total_count}个):
{chart_list}

⏰ **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
*所有图表已保存到本地目录*"""
            
            if self.bot.send_markdown(overview_content):
                success_count += 1
            
            # 为每个图表发送详细信息
            for chart_file in chart_files:
                if os.path.exists(chart_file):
                    filename = os.path.basename(chart_file)
                    file_size = os.path.getsize(chart_file)
                    
                    # 根据文件名判断图表类型
                    chart_type = self._get_chart_type(filename)
                    
                    detail_content = f"""📊 **{chart_type}**

📁 文件名: {filename}
📏 文件大小: {file_size:,} bytes
📅 修改时间: {datetime.fromtimestamp(os.path.getmtime(chart_file)).strftime('%Y-%m-%d %H:%M:%S')}"""
                    
                    if self.bot.send_text(detail_content):
                        success_count += 1
                    
                    # 添加延迟避免频率限制
                    time.sleep(1)
            
            print(f"图表通知发送完成: {success_count}/{total_count + 1}")
            return success_count > 0
            
        except Exception as e:
            print(f"发送图表通知失败: {e}")
            return False
    
    def _get_chart_type(self, filename: str) -> str:
        """
        根据文件名获取图表类型描述
        
        Args:
            filename: 文件名
            
        Returns:
            str: 图表类型描述
        """
        chart_types = {
            'altcoin_index': '山寨币指数',
            'volatility_index': '波动率指数',
            'volatility_combined_index': '综合波动率指数',
            'liquidity_index': '流动性指数',
            'market_breadth_index': '市场宽度指数',
            'ma_breadth_index': '均线宽度指数',
            'new_highs_index': '创新高指数',
            'marketzdf_index': '全市场涨跌幅指数',
            'ad_percentage': '涨跌比例',
            'up_down_ratio': '多空比例',
            'extreme_move_ratio': '极端波动比例',
            'btc_rainbow_table': 'BTC彩虹价格表',
            'altcoin_season_index': '山寨币季节指数',
            'fear_greed_index': '恐慌贪婪指数'
        }
        
        for key, description in chart_types.items():
            if key in filename.lower():
                return description
        
        return '未知图表类型'
    
    def send_error_notification(self, error_message: str, error_type: str = "系统错误") -> bool:
        """
        发送错误通知
        
        Args:
            error_message: 错误信息
            error_type: 错误类型
            
        Returns:
            bool: 发送是否成功
        """
        try:
            content = f"""⚠️ **{error_type}**

🕐 **时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
❌ **错误信息**: {error_message}

请检查系统状态并及时处理。"""
            
            return self.bot.send_markdown(content)
            
        except Exception as e:
            print(f"发送错误通知失败: {e}")
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
            content = f"""📊 **Y指数每日报告**

📅 **日期**: {datetime.now().strftime('%Y年%m月%d日')}

📈 **核心指标**:
• Y指数: {report_data.get('y_idx', 'N/A')}
• 市场状态: {report_data.get('market_status', 'N/A')}
• 风险等级: {report_data.get('risk_level', 'N/A')}

📊 **技术指标**:
• 波动率: {report_data.get('volatility', 'N/A')}
• 流动性: {report_data.get('liquidity', 'N/A')}
• 市场宽度: {report_data.get('market_breadth', 'N/A')}

💡 **市场观察**:
{report_data.get('market_observation', '暂无特殊观察')}

---
*报告由Y指数量化系统自动生成*"""
            
            return self.bot.send_markdown(content)
            
        except Exception as e:
            print(f"发送每日报告失败: {e}")
            return False