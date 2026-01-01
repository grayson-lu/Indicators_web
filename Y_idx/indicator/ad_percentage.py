'''
AD百分比指标
Advance/Decline Percentage
衡量上涨股票数量与下跌股票数量的比例
'''
import os
import yquant.common.binance_utils as binance
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime
from yquant.db.models.bn_account import BnAccount
from yquant.config.config import cfg
import yquant.common.common_utils as common
from .base_indicator import BaseIndicator

pd.set_option('display.unicode.ambiguous_as_wide', True)
pd.set_option('display.unicode.east_asian_width', True)
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 180)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
plt.rcParams['font.sans-serif'] = ['SimHei']  
plt.rcParams['axes.unicode_minus'] = False


class AD百分比(BaseIndicator):

    def indicator_slug(self) -> str:
        """
        重载保存前缀，统一文件名为 ad_percentage
        """
        return 'ad_percentage'

    def indicator_title(self) -> str:
        """
        图表标题
        """
        return 'AD百分比指标'

    def stat(self, acc: str, backdays=365, windows=[30], save_img=True, interval='1d', start_time=None):
        """
        统计AD百分比指标（继承基类入口）
        """
        return super().stat(acc, backdays, windows, save_img, interval, start_time)

    def stat_with_data(self, df_dict, acc: str, start_time=None, backdays=365, windows=[30], save_img=True, interval='1d'):
        """
        使用已获取的数据统计（继承基类入口）
        """
        return super().stat_with_data(df_dict, acc, start_time, backdays, windows, save_img, interval)

    def process_data(self, df_dict, windows, backdays, interval, start_time):
        # 原有实现保留（函数级注释已在文件中），此处仅签名对齐基类
        '''
        处理数据计算AD百分比指标
        核心逻辑:
        - 对每个窗口window计算N日涨跌幅: `return_{window}d`
        - 上涨判断: `return_{window}d > 0`，下跌判断: `< 0`
        - 在每个时间点，仅保留成交额排名前100的活跃币种以减少噪音
        - AD百分比定义为净涨跌百分比: `(上涨数-下跌数)/总数×100`
        - 市场强度判定: AD百分比>0为"偏多"，<0为"偏空"，=0为"平衡"
        输出列:
        - `AD百分比_{window}d`、`AD比率_{window}d`、`净上涨百分比_{window}d`等
        '''
        # 全币种数据合成一个df
        df_list = []
        for symbol in df_dict:
            df = df_dict[symbol]
            df_list.append(df)
        all_df = pd.concat(df_list)
        all_df.reset_index(inplace=True)

        df_list = []
        for symbol, _df in all_df.groupby('symbol'):
            _df['daily_return'] = _df['close'].pct_change()
            for window in windows:
                _df[f'return_{window}d'] = _df['close'].pct_change(window)
                _df[f'is_advance_{window}d'] = (_df[f'return_{window}d'] > 0).astype(int)
                _df[f'is_decline_{window}d'] = (_df[f'return_{window}d'] < 0).astype(int)
            if interval == '1h':
                _df['成交额'] = _df['quote_volume'].rolling(24 * 7, min_periods=1).sum()
            elif interval == '1d':
                _df['成交额'] = _df['quote_volume'].rolling(7, min_periods=1).sum()
            df_list.append(_df)
        all_df = pd.concat(df_list)
        all_df.reset_index(inplace=True)

        dfs = []
        for candle_begin_time, _df in all_df.groupby('candle_begin_time'):
            _df = _df.copy()
            _df['成交额排名'] = _df['成交额'].rank(ascending=False, method='first')
            _df = _df[_df['成交额排名'] <= self.top_n]
            if len(_df) == 0:
                continue
            row = {'candle_begin_time': candle_begin_time}
            total_symbols = len(_df)
            row['总币种数量'] = total_symbols
            for window in windows:
                advance_count = _df[f'is_advance_{window}d'].sum()
                decline_count = _df[f'is_decline_{window}d'].sum()
                unchanged_count = total_symbols - advance_count - decline_count
                ad_percentage = ((advance_count - decline_count) / total_symbols) * 100 if total_symbols > 0 else 0
                ad_ratio = advance_count / decline_count if decline_count > 0 else np.inf
                net_advance_percentage = ad_percentage
                row[f'上涨币种数_{window}d'] = advance_count
                row[f'下跌币种数_{window}d'] = decline_count
                row[f'横盘币种数_{window}d'] = unchanged_count
                row[f'AD百分比_{window}d'] = ad_percentage
                row[f'AD比率_{window}d'] = ad_ratio if ad_ratio != np.inf else advance_count
                row[f'净上涨百分比_{window}d'] = net_advance_percentage
                market_strength = "偏多" if ad_percentage > 0 else ("偏空" if ad_percentage < 0 else "平衡")
                row[f'市场强度_{window}d'] = market_strength
            dfs.append(pd.DataFrame([row]))
        final_df = pd.concat(dfs, ignore_index=True)
        if start_time is not None:
            final_df = final_df[final_df['candle_begin_time'] > start_time]
        return final_df

    def draw_index(self, title, windows, equity_df):
        """
        绘制 AD 百分比指标图表
        参数:
        - title: 图表标题
        - windows: 计算窗口列表（如 [7, 30]）
        - equity_df: 指标结果数据表（需包含 AD 百分比相关列）
        说明:
        - 使用统一的保存路径 `self.png_path()` 输出图片
        - 统一绘制 AD 百分比与净上涨百分比曲线，并标注阈值线
        """
        fig = plt.figure(tight_layout=False, figsize=(32, 8), dpi=80, facecolor='w', edgecolor='k')
        import matplotlib.gridspec as gridspec
        gs = gridspec.GridSpec(10, 12)
        ax = fig.add_subplot(gs[0:10, 0:11])
        for window in windows:
            ax.plot(equity_df['candle_begin_time'], equity_df[f'AD百分比_{window}d'], label=f'AD百分比_{window}d')
            ax.plot(equity_df['candle_begin_time'], equity_df[f'净上涨百分比_{window}d'], label=f'净上涨百分比_{window}d', linestyle='--')
        ax.axhline(y=50, color='r', linestyle=':', alpha=0.7, label='偏多阈值(+50%)')
        ax.axhline(y=0, color='gray', linestyle='-', alpha=0.7, label='平衡线(0%)')
        ax.axhline(y=-50, color='g', linestyle=':', alpha=0.7, label='偏空阈值(-50%)')
        ax.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        plt.xticks(rotation=30)
        plt.grid(True, linestyle='--', alpha=0.3)
        plt.title(title, fontsize='large', fontweight='bold', color='blue', loc='center')
        plt.tight_layout()
        plt.savefig(self.png_path(), bbox_inches='tight')
        plt.clf(); plt.cla(); plt.close('all')


# 已移除脚本入口（统一从框架调用）
