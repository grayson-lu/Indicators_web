#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一企业微信每日推送模块
整合所有推送功能，实现每天早上定时推送丰富的市场数据报告
"""

import os
import sys
import json
import time
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 企业微信机器人推送类
class WechatWorkBot:
    """企业微信机器人推送"""
    
    def __init__(self, webhook: str):
        """初始化企业微信机器人
        
        Args:
            webhook: 可以是完整的企业微信机器人 Webhook URL，或仅包含 `key` 的字符串
        
        Returns:
            None
        """
        import re
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 规范化与校验 webhook 输入（支持完整URL或仅key，宽松提取key）
        def normalize_webhook(inp: str) -> tuple[str | None, str | None]:
            """规范化并校验Webhook
            
            Args:
                inp: 用户传入的Webhook（完整URL或key）
            
            Returns:
                (normalized_url, error_msg): 若校验失败则返回(None, 错误信息)
            """
            if not inp:
                return None, "未提供Webhook"
            val = inp.strip().strip('`')
            key = None
            # 完整URL：宽松匹配，提取 ?key= 后的值
            if val.lower().startswith("http"):
                m = re.search(r"key=([A-Za-z0-9\-]{8,})", val)
                if m:
                    key = m.group(1)
                else:
                    return None, "Webhook URL缺少或不含合法key参数"
            else:
                # 仅key：宽松长度校验
                if re.match(r"^[A-Za-z0-9\-]{8,}$", val):
                    key = val
                else:
                    return None, "Webhook key格式不正确"
            # 构造规范URL
            normalized_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"
            return normalized_url, None
        
        normalized, err = normalize_webhook(webhook)
        if err:
            self.logger.error(f"Webhook校验失败: {err}")
        else:
            obfuscated = (normalized.split('key=')[-1][:8] + '...') if normalized and 'key=' in normalized else 'unknown'
            self.logger.info(f"Webhook已配置 (key: {obfuscated})")
        self.webhook_url = normalized
    def send_text(self, content: str, mentioned_list: List[str] = None, mentioned_mobile_list: List[str] = None) -> "NotificationResult":
        """发送文本消息
        
        Args:
            content: 文本内容
            mentioned_list: 需要@的用户ID列表
            mentioned_mobile_list: 需要@的手机号列表
        
        Returns:
            NotificationResult: 结构化推送结果
        """
        if not self.webhook_url:
            msg = "未配置有效的企业微信Webhook"
            self.logger.error(msg)
            return NotificationResult(False, msg, platform="wechat_work", level="error")
        try:
            data = {
                "msgtype": "text",
                "text": {
                    "content": content,
                    "mentioned_list": mentioned_list or [],
                    "mentioned_mobile_list": mentioned_mobile_list or []
                }
            }
            response = self.session.post(self.webhook_url, json=data, timeout=30)
            result = {}
            try:
                result = response.json()
            except Exception:
                pass
            if isinstance(result, dict) and result.get('errcode') == 0:
                self.logger.info("文本消息发送成功")
                return NotificationResult(True, "ok", platform="wechat_work", level="success")
            errcode = (result or {}).get('errcode')
            errmsg = (result or {}).get('errmsg') or f"HTTP {response.status_code}"
            self.logger.error(f"文本消息发送失败: {{'errcode': {errcode}, 'errmsg': '{errmsg}'}}")
            return NotificationResult(False, errmsg, platform="wechat_work", level="error")
        except Exception as e:
            self.logger.error(f"发送文本消息异常: {e}")
            return NotificationResult(False, f"请求异常: {e}", platform="wechat_work", level="error")
    def send_markdown(self, content: str) -> "NotificationResult":
        """发送Markdown消息
        
        Args:
            content: Markdown内容
        
        Returns:
            NotificationResult: 结构化推送结果
        """
        if not self.webhook_url:
            msg = "未配置有效的企业微信Webhook"
            self.logger.error(msg)
            return NotificationResult(False, msg, platform="wechat_work", level="error")
        try:
            data = {
                "msgtype": "markdown",
                "markdown": {
                    "content": content
                }
            }
            response = self.session.post(self.webhook_url, json=data, timeout=30)
            result = {}
            try:
                result = response.json()
            except Exception:
                pass
            if isinstance(result, dict) and result.get('errcode') == 0:
                self.logger.info("Markdown消息发送成功")
                return NotificationResult(True, "ok", platform="wechat_work", level="success")
            errcode = (result or {}).get('errcode')
            errmsg = (result or {}).get('errmsg') or f"HTTP {response.status_code}"
            self.logger.error(f"Markdown消息发送失败: {{'errcode': {errcode}, 'errmsg': '{errmsg}'}}")
            return NotificationResult(False, errmsg, platform="wechat_work", level="error")
        except Exception as e:
            self.logger.error(f"发送Markdown消息异常: {e}")
            return NotificationResult(False, f"请求异常: {e}", platform="wechat_work", level="error")
    def send_image(self, base64_content: str, md5: str) -> "NotificationResult":
        """发送图片消息
        
        Args:
            base64_content: 图片base64编码
            md5: 图片MD5值
        
        Returns:
            NotificationResult: 结构化推送结果
        """
        if not self.webhook_url:
            msg = "未配置有效的企业微信Webhook"
            self.logger.error(msg)
            return NotificationResult(False, msg, platform="wechat_work", level="error")
        try:
            data = {
                "msgtype": "image",
                "image": {
                    "base64": base64_content,
                    "md5": md5
                }
            }
            response = self.session.post(self.webhook_url, json=data, timeout=30)
            result = {}
            try:
                result = response.json()
            except Exception:
                pass
            if isinstance(result, dict) and result.get('errcode') == 0:
                self.logger.info("图片消息发送成功")
                return NotificationResult(True, "ok", platform="wechat_work", level="success")
            errcode = (result or {}).get('errcode')
            errmsg = (result or {}).get('errmsg') or f"HTTP {response.status_code}"
            self.logger.error(f"图片消息发送失败: {{'errcode': {errcode}, 'errmsg': '{errmsg}'}}")
            return NotificationResult(False, errmsg, platform="wechat_work", level="error")
        except Exception as e:
            self.logger.error(f"发送图片消息异常: {e}")
            return NotificationResult(False, f"请求异常: {e}", platform="wechat_work", level="error")


# 通知结果类
class NotificationResult:
    """推送结果封装"""
    
    def __init__(self, success: bool = False, message: str = "", platform: str = "", level: str = "info"):
        """初始化推送结果
        
        Args:
            success: 推送是否成功
            message: 结果消息
            platform: 推送平台
            level: 通知级别
        """
        self.success = success
        self.message = message
        self.platform = platform
        self.level = level
        self.timestamp = datetime.now()


# 通知级别枚举
class NotificationLevel:
    """通知级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"
    CRITICAL = "critical"
