'''
Y指数综合指标
整合 Y 指数、资金费率、稳定币供应量、成交量等关键指标
统一基类签名、日志与保存路径
'''
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

from .base_indicator import BaseIndicator
from .funding_rate_monitor import 全市场资金费率监控
from .stablecoin_supply_monitor import 链上稳定币总供应量

pd.set_option('display.unicode.ambiguous_as_wide', True)
pd.set_option('display.unicode.east_asian_width', True)
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 180)


class Y指数综合指标(BaseIndicator):
    def indicator_slug(self) -> str:
        """
        返回统一保存前缀（CSV/PNG 文件名使用）
        """
        return 'y_composite_index'

    def indicator_title(self) -> str:
        """
        返回统一的图表标题
        """
        return 'Y指数综合指标'

    def stat(self, acc: str, backdays=365, windows=[1, 7, 30], interval='1d', start_time=None):
        """
        统计综合指标（接入基类统一入口）
        参数:
        - acc/backdays/windows/interval/start_time 同基类约定
        返回: 指标结果 DataFrame
        """
        # 基类统一拉取 df_dict 并回调 process_data
        return super().stat(acc=acc, backdays=backdays, windows=windows, save_img=True, interval=interval, start_time=start_time)

    def stat_with_data(self, df_dict, acc: str, start_time=None, backdays=365, windows=[1, 7, 30], interval='1d'):
        """
        使用已有数据统计综合指标（接入基类统一入口）
        参数同 stat
        返回: 指标结果 DataFrame
        """
        return super().stat_with_data(df_dict=df_dict, acc=acc, start_time=start_time, backdays=backdays, windows=windows, save_img=True, interval=interval)

    def process_data(self, df_dict, windows, backdays, interval, start_time):
        """
        处理数据并计算综合指标（统一签名）
        步骤:
        - 计算基础 Y 指数（基于收益和成交量缩放）
        - 计算资金费率指标（复用已重构模块）
        - 计算稳定币供应量指标（复用已重构模块）
        - 合并为综合 DataFrame 并保存
        """
        if not isinstance(df_dict, dict) or len(df_dict) == 0:
            self.warn('y_composite.process_data - df_dict 为空')
            return pd.DataFrame()
        # 1. 基础 Y 指数
        y_index_df = self._calc_y_index(df_dict, windows, interval)
        # 2. 资金费率（8h 数据）
        funding_monitor = 全市场资金费率监控()
        funding_df = funding_monitor.process_data(df_dict, windows, backdays, '8h', start_time)
        # 3. 稳定币供应量（1d 数据）
        stable_monitor = 链上稳定币总供应量()
        stable_df = stable_monitor.process_data(df_dict, windows, backdays, '1d', start_time)
        # 4. 合并
        final_df = self._integrate(y_index_df, funding_df, stable_df)
        # 起始过滤
        if start_time is not None and not final_df.empty:
            final_df = final_df[final_df['candle_begin_time'] > pd.to_datetime(start_time)]
        # 统一保存与日志
        self.save_csv(final_df)
        if not final_df.empty:
            self.log(final_df.tail().to_string())
        return final_df

    def draw_index(self, title, windows, df):
        """
        绘制并保存综合指标图（统一签名/统一保存路径）
        子图:
        - Y 指数与其均线
        - 资金费率总和
        - 稳定币总供应量(十亿)
        """
        if df is None or df.empty:
            self.warn('draw_index - 数据为空，跳过绘图')
            return
        fig, axes = plt.subplots(3, 1, figsize=(16, 12), sharex=True)
        # 1 Y 指数
        axes[0].plot(df['candle_begin_time'], df['Y指数'], label='Y指数', color='tab:blue')
        for w in windows:
            col = f'Y指数_MA{w}'
            if col in df.columns:
                axes[0].plot(df['candle_begin_time'], df[col], label=f'MA{w}', alpha=0.7)
        axes[0].set_title(title); axes[0].legend(loc='best'); axes[0].grid(True, alpha=0.3)
        # 2 资金费率
        if '资金费率总和' in df.columns:
            axes[1].plot(df['candle_begin_time'], df['资金费率总和'], label='资金费率总和', color='tab:orange')
            axes[1].axhline(y=0, color='k', linestyle='--', alpha=0.5)
            axes[1].set_title('资金费率'); axes[1].legend(loc='best'); axes[1].grid(True, alpha=0.3)
        # 3 稳定币供应量(十亿)
        if 'total_supply_billion' in df.columns:
            axes[2].plot(df['candle_begin_time'], df['total_supply_billion'], label='稳定币总供应量(十亿)', color='tab:green')
            axes[2].set_title('稳定币总供应量'); axes[2].legend(loc='best'); axes[2].grid(True, alpha=0.3)
        plt.xticks(rotation=30)
        plt.tight_layout()
        plt.savefig(self.png_path(), bbox_inches='tight')
        plt.close()

    # 内部方法
    def _calc_y_index(self, df_dict, windows, interval):
        """
        计算基础 Y 指数：收益与成交量缩放合成
        返回: DataFrame[candle_begin_time, Y指数, Y指数_MA{w}...]
        """
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
        all_times = pd.to_datetime(pd.unique(pd.concat([v['candle_begin_time'] for v in per_symbol.values()]).values))
        all_times = pd.Series(all_times).sort_values().values
        rows = []
        for ts in all_times:
            snapshot = []
            for symbol, d in per_symbol.items():
                row = d[d['candle_begin_time'] == ts]
                if len(row) > 0:
                    snapshot.append({'symbol': symbol, 'score': float(row['score'].iloc[0]), '成交额': float(row['成交额'].iloc[0])})
            if len(snapshot) == 0:
                continue
            snap_df = pd.DataFrame(snapshot)
            snap_df['成交额排名'] = snap_df['成交额'].rank(ascending=False, method='first')
            active = snap_df[snap_df['成交额排名'] <= self.top_n]
            if len(active) == 0:
                continue
            y_index = active['score'].mean()
            rows.append({'candle_begin_time': ts, 'Y指数': y_index})
        result = pd.DataFrame(rows).sort_values('candle_begin_time')
        for w in windows:
            result[f'Y指数_MA{w}'] = result['Y指数'].rolling(w, min_periods=1).mean()
        return result

    def _integrate(self, y_df, funding_df, stable_df):
        """
        合并各指标为综合表
        列选择：Y指数、资金费率总和、稳定币总供应量(十亿)
        """
        df = y_df.copy()
        if not df.empty and funding_df is not None and not funding_df.empty:
            df = df.merge(funding_df[['candle_begin_time', '资金费率总和']], on='candle_begin_time', how='left')
        if not df.empty and stable_df is not None and not stable_df.empty:
            df = df.merge(stable_df[['candle_begin_time', 'total_supply_billion']], on='candle_begin_time', how='left')
        return df
