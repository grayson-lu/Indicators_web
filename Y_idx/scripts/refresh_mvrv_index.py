"""
生成 MVRV 指标数据的辅助脚本（函数级注释）
用途：
- 构建交易所连接并抓取必要行情数据
- 调用 onchain_indicators.MVRV指标 的 process_data 生成并保存 data/mvrv_index.csv
- 在控制台输出生成结果与目标 CSV 文件信息
"""
import os
import sys
from datetime import datetime, timedelta

# 将项目根目录加入搜索路径
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

import ccxt
import yquant.common.binance_utils as binance
import yquant.common.common_utils as common
from yquant.config.config import cfg
from indicator.onchain_indicators import MVRV指标


def build_exchange():
    """
    构建交易所实例（函数级注释）
    行为：
    - 优先使用主配置，其次备用配置，最后默认限速配置
    返回：binance 期货交易所实例
    """
    try:
        return ccxt.binance(cfg.binance.get_exchange_config())
    except Exception:
        try:
            return ccxt.binance(cfg.binance.get_backup_config())
        except Exception:
            return ccxt.binance({
                'enableRateLimit': True,
                'timeout': 60000,
                'options': {'defaultType': 'future'}
            })


def main():
    """
    主入口（函数级注释）
    行为：
    - 抓取全市场 USDT 永续日线数据构造 df_dict
    - 调用 MVRV指标.process_data 生成并保存 CSV
    - 输出 CSV 文件大小与修改时间
    """
    print("Starting MVRV refresh...")
    exchange = build_exchange()
    symbol_list = binance.get_usdt_swap_symbols_robust(exchange)
    run_time = common.cacu_run_time('1d', datetime.now())
    backdays = 365
    max_day = max(365, backdays)
    df_dict = binance.u_furture_fetch_all_swap_candle_data(
        exchange, symbol_list, '1d', run_time, max_day * 2 + 10, True, False, njobs=30
    )

    mvrv = MVRV指标()
    mvrv.process_data(
        df_dict=df_dict,
        windows=[30, 90, 365],
        backdays=backdays,
        interval='1d',
        start_time=datetime.now() - timedelta(days=backdays)
    )

    out_path = os.path.join(ROOT, 'data', 'mvrv_index.csv')
    if os.path.exists(out_path):
        size = os.path.getsize(out_path)
        mtime = datetime.fromtimestamp(os.path.getmtime(out_path))
        print(f"CSV: {out_path} | size={size} bytes | mtime={mtime}")
    else:
        print(f"CSV missing: {out_path}")


if __name__ == "__main__":
    main()