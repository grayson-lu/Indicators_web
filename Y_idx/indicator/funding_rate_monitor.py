'''
全市场资金费率监控指标
Funding Rate Monitor
监控期货合约资金费率，分析市场情绪和多空力量对比
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


class 全市场资金费率监控(BaseIndicator):
    def indicator_slug(self) -> str:
        """
        返回统一保存文件前缀（CSV/PNG 文件名）
        """
        return 'funding_rate_monitor'

    def indicator_title(self) -> str:
        """
        返回统一的图表标题
        """
        return '全市场资金费率监控'

    def stat(self, acc: str, backdays=365, windows=[1, 7, 30], interval='8h', start_time=None):
        """
        统计全市场资金费率监控指标（统一入口）
        参数:
        - acc/backdays/windows/interval/start_time 按统一约定
        返回: 指标结果 DataFrame
        """
        self.log(f'统计全市场资金费率监控指标, windows = {windows}')
        funding_data = self.fetch_funding_rate_data(backdays)
        return self.process_data(funding_data, windows, backdays, interval, start_time)

    def stat_with_data(self, funding_data, acc: str, start_time=None, backdays=365, windows=[1, 7, 30], interval='8h'):
        """
        使用已有资金费率数据统计（统一入口）
        - 未传入 funding_data 时将自动生成模拟数据
        参数与行为与 stat 保持一致
        """
        self.log(f'使用已有数据统计全市场资金费率监控指标, windows = {windows}')
        if funding_data is None:
            funding_data = self.fetch_funding_rate_data(backdays)
        return self.process_data(funding_data, windows, backdays, interval, start_time)

    def fetch_funding_rate_data(self, backdays):
        """
        获取资金费率数据（模拟）
        - 真实环境应从交易所API抓取，此处为规范化演示
        返回: DataFrame，包含 'timestamp', 'symbol', 'funding_rate', 'funding_rate_pct'
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(days=backdays + 30)
        time_range = pd.date_range(start=start_time, end=end_time, freq='8H')
        symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'XRPUSDT',
                   'SOLUSDT', 'DOTUSDT', 'DOGEUSDT', 'AVAXUSDT', 'MATICUSDT',
                   'LINKUSDT', 'LTCUSDT', 'UNIUSDT', 'ATOMUSDT', 'FILUSDT',
                   'TRXUSDT', 'ETCUSDT', 'XLMUSDT', 'VETUSDT', 'ICPUSDT']
        funding_data = []
        for timestamp in time_range:
            for symbol in symbols:
                base_rate = np.random.normal(0, 0.0001)
                trend_factor = np.sin(len(funding_data) * 0.01) * 0.00005
                volatility = np.random.normal(0, 0.00002)
                funding_rate = base_rate + trend_factor + volatility
                funding_rate = max(-0.001, min(0.001, funding_rate))
                funding_data.append({
                    'timestamp': timestamp,
                    'symbol': symbol,
                    'funding_rate': funding_rate,
                    'funding_rate_pct': funding_rate * 100
                })
        return pd.DataFrame(funding_data)

    def process_data(self, df_dict, windows, backdays, interval, start_time):
        """
        处理数据计算资金费率监控指标（统一签名）
        参数:
        - df_dict: 资金费率 DataFrame 或 dict（键为币种，值为DataFrame）
        - windows: 时间窗口列表（单位天），用于移动统计
        - backdays: 回看天数
        - interval: 时间间隔（资金费率为'8h'）
        - start_time: 起始时间过滤
        返回: 汇总后的资金费率监控指标数据，并保存到CSV
        """
        funding_df = None
        if isinstance(df_dict, pd.DataFrame):
            funding_df = df_dict
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
                    funding_df = pd.concat(parts, ignore_index=True)
            except Exception as e:
                self.warn(f'资金费率字典合并失败: {e}')
                funding_df = None
        if funding_df is None or not isinstance(funding_df, pd.DataFrame) or funding_df.empty:
            self.warn('资金费率数据为空或类型不正确，返回空DataFrame')
            return pd.DataFrame()
        df = funding_df.copy()
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values(['timestamp', 'symbol'])
        dfs = []
        for timestamp, group in df.groupby('timestamp'):
            group = group.copy()
            if len(group) == 0:
                continue
            row = {'candle_begin_time': timestamp}
            row['币种数量'] = len(group)
            funding_rates = group['funding_rate'].dropna()
            if len(funding_rates) > 0:
                row['平均资金费率'] = funding_rates.mean() * 100
                row['中位数资金费率'] = funding_rates.median() * 100
                row['资金费率标准差'] = funding_rates.std() * 100
                row['最大资金费率'] = funding_rates.max() * 100
                row['最小资金费率'] = funding_rates.min() * 100
                positive_rates = funding_rates[funding_rates > 0]
                negative_rates = funding_rates[funding_rates < 0]
                zero_rates = funding_rates[funding_rates == 0]
                row['正费率币种数'] = len(positive_rates)
                row['负费率币种数'] = len(negative_rates)
                row['零费率币种数'] = len(zero_rates)
                row['正费率占比'] = (len(positive_rates) / len(funding_rates)) * 100
                row['负费率占比'] = (len(negative_rates) / len(funding_rates)) * 100
                row['零费率占比'] = (len(zero_rates) / len(funding_rates)) * 100
                high_positive = len(funding_rates[funding_rates > 0.0001])
                high_negative = len(funding_rates[funding_rates < -0.0001])
                row['高正费率币种数'] = high_positive
                row['高负费率币种数'] = high_negative
                row['高正费率占比'] = (high_positive / len(funding_rates)) * 100
                row['高负费率占比'] = (high_negative / len(funding_rates)) * 100
                avg_rate = funding_rates.mean()
                row['市场情绪'] = self.get_market_sentiment(avg_rate)
                long_bias = len(positive_rates) / len(funding_rates) if len(funding_rates) > 0 else 0.5
                row['多空力量对比'] = long_bias * 100
                row['多空状态'] = self.get_long_short_status(long_bias)
                rate_range = funding_rates.max() - funding_rates.min()
                row['费率波动幅度'] = rate_range * 100
                row['费率波动状态'] = self.get_volatility_status(rate_range)
                rate_concentration = len(funding_rates[abs(funding_rates) < 0.00001]) / len(funding_rates)
                row['费率集中度'] = rate_concentration * 100
            else:
                for col in ['平均资金费率', '中位数资金费率', '资金费率标准差', '最大资金费率', '最小资金费率',
                           '正费率币种数', '负费率币种数', '零费率币种数', '正费率占比', '负费率占比', '零费率占比',
                           '高正费率币种数', '高负费率币种数', '高正费率占比', '高负费率占比', '多空力量对比',
                           '费率波动幅度', '费率集中度']:
                    row[col] = np.nan
                row['市场情绪'] = '无数据'
                row['多空状态'] = '无数据'
                row['费率波动状态'] = '无数据'
            dfs.append(pd.DataFrame([row]))
        if not dfs:
            return pd.DataFrame()
        result_df = pd.concat(dfs, ignore_index=True)
        result_df = result_df.sort_values('candle_begin_time')
        for window in windows:
            periods = window * 3  # 8小时为一个周期，1天=3个周期
            result_df[f'平均资金费率_{window}d'] = result_df['平均资金费率'].rolling(periods).mean()
            result_df[f'资金费率波动_{window}d'] = result_df['资金费率标准差'].rolling(periods).mean()
            result_df[f'多空力量趋势_{window}d'] = result_df['多空力量对比'].rolling(periods).mean()
            result_df[f'高费率频率_{window}d'] = (result_df['高正费率占比'] + result_df['高负费率占比']).rolling(periods).mean()
            result_df[f'费率趋势_{window}d'] = result_df['平均资金费率'].rolling(periods).apply(
                lambda x: (x.iloc[-1] - x.iloc[0]) if len(x) == periods and not pd.isna(x.iloc[0]) else np.nan
            )
            result_df[f'市场热度_{window}d'] = result_df['费率波动幅度'].rolling(periods).mean()
        if start_time is not None:
            result_df = result_df[result_df['candle_begin_time'] > pd.to_datetime(start_time)]
        self.save_csv(result_df)
        if not result_df.empty:
            self.log(result_df.tail().to_string())
        return result_df

    def get_market_sentiment(self, avg_rate):
        """
        根据平均资金费率获取市场情绪
        返回: 描述字符串
        """
        rate_pct = avg_rate * 100
        if rate_pct > 0.01:
            return '极度贪婪'
        elif rate_pct > 0.005:
            return '贪婪'
        elif rate_pct > -0.005:
            return '中性'
        elif rate_pct > -0.01:
            return '恐惧'
        else:
            return '极度恐惧'

    def get_long_short_status(self, long_bias):
        """
        根据多头偏向获取多空状态
        """
        if long_bias > 0.7:
            return '多头主导'
        elif long_bias > 0.6:
            return '多头优势'
        elif long_bias > 0.4:
            return '多空平衡'
        elif long_bias > 0.3:
            return '空头优势'
        else:
            return '空头主导'

    def get_volatility_status(self, rate_range):
        """
        根据费率波动幅度获取波动状态
        """
        range_pct = rate_range * 100
        if range_pct > 0.05:
            return '极高波动'
        elif range_pct > 0.03:
            return '高波动'
        elif range_pct > 0.01:
            return '中等波动'
        elif range_pct > 0.005:
            return '低波动'
        else:
            return '极低波动'

    def draw_index(self, title, windows, equity_df):
        """
        绘制并保存资金费率监控图（统一签名/统一保存路径）
        - 输出路径统一使用 self.png_path()
        """
        fig = plt.figure(tight_layout=False, figsize=(32, 16), dpi=80, facecolor='w', edgecolor='k')
        gs = gridspec.GridSpec(30, 12)
        # 上图：平均资金费率
        ax1 = fig.add_subplot(gs[0:8, 0:11])
        ax1.plot(equity_df['candle_begin_time'], equity_df['平均资金费率'], label='平均资金费率(%)', color='blue', linewidth=2)
        for window in windows:
            col_name = f'平均资金费率_{window}d'
            if col_name in equity_df.columns:
                ax1.plot(equity_df['candle_begin_time'], equity_df[col_name], label=f'MA{window}d', alpha=0.7)
        ax1.axhline(y=0, color='black', linestyle='-', alpha=0.5)
        ax1.axhline(y=0.01, color='red', linestyle=':', alpha=0.7, label='贪婪线(0.01%)')
        ax1.axhline(y=-0.01, color='green', linestyle=':', alpha=0.7, label='恐惧线(-0.01%)')
        ax1.set_ylabel('资金费率 (%)')
        ax1.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        ax1.grid(True, linestyle='--', alpha=0.3)
        ax1.set_title('市场平均资金费率', fontsize='medium', fontweight='bold')
        # 中图：多空力量对比
        ax2 = fig.add_subplot(gs[10:18, 0:11])
        ax2.plot(equity_df['candle_begin_time'], equity_df['多空力量对比'], label='多空力量对比(%)', color='purple', linewidth=2)
        for window in windows:
            col_name = f'多空力量趋势_{window}d'
            if col_name in equity_df.columns:
                ax2.plot(equity_df['candle_begin_time'], equity_df[col_name], label=f'趋势{window}d', alpha=0.7)
        ax2.axhline(y=50, color='black', linestyle='-', alpha=0.5, label='平衡线')
        ax2.axhline(y=70, color='red', linestyle=':', alpha=0.7, label='多头主导(70%)')
        ax2.axhline(y=30, color='green', linestyle=':', alpha=0.7, label='空头主导(30%)')
        ax2.set_ylabel('多头占比 (%)')
        ax2.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        ax2.grid(True, linestyle='--', alpha=0.3)
        ax2.set_title('多空力量对比', fontsize='medium', fontweight='bold')
        # 下图：费率分布
        ax3 = fig.add_subplot(gs[20:28, 0:11])
        ax3.plot(equity_df['candle_begin_time'], equity_df['正费率占比'], label='正费率占比(%)', color='red')
        ax3.plot(equity_df['candle_begin_time'], equity_df['负费率占比'], label='负费率占比(%)', color='green')
        ax3.plot(equity_df['candle_begin_time'], equity_df['零费率占比'], label='零费率占比(%)', color='gray', linestyle='--')
        ax3.set_ylabel('占比 (%)')
        ax3.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        ax3.grid(True, linestyle='--', alpha=0.3)
        ax3.set_title('资金费率分布', fontsize='medium', fontweight='bold')
        plt.xticks(rotation=30)
        plt.tight_layout()
        png_file = self.png_path()
        plt.savefig(png_file, bbox_inches='tight')
        self.log(f'图表已保存: {png_file}')
        plt.close('all')