# 数据验证工具函数
def safe_dataframe_get(df, column: str | None = None, default: float = 0.0, index: int | None = None):
    """安全地从DataFrame获取数据（兼容index参数）
    
    函数级注释：
    - 支持通过`column`获取最后一个有效值；
    - 支持通过`index`指定位置访问（如`index=-1`取最后一行）；
    - 当列不存在、索引越界或值为NaN时，返回`default`并静默处理。
    
    Args:
        df: DataFrame对象
        column: 列名（可选）
        default: 默认返回值（数值型）
        index: 行索引（可选，支持负索引）
    
    Returns:
        - 若提供`column`且未提供`index`：返回该列最后一个有效数值；
        - 若同时提供`column`与`index`：返回该列在指定索引处的数值；
        - 若仅提供`index`：返回该行（Series），失败时返回`default`；
        - 其它情况：返回`default`。
    """
    try:
        if df is None or not isinstance(df, pd.DataFrame) or len(df) == 0:
            return default

        # 同时提供列与索引：优先返回该列的指定位置值
        if column is not None and isinstance(column, str) and column in df.columns:
            if index is None:
                # 取最后一个有效值
                val = df[column].iloc[-1]
                return val if not pd.isna(val) else default
            else:
                # 位置访问（兼容负索引）
                try:
                    val = df[column].iloc[index]
                    return val if not pd.isna(val) else default
                except Exception:
                    return default

        # 仅提供索引：返回整行（兼容历史调用）
        if index is not None:
            try:
                row = df.iloc[index]
                return row if row is not None else default
            except Exception:
                return default

        # 未提供有效列或索引：返回默认值
        return default
    except Exception:
        return default

