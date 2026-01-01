'''
Y指数单指标实现
统一接入 BaseIndicator，移除硬编码路径与交易所依赖
'''
import pandas as pd
import numpy as np
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


class Y指数(BaseIndicator):
    def indicator_slug(self) -> str:
        """
        返回统一保存前缀（CSV/PNG 文件名使用）
        """
        return 'y_index'

    def indicator_title(self) -> str:
        """
        返回统一的图表标题
        """
        return 'Y指数'

    def stat(self, acc: str, backdays=365, windows=[1, 7, 30], interval='1d', start_time=None):
        """
        统计 Y 指数（统一入口）
        参数:
        - acc/backdays/windows/interval/start_time 同统一约定
        返回: 指标结果 DataFrame
        行为:
        - 若无外部数据，则生成模拟的多币种行情数据（包含close/volume/quote_volume）
        - 交由 process_data 进行统一计算与保存
        """
        self.log(f'统计 Y 指数, windows = {windows}, interval = {interval}')
        # 生成模拟数据
        end = pd.Timestamp.now(); start = end - pd.Timedelta(days=backdays + 30)
        freq = '1H' if interval == '1h' else '1D'
        dates = pd.date_range(start=start, end=end, freq=freq)
        symbols = ['BTCUSDT','ETHUSDT','BNBUSDT','ADAUSDT','XRPUSDT','SOLUSDT','DOTUSDT','MATICUSDT']
        df_dict = {}
        for s in symbols:
            base = 100 + np.random.normal(0, 5)
            prices = []
            vols = []
            qvols = []
            price = base
            for i, t in enumerate(dates):
                drift = np.sin(i * 0.01) * 0.5
                shock = np.random.normal(0, 1)
                price = max(0.5, price + drift + shock)
                prices.append(price)
                v = max(1, np.random.lognormal(mean=2.5, sigma=0.5))
                q = v * price
                vols.append(v)
                qvols.append(q)
            df = pd.DataFrame({
                'candle_begin_time': dates,
                'symbol': s,
                'close': prices,
                'volume': vols,
                'quote_volume': qvols,
            })
            df_dict[s] = df
        return self.process_data(df_dict, windows, backdays, interval, start_time)

    def stat_with_data(self, df_dict, acc: str, start_time=None, backdays=365, windows=[1, 7, 30], interval='1d'):
        """
        使用已有数据统计 Y 指数（统一入口）
        参数同 stat；当 df_dict 为空时将自动生成模拟数据
        """
        self.log(f'使用已有数据统计 Y 指数, windows = {windows}, interval = {interval}')
        if not isinstance(df_dict, dict) or len(df_dict) == 0:
            return self.stat(acc=acc, backdays=backdays, windows=windows, interval=interval, start_time=start_time)
        return self.process_data(df_dict, windows, backdays, interval, start_time)

    def process_data(self, df_dict, windows, backdays, interval, start_time):
        """
        处理数据并计算 Y 指数（统一签名）
        核心思路:
        - 按币种计算日收益与成交量缩放后得分(score)
        - 每个时间点按成交额排名选取前 self.top_n 活跃币种，求 score 平均即 Y 指数
        - 计算不同窗口的移动平均
        返回: 计算完成的 DataFrame（统一通过 self.save_csv 保存）
        """
        if not isinstance(df_dict, dict) or len(df_dict) == 0:
            self.warn('y_index.process_data - df_dict 为空')
            return pd.DataFrame()
        # 分币种预处理：score 与 成交额（用于活跃筛选）
        per_symbol = {}
        for symbol, _df in df_dict.items():
            try:
                d = _df.copy()
                d['candle_begin_time'] = pd.to_datetime(d['candle_begin_time'])
                d = d.sort_values('candle_begin_time')
                d['ret_1d'] = d['close'].pct_change(1)
                d['vol_scaled'] = (d['volume'] - d['volume'].rolling(7, min_periods=1).mean()) / (d['volume'].rolling(7, min_periods=1).std() + 1e-9)
                d['score'] = d['ret_1d'] * 0.6 + d['vol_scaled'] * 0.4
                if interval == '1h':
                    d['成交额'] = d['quote_volume'].rolling(24 * 2, min_periods=1).sum()
                else:
                    d['成交额'] = d['quote_volume'].rolling(2, min_periods=1).sum()
                per_symbol[symbol] = d[['candle_begin_time', 'score', '成交额']]
            except Exception as e:
                self.warn(f'{symbol} 计算 score 失败: {e}')
        if len(per_symbol) == 0:
            return pd.DataFrame()
        # 统一时间索引
        all_times = pd.to_datetime(pd.unique(pd.concat([v['candle_begin_time'] for v in per_symbol.values()]).values))
        all_times = pd.Series(all_times).sort_values().values
        rows = []
        for ts in all_times:
            # 汇总该时刻各币种数据
            snapshot = []
            for symbol, d in per_symbol.items():
                row = d[d['candle_begin_time'] == ts]
                if len(row) > 0:
                    snapshot.append({'symbol': symbol, 'score': float(row['score'].iloc[0]), '成交额': float(row['成交额'].iloc[0])})
            if len(snapshot) == 0:
                continue
            snap_df = pd.DataFrame(snapshot)
            # 选取前 self.top_n 活跃币种
            snap_df['成交额排名'] = snap_df['成交额'].rank(ascending=False, method='first')
            active = snap_df[snap_df['成交额排名'] <= self.top_n]
            if len(active) == 0:
                continue
            y_index = active['score'].mean()
            rows.append({'candle_begin_time': ts, 'Y指数': y_index})
        result = pd.DataFrame(rows).sort_values('candle_begin_time')
        # 计算窗口移动平均
        for w in windows:
            result[f'Y指数_MA{w}'] = result['Y指数'].rolling(w, min_periods=1).mean()
        # 起始过滤
        if start_time is not None and not result.empty:
            result = result[result['candle_begin_time'] > pd.to_datetime(start_time)]
        # 统一保存与日志
        self.save_csv(result)
        if not result.empty:
            self.log(result.tail().to_string())
        return result

    def draw_index(self, title, windows, df):
        """
        绘制并保存 Y 指数图（统一签名/统一保存路径）
        - 输出路径统一使用 self.png_path()
        """
        if df is None or df.empty:
            self.warn('draw_index - 数据为空，跳过绘图')
            return
        fig = plt.figure(figsize=(16, 9), dpi=100)
        ax = fig.add_subplot(111)
        ax.plot(df['candle_begin_time'], df['Y指数'], label='Y指数', color='blue')
        for w in windows:
            col = f'Y指数_MA{w}'
            if col in df.columns:
                ax.plot(df['candle_begin_time'], df[col], label=f'MA{w}', alpha=0.7)
        ax.legend(loc='best')
        ax.grid(True, linestyle='--', alpha=0.3)
        ax.set_title(title)
        plt.tight_layout()
        plt.savefig(self.png_path(), bbox_inches='tight')
        plt.close('all')
