"""
生成稳定币供应量数据的辅助脚本（函数级注释）
用途：
- 调用 indicator.stablecoin_supply_monitor.链上稳定币总供应量 的 stat 生成并保存 data/stablecoin_supply.csv
- 在控制台输出生成结果与目标 CSV 文件信息
"""
import os
import sys
from datetime import datetime, timedelta

# 将项目根目录加入搜索路径
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from indicator.stablecoin_supply_monitor import 链上稳定币总供应量


def main():
    """
    主入口（函数级注释）
    行为：
    - 直接使用指标类生成模拟的稳定币供应量时间序列
    - 保存 CSV 并输出文件信息
    """
    print("Starting stablecoin supply refresh...")
    indicator = 链上稳定币总供应量()
    indicator.stat(acc='qqdev', backdays=365, windows=[1, 7, 30], interval='1d', start_time=datetime.now() - timedelta(days=365))

    out_path = os.path.join(ROOT, 'data', 'stablecoin_supply.csv')
    if os.path.exists(out_path):
        size = os.path.getsize(out_path)
        mtime = datetime.fromtimestamp(os.path.getmtime(out_path))
        print(f"CSV: {out_path} | size={size} bytes | mtime={mtime}")
    else:
        print(f"CSV missing: {out_path}")


if __name__ == "__main__":
    main()