def safe_read_csv(file_path: str | Path) -> Optional[pd.DataFrame]:
    """安全读取CSV为DataFrame
    
    Args:
        file_path: 文件路径（Path或字符串）
    
    Returns:
        DataFrame或None：读取失败或文件不存在时返回None
    """
    try:
        fp = Path(file_path)
        if not fp.exists():
            return None
        df = pd.read_csv(fp)
        # 若包含日期列，按日期排序保证最新在最后一行
        for col in ['date', 'Date', 'timestamp']:
            if col in df.columns:
                try:
                    df[col] = pd.to_datetime(df[col], errors='coerce')
                    df = df.sort_values(by=col)
                except Exception:
                    pass
                break
        return df
    except Exception:
        return None

def validate_numeric_range(value, min_val=None, max_val=None, default=0.0, name: str | None = None, **kwargs):
    """验证数值范围（兼容name与额外参数）
    
    函数级注释：
    - 兼容历史调用传入的`name`与其它冗余参数，避免因签名不匹配抛错；
    - 对None/NaN返回`default`；越界时钳制到[min_val, max_val]；
    - 返回类型为数值，用于数据清洗与容错。
    
    Args:
        value: 原始数值
        min_val: 最小边界（可选）
        max_val: 最大边界（可选）
        default: 默认返回值
        name: 字段名（可选，仅用于兼容，不影响逻辑）
        **kwargs: 兼容额外参数，安全忽略
    
    Returns:
        数值：按边界钳制后的值或默认值
    """
    try:
        if value is None or pd.isna(value):
            return default
        # 尝试转换为浮点数
        try:
            v = float(value)
        except (ValueError, TypeError):
            return default
        if min_val is not None and v < float(min_val):
            return float(min_val)
        if max_val is not None and v > float(max_val):
            return float(max_val)
        return v
    except Exception:
        return default

