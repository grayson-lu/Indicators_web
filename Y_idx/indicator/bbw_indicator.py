# -*- coding: utf-8 -*-
"""
BBW（布林带宽度）指标计算模块

提供从价格序列计算 BBW 的通用函数：
- compute_bbw_series(df, price_col='close', window=20, k=2.0)

输出仅包含 ['candle_begin_time', 'BBW']，方便后续通用变化率计算与对比复用。
"""

from __future__ import annotations
from typing import Optional
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from .base_indicator import BaseIndicator
# 交易所与工具依赖（统一数据抓取入口）
import yquant.common.binance_utils as binance
import ccxt
from yquant.db.models.bn_account import BnAccount
from yquant.config.config import cfg
import yquant.common.common_utils as common


def compute_bbw_series(df: pd.DataFrame, price_col: str = 'close', window: int = 20, k: float = 2.0) -> pd.DataFrame:
    """
    计算布林带宽度（BBW）时间序列
    定义：
        - MiddleBand = 价格的移动平均（window）
        - UpperBand  = MiddleBand + k * 标准差（window）
        - LowerBand  = MiddleBand - k * 标准差（window）
        - BBW = (UpperBand - LowerBand) / MiddleBand

    参数:
        df (pd.DataFrame): 输入数据，至少包含 'candle_begin_time' 和价格列
        price_col (str): 价格列名称（默认 'close'）
        window (int): 移动平均和标准差的窗口大小（默认 20）
        k (float): 标准差倍数（默认 2.0）

    返回:
        pd.DataFrame: 仅包含 ['candle_begin_time', 'BBW'] 的结果；无效时返回空表
    """
    if df is None or df.empty or price_col not in df.columns:
        return pd.DataFrame(columns=['candle_begin_time', 'BBW'])

    x = df.copy()

    # 统一时间列为时间类型并排序
    if 'candle_begin_time' in x.columns and not str(x['candle_begin_time'].dtype).startswith('datetime'):
        x['candle_begin_time'] = pd.to_datetime(x['candle_begin_time'], errors='coerce')
    x = x.dropna(subset=['candle_begin_time']).sort_values('candle_begin_time')

    # 确保价格为数值
    x[price_col] = pd.to_numeric(x[price_col], errors='coerce')

    # 计算中轨与标准差
    ma = x[price_col].rolling(window=window, min_periods=window).mean()
    std = x[price_col].rolling(window=window, min_periods=window).std()
    upper = ma + k * std
    lower = ma - k * std

    # 防止除以 0
    bbw = (upper - lower) / ma.replace(0, np.nan)

    out = pd.DataFrame({
        'candle_begin_time': x['candle_begin_time'],
        'BBW': bbw
    }).dropna(subset=['BBW'])

    return out


