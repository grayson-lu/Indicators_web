'''
Binance账户模型
'''

class BnAccount:
    """
    Binance账户类
    """
    # 在这里添加账户配置
    # 格式: '账户名': ('api_key', 'api_secret')
    _ACCOUNTS = {
        'qqdev': ('YOUR_API_KEY', 'YOUR_API_SECRET'),
    }
    
    def __init__(self, api_key=None, api_secret=None, acc=None):
        """
        初始化账户实例
        
        Args:
            api_key (str, optional): API Key
            api_secret (str, optional): API Secret
            acc (str, optional): 账户名，用于获取预设配置
        """
        if acc is not None:
            api_key, api_secret = self._ACCOUNTS[acc]
        self._api_key = api_key
        self._api_secret = api_secret
    
    @property
    def api_key(self):
        """获取API Key"""
        return self._api_key
    
    @property
    def api_secret(self):
        """获取API Secret"""
        return self._api_secret
