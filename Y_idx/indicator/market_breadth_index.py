'''
市场宽度和创新高指数
监控加密货币市场的宽度与创新高数量，统一基类与保存路径
'''
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False
from .base_indicator import BaseIndicator
import concurrent.futures

class MarketBreadthIndex(BaseIndicator):
    def indicator_slug(self) -> str:
        """
        返回统一的保存前缀 slug，用于 CSV/PNG 文件名（函数级注释）
        """
        return "market_breadth_index"

    def indicator_title(self) -> str:
        """
        返回统一的图表标题（函数级注释）
        """
        return "市场宽度与创新高指数"

    def stat(self, acc:str, backdays=365, windows=[7, 30, 90, 365], interval='1d', start_time=None):
        """
        统计市场宽度与创新高（统一入口，函数级注释）
        参数:
        - acc/backdays/windows/interval/start_time 同统一约定
        返回: 指标结果 DataFrame
        行为:
        - 生成模拟行情数据（close/high/volume/quote_volume），符合同步接口
        - 调用 process_data 统一计算与保存
        """
        self.log(f'统计市场宽度与创新高, windows = {windows}, interval = {interval}')
        end = pd.Timestamp.now(); start = end - pd.Timedelta(days=backdays + 30)
        freq = '1H' if interval == '1h' else '1D'
        dates = pd.date_range(start=start, end=end, freq=freq)
        symbols = [f'COIN{i}USDT' for i in range(1, 101)]
        df_dict = {}
        for s in symbols:
            prices = []
            highs = []
            vols = []
            qvols = []
            price = 100 + np.random.normal(0, 5)
            for i, t in enumerate(dates):
                drift = np.sin(i * 0.005) * 0.3
                shock = np.random.normal(0, 1)
                price = max(0.5, price + drift + shock)
                prices.append(price)
                highs.append(price * (1 + abs(np.random.normal(0, 0.02))))
                v = max(1, np.random.lognormal(mean=2.3, sigma=0.6))
                q = v * price
                vols.append(v)
                qvols.append(q)
            df = pd.DataFrame({
                'candle_begin_time': dates,
                'symbol': s,
                'close': prices,
                'high': highs,
                'volume': vols,
                'quote_volume': qvols,
            })
            df_dict[s] = df
        return self.process_data(df_dict, windows, backdays, interval, start_time)

    def stat_with_data(self, df_dict, acc:str, start_time=None, backdays=365, windows=[7, 30, 90, 365], interval='1d'):
        """
        使用已有数据统计市场宽度与创新高（统一入口，函数级注释）
        参数同 stat
        返回: 指标结果 DataFrame
        """
        self.log(f'使用已有数据统计市场宽度与创新高, windows = {windows}, interval = {interval}')
        if not isinstance(df_dict, dict) or len(df_dict) == 0:
            return self.stat(acc=acc, backdays=backdays, windows=windows, interval=interval, start_time=start_time)
        return self.process_data(df_dict, windows, backdays, interval, start_time)

    def process_data(self, df_dict, windows, backdays, interval, start_time):
        """
        处理数据并计算市场宽度与创新高（统一签名，函数级注释）
        参数:
        - df_dict: 所有交易对的K线数据字典
        - windows: 指标窗口列表
        - backdays: 回溯天数（未直接使用）
        - interval: 周期 '1d' 或 '1h'
        - start_time: 起始时间过滤
        返回: 计算完成的 DataFrame（统一通过 self.save_csv 保存）
        """
        # 只使用现货币种数据（示例：USDT 计价且非永续合约标记）
        spot_symbols = [s for s in df_dict.keys() if s.endswith('USDT') and not s.endswith('_PERP')]
        # 并行预处理数据
        def process_symbol(symbol):
            try:
                df = df_dict[symbol].copy()
                df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'])
                df['daily_return'] = df['close'].pct_change(1) * 100
                return symbol, df[['candle_begin_time', 'daily_return', 'close', 'high', 'volume']]
            except Exception as e:
                self.warn(f"处理 {symbol} 时出错: {str(e)}")
                return symbol, None
        daily_returns = {}
        timestamps = None
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            future_to_symbol = {executor.submit(process_symbol, symbol): symbol for symbol in spot_symbols}
            for future in concurrent.futures.as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    symbol, result = future.result()
                    if result is not None:
                        daily_returns[symbol] = result
                        if timestamps is None:
                            timestamps = result['candle_begin_time']
                except Exception as e:
                    self.warn(f"{symbol} 生成结果时出错: {str(e)}")
        # 使用 self.top_n 进行活跃币种筛选（按平均成交量排序，提前到批处理前）
        if hasattr(self, 'top_n') and isinstance(self.top_n, int) and self.top_n > 0:
            avg_volumes = []
            for symbol, df in daily_returns.items():
                if df is not None and 'volume' in df.columns:
                    avg_volumes.append((symbol, float(np.nanmean(df['volume']))))
            if len(avg_volumes) > 0:
                avg_volumes.sort(key=lambda x: x[1], reverse=True)
                selected = [s for s, _ in avg_volumes[:self.top_n]]
                spot_symbols = [s for s in spot_symbols if s in selected]
                daily_returns = {s: daily_returns[s] for s in selected if s in daily_returns}
        if timestamps is None or len(daily_returns) == 0:
            return pd.DataFrame()
        timestamps_dates = pd.DatetimeIndex(timestamps)
        # 预先创建结果DataFrame
        result_data = pd.DataFrame({
            'candle_begin_time': timestamps,
            '涨幅币种比例': np.zeros(len(timestamps)),
            '跌幅币种比例': np.zeros(len(timestamps)),
            '持平币种比例': np.zeros(len(timestamps)),
            '爆拉币种占比': np.zeros(len(timestamps)),
            '暴跌币种占比': np.zeros(len(timestamps)),
            '市场宽度指数': np.zeros(len(timestamps))
        })
        ma_periods = [5, 10, 20, 60]
        for window in windows:
            result_data[f'创{window}日新高占比'] = np.zeros(len(timestamps))
        for ma in ma_periods:
            result_data[f'收盘价大于MA{ma}比例'] = np.zeros(len(timestamps))
            result_data[f'MA{ma}市场宽度指数'] = np.zeros(len(timestamps))
        # 计数器
        total_counts = np.zeros(len(timestamps))
        up_counts = np.zeros(len(timestamps))
        down_counts = np.zeros(len(timestamps))
        flat_counts = np.zeros(len(timestamps))
        extreme_up_counts = np.zeros(len(timestamps))
        extreme_down_counts = np.zeros(len(timestamps))
        new_highs_counts = {window: np.zeros(len(timestamps)) for window in windows}
        total_counts_new_highs = np.zeros(len(timestamps))
        ma_above_counts = {ma: np.zeros(len(timestamps)) for ma in ma_periods}
        total_counts_ma = np.zeros(len(timestamps))
        # 批量处理符号
        batch_size = 100
        batches = [spot_symbols[i:i+batch_size] for i in range(0, len(spot_symbols), batch_size)]
        for batch_symbols in batches:
            valid_symbols = [s for s in batch_symbols if s in daily_returns]
            for symbol in valid_symbols:
                df = daily_returns[symbol]
                for t_idx, timestamp in enumerate(timestamps_dates):
                    row = df[df['candle_begin_time'] == timestamp]
                    if len(row) > 0:
                        row_idx = row.index[0]
                        # 市场宽度统计
                        if not pd.isna(row['daily_return'].values[0]):
                            rv = row['daily_return'].values[0]
                            if rv > 0:
                                up_counts[t_idx] += 1
                            elif rv < 0:
                                down_counts[t_idx] += 1
                            else:
                                flat_counts[t_idx] += 1
                            if rv >= 20:
                                extreme_up_counts[t_idx] += 1
                            elif rv <= -20:
                                extreme_down_counts[t_idx] += 1
                            total_counts[t_idx] += 1
                        # 创新高与均线
                        if row_idx >= max(windows) and t_idx >= max(windows):
                            current_price = df.loc[row_idx, 'close']
                            for window in windows:
                                if row_idx >= window:
                                    lookback_prices = df.loc[row_idx-window:row_idx-1, 'high']
                                    if current_price > lookback_prices.max():
                                        new_highs_counts[window][t_idx] += 1
                            total_counts_new_highs[t_idx] += 1
                            if row_idx >= max(ma_periods):
                                for ma in ma_periods:
                                    if row_idx >= ma:
                                        ma_value = df.loc[row_idx-ma:row_idx-1, 'close'].mean()
                                        if current_price > ma_value:
                                            ma_above_counts[ma][t_idx] += 1
                                total_counts_ma[t_idx] += 1
        # 汇总结果
        total_counts = np.maximum(total_counts, 1)
        total_counts_new_highs = np.maximum(total_counts_new_highs, 1)
        total_counts_ma = np.maximum(total_counts_ma, 1)
        result_data['市场宽度指数'] = (up_counts - down_counts) / total_counts * 100
        result_data['涨幅币种比例'] = up_counts / total_counts
        result_data['跌幅币种比例'] = down_counts / total_counts
        result_data['持平币种比例'] = flat_counts / total_counts
        result_data['爆拉币种占比'] = extreme_up_counts / total_counts
        result_data['暴跌币种占比'] = extreme_down_counts / total_counts
        for window in windows:
            result_data[f'创{window}日新高占比'] = new_highs_counts[window] / total_counts_new_highs
        for ma in ma_periods:
            result_data[f'收盘价大于MA{ma}比例'] = ma_above_counts[ma] / total_counts_ma
            result_data[f'MA{ma}市场宽度指数'] = (ma_above_counts[ma] / total_counts_ma - 0.5) * 200
        result_data = result_data.sort_values('candle_begin_time')
        for window in windows:
            result_data[f'市场宽度指数_{window}d'] = result_data['市场宽度指数'].rolling(window=window).mean()
        # AD百分比
        result_data['AD差值'] = result_data['涨幅币种比例'] - result_data['跌幅币种比例']
        result_data['AD累计'] = result_data['AD差值'].ewm(span=30).mean()
        ad_mean = result_data['AD累计'].mean(); ad_std = result_data['AD累计'].std()
        if ad_std > 0:
            result_data['AD百分比_标准化'] = ((result_data['AD累计'] - ad_mean) / ad_std) * 50
            method1_range = (result_data['AD累计'] * 200).max() - (result_data['AD累计'] * 200).min()
            method2_range = result_data['AD百分比_标准化'].max() - result_data['AD百分比_标准化'].min()
            result_data['AD百分比'] = result_data['AD百分比_标准化'] if abs(method2_range - 200) < abs(method1_range - 200) else (result_data['AD累计'] * 200)
            if 'AD百分比_标准化' in result_data.columns:
                result_data.drop('AD百分比_标准化', axis=1, inplace=True)
        else:
            result_data['AD百分比'] = result_data['AD累计'] * 200
        if start_time is not None:
            result_data = result_data[result_data['candle_begin_time'] > pd.to_datetime(start_time)]
        # 统一保存与日志
        self.save_csv(result_data)
        if not result_data.empty:
            self.log(result_data.tail().to_string())
        return result_data

    def draw_index(self, df, start_time=None, interval='1d'):
        """
        绘制统一图表集合并保存到统一路径（单图多子图，函数级注释）
        自动解析 df 中的窗口列，避免额外参数。
        参数:
        - df: 指标结果 DataFrame
        - start_time/interval: 统一签名占位
        """
        if df is None or df.empty:
            self.warn('draw_index - 数据为空，跳过绘图')
            return
        # 解析可用窗口
        import re
        windows = sorted({int(m.group(1)) for col in df.columns for m in [re.search(r'^市场宽度指数_(\d+)d$', col)] if m})
        high_windows = sorted({int(m.group(1)) for col in df.columns for m in [re.search(r'^创(\d+)日新高占比$', col)] if m})
        if not windows and '市场宽度指数' in df.columns:
            windows = []
        fig, axes = plt.subplots(3, 2, figsize=(18, 12))
        axes = axes.flatten()
        # 1 市场宽度指数
        axes[0].plot(df['candle_begin_time'], df['市场宽度指数'], label='当日市场宽度')
        for window in windows:
            col = f'市场宽度指数_{window}d'
            if col in df.columns:
                axes[0].plot(df['candle_begin_time'], df[col], label=f'{window}日市场宽度')
        axes[0].axhline(y=0, color='k', linestyle='--', alpha=0.5)
        axes[0].axhline(y=50, color='g', linestyle='--', alpha=0.5)
        axes[0].axhline(y=-50, color='r', linestyle='--', alpha=0.5)
        axes[0].set_title('市场宽度指数'); axes[0].legend(); axes[0].grid(True, alpha=0.3)
        # 2 创新高占比
        for window in high_windows:
            col = f'创{window}日新高占比'
            if col in df.columns:
                axes[1].plot(df['candle_begin_time'], df[col] * 100, label=col)
        axes[1].set_title('创新高指标'); axes[1].legend(); axes[1].grid(True, alpha=0.3)
        # 3 均线宽度
        ma_periods = [5, 10, 20, 60]
        for ma in ma_periods:
            col = f'MA{ma}市场宽度指数'
            if col in df.columns:
                axes[2].plot(df['candle_begin_time'], df[col], label=f'MA{ma}市场宽度')
        axes[2].axhline(y=0, color='k', linestyle='--', alpha=0.5)
        axes[2].axhline(y=50, color='g', linestyle='--', alpha=0.5)
        axes[2].axhline(y=-50, color='r', linestyle='--', alpha=0.5)
        axes[2].set_title('基于均线的市场宽度'); axes[2].legend(); axes[2].grid(True, alpha=0.3)
        # 4 AD百分比
        axes[3].plot(df['candle_begin_time'], df['AD百分比'], label='AD百分比')
        axes[3].axhline(y=0, color='k', linestyle='--', alpha=0.5)
        axes[3].axhline(y=80, color='g', linestyle='--', alpha=0.5)
        axes[3].axhline(y=-80, color='r', linestyle='--', alpha=0.5)
        axes[3].set_title('AD百分比'); axes[3].legend(); axes[3].grid(True, alpha=0.3)
        # 5 涨跌比例
        axes[4].plot(df['candle_begin_time'], df['涨幅币种比例'] * 100, label='涨幅币种比例', color='g')
        axes[4].plot(df['candle_begin_time'], df['跌幅币种比例'] * 100, label='跌幅币种比例', color='r')
        axes[4].axhline(y=50, color='k', linestyle='--', alpha=0.5)
        axes[4].set_title('涨跌比例'); axes[4].legend(); axes[4].grid(True, alpha=0.3)
        # 6 极端波动
        if '爆拉币种占比' in df.columns and '暴跌币种占比' in df.columns:
            axes[5].plot(df['candle_begin_time'], df['爆拉币种占比'] * 100, label='爆拉占比(>20%)', color='g')
            axes[5].plot(df['candle_begin_time'], df['暴跌币种占比'] * 100, label='暴跌占比(<-20%)', color='r')
        axes[5].set_title('爆拉暴跌占比'); axes[5].legend(); axes[5].grid(True, alpha=0.3)
        for ax in axes:
            ax.tick_params(axis='x', rotation=30)
        fig.suptitle(self.indicator_title())
        fig.tight_layout()
        plt.savefig(self.png_path(), bbox_inches='tight')
        plt.close()
