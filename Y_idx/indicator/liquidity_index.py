'''
市场流动性指数
监控加密货币市场的整体流动性情况
'''
import pandas as pd
import numpy as np

pd.set_option('display.unicode.ambiguous_as_wide', True)
pd.set_option('display.unicode.east_asian_width', True)
pd.set_option('display.max_rows', 500)  # 最多显示数据的行数
pd.set_option('display.max_columns', 500)  # 最多显示数据的列数
pd.set_option('display.width', 180)  # 设置打印宽度(**重要**)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False
from indicator.base_indicator import BaseIndicator

class 市场流动性(BaseIndicator):

    def stat(self, acc:str, backdays=365, windows = [30], save_img = True, interval = '1d', start_time = None):
        """
        统计市场流动性（接入基类）
        参数:
        - acc: 账户标识
        - backdays: 回溯天数
        - windows: 窗口列表
        - save_img: 是否保存图像
        - interval: 周期 '1d' 或 '1h'
        - start_time: 起始时间过滤
        行为:
        - 委托基类统一拉取数据与保存CSV
        - 返回计算后的结果DataFrame
        """
        return super().stat(acc=acc, backdays=backdays, windows=windows, save_img=save_img, interval=interval, start_time=start_time)

    def stat_with_data(self, df_dict, acc:str, start_time=None, backdays=365, windows=[30], save_img=True, interval='1d'):
        """
        使用已有数据统计市场流动性（接入基类）
        参数:
        - df_dict: 预先获取的K线数据
        - 其余同 stat
        行为:
        - 委托基类统一保存CSV与绘图
        """
        return super().stat_with_data(df_dict=df_dict, acc=acc, start_time=start_time, backdays=backdays, windows=windows, save_img=save_img, interval=interval)

    def process_data(self, df_dict, windows, backdays, interval, start_time):
        """
        处理数据计算市场流动性（统一签名）
        参数:
        - df_dict: 所有交易对的K线数据字典
        - windows: 统计窗口列表
        - backdays: 回溯天数（未直接使用）
        - interval: 周期 '1d' 或 '1h'
        - start_time: 起始时间过滤
        返回:
        - 计算完成的 DataFrame（不负责保存，由基类处理）
        """
        df_list = []
        for symbol in df_dict:
            df = df_dict[symbol]
            df_list.append(df)
        if not df_list:
            self.warn("liquidity_index.process_data - 初次汇总 df_list 为空")
            return pd.DataFrame()
        all_df = pd.concat(df_list)
        all_df.reset_index(inplace=True)

        df_list = []
        for symbol, _df in all_df.groupby('symbol'):
            _df['daily_return'] = _df['close'].pct_change()
            _df['daily_return_abs'] = _df['daily_return'].abs()
            _df['norm_volume'] = _df['quote_volume'] / _df['close']
            for window in windows:
                _df[f'price_volatility_{window}d'] = _df['daily_return'].rolling(window).std()
                _df[f'avg_norm_volume_{window}d'] = _df['norm_volume'].rolling(window).mean()
                _df[f'liquidity_index1_{window}d'] = _df[f'price_volatility_{window}d'] / _df[f'avg_norm_volume_{window}d']
                _df[f'liquidity_index2_{window}d'] = (_df['high'] - _df['low']) / _df['norm_volume']
            if interval == '1h':
                _df['成交额'] = _df['quote_volume'].rolling(24 * 7, min_periods=1).sum()
            elif interval == '1d':
                _df['成交额'] = _df['quote_volume'].rolling(7, min_periods=1).sum()
            df_list.append(_df)
        if not df_list:
            self.warn("liquidity_index.process_data - 分币种 df_list 为空")
            return pd.DataFrame()
        all_df = pd.concat(df_list)
        all_df.reset_index(inplace=True)

        dfs = []
        for candle_begin_time, _df in all_df.groupby('candle_begin_time'):
            _df = _df.copy()
            _df['成交额排名'] = _df['成交额'].rank(ascending=False, method='first')
            _df = _df[_df['成交额排名'] <= self.top_n]
            if len(_df) == 0:
                continue
            row = {'candle_begin_time': candle_begin_time, '市场总成交量': _df['quote_volume'].sum()}
            for window in windows:
                liq_col1 = f'liquidity_index1_{window}d'
                _df[liq_col1] = _df[liq_col1].replace([np.inf, -np.inf], np.nan)
                avg_liquidity1 = _df[liq_col1].mean(); median_liquidity1 = _df[liq_col1].median()
                row[f'流动性指数1_均值_{window}d'] = avg_liquidity1
                row[f'流动性指数1_中位数_{window}d'] = median_liquidity1
                liq_col2 = f'liquidity_index2_{window}d'
                _df[liq_col2] = _df[liq_col2].replace([np.inf, -np.inf], np.nan)
                avg_liquidity2 = _df[liq_col2].mean(); median_liquidity2 = _df[liq_col2].median()
                row[f'流动性指数2_均值_{window}d'] = avg_liquidity2
                row[f'流动性指数2_中位数_{window}d'] = median_liquidity2
                market_depth = _df['quote_volume'].sum() / _df[f'price_volatility_{window}d'].mean() if not pd.isna(_df[f'price_volatility_{window}d'].mean()) and _df[f'price_volatility_{window}d'].mean() != 0 else np.nan
                row[f'市场深度指数_{window}d'] = market_depth
                if not pd.isna(avg_liquidity1) and avg_liquidity1 != 0:
                    row[f'综合流动性指数_{window}d'] = 1 / avg_liquidity1
                else:
                    row[f'综合流动性指数_{window}d'] = np.nan
            dfs.append(pd.DataFrame([row]))
        final_df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
        for window in windows:
            col = f'综合流动性指数_{window}d'
            if not final_df.empty:
                max_val = final_df[col].max(); min_val = final_df[col].min()
                if max_val != min_val and not pd.isna(max_val) and not pd.isna(min_val):
                    final_df[col] = (final_df[col] - min_val) / (max_val - min_val) * 100
        if start_time is not None and not final_df.empty:
            final_df = final_df[final_df['candle_begin_time'] > start_time]
        return final_df

    def draw_index(self, title, windows, equity_df):
        """
        绘制流动性曲线图并保存到统一路径
        参数:
        - title: 图表标题
        - windows: 窗口列表
        - equity_df: 指标结果数据
        """
        fig = plt.figure(tight_layout=False, figsize=(32, 8), dpi=80, facecolor='w', edgecolor='k')
        gs = gridspec.GridSpec(10, 12)
        ax = fig.add_subplot(gs[0:10, 0:11])
        for window in windows:
            ax.plot(equity_df['candle_begin_time'], equity_df[f'综合流动性指数_{window}d'], label=f'综合流动性指数_{window}d')
        ax.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        plt.xticks(rotation=30); plt.grid(True, linestyle='--', alpha=0.3)
        plt.title(title, fontsize='large', fontweight='bold', color='blue', loc='center')
        plt.tight_layout(); plt.savefig(self.png_path(), bbox_inches='tight')
        plt.clf(); plt.cla(); plt.close('all')


if __name__ == '__main__':
    liquidity_index = 市场流动性()
    df = liquidity_index.stat(
        acc = 'qqdev', 
        start_time='2021-01-01',
        backdays=1200,
        windows = [7, 30, 90],
        save_img=True
    )
