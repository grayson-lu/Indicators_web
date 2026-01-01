"""
统一推送通知配置
支持多平台推送配置管理
"""
import json
from pathlib import Path
from typing import Any, Dict, Optional

class NotificationConfig:
    """统一推送通知配置类"""
    
    def __init__(self):
        """初始化配置"""
        # 全局推送设置
        self.enable_notifications = True  # 是否启用通知
        self.push_on_update = True        # 数据更新时推送
        self.push_on_error = True         # 错误时推送
        self.daily_report_time = "13:50"  # 每日报告推送时间
        self.push_interval_minutes = 3    # 推送间隔（分钟）
        
        # 推送内容设置
        self.push_charts = True           # 是否推送图表信息
        self.push_summary = True          # 是否推送概况摘要
        self.push_detailed_data = True    # 是否推送详细数据
        
        # 企业微信配置
        self.wechat_work_config = {
            'enabled': False,
            'webhook_url': '',
            'mentioned_users': [],        # @的用户ID列表
            'mentioned_mobiles': [],      # @的手机号列表
            'retry_count': 3,             # 重试次数
            'retry_delay': 1,             # 重试延迟（秒）
            'timeout': 30                 # 请求超时（秒）
        }
        
        # 钉钉配置
        self.dingtalk_config = {
            'enabled': False,  # 默认禁用钉钉
            'webhook_url': '',  # 钉钉机器人webhook地址
            'secret': '',       # 签名密钥（可选）
            'at_all': False,    # 是否@所有人
            'at_mobiles': [],   # @的手机号列表
            'retry_count': 3,   # 重试次数
            'retry_delay': 1,   # 重试延迟（秒）
            'timeout': 30       # 请求超时（秒）
        }
        
        # 图表推送配置
        self.chart_files = [
            'altcoin_index.png',
            'volatility_index.png', 
            'volatility_combined_index.png',
            'liquidity_index.png',
            'market_breadth_index.png',
            'ma_breadth_index.png',
            'new_highs_index.png',
            'marketzdf_index.png',
            'ad_percentage.png',
            'up_down_ratio.png',
            'extreme_move_ratio.png',
            'btc_rainbow_table.png',
            'altcoin_season_index.png',
            'fear_greed_index.png'
        ]

    @classmethod
    def load_from_file(cls, path: str | Path) -> "NotificationConfig":
        """从JSON文件加载配置"""
        config = cls()
        path = Path(path)
        if not path.exists():
            return config

        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            return config

        platforms = data.get('platforms', data)
        if not isinstance(platforms, dict):
            return config

        wechat = platforms.get('wechat_work') or platforms.get('wechat') or platforms.get('wecom')
        if isinstance(wechat, dict):
            config._apply_platform_config(config.wechat_work_config, wechat)

        dingtalk = platforms.get('dingtalk')
        if isinstance(dingtalk, dict):
            config._apply_platform_config(config.dingtalk_config, dingtalk)

        return config

    @staticmethod
    def _apply_platform_config(target: Dict[str, Any], source: Dict[str, Any]) -> None:
        """将外部配置合并到平台配置"""
        target['enabled'] = bool(source.get('enabled', target.get('enabled', False)))
        if source.get('webhook_url'):
            target['webhook_url'] = source['webhook_url']
        if source.get('timeout') is not None:
            target['timeout'] = source['timeout']
        if source.get('retry_count') is not None:
            target['retry_count'] = source['retry_count']
        if source.get('retry_attempts') is not None:
            target['retry_count'] = source['retry_attempts']
        if source.get('retry_delay') is not None:
            target['retry_delay'] = source['retry_delay']
        if source.get('secret') is not None:
            target['secret'] = source.get('secret', target.get('secret', ''))
    
    def is_any_platform_enabled(self) -> bool:
        """
        检查是否有任何平台启用
        
        Returns:
            bool: 是否有平台启用
        """
        if not self.enable_notifications:
            return False
        
        return (self.wechat_work_config.get('enabled', False) or 
                self.dingtalk_config.get('enabled', False))
    
    def get_unified_config(self) -> dict:
        """
        获取统一推送管理器配置
        
        Returns:
            dict: 配置字典
        """
        config = {}
        
        if self.wechat_work_config.get('enabled', False):
            config['wechat_work'] = self.wechat_work_config.copy()
        
        if self.dingtalk_config.get('enabled', False):
            config['dingtalk'] = self.dingtalk_config.copy()
        
        return config
    
    def validate_config(self) -> dict:
        """
        验证配置有效性
        
        Returns:
            dict: 验证结果，包含各平台状态
        """
        result = {
            'wechat_work': False,
            'dingtalk': False,
            'any_enabled': False
        }
        
        # 验证企业微信配置
        if (self.wechat_work_config.get('enabled', False) and 
            self.wechat_work_config.get('webhook_url', '')):
            result['wechat_work'] = True
        
        # 验证钉钉配置
        if (self.dingtalk_config.get('enabled', False) and 
            self.dingtalk_config.get('webhook_url', '')):
            result['dingtalk'] = True
        
        result['any_enabled'] = result['wechat_work'] or result['dingtalk']
        
        return result
    
    def enable_wechat_work(self, webhook_url: str, **kwargs):
        """
        启用企业微信推送
        
        Args:
            webhook_url: webhook地址
            **kwargs: 其他配置参数
        """
        self.wechat_work_config['enabled'] = True
        self.wechat_work_config['webhook_url'] = webhook_url
        
        # 更新其他配置
        for key, value in kwargs.items():
            if key in self.wechat_work_config:
                self.wechat_work_config[key] = value
    
    def enable_dingtalk(self, webhook_url: str, secret: str = '', **kwargs):
        """
        启用钉钉推送
        
        Args:
            webhook_url: webhook地址
            secret: 签名密钥
            **kwargs: 其他配置参数
        """
        self.dingtalk_config['enabled'] = True
        self.dingtalk_config['webhook_url'] = webhook_url
        self.dingtalk_config['secret'] = secret
        
        # 更新其他配置
        for key, value in kwargs.items():
            if key in self.dingtalk_config:
                self.dingtalk_config[key] = value
    
    def disable_platform(self, platform: str):
        """
        禁用指定平台
        
        Args:
            platform: 平台名称 ('wechat_work' 或 'dingtalk')
        """
        if platform == 'wechat_work':
            self.wechat_work_config['enabled'] = False
        elif platform == 'dingtalk':
            self.dingtalk_config['enabled'] = False
    
    def get_push_interval_minutes(self) -> int:
        """获取推送间隔（分钟）"""
        return self.push_interval_minutes
    
    def set_push_interval_minutes(self, minutes: int):
        """设置推送间隔（分钟）"""
        self.push_interval_minutes = minutes
