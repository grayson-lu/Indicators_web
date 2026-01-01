"""
生成交易所净流入数据的辅助脚本（函数级注释）
用途：
- 调用 kanban_fixed.ensure_exchange_flow_recent 触发自愈刷新
- 在控制台打印刷新结果并输出数据文件大小
"""
import os
import sys
from datetime import datetime

# 将项目根目录加入搜索路径
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from kanban_fixed import ensure_exchange_flow_recent


def main():
    """
    主入口（函数级注释）
    行为：
    - 触发交易所净流入数据刷新
    - 输出刷新是否发生以及目标CSV的大小
    """
    print("Starting exchange flow refresh...")
    refreshed = ensure_exchange_flow_recent(max_age_days=1, min_interval_minutes=1)
    print("Refreshed:", refreshed)
    out_path = os.path.join(ROOT, "data", "exchange_flow.csv")
    if os.path.exists(out_path):
        size = os.path.getsize(out_path)
        mtime = datetime.fromtimestamp(os.path.getmtime(out_path))
        print(f"CSV: {out_path} | size={size} bytes | mtime={mtime}")
    else:
        print(f"CSV missing: {out_path}")


if __name__ == "__main__":
    main()