'''
链上稳定币总供应量监控指标
Stablecoin Supply Monitor
监控链上稳定币供应量变化，分析市场流动性与资金流向
'''
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

from .base_indicator import BaseIndicator

pd.set_option('display.unicode.ambiguous_as_wide', True)
pd.set_option('display.unicode.east_asian_width', True)
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 180)


class 链上稳定币总供应量(BaseIndicator):
    def indicator_slug(self) -> str:
        """
        返回统一保存前缀（CSV/PNG 文件名使用）
        """
        return 'stablecoin_supply'

    def indicator_title(self) -> str:
        """
        返回统一的图表标题
        """
        return '链上稳定币总供应量'

    def stat(self, acc: str, backdays=365, windows=[1, 7, 30], interval='1d', start_time=None):
        """
        统计链上稳定币总供应量指标
        参数:
        - acc: 账户标识（保持统一签名，不用于计算）
        - backdays: 回溯天数
        - windows: 指标窗口列表（如[1,7,30]）
        - interval: 周期字符串（'1d'/'1h'），本指标按日计算
        - start_time: 起始时间过滤
        返回: 指标结果 DataFrame
        """
        self.log(f'统计稳定币供应量，windows={windows}, backdays={backdays}')
        df_dict = {}  # 本指标无需交易所行情，保留统一签名
        return self.process_data(df_dict, windows, backdays, interval, start_time)

    def stat_with_data(self, df_dict, acc: str, start_time=None, backdays=365, windows=[1, 7, 30], interval='1d'):
        """
        使用外部数据字典进行统计（保持统一签名）
        参数同 stat；当 df_dict 中包含 BTCUSDT 时用于关联分析，否则仅计算供应量部分
        返回: 指标结果 DataFrame
        """
        self.log(f'使用已有数据统计稳定币供应量，windows={windows}, backdays={backdays}')
        if df_dict is None:
            df_dict = {}
        return self.process_data(df_dict, windows, backdays, interval, start_time)

    def fetch_stablecoin_supply_data(self, backdays):
        """
        获取稳定币供应量数据（模拟）
        - 生成 USDT/USDC/BUSD/DAI/TUSD 的日度供应量时间序列
        - 同时计算总供应量
        返回: DataFrame[date, <coin>_supply, total_supply]
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=backdays + 30)
        date_range = pd.date_range(start=start_date, end=end_date, freq='D')
        stablecoins = {
            'USDT': {'initial_supply': 80_000_000_000, 'growth_rate': 0.0001},
            'USDC': {'initial_supply': 50_000_000_000, 'growth_rate': 0.0002},
            'BUSD': {'initial_supply': 20_000_000_000, 'growth_rate': 0.0001},
            'DAI':  {'initial_supply': 8_000_000_000,  'growth_rate': 0.0001},
            'TUSD': {'initial_supply': 2_000_000_000,  'growth_rate': 0.0001},
        }
        rows = []
        for i, date in enumerate(date_range):
            row = {'date': date}
            total_supply = 0
            for coin, params in stablecoins.items():
                base_supply = params['initial_supply']
                growth = params['growth_rate'] * i
                random_factor = 1 + np.random.normal(0, 0.01)
                current_supply = base_supply * (1 + growth) * random_factor
                row[f'{coin}_supply'] = current_supply
                total_supply += current_supply
            row['total_supply'] = total_supply
            rows.append(row)
        return pd.DataFrame(rows)

    def process_data(self, df_dict, windows, backdays, interval, start_time):
        """
        处理数据并计算稳定币供应量相关指标
        参数:
        - df_dict: 市场数据字典（可选，若包含 BTCUSDT 用于相关性分析）
        - windows: 指标窗口列表
        - backdays: 回溯天数
        - interval: 周期字符串（'1d'/'1h'）
        - start_time: 起始时间过滤
        返回: 指标结果 DataFrame，并通过 self.save_csv 保存
        """
        # 供应量与窗口衍生指标
        src = self.fetch_stablecoin_supply_data(backdays)
        df = src.copy()
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        for window in windows:
            df[f'total_supply_change_{window}d'] = df['total_supply'].pct_change(window) * 100
            df[f'total_supply_ma_{window}d'] = df['total_supply'].rolling(window).mean()
            for coin in ['USDT', 'USDC', 'BUSD', 'DAI', 'TUSD']:
                col = f'{coin}_supply'
                if col in df.columns:
                    df[f'{coin}_change_{window}d'] = df[col].pct_change(window) * 100
                    df[f'{coin}_ma_{window}d'] = df[col].rolling(window).mean()
            df[f'supply_growth_rate_{window}d'] = df['total_supply'].rolling(window).apply(
                lambda x: (x.iloc[-1] / x.iloc[0] - 1) * 100 if len(x) == window and x.iloc[0] > 0 else np.nan
            )
            df[f'supply_volatility_{window}d'] = df[f'total_supply_change_{window}d'].rolling(window).std()
            df[f'supply_trend_strength_{window}d'] = df[f'total_supply_change_{window}d'].rolling(window).mean()

        # 若有 BTC 行情，计算关联性
        if isinstance(df_dict, dict) and 'BTCUSDT' in df_dict:
            btc_df = df_dict['BTCUSDT'].copy()
            btc_df['date'] = pd.to_datetime(btc_df['candle_begin_time'])
            df = df.merge(btc_df[['date', 'close']], on='date', how='left')
            df.rename(columns={'close': 'btc_price'}, inplace=True)
            for window in windows:
                if len(df) >= window:
                    df[f'supply_btc_corr_{window}d'] = df['total_supply'].rolling(window).corr(df['btc_price'])

        # 汇总结果行
        out_rows = []
        for _, row in df.iterrows():
            r = {
                'candle_begin_time': row['date'],
                'total_supply': row['total_supply'],
                'total_supply_billion': row['total_supply'] / 1e9,
            }
            for coin in ['USDT', 'USDC', 'BUSD', 'DAI', 'TUSD']:
                sc = row.get(f'{coin}_supply', np.nan)
                if not pd.isna(sc):
                    r[f'{coin}_supply_billion'] = sc / 1e9
                    r[f'{coin}_market_share'] = (sc / row['total_supply']) * 100 if row['total_supply'] > 0 else np.nan
            for window in windows:
                r[f'总供应量变化_{window}d'] = row.get(f'total_supply_change_{window}d', np.nan)
                r[f'供应量增长率_{window}d'] = row.get(f'supply_growth_rate_{window}d', np.nan)
                r[f'供应量波动率_{window}d'] = row.get(f'supply_volatility_{window}d', np.nan)
                r[f'供应量趋势强度_{window}d'] = row.get(f'supply_trend_strength_{window}d', np.nan)
                if f'supply_btc_corr_{window}d' in df.columns:
                    r[f'供应量BTC关联性_{window}d'] = row.get(f'supply_btc_corr_{window}d', np.nan)
                r[f'供应量状态_{window}d'] = self.get_supply_status(r[f'供应量增长率_{window}d'])
                r[f'流动性状态_{window}d'] = self.get_liquidity_status(r[f'供应量波动率_{window}d'])
                for coin in ['USDT', 'USDC', 'BUSD', 'DAI', 'TUSD']:
                    ch_col = f'{coin}_change_{window}d'
                    if ch_col in df.columns:
                        r[f'{coin}变化_{window}d'] = row.get(ch_col, np.nan)
            if 'btc_price' in df.columns:
                r['BTC价格'] = row.get('btc_price', np.nan)
            out_rows.append(r)
        final_df = pd.DataFrame(out_rows)
        if start_time is not None and not final_df.empty:
            final_df = final_df[final_df['candle_begin_time'] > pd.to_datetime(start_time)]

        # 统一保存与日志
        self.save_csv(final_df)
        if not final_df.empty:
            self.log(final_df.tail().to_string())
        return final_df

    def get_supply_status(self, growth_rate):
        """
        根据供应量增长率返回状态字符串
        """
        if pd.isna(growth_rate):
            return '无数据'
        if growth_rate > 5:
            return '快速扩张'
        if growth_rate > 2:
            return '稳定增长'
        if growth_rate > -2:
            return '基本稳定'
        if growth_rate > -5:
            return '轻微收缩'
        return '快速收缩'

    def get_liquidity_status(self, volatility):
        """
        根据供应量波动率返回流动性状态
        """
        if pd.isna(volatility):
            return '无数据'
        if volatility < 1:
            return '极稳定'
        if volatility < 2:
            return '稳定'
        if volatility < 5:
            return '一般'
        if volatility < 10:
            return '波动较大'
        return '高度波动'

    def get_competition_status(self, hhi):
        """
        根据 HHI 指数返回市场竞争状态
        """
        if pd.isna(hhi):
            return '未知'
        if hhi < 1500:
            return '竞争充分'
        if hhi < 2500:
            return '竞争一般'
        return '高度集中'

    def draw_index(self, title, windows, df):
        """
        绘制稳定币供应量与变化的组合图（统一签名/统一保存路径）
        参数:
        - title: 图表标题
        - windows: 指标窗口列表
        - df: 指标结果数据（process_data 输出）
        行为:
        - 采用两子图：总供应量(十亿) 与 不同窗口的供应量变化(%)
        - 统一使用 self.png_path() 保存图表
        """
        if df is None or df.empty:
            self.warn('draw_index - 数据为空，跳过绘图')
            return
        fig, axes = plt.subplots(2, 1, figsize=(16, 9), sharex=True)
        # 子图1：总供应量
        axes[0].plot(df['candle_begin_time'], df['total_supply_billion'], label='总供应量(十亿)', color='tab:blue')
        axes[0].set_title(title)
        axes[0].set_ylabel('十亿')
        axes[0].grid(True, alpha=0.3)
        axes[0].legend(loc='best')
        # 子图2：各窗口变化
        for window in windows:
            col = f'总供应量变化_{window}d'
            if col in df.columns:
                axes[1].plot(df['candle_begin_time'], df[col], label=col)
        axes[1].axhline(y=0, color='k', linestyle='--', alpha=0.3)
        axes[1].set_ylabel('%')
        axes[1].grid(True, alpha=0.3)
        axes[1].legend(loc='best')
        plt.xticks(rotation=30)
        plt.tight_layout()
        plt.savefig(self.png_path(), bbox_inches='tight')
        plt.close()
