"""
链上指标模块（重构版）
包含 MVRV 指标、稳定币供应量指标、交易所净流入流出指标
统一接入 BaseIndicator，统一日志、保存路径与方法签名
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False
warnings.filterwarnings('ignore')

from .base_indicator import BaseIndicator

pd.set_option('display.unicode.ambiguous_as_wide', True)
pd.set_option('display.unicode.east_asian_width', True)
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 180)


class MVRV指标(BaseIndicator):
    """MVRV (Market Value to Realized Value) 指标类，继承 BaseIndicator"""

    def indicator_slug(self) -> str:
        """指标保存文件前缀（函数级注释）"""
        return 'mvrv_index'

    def indicator_title(self) -> str:
        """指标图表标题（函数级注释）"""
        return 'MVRV指标'

    def calculate_mvrv_ratio(self, df_dict, windows=[30, 90, 365]):
        """
        计算 MVRV 比率（函数级注释，基于模拟实现价值）
        参数:
            df_dict: 包含价格数据的字典，需至少包含 BTCUSDT 的 K 线
            windows: 计算窗口期列表
        返回:
            DataFrame: 包含 MVRV 比率及 Z-Score 的时间序列
        """
        try:
            btc_data = None
            for symbol, df in df_dict.items():
                if 'BTC' in symbol and 'USDT' in symbol:
                    btc_data = df.copy()
                    break
            if btc_data is None or btc_data.empty:
                self.warn('未找到 BTCUSDT 价格数据')
                return pd.DataFrame()
            btc_data = btc_data.sort_values('candle_begin_time')
            btc_data['candle_begin_time'] = pd.to_datetime(btc_data['candle_begin_time'])
            result_df = btc_data[['candle_begin_time', 'close']].copy()
            result_df.rename(columns={'close': 'btc_price'}, inplace=True)
            for window in windows:
                realized_value = result_df['btc_price'].rolling(window=window, min_periods=1).mean()
                market_value = result_df['btc_price']
                mvrv_ratio = market_value / realized_value
                result_df[f'mvrv_{window}d'] = mvrv_ratio
                mvrv_mean = mvrv_ratio.rolling(window=window*2, min_periods=window).mean()
                mvrv_std = mvrv_ratio.rolling(window=window*2, min_periods=window).std()
                result_df[f'mvrv_zscore_{window}d'] = (mvrv_ratio - mvrv_mean) / mvrv_std.replace(0, np.nan)
            result_df['mvrv_composite_signal'] = self._generate_mvrv_signals(result_df, windows)
            return result_df
        except Exception as e:
            self.warn(f'计算 MVRV 比率时出错: {e}')
            return pd.DataFrame()

    def _generate_mvrv_signals(self, df, windows):
        """
        生成 MVRV 信号（函数级注释）
        参数:
            df: 包含 MVRV 数据的 DataFrame
            windows: 窗口期列表
        返回:
            Series: MVRV 信号序列
        """
        signals = []
        for _, row in df.iterrows():
            signal_scores = []
            for window in windows:
                mvrv_col = f'mvrv_{window}d'
                zscore_col = f'mvrv_zscore_{window}d'
                if pd.isna(row.get(mvrv_col)) or pd.isna(row.get(zscore_col)):
                    continue
                mvrv_value = row[mvrv_col]
                zscore_value = row[zscore_col]
                if mvrv_value < 0.8:
                    signal_scores.append(-2)
                elif mvrv_value < 1.0:
                    signal_scores.append(-1)
                elif mvrv_value < 1.5:
                    signal_scores.append(0)
                elif mvrv_value < 2.0:
                    signal_scores.append(1)
                else:
                    signal_scores.append(2)
                if zscore_value < -1.5:
                    signal_scores[-1] -= 1
                elif zscore_value > 1.5:
                    signal_scores[-1] += 1
            if signal_scores:
                avg_score = np.mean(signal_scores)
                if avg_score <= -1.5:
                    signals.append('极度低估')
                elif avg_score <= -0.5:
                    signals.append('低估')
                elif avg_score <= 0.5:
                    signals.append('合理')
                elif avg_score <= 1.5:
                    signals.append('高估')
                else:
                    signals.append('极度高估')
            else:
                signals.append('未知')
        return pd.Series(signals, index=df.index)

    def process_data(self, df_dict, windows, backdays, interval, start_time):
        """
        统一的 process_data 方法（函数级注释）
        返回：保存 CSV 并返回结果
        """
        df = self.calculate_mvrv_ratio(df_dict, windows)
        if df.empty:
            return df
        if start_time is not None:
            df = df[df['candle_begin_time'] >= pd.to_datetime(start_time)]
        self.save_csv(df)
        self.log(df.tail().to_string())
        return df

    def draw_index(self, title, windows, df):
        """
        绘制并保存 MVRV 指标图（函数级注释）
        输出路径统一使用 self.png_path('mvrv_index')
        """
        try:
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10))
            ax1.plot(df['candle_begin_time'], df['mvrv_30d'], label='MVRV 30日', linewidth=2, color='#28a745')
            ax1.plot(df['candle_begin_time'], df['mvrv_90d'], label='MVRV 90日', linewidth=2, color='#17a2b8')
            ax1.plot(df['candle_begin_time'], df['mvrv_365d'], label='MVRV 365日', linewidth=2, color='#6f42c1')
            ax1.axhline(y=1.0, color='gray', linestyle='--', alpha=0.7, label='公允价值')
            ax1.axhline(y=0.8, color='green', linestyle='--', alpha=0.7, label='低估区域')
            ax1.axhline(y=1.5, color='red', linestyle='--', alpha=0.7, label='高估区域')
            ax1.set_title('MVRV比率走势图', fontsize=16, fontweight='bold')
            ax1.set_ylabel('MVRV比率', fontsize=12)
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            ax2.plot(df['candle_begin_time'], df['mvrv_zscore_30d'], label='MVRV Z-Score 30日', linewidth=2, color='#ffc107')
            ax2.plot(df['candle_begin_time'], df['mvrv_zscore_90d'], label='MVRV Z-Score 90日', linewidth=2, color='#dc3545')
            ax2.axhline(y=0, color='gray', linestyle='-', alpha=0.7)
            ax2.axhline(y=1.5, color='red', linestyle='--', alpha=0.7, label='超买')
            ax2.axhline(y=-1.5, color='green', linestyle='--', alpha=0.7, label='超卖')
            ax2.set_title('MVRV Z-Score走势图', fontsize=16, fontweight='bold')
            ax2.set_xlabel('日期', fontsize=12)
            ax2.set_ylabel('Z-Score', fontsize=12)
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            for ax in [ax1, ax2]:
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
                ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
                plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
            plt.tight_layout()
            out_png = self.png_path('mvrv_index')
            plt.savefig(out_png, dpi=300, bbox_inches='tight')
            plt.close('all')
            self.log(f'MVRV 指标图表已保存到 {out_png}')
        except Exception as e:
            self.warn(f'绘制 MVRV 图表时出错: {e}')


class 链上稳定币供应量(BaseIndicator):
    """链上稳定币供应量指标类，继承 BaseIndicator"""

    def indicator_slug(self) -> str:
        """指标保存文件前缀（函数级注释）"""
        return 'stablecoin_supply_sim'

    def indicator_title(self) -> str:
        """指标图表标题（函数级注释）"""
        return '链上稳定币供应量'

    def __init__(self):
        """初始化稳定币供应量指标类（函数级注释）"""
        super().__init__()
        self.stablecoins = ['USDT', 'USDC', 'BUSD', 'DAI', 'TUSD']

    def calculate_stablecoin_supply(self, df_dict, windows=[7, 30]):
        """
        计算稳定币供应量指标（函数级注释，模拟版本）
        参数:
            df_dict: 包含交易数据的字典
            windows: 计算窗口期列表
        返回:
            DataFrame: 包含稳定币总供应量及变化率的时间序列
        """
        try:
            base_data = None
            for symbol, df in df_dict.items():
                if 'BTC' in symbol and 'USDT' in symbol:
                    base_data = df[['candle_begin_time']].copy()
                    break
            if base_data is None:
                self.warn('未找到基准时间数据')
                return pd.DataFrame()
            base_data = base_data.sort_values('candle_begin_time')
            base_data['candle_begin_time'] = pd.to_datetime(base_data['candle_begin_time'])
            market_activity = self._calculate_market_activity(df_dict)
            base_supply = 120e9
            supply_data = []
            for i, _row in base_data.iterrows():
                activity_factor = market_activity.get(i, 1.0)
                daily_change = np.random.normal(0, 0.002) * activity_factor
                current_supply = base_supply if i == 0 else supply_data[-1] * (1 + daily_change)
                supply_data.append(current_supply)
            result_df = base_data.copy()
            result_df['total_stablecoin_supply'] = supply_data
            for window in windows:
                result_df[f'supply_ma{window}'] = result_df['total_stablecoin_supply'].rolling(window=window).mean()
            for window in windows:
                result_df[f'supply_change_{window}d'] = result_df['total_stablecoin_supply'].pct_change(periods=window)
            result_df['supply_signal'] = self._generate_supply_signals(result_df)
            result_df['total_supply_billion'] = result_df['total_stablecoin_supply'] / 1e9
            return result_df
        except Exception as e:
            self.warn(f'计算稳定币供应量时出错: {e}')
            return pd.DataFrame()

    def _calculate_market_activity(self, df_dict):
        """
        计算市场活跃度（函数级注释）
        返回：索引 -> 活跃度的字典
        """
        try:
            activity_scores = {}
            total_volumes = []
            for symbol, df in df_dict.items():
                if df is not None and not df.empty and 'volume' in df.columns:
                    total_volumes.append(df['volume'].sum())
            if total_volumes:
                avg_volume = np.mean(total_volumes)
                for i in range(len(total_volumes)):
                    activity_scores[i] = total_volumes[i] / (avg_volume + 1e-9)
            return activity_scores
        except Exception as e:
            self.warn(f'计算市场活跃度时出错: {e}')
            return {}

    def _generate_supply_signals(self, df):
        """
        生成稳定币供应量信号（函数级注释）
        返回：信号序列
        """
        signals = []
        for _, row in df.iterrows():
            scores = []
            if not pd.isna(row.get('supply_change_7d')):
                change_7d = row['supply_change_7d']
                if change_7d > 0.02:
                    scores.append(1)
                elif change_7d < -0.02:
                    scores.append(-1)
                else:
                    scores.append(0)
            if not pd.isna(row.get('supply_change_30d')):
                change_30d = row['supply_change_30d']
                if change_30d > 0.05:
                    scores.append(1)
                elif change_30d < -0.05:
                    scores.append(-1)
                else:
                    scores.append(0)
            if scores:
                avg = np.mean(scores)
                signals.append('积极' if avg > 0.5 else ('消极' if avg < -0.5 else '中性'))
            else:
                signals.append('未知')
        return pd.Series(signals, index=df.index)

    def process_data(self, df_dict, windows, backdays, interval, start_time):
        """
        统一的 process_data 方法（函数级注释）
        返回：保存 CSV 并返回结果
        """
        df = self.calculate_stablecoin_supply(df_dict, windows)
        if df.empty:
            return df
        if start_time is not None:
            df = df[df['candle_begin_time'] >= pd.to_datetime(start_time)]
        self.save_csv(df)
        self.log(df.tail().to_string())
        return df

    def draw_index(self, title, windows, df):
        """
        绘制并保存稳定币供应量图（函数级注释）
        输出路径统一使用 self.png_path('stablecoin_supply')
        """
        try:
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10))
            ax1.plot(df['candle_begin_time'], df['total_stablecoin_supply']/1e9, label='总供应量', linewidth=3, color='#17a2b8')
            if 'supply_ma7' in df.columns:
                ax1.plot(df['candle_begin_time'], df['supply_ma7']/1e9, label='7日均线', linewidth=2, color='#ffc107', alpha=0.8)
            if 'supply_ma30' in df.columns:
                ax1.plot(df['candle_begin_time'], df['supply_ma30']/1e9, label='30日均线', linewidth=2, color='#dc3545', alpha=0.8)
            ax1.set_title('稳定币总供应量走势图', fontsize=16, fontweight='bold')
            ax1.set_ylabel('供应量 (十亿)', fontsize=12)
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            ax2.plot(df['candle_begin_time'], df.get('supply_change_7d', pd.Series(index=df.index))*100, label='7日变化率', linewidth=2, color='#28a745')
            ax2.plot(df['candle_begin_time'], df.get('supply_change_30d', pd.Series(index=df.index))*100, label='30日变化率', linewidth=2, color='#6f42c1')
            ax2.axhline(y=0, color='gray', linestyle='-', alpha=0.7)
            ax2.axhline(y=2, color='red', linestyle='--', alpha=0.7, label='高增长')
            ax2.axhline(y=-2, color='green', linestyle='--', alpha=0.7, label='负增长')
            ax2.set_title('稳定币供应量变化率', fontsize=16, fontweight='bold')
            ax2.set_xlabel('日期', fontsize=12)
            ax2.set_ylabel('变化率 (%)', fontsize=12)
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            for ax in [ax1, ax2]:
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
                ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
                plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
            plt.tight_layout()
            out_png = self.png_path('stablecoin_supply')
            plt.savefig(out_png, dpi=300, bbox_inches='tight')
            plt.close('all')
            self.log(f'稳定币供应量图表已保存到 {out_png}')
        except Exception as e:
            self.warn(f'绘制稳定币供应量图表时出错: {e}')


class 交易所净流入流出(BaseIndicator):
    """交易所净流入流出指标类，继承 BaseIndicator"""

    def indicator_slug(self) -> str:
        """指标保存文件前缀（函数级注释）"""
        return 'exchange_flow_sim'

    def indicator_title(self) -> str:
        """指标图表标题（函数级注释）"""
        return '交易所净流入流出'

    def calculate_exchange_flow(self, df_dict, windows=[7, 30]):
        """
        计算交易所净流入流出（函数级注释，模拟版本）
        参数:
            df_dict: 包含交易数据的字典
            windows: 计算窗口期列表
        返回:
            DataFrame: 包含净流入流出、比率与强度的时间序列
        """
        try:
            base_data = None
            for symbol, df in df_dict.items():
                if 'BTC' in symbol and 'USDT' in symbol:
                    base_data = df[['candle_begin_time', 'volume', 'close']].copy()
                    break
            if base_data is None:
                self.warn('未找到基准数据')
                return pd.DataFrame()
            base_data = base_data.sort_values('candle_begin_time')
            base_data['candle_begin_time'] = pd.to_datetime(base_data['candle_begin_time'])
            result_df = base_data.copy()
            result_df['price_change'] = result_df['close'].pct_change()
            net_flows = []
            for _, row in result_df.iterrows():
                volume = row['volume']
                price_change = row['price_change'] if not pd.isna(row['price_change']) else 0
                base_flow = volume * price_change * np.random.uniform(0.1, 0.3)
                noise = np.random.normal(0, volume * 0.05)
                net_flow = base_flow + noise
                net_flows.append(net_flow)
            result_df['net_flow'] = net_flows
            for window in windows:
                result_df[f'net_flow_ma{window}'] = result_df['net_flow'].rolling(window=window).mean()
            result_df['inflow'] = result_df['net_flow'].apply(lambda x: max(x, 0))
            result_df['outflow'] = result_df['net_flow'].apply(lambda x: abs(min(x, 0)))
            result_df['flow_ratio'] = result_df['inflow'] / (result_df['outflow'] + 1e-10)
            result_df['flow_intensity'] = abs(result_df['net_flow']) / (result_df['volume'] + 1e-9)
            result_df['flow_signal'] = self._generate_flow_signals(result_df)
            return result_df
        except Exception as e:
            self.warn(f'计算交易所净流入流出时出错: {e}')
            return pd.DataFrame()

    def _generate_flow_signals(self, df):
        """
        生成交易所流动信号（函数级注释）
        返回：信号序列
        """
        signals = []
        for _, row in df.iterrows():
            scores = []
            net_flow = row['net_flow']
            scores.append(1 if net_flow > 0 else -1)
            flow_ratio = row.get('flow_ratio')
            if not pd.isna(flow_ratio):
                if flow_ratio > 1.5:
                    scores.append(1)
                elif flow_ratio < 0.5:
                    scores.append(-1)
                else:
                    scores.append(0)
            intensity = row.get('flow_intensity')
            if not pd.isna(intensity):
                if intensity > 0.1:
                    scores.append(1 if net_flow > 0 else -1)
                else:
                    scores.append(0)
            if scores:
                avg = np.mean(scores)
                signals.append('净流入' if avg > 0.5 else ('净流出' if avg < -0.5 else '平衡'))
            else:
                signals.append('未知')
        return pd.Series(signals, index=df.index)

    def process_data(self, df_dict, windows, backdays, interval, start_time):
        """
        统一的 process_data 方法（函数级注释）
        返回：保存 CSV 并返回结果
        """
        df = self.calculate_exchange_flow(df_dict, windows)
        if df.empty:
            return df
        if start_time is not None:
            df = df[df['candle_begin_time'] >= pd.to_datetime(start_time)]
        self.save_csv(df)
        self.log(df.tail().to_string())
        return df

    def draw_index(self, title, windows, df):
        """
        绘制并保存交易所净流入流出图（函数级注释）
        输出路径统一使用 self.png_path('exchange_flow')
        """
        try:
            fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 12))
            colors = ['green' if x >= 0 else 'red' for x in df['net_flow']]
            ax1.bar(df['candle_begin_time'], df['net_flow']/1e6, color=colors, alpha=0.7, label='净流入流出')
            if 'net_flow_ma7' in df.columns:
                ax1.plot(df['candle_begin_time'], df['net_flow_ma7']/1e6, label='7日均线', linewidth=2, color='#ffc107')
            if 'net_flow_ma30' in df.columns:
                ax1.plot(df['candle_begin_time'], df['net_flow_ma30']/1e6, label='30日均线', linewidth=2, color='#6f42c1')
            ax1.axhline(y=0, color='gray', linestyle='-', alpha=0.7)
            ax1.set_title('交易所净流入流出', fontsize=16, fontweight='bold')
            ax1.set_ylabel('净流入流出 (百万)', fontsize=12)
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            ax2.plot(df['candle_begin_time'], df['flow_ratio'], label='流入流出比率', linewidth=2, color='#17a2b8')
            ax2.axhline(y=1, color='gray', linestyle='-', alpha=0.7, label='平衡线')
            ax2.axhline(y=1.5, color='green', linestyle='--', alpha=0.7, label='流入占优')
            ax2.axhline(y=0.5, color='red', linestyle='--', alpha=0.7, label='流出占优')
            ax2.set_title('流入流出比率', fontsize=16, fontweight='bold')
            ax2.set_ylabel('比率', fontsize=12)
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            ax3.plot(df['candle_begin_time'], df['flow_intensity'], label='流动强度', linewidth=2, color='#fd7e14')
            ax3.axhline(y=0.1, color='red', linestyle='--', alpha=0.7, label='高强度阈值')
            ax3.set_title('流动强度', fontsize=16, fontweight='bold')
            ax3.set_xlabel('日期', fontsize=12)
            ax3.set_ylabel('强度 (USD)')
            ax3.legend()
            ax3.grid(True, alpha=0.3)
            for ax in [ax1, ax2, ax3]:
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
                ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
                plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
            plt.tight_layout()
            out_png = self.png_path('exchange_flow')
            plt.savefig(out_png, dpi=300, bbox_inches='tight')
            plt.close('all')
            self.log(f'交易所净流入流出图表已保存到 {out_png}')
        except Exception as e:
            self.warn(f'绘制交易所净流入流出图表时出错: {e}')
