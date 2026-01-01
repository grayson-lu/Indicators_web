'''
配置文件
'''

class BinanceConfig:
    """
    Binance配置类
    """
    def __init__(self):
        # API请求基础配置
        self.timeout = 60000  # 增加超时时间到60秒
        self.rateLimit = 1200  # 稍微增加请求间隔
        self.verbose = False  # 是否显示详细日志
        self.hostname = 'fapi.binance.com'  # API主机名，修改为futures API
        self.enableRateLimit = True  # 是否启用频率限制
        
        # 代理配置 - 支持多种配置方式
        self.proxies = {
            "http": "http://127.0.0.1:7897",
            "https": "http://127.0.0.1:7897"
        }
        
        # 备用代理配置
        self.backup_proxies = {
            "http": None,
            "https": None
        }
        
        # 网络重试配置
        self.max_retries = 5
        self.retry_delay = 3
        self.backoff_factor = 2
        
    def get_exchange_config(self):
        """
        获取交易所配置字典
        
        Returns:
            dict: ccxt交易所配置
        """
        return {
            'enableRateLimit': self.enableRateLimit,
            'timeout': self.timeout,
            'rateLimit': self.rateLimit,
            'verbose': self.verbose,
            'hostname': self.hostname,
            'proxies': self.proxies,
            'options': {
                'defaultType': 'future',  # 默认使用期货API
                'adjustForTimeDifference': True,  # 自动调整时间差
            }
        }
        
    def get_backup_config(self):
        """
        获取备用配置（无代理）
        
        Returns:
            dict: 备用交易所配置
        """
        config = self.get_exchange_config()
        config['proxies'] = self.backup_proxies
        config['timeout'] = self.timeout * 2  # 无代理时增加超时时间
        return config
        
    def getApi(self, acc):
        """获取API配置
        
        Args:
            acc (str): 账户名
            
        Returns:
            BnAccount: 账户实例
        """
        from ..db.models.bn_account import BnAccount
        return BnAccount(acc=acc)  # 使用acc参数创建账户实例

class Config:
    """
    全局配置类
    """
    def __init__(self):
        self.binance = BinanceConfig()

# 全局配置实例
cfg = Config()