class BBWIndicator(BaseIndicator):
    """
    BBW（布林带宽度）指标管理器
    继承自BaseIndicator，提供标准化的BBW指标计算和图表绘制功能
    """

    def indicator_slug(self) -> str:
        """
        指标保存文件前缀
        """
        return 'bbw'

    def indicator_title(self) -> str:
        """
        指标图表标题
        """
        return '布林带宽度(BBW)指标'

    def stat(self, acc: str, backdays=365, windows=[20], save_img=True, interval='1d', start_time=None):
        """
        统计BBW指标（函数级注释）
        参数:
            acc: 账户标识（用于交易所连接）
            backdays: 回溯天数
            windows: 统计窗口列表
            save_img: 是否保存图像
            interval: 周期 '1d' 或 '1h'
            start_time: 起始时间过滤
        行为:
            - 抓取交易对K线数据
            - 调用 process_data 计算BBW
            - 使用基类保存CSV并绘图
        返回:
            计算后的结果DataFrame
        """
        self.log(f'统计BBW指标, windows = {windows}')
        exchange = self.get_default_exchange(acc)
        exchange_rules = binance.u_furture_get_exchangeinfo(exchange)
        symbol_list = [s['symbol'] for s in exchange_rules['symbols']
                       if s.get('status') == 'TRADING' and s.get('quoteAsset') == 'USDT' and s.get('contractType') == 'PERPETUAL']
        run_time = common.cacu_run_time('1h', datetime.now())
        max_day = max(max(windows), backdays)
        if interval == '1h':
            df_dict = binance.u_furture_fetch_all_swap_candle_data(
                exchange, symbol_list, '1h', run_time, 24 * max_day * 2 + 10, True, False, njobs=8)
        elif interval == '1d':
            df_dict = binance.u_furture_fetch_all_swap_candle_data(
                exchange, symbol_list, '1d', run_time, max_day * 2 + 10, True, False, njobs=8)
        else:
            self.warn(f"不支持的 interval: {interval}")
            return pd.DataFrame()
        df = self.process_data(df_dict, windows, backdays, interval, start_time)
        if df is not None and not df.empty:
            self.save_csv(df)
            if save_img:
                self.draw_index(df, start_time=start_time, interval=interval)
        return df

    def stat_with_data(self, df_dict, acc: str, start_time=None, backdays=365, windows=[20], save_img=True, interval='1d'):
        """
        使用已有数据统计BBW指标（函数级注释）
        参数同 stat
        """
        self.log(f'使用已有数据统计BBW指标, windows = {windows}')
        df = self.process_data(df_dict, windows, backdays, interval, start_time)
        if df is not None and not df.empty:
            self.save_csv(df)
            if save_img:
                self.draw_index(df, start_time=start_time, interval=interval)
        return df

    def get_default_exchange(self, acc: str):
        """
        获取默认交易所连接（函数级注释）
        参数:
            acc: 账户标识
        返回:
            ccxt.binance 交易所实例
        """
        api: BnAccount = cfg.binance.getApi(acc)
        exchange = ccxt.binance({
            'apiKey': api.api_key,
            'secret': api.api_secret,
            'timeout': cfg.binance.timeout,
            'rateLimit': cfg.binance.rateLimit,
            'verbose': cfg.binance.verbose,
            'hostname': cfg.binance.hostname,
            'enableRateLimit': cfg.binance.enableRateLimit,
            'proxies': cfg.binance.proxies
        })
        return exchange

    def process_data(self, df_dict, windows, backdays, interval, start_time):
        """
        处理数据计算BBW指标（函数级注释）
        参数:
            df_dict: {symbol: DataFrame} 的字典
            windows: 布林带窗口大小列表
            backdays: 回溯天数（未直接使用，统一签名）
            interval: 时间粒度（未直接使用，统一签名）
            start_time: 开始时间过滤（未直接使用，统一签名）
        行为:
            - 选择主要交易对（优先 BTCUSDT）
            - 计算各窗口的BBW并合并
        返回:
            DataFrame: 包含BBW指标的计算结果
        """
        self.log(f'处理数据计算BBW指标, windows = {windows}')
        
        # 获取主要交易对（如BTCUSDT）的数据
        main_symbol = 'BTCUSDT'
        if main_symbol not in df_dict:
            # 如果BTCUSDT不存在，使用字典中的第一个交易对
            main_symbol = list(df_dict.keys())[0]
        
        df = df_dict[main_symbol].copy()

        # 归一化时间列，稳健处理缺失的'timestamp'（函数级注释）
        # - 优先使用'timestamp'，其次使用常见列名；若皆缺失则尝试从索引构造
        possible_ts_cols = ['timestamp', 'candle_begin_time', 'open_time', 'time', 'Date', 'date']
        ts_col = next((c for c in possible_ts_cols if c in df.columns), None)
        if ts_col is None:
            # 如果索引是日期时间或可解析为日期时间，则用索引生成
            if str(df.index.dtype).startswith('datetime'):
                df['timestamp'] = df.index
            else:
                try:
                    df['timestamp'] = pd.to_datetime(df.index, errors='coerce')
                except Exception:
                    self.warn("BBWIndicator: 无法识别时间列且索引不可解析为时间，返回空结果")
                    return pd.DataFrame()
        else:
            # 统一命名为'timestamp'
            if ts_col != 'timestamp':
                df['timestamp'] = df[ts_col]
        # 强制转换为datetime并去除无效
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp']).sort_values('timestamp')
        df = df.drop_duplicates(subset=['timestamp'], keep='last').reset_index(drop=True)

        # 归一化价格列，稳健处理缺失的'close'（函数级注释）
        possible_price_cols = ['close', 'Close', 'closing_price', 'price', 'last', 'c']
        price_col = next((c for c in possible_price_cols if c in df.columns), None)
        if price_col is None:
            self.warn("BBWIndicator: 未找到价格列(close/price等)，返回空结果")
            return pd.DataFrame()
        # 统一转换为数值
        df[price_col] = pd.to_numeric(df[price_col], errors='coerce')
        df = df.dropna(subset=[price_col])
        # 函数compute_bbw_series要求'candle_begin_time'，此处映射
        df['candle_begin_time'] = df['timestamp']
        
        # 计算不同窗口的BBW指标
        result_dfs = []
        for window in windows:
            bbw_df = compute_bbw_series(df, price_col=price_col, window=window, k=2.0)
            bbw_df = bbw_df.rename(columns={'BBW': f'BBW_{window}'})
            result_dfs.append(bbw_df)
        
        # 合并所有结果
        if result_dfs:
            final_df = result_dfs[0]
            for i in range(1, len(result_dfs)):
                final_df = final_df.merge(result_dfs[i], on='candle_begin_time', how='outer')
            
            # 转换回timestamp格式
            final_df['timestamp'] = final_df['candle_begin_time']
            final_df = final_df.drop('candle_begin_time', axis=1)
            final_df = final_df.sort_values('timestamp')
            
            return final_df
        else:
            return pd.DataFrame()

    def draw_index(self, df, start_time=None, interval='1d'):
        """
        绘制BBW指标图表（函数级注释）
        参数:
            df: 包含BBW指标数据的DataFrame
            start_time: 开始时间
            interval: 时间间隔
        行为:
            - 绘制各窗口BBW曲线，保存到 self.png_path()
        """
        if df.empty:
            self.warn('BBW数据为空，无法绘制图表')
            return
        
        bbw_columns = [col for col in df.columns if col.startswith('BBW_')]
        if not bbw_columns:
            self.warn('未找到BBW指标列')
            return
        
        fig, ax = plt.subplots(figsize=(15, 8))
        colors = ['blue', 'red', 'green', 'orange', 'purple']
        for i, col in enumerate(bbw_columns):
            color = colors[i % len(colors)]
            window = col.replace('BBW_', '')
            ax.plot(df['timestamp'], df[col], label=f'BBW({window})', color=color, linewidth=2)
        
        ax.set_xlabel('时间')
        ax.set_ylabel('BBW值')
        ax.set_title(self.indicator_title())
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        plt.savefig(self.png_path(), dpi=300, bbox_inches='tight')
        plt.close()
        self.log(f'BBW图表已保存至: {self.png_path()}')