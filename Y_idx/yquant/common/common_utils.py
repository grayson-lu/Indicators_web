'''
通用工具函数
'''
from datetime import datetime, timedelta

def cacu_run_time(interval, now=None):

    if now is None:
        now = datetime.now()
    
    if interval == '1h':
        # 将分钟和秒都设置为0，获取整点时间
        run_time = now.replace(minute=0, second=0, microsecond=0)
    elif interval == '1d':
        # 将小时、分钟和秒都设置为0，获取当日0点时间
        run_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        raise ValueError(f"Unsupported interval: {interval}")
    
    return run_time