def safe_parse_float(value, default=0.0):
    """安全地解析浮点数"""
    try:
        if value is None:
            return default
        return float(value)
    except (ValueError, TypeError):
        return default

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('daily_wechat_push.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DailyMarketDataCollector:
    """市场数据收集器"""
    
    def __init__(self):
        self.data_dir = Path("y_data")
        self.market_data_cache = {}
        
    def get_y_index_data(self) -> Dict[str, Any]:
        """获取Y指数数据"""
        try:
            y_idx_file = self.data_dir / "y_idx.csv"
            if not y_idx_file.exists():
                logger.warning("Y指数数据文件不存在")
                return {}
                
            df = safe_read_csv(y_idx_file)
            if df is None or df.empty:
                logger.warning("Y指数数据为空")
                return {}
                
            # 获取最新数据
            latest_data = df.iloc[-1]
            
            # 计算变化率
            y_idx_values = df['y_idx'].values if 'y_idx' in df.columns else []
            if len(y_idx_values) >= 2:
                change_1d = ((y_idx_values[-1] - y_idx_values[-2]) / y_idx_values[-2] * 100) if y_idx_values[-2] != 0 else 0
            else:
                change_1d = 0
                
            if len(y_idx_values) >= 8:
                change_7d = ((y_idx_values[-1] - y_idx_values[-8]) / y_idx_values[-8] * 100) if y_idx_values[-8] != 0 else 0
            else:
                change_7d = 0
                
            if len(y_idx_values) >= 31:
                change_30d = ((y_idx_values[-1] - y_idx_values[-31]) / y_idx_values[-31] * 100) if y_idx_values[-31] != 0 else 0
            else:
                change_30d = 0
            
            return {
                'current_value': safe_parse_float(latest_data.get('y_idx', 0)),
                'change_1d': round(change_1d, 2),
                'change_7d': round(change_7d, 2),
                'change_30d': round(change_30d, 2),
                'date': latest_data.get('date', '未知')
            }
            
        except Exception as e:
            logger.error(f"获取Y指数数据失败: {e}")
            return {}
    
    def get_market_sentiment(self) -> Dict[str, Any]:
        """获取市场情绪数据"""
        try:
            sentiment_file = self.data_dir / "market_sentiment.csv"
            if not sentiment_file.exists():
                return {}
                
            df = safe_read_csv(sentiment_file)
            if df is None or df.empty:
                return {}
                
            latest = df.iloc[-1]
            return {
                'fear_greed_index': safe_parse_float(latest.get('fear_greed_index', 50)),
                'sentiment_level': latest.get('sentiment_level', '中性'),
                'extreme_coins_ratio': safe_parse_float(latest.get('extreme_coins_ratio', 0)),
                'ahp999_index': safe_parse_float(latest.get('ahp999', 0))
            }
            
        except Exception as e:
            logger.error(f"获取市场情绪数据失败: {e}")
            return {}
    
    def get_market_breadth(self) -> Dict[str, Any]:
        """获取市场宽度数据"""
        try:
            breadth_file = self.data_dir / "market_breadth.csv"
            if not breadth_file.exists():
                return {}
                
            df = safe_read_csv(breadth_file)
            if df is None or df.empty:
                return {}
                
            latest = df.iloc[-1]
            return {
                'new_high_ratio': safe_parse_float(latest.get('new_high_ratio', 0)),
                'new_low_ratio': safe_parse_float(latest.get('new_low_ratio', 0)),
                'advance_decline_ratio': safe_parse_float(latest.get('advance_decline_ratio', 1)),
                'ad_percentage': safe_parse_float(latest.get('ad_percentage', 50))
            }
            
        except Exception as e:
            logger.error(f"获取市场宽度数据失败: {e}")
            return {}
    
    def get_chain_metrics(self) -> Dict[str, Any]:
        """获取链上指标"""
        try:
            chain_file = self.data_dir / "chain_metrics.csv"
            if not chain_file.exists():
                return {}
                
            df = safe_read_csv(chain_file)
            if df is None or df.empty:
                return {}
                
            latest = df.iloc[-1]
            return {
                'mvrv_ratio': safe_parse_float(latest.get('mvrv_ratio', 1)),
                'stablecoin_supply': safe_parse_float(latest.get('stablecoin_supply', 0)),
                'exchange_netflow': safe_parse_float(latest.get('exchange_netflow', 0)),
                'funding_rate_avg': safe_parse_float(latest.get('funding_rate_avg', 0))
            }
            
        except Exception as e:
            logger.error(f"获取链上指标失败: {e}")
            return {}
    
    def get_volatility_data(self) -> Dict[str, Any]:
        """获取波动率数据"""
        try:
            vol_file = self.data_dir / "volatility_data.csv"
            if not vol_file.exists():
                return {}
                
            df = safe_read_csv(vol_file)
            if df is None or df.empty:
                return {}
                
            latest = df.iloc[-1]
            return {
                'volatility_30d': safe_parse_float(latest.get('volatility_30d', 0)),
                'volatility_7d': safe_parse_float(latest.get('volatility_7d', 0)),
                'market_liquidity': safe_parse_float(latest.get('market_liquidity', 0))
            }
            
        except Exception as e:
            logger.error(f"获取波动率数据失败: {e}")
            return {}
    
    def collect_all_data(self) -> Dict[str, Any]:
        """收集所有市场数据"""
        logger.info("开始收集市场数据...")
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(self.get_y_index_data): "y_index",
                executor.submit(self.get_market_sentiment): "sentiment",
                executor.submit(self.get_market_breadth): "breadth",
                executor.submit(self.get_chain_metrics): "chain",
                executor.submit(self.get_volatility_data): "volatility"
            }
            
            results = {}
            for future in as_completed(futures):
                data_type = futures[future]
                try:
                    results[data_type] = future.result()
                    logger.info(f"成功收集 {data_type} 数据")
                except Exception as e:
                    logger.error(f"收集 {data_type} 数据失败: {e}")
                    results[data_type] = {}
        
        # 添加时间戳
        results['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        results['status'] = 'success'
        
        logger.info("市场数据收集完成")
        return results

class RichContentGenerator:
    """丰富内容生成器"""
    
    def __init__(self):
        self.emojis = {
            'up': '📈',
            'down': '📉',
            'flat': '➡️',
            'warning': '⚠️',
            'info': 'ℹ️',
            'rocket': '🚀',
            'chart': '📊',
            'money': '💰',
            'fire': '🔥',
            'cold': '❄️',
            'extreme': '🔴',
            'neutral': '🟡',
            'safe': '🟢'
        }
    
    def format_percentage(self, value: float, include_sign: bool = True) -> str:
        """格式化百分比"""
        sign = '+' if value > 0 else '' if value == 0 else '-'
        abs_value = abs(value)
        formatted = f"{abs_value:.2f}%"
        
        if include_sign:
            formatted = f"{sign}{formatted}"
        
        # 添加表情符号
        if value > 5:
            emoji = self.emojis['rocket']
        elif value > 1:
            emoji = self.emojis['up']
        elif value > -1:
            emoji = self.emojis['flat']
        elif value > -5:
            emoji = self.emojis['down']
        else:
            emoji = self.emojis['cold']
            
        return f"{formatted} {emoji}"
    
    def get_sentiment_emoji(self, level: str) -> str:
        """根据情绪水平获取表情"""
        level_lower = level.lower()
        if '恐' in level_lower or 'panic' in level_lower:
            return self.emojis['cold']
        elif '贪' in level_lower or 'greed' in level_lower:
            return self.emojis['fire']
        elif '极' in level_lower or 'extreme' in level_lower:
            return self.emojis['extreme']
        else:
            return self.emojis['neutral']
    
    def generate_markdown_report(self, data: Dict[str, Any]) -> str:
        """生成Markdown格式的市场报告"""
        
        # 标题部分
        report_time = data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        title = f"📊 **每日市场报告** - {report_time.split()[0]}"
        
        markdown_lines = [title, "=" * 40, ""]
        
        # Y指数部分
        y_data = data.get('y_index', {})
        if y_data:
            current = y_data.get('current_value', 0)
            change_1d = y_data.get('change_1d', 0)
            change_7d = y_data.get('change_7d', 0)
            change_30d = y_data.get('change_30d', 0)
            
            markdown_lines.extend([
                "## 🎯 Y指数概览",
                f"**当前值**: {current:.2f}",
                f"**日变化**: {self.format_percentage(change_1d)}",
                f"**周变化**: {self.format_percentage(change_7d)}",
                f"**月变化**: {self.format_percentage(change_30d)}",
                ""
            ])
        
        # 市场情绪部分
        sentiment_data = data.get('sentiment', {})
        if sentiment_data:
            fg_index = sentiment_data.get('fear_greed_index', 50)
            level = sentiment_data.get('sentiment_level', '中性')
            extreme_ratio = sentiment_data.get('extreme_coins_ratio', 0)
            ahp999 = sentiment_data.get('ahp999_index', 0)
            
            sentiment_emoji = self.get_sentiment_emoji(level)
            
            markdown_lines.extend([
                "## 😊 市场情绪",
                f"**恐慌贪婪指数**: {fg_index:.1f} {sentiment_emoji}",
                f"**情绪等级**: {level}",
                f"**极端币种比例**: {extreme_ratio:.2f}%",
                f"**AHR999指数**: {ahp999:.3f}",
                ""
            ])
        
        # 市场宽度部分
        breadth_data = data.get('breadth', {})
        if breadth_data:
            new_high = breadth_data.get('new_high_ratio', 0)
            new_low = breadth_data.get('new_low_ratio', 0)
            ad_ratio = breadth_data.get('advance_decline_ratio', 1)
            ad_percentage = breadth_data.get('ad_percentage', 50)
            
            markdown_lines.extend([
                "## 📈 市场宽度",
                f"**新高比例**: {new_high:.2f}% {self.emojis['up'] if new_high > new_low else self.emojis['down']}",
                f"**新低比例**: {new_low:.2f}%",
                f"**涨跌比**: {ad_ratio:.2f}",
                f"**A/D百分比**: {ad_percentage:.1f}%",
                ""
            ])
        
        # 链上指标部分
        chain_data = data.get('chain', {})
        if chain_data:
            mvrv = chain_data.get('mvrv_ratio', 1)
            stable_supply = chain_data.get('stablecoin_supply', 0)
            netflow = chain_data.get('exchange_netflow', 0)
            funding = chain_data.get('funding_rate_avg', 0)
            
            # MVRV解读
            if mvrv > 3.5:
                mvrv_status = "🔴 高风险"
            elif mvrv > 2.5:
                mvrv_status = "🟡 中等风险"
            else:
                mvrv_status = "🟢 相对安全"
            
            # 资金费率解读
            if funding > 0.02:
                funding_status = "🔴 极度乐观"
            elif funding > 0.01:
                funding_status = "🟡 乐观"
            elif funding < -0.01:
                funding_status = "🔵 悲观"
            else:
                funding_status = "🟢 中性"
            
            markdown_lines.extend([
                "## ⛓️ 链上指标",
                f"**MVRV比率**: {mvrv:.2f} {mvrv_status}",
                f"**稳定币供应量**: {stable_supply:,.0f} USDT",
                f"**交易所净流入**: {netflow:+,.0f} USDT {self.emojis['up'] if netflow > 0 else self.emojis['down']}",
                f"**平均资金费率**: {funding:.4f}% {funding_status}",
                ""
            ])
        
        # 波动率部分
        vol_data = data.get('volatility', {})
        if vol_data:
            vol_30d = vol_data.get('volatility_30d', 0)
            vol_7d = vol_data.get('volatility_7d', 0)
            liquidity = vol_data.get('market_liquidity', 0)
            
            # 波动率解读
            if vol_30d > 80:
                vol_status = "🔴 极高波动"
            elif vol_30d > 60:
                vol_status = "🟡 高波动"
            elif vol_30d > 40:
                vol_status = "🟢 中等波动"
            else:
                vol_status = "🔵 低波动"
            
            markdown_lines.extend([
                "## 📊 波动率分析",
                f"**30天波动率**: {vol_30d:.1f}% {vol_status}",
                f"**7天波动率**: {vol_7d:.1f}%",
                f"**市场流动性**: {liquidity:.1f}",
                ""
            ])
        
        # 总结部分
        markdown_lines.extend([
            "## 💡 市场总结",
            self._generate_market_summary(data),
            "",
            "---",
            "📱 *本报告由Y指数系统自动生成*",
            "🔍 *数据来源: 全市场多维度分析*",
            f"⏰ *更新时间: {report_time}*"
        ])
        
        return "\n".join(markdown_lines)
    
    def _generate_market_summary(self, data: Dict[str, Any]) -> str:
        """生成市场总结"""
        summary_parts = []
        
        # Y指数总结
        y_data = data.get('y_index', {})
        if y_data:
            change_1d = y_data.get('change_1d', 0)
            if change_1d > 3:
                summary_parts.append("🚀 市场强势上涨，Y指数显示积极信号")
            elif change_1d < -3:
                summary_parts.append("📉 市场明显回调，需要关注风险")
            else:
                summary_parts.append("➡️ 市场相对平稳，维持震荡格局")
        
        # 情绪总结
        sentiment_data = data.get('sentiment', {})
        if sentiment_data:
            fg_index = sentiment_data.get('fear_greed_index', 50)
            if fg_index > 75:
                summary_parts.append("🔥 市场情绪极度贪婪，注意泡沫风险")
            elif fg_index > 55:
                summary_parts.append("😊 市场情绪偏向乐观")
            elif fg_index < 25:
                summary_parts.append("❄️ 市场情绪恐慌，可能是买入机会")
            else:
                summary_parts.append("😐 市场情绪相对理性")
        
        # 链上总结
        chain_data = data.get('chain', {})
        if chain_data:
            mvrv = chain_data.get('mvrv_ratio', 1)
            funding = chain_data.get('funding_rate_avg', 0)
            
            if mvrv > 3.5:
                summary_parts.append("⚠️ 链上数据显示高估风险")
            if funding > 0.02:
                summary_parts.append("📈 资金费率显示市场过热")
            elif funding < -0.02:
                summary_parts.append("📉 资金费率显示市场过度悲观")
        
        if not summary_parts:
            return "📊 市场数据正常，建议持续关注"
        
        return "\n".join(summary_parts)

class DailyWechatPushSystem:
    """每日企业微信推送系统"""
    
    def __init__(self, webhook_url: str = None):
        """初始化推送系统"""
        self.webhook_url = webhook_url or os.getenv('WECHAT_WEBHOOK_URL')
        if not self.webhook_url:
            raise ValueError("未配置企业微信Webhook地址")
        
        self.wechat_bot = WechatWorkBot(self.webhook_url)
        self.data_collector = DailyMarketDataCollector()
        self.content_generator = RichContentGenerator()
        
        logger.info("每日企业微信推送系统初始化完成")
    
    def send_daily_report(self) -> NotificationResult:
        """发送每日市场报告"""
        try:
            logger.info("开始生成每日市场报告...")
            
            # 收集数据
            market_data = self.data_collector.collect_all_data()
            
            if not market_data or market_data.get('status') != 'success':
                error_msg = "市场数据收集失败"
                logger.error(error_msg)
                return NotificationResult(False, error_msg)
            
            # 生成内容
            markdown_content = self.content_generator.generate_markdown_report(market_data)
            
            # 发送消息
            result = self.wechat_bot.send_markdown(markdown_content)
            
            if result.success:
                logger.info("每日市场报告发送成功")
            else:
                logger.error(f"每日市场报告发送失败: {result.message}")
            
            return result
            
        except Exception as e:
            error_msg = f"发送每日报告异常: {str(e)}"
            logger.error(error_msg)
            return NotificationResult(False, error_msg)
    
    def send_simple_text(self, content: str) -> NotificationResult:
        """发送简单文本消息"""
        return self.wechat_bot.send_text(content)
    
    def send_markdown(self, content: str) -> NotificationResult:
        """发送Markdown消息"""
        return self.wechat_bot.send_markdown(content)
    
    def test_connection(self) -> NotificationResult:
        """测试企业微信Webhook连通性
        
        Returns:
            NotificationResult: 包含success与message的结构化结果
        """
        try:
            test_result = self.send_simple_text("🧪 企业微信推送连接测试")
            if test_result.success:
                logger.info("连接测试成功")
            else:
                logger.error(f"连接测试失败: {test_result.message}")
            return test_result
        except Exception as e:
            logger.error(f"连接测试异常: {e}")
            return NotificationResult(False, f"连接测试异常: {e}")

def create_daily_push_scheduler():
    """创建每日推送调度器"""
    import schedule
    import time
    
    webhook_url = os.getenv('WECHAT_WEBHOOK_URL')
    if not webhook_url:
        logger.error("未配置企业微信Webhook地址，请设置 WECHAT_WEBHOOK_URL 环境变量")
        return None
    
    try:
        push_system = DailyWechatPushSystem(webhook_url)
        
        # 测试连接
        test_result = push_system.test_connection()
        if not test_result or not test_result.success:
            logger.error("企业微信连接测试失败")
            return None
        
        # 每天早上8点推送
        schedule.every().day.at("08:00").do(push_system.send_daily_report)
        
        # 添加一些测试时间（可选）
        schedule.every().day.at("09:30").do(push_system.send_daily_report)  # 早盘
        schedule.every().day.at("15:00").do(push_system.send_daily_report)  # 午盘
        schedule.every().day.at("21:00").do(push_system.send_daily_report)  # 晚盘
        
        logger.info("每日推送调度器创建成功")
        logger.info("推送时间: 08:00, 09:30, 15:00, 21:00")
        
        return push_system
        
    except Exception as e:
        logger.error(f"创建推送调度器失败: {e}")
        return None

def main():
    """主函数"""
    logger.info("启动每日企业微信推送系统...")
    
    # 创建调度器
    push_system = create_daily_push_scheduler()
    
    if push_system is None:
        logger.error("推送系统初始化失败")
        return 1
    
    logger.info("推送系统运行中...")
    logger.info("按 Ctrl+C 停止程序")
    
    try:
        # 立即执行一次测试
        logger.info("执行初始测试推送...")
        result = push_system.send_daily_report()
        if result.success:
            logger.info("初始测试推送成功")
        else:
            logger.error(f"初始测试推送失败: {result.message}")
        
        # 运行调度器
        import schedule
        import time
        
        while True:
            schedule.run_pending()
            time.sleep(60)  # 每分钟检查一次
            
    except KeyboardInterrupt:
        logger.info("用户停止程序")
        return 0
    except Exception as e:
        logger.error(f"程序运行异常: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)