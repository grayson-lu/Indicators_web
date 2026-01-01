"""
企业微信推送配置
"""

class WechatWorkConfig:
    """企业微信配置类"""
    
    def __init__(self):
        # 企业微信机器人配置
        self.webhook_url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=965cc519-2565-4d1b-a9c0-7d4dcecfadbb"  # 您的企业微信机器人webhook地址
        
        # 推送设置
        self.enable_push = True  # 是否启用推送
        self.push_on_update = True  # 数据更新时推送
        self.push_on_error = True  # 错误时推送
        self.daily_report_time = "13:50"  # 每日报告推送时间
        self.push_interval_minutes = 3  # 推送间隔（分钟）
        
        # @用户设置
        self.mentioned_users = []  # @的用户ID列表
        self.mentioned_mobiles = []  # @的手机号列表
        
        # 推送内容设置
        self.push_charts = True  # 是否推送图表信息
        self.push_summary = True  # 是否推送概况摘要
        self.push_detailed_data = True  # 是否推送详细数据
        
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
    
    def is_valid(self) -> bool:
        """检查配置是否有效"""
        return bool(self.webhook_url and self.enable_push)
    
    def get_webhook_url(self) -> str:
        """获取webhook地址"""
        return self.webhook_url
    
    def set_webhook_url(self, url: str):
        """设置webhook地址"""
        self.webhook_url = url
    
    def get_push_interval_minutes(self) -> int:
        """获取推送间隔（分钟）"""
        return self.push_interval_minutes
    
    def set_push_interval_minutes(self, minutes: int):
        """设置推送间隔（分钟）"""
        self.push_interval_minutes = minutes