'''
爆拉暴跌币种占比指标
Extreme Move Ratio
统计在给定时间窗口内发生极端上涨/下跌的币种占比
统一继承 BaseIndicator，统一方法签名与保存路径
'''
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

from .base_indicator import BaseIndicator

pd.set_option('display.unicode.ambiguous_as_wide', True)
pd.set_option('display.unicode.east_asian_width', True)
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 180)


class 爆拉暴跌币种占比(BaseIndicator):
    def indicator_slug(self) -> str:
        """
        返回统一保存文件前缀（CSV/PNG 文件名）
        """
        return 'extreme_move_ratio'

    def indicator_title(self) -> str:
        """
        返回统一的图表标题
        """
        return '爆拉暴跌币种占比'

    def stat(self, acc: str, backdays=365, windows=[1, 7, 30], interval='1d', start_time=None):
        """
        统计极端波动比例指标（统一入口）
        参数:
        - acc/backdays/windows/interval/start_time 按统一约定
        返回: 指标结果 DataFrame
        """
        self.log(f'统计极端波动比例, windows = {windows}')
        df = self._mock_price_data(backdays)
        return self.process_data(df, windows, backdays, interval, start_time)

    def stat_with_data(self, df, acc: str, start_time=None, backdays=365, windows=[1, 7, 30], interval='1d'):
        """
        使用已有价格数据统计（统一入口）
        - 未传入 df 时将自动生成模拟数据
        参数与行为与 stat 保持一致
        """
        self.log(f'使用已有数据统计极端波动比例, windows = {windows}')
        if df is None:
            df = self._mock_price_data(backdays)
        return self.process_data(df, windows, backdays, interval, start_time)

    def _mock_price_data(self, backdays):
        """
        生成模拟的日线价格数据供计算使用
        返回: DataFrame，包含多个币种的收盘价
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(days=backdays + 30)
        time_range = pd.date_range(start=start_time, end=end_time, freq='1D')
        symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'XRPUSDT',
                   'SOLUSDT', 'DOTUSDT', 'DOGEUSDT', 'AVAXUSDT', 'MATICUSDT',
                   'LINKUSDT', 'LTCUSDT', 'UNIUSDT', 'ATOMUSDT', 'FILUSDT',
                   'TRXUSDT', 'ETCUSDT', 'XLMUSDT', 'VETUSDT', 'ICPUSDT']
        rows = []
        for t in time_range:
            for sym in symbols:
                base = 100 + np.random.normal(0, 5)
                trend = np.sin(len(rows) * 0.01) * 2
                vol = np.random.normal(0, 1)
                price = max(1, base + trend + vol)
                rows.append({'candle_begin_time': t, 'symbol': sym, 'close': price})
        df = pd.DataFrame(rows)
        df = df.sort_values(['candle_begin_time', 'symbol'])
        return df

    def process_data(self, df_dict, windows, backdays, interval, start_time):
        """
        处理数据计算极端波动比例指标（统一签名）
        参数:
        - df_dict: 价格 DataFrame 或 dict（键为币种，值为DataFrame）
        - windows: 时间窗口列表（单位天）
        - backdays: 回看天数
        - interval: 时间间隔（此处为'1d'）
        - start_time: 起始时间过滤
        返回: 汇总后的极端波动比例数据，并保存到CSV
        """
        price_df = None
        if isinstance(df_dict, pd.DataFrame):
            price_df = df_dict
        elif isinstance(df_dict, dict) and df_dict:
            try:
                parts = []
                for sym, _df in df_dict.items():
                    if _df is None or _df.empty:
                        continue
                    tmp = _df.copy()
                    if 'symbol' not in tmp.columns:
                        tmp['symbol'] = sym
                    parts.append(tmp)
                if parts:
                    price_df = pd.concat(parts, ignore_index=True)
            except Exception as e:
                self.warn(f'价格字典合并失败: {e}')
                price_df = None
        if price_df is None or not isinstance(price_df, pd.DataFrame) or price_df.empty:
            self.warn('价格数据为空或类型不正确，返回空DataFrame')
            return pd.DataFrame()
        df = price_df.copy()
        df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'])
        df = df.sort_values(['candle_begin_time', 'symbol'])
        df['pct'] = df.groupby('symbol')['close'].pct_change()
        # 计算极端波动：涨幅超过5% 或 跌幅超过5%
        df['极端上涨'] = (df['pct'] >= 0.05).astype(int)
        df['极端下跌'] = (df['pct'] <= -0.05).astype(int)
        dfs = []
        for t, g in df.groupby('candle_begin_time'):
            total = len(g)
            up = g['极端上涨'].sum()
            down = g['极端下跌'].sum()
            row = {
                'candle_begin_time': t,
                '币种数量': total,
                '爆拉币种数': int(up),
                '暴跌币种数': int(down),
                '爆拉占比': (up / total) * 100 if total > 0 else np.nan,
                '暴跌占比': (down / total) * 100 if total > 0 else np.nan,
                '极端波动占比': ((up + down) / total) * 100 if total > 0 else np.nan
            }
            dfs.append(pd.DataFrame([row]))
        result_df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
        result_df = result_df.sort_values('candle_begin_time')
        for window in windows:
            result_df[f'爆拉占比_{window}d'] = result_df['爆拉占比'].rolling(window).mean()
            result_df[f'暴跌占比_{window}d'] = result_df['暴跌占比'].rolling(window).mean()
            result_df[f'极端波动占比_{window}d'] = result_df['极端波动占比'].rolling(window).mean()
        if start_time is not None:
            result_df = result_df[result_df['candle_begin_time'] > pd.to_datetime(start_time)]
        self.save_csv(result_df)
        if not result_df.empty:
            self.log(result_df.tail().to_string())
        return result_df

    def draw_index(self, title, windows, df):
        """
        绘制并保存极端波动比例图（统一签名/统一保存路径）
        - 输出路径统一使用 self.png_path()
        """
        fig = plt.figure(tight_layout=False, figsize=(28, 14), dpi=80, facecolor='w', edgecolor='k')
        gs = gridspec.GridSpec(24, 12)
        ax1 = fig.add_subplot(gs[0:10, 0:11])
        ax1.plot(df['candle_begin_time'], df['爆拉占比'], label='爆拉占比(%)', color='red', linewidth=2)
        ax1.plot(df['candle_begin_time'], df['暴跌占比'], label='暴跌占比(%)', color='green', linewidth=2)
        for window in windows:
            u = f'爆拉占比_{window}d'
            d = f'暴跌占比_{window}d'
            if u in df.columns:
                ax1.plot(df['candle_begin_time'], df[u], label=f'爆拉MA{window}d', alpha=0.6)
            if d in df.columns:
                ax1.plot(df['candle_begin_time'], df[d], label=f'暴跌MA{window}d', alpha=0.6)
        ax1.set_ylabel('占比 (%)')
        ax1.grid(True, linestyle='--', alpha=0.3)
        ax1.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        ax1.set_title('爆拉/暴跌占比', fontsize='medium', fontweight='bold')
        ax2 = fig.add_subplot(gs[12:22, 0:11])
        ax2.plot(df['candle_begin_time'], df['极端波动占比'], label='极端波动占比(%)', color='blue', linewidth=2)
        for window in windows:
            col = f'极端波动占比_{window}d'
            if col in df.columns:
                ax2.plot(df['candle_begin_time'], df[col], label=f'MA{window}d', alpha=0.6)
        ax2.set_ylabel('占比 (%)')
        ax2.grid(True, linestyle='--', alpha=0.3)
        ax2.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        ax2.set_title('极端波动占比', fontsize='medium', fontweight='bold')
        plt.xticks(rotation=30)
        plt.tight_layout()
        png_file = self.png_path()
        plt.savefig(png_file, bbox_inches='tight')
        self.log(f'图表已保存: {png_file}')
        plt.close('all')
