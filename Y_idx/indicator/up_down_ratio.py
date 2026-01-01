'''
涨跌比重指标
统计市场中上涨和下跌币种的比重分布
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


# 已移除data目录创建，统一由 BaseIndicator 管理

class 涨跌比重(BaseIndicator):

    def indicator_slug(self) -> str:
        """
        保存前缀：up_down_ratio
        """
        return 'up_down_ratio'

    def indicator_title(self) -> str:
        """
        图表标题
        """
        return '涨跌比重指标'

    def stat(self, acc: str, backdays=365, windows=[1, 7, 30], save_img=True, interval='1d', start_time=None):
        """
        统计入口（继承基类）
        """
        return super().stat(acc, backdays, windows, save_img, interval, start_time)

    def stat_with_data(self, df_dict, acc: str, start_time=None, backdays=365, windows=[1, 7, 30], save_img=True, interval='1d'):
        """
        复用数据入口（继承基类）
        """
        return super().stat_with_data(df_dict, acc, start_time, backdays, windows, save_img, interval)

    def process_data(self, df_dict, windows, backdays, interval, start_time):
        """
        处理数据并计算涨跌比重指标
        参数:
        - df_dict: 币种到K线DataFrame的映射
        - windows: 窗口期列表（如 [1,7,30]）
        - backdays: 回溯天数（保留原签名）
        - interval: 时间粒度（'1d' 或 '1h'）
        - start_time: 起始筛选时间
        返回:
        - final_df: 包含各窗口涨跌分布与统计的DataFrame
        说明:
        - 保持原有计算逻辑不变
        - 活跃筛选统一使用 self.top_n 的成交额排名过滤
        - 使用 self.warn/self.log 输出日志
        """
        df_list = []
        for symbol in df_dict:
            df = df_dict[symbol]
            df_list.append(df)
        if not df_list:
            self.warn("up_down_ratio.process_data - 初次汇总 df_list 为空")
            return pd.DataFrame()
        all_df = pd.concat(df_list)
        all_df.reset_index(inplace=True)

        df_list = []
        for symbol, _df in all_df.groupby('symbol'):
            for window in windows:
                if window == 1:
                    _df[f'return_{window}d'] = _df['close'].pct_change()
                else:
                    _df[f'return_{window}d'] = _df['close'].pct_change(window)
                _df[f'return_category_{window}d'] = _df[f'return_{window}d'].apply(lambda x: self.categorize_return(x))
            if interval == '1h':
                _df['成交额'] = _df['quote_volume'].rolling(24 * 7, min_periods=1).sum()
            elif interval == '1d':
                _df['成交额'] = _df['quote_volume'].rolling(7, min_periods=1).sum()
            df_list.append(_df)
        if not df_list:
            self.warn("up_down_ratio.process_data - 分币种计算后 df_list 为空")
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
            row = {'candle_begin_time': candle_begin_time}
            row['总币种数量'] = len(_df)
            for window in windows:
                categories = ['大涨', '中涨', '小涨', '横盘', '小跌', '中跌', '大跌']
                category_counts = _df[f'return_category_{window}d'].value_counts()
                total_count = len(_df)
                for category in categories:
                    count = category_counts.get(category, 0)
                    percentage = (count / total_count) * 100 if total_count > 0 else 0
                    row[f'{category}数量_{window}d'] = count
                    row[f'{category}比重_{window}d'] = percentage
                up_count = category_counts.get('大涨', 0) + category_counts.get('中涨', 0) + category_counts.get('小涨', 0)
                down_count = category_counts.get('大跌', 0) + category_counts.get('中跌', 0) + category_counts.get('小跌', 0)
                flat_count = category_counts.get('横盘', 0)
                row[f'上涨总数_{window}d'] = up_count
                row[f'下跌总数_{window}d'] = down_count
                row[f'横盘总数_{window}d'] = flat_count
                row[f'上涨比重_{window}d'] = (up_count / total_count) * 100 if total_count > 0 else 0
                row[f'下跌比重_{window}d'] = (down_count / total_count) * 100 if total_count > 0 else 0
                row[f'横盘比重_{window}d'] = (flat_count / total_count) * 100 if total_count > 0 else 0
                row[f'涨跌比率_{window}d'] = up_count / down_count if down_count > 0 else np.inf
                row[f'市场情绪_{window}d'] = self.get_market_sentiment(up_count, down_count, total_count)
                valid_returns = _df[f'return_{window}d'].dropna()
                if len(valid_returns) > 0:
                    row[f'平均涨跌幅_{window}d'] = valid_returns.mean() * 100
                    row[f'涨跌幅标准差_{window}d'] = valid_returns.std() * 100
                    row[f'涨跌幅偏度_{window}d'] = valid_returns.skew()
                else:
                    row[f'平均涨跌幅_{window}d'] = 0
                    row[f'涨跌幅标准差_{window}d'] = 0
                    row[f'涨跌幅偏度_{window}d'] = 0
            dfs.append(pd.DataFrame([row]))
        final_df = pd.concat(dfs, ignore_index=True)
        if start_time is not None:
            final_df = final_df[final_df['candle_begin_time'] > start_time]
        return final_df

    def categorize_return(self, r: float) -> str:
        """
        将涨跌幅划分为七档类别
        返回: '大涨'/'中涨'/'小涨'/'横盘'/'小跌'/'中跌'/'大跌'
        说明: 保持原阈值逻辑（示例：>=10%为大涨，<=-10%为大跌等）
        """
        if pd.isna(r):
            return '横盘'
        if r >= 0.1:
            return '大涨'
        elif r >= 0.05:
            return '中涨'
        elif r > 0.0:
            return '小涨'
        elif r <= -0.1:
            return '大跌'
        elif r <= -0.05:
            return '中跌'
        elif r < 0.0:
            return '小跌'
        else:
            return '横盘'

    def get_market_sentiment(self, up_count, down_count, total_count):
        """
        根据涨跌比重获取市场情绪（函数级注释）
        """
        up_ratio = up_count / total_count if total_count > 0 else 0
        if up_ratio > 0.7:
            return '极度乐观'
        elif up_ratio > 0.6:
            return '乐观'
        elif up_ratio > 0.4:
            return '中性'
        elif up_ratio > 0.3:
            return '悲观'
        else:
            return '极度悲观'

    def draw_index(self, title, windows, equity_df):
        """
        绘制涨跌比重指标图表
        参数:
        - title: 图表标题
        - windows: 计算窗口列表（如 [1,7,30]）
        - equity_df: 指标结果数据表
        说明:
        - 统一使用 self.png_path() 保存图表
        - 上图展示上涨/下跌比重曲线；中图展示涨跌比率；统一阈值线标注
        """
        import matplotlib.gridspec as gridspec
        fig = plt.figure(tight_layout=False, figsize=(32, 12), dpi=80, facecolor='w', edgecolor='k')
        gs = gridspec.GridSpec(20, 12)
        ax1 = fig.add_subplot(gs[0:8, 0:11])
        for window in windows:
            ax1.plot(equity_df['candle_begin_time'], equity_df[f'上涨比重_{window}d'], label=f'上涨比重_{window}d')
            ax1.plot(equity_df['candle_begin_time'], equity_df[f'下跌比重_{window}d'], label=f'下跌比重_{window}d', linestyle='--')
        ax1.axhline(y=70, color='g', linestyle=':', alpha=0.7, label='强势线(70%)')
        ax1.axhline(y=50, color='gray', linestyle='-', alpha=0.5, label='平衡线(50%)')
        ax1.axhline(y=30, color='r', linestyle=':', alpha=0.7, label='弱势线(30%)')
        ax1.set_ylabel('比重 (%)')
        ax1.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        ax1.grid(True, linestyle='--', alpha=0.3)
        ax1.set_title('市场涨跌比重分布', fontsize='medium', fontweight='bold')
        ax2 = fig.add_subplot(gs[10:18, 0:11])
        for window in windows:
            ratio_data = equity_df[f'涨跌比率_{window}d'].replace([np.inf, -np.inf], np.nan)
            ax2.plot(equity_df['candle_begin_time'], ratio_data, label=f'涨跌比率_{window}d')
        ax2.axhline(y=2, color='g', linestyle=':', alpha=0.7, label='强势线(2.0)')
        ax2.axhline(y=1, color='gray', linestyle='-', alpha=0.5, label='平衡线(1.0)')
        ax2.axhline(y=0.5, color='r', linestyle=':', alpha=0.7, label='弱势线(0.5)')
        ax2.set_ylabel('涨跌比率')
        ax2.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        ax2.grid(True, linestyle='--', alpha=0.3)
        ax2.set_title('市场涨跌比率', fontsize='medium', fontweight='bold')
        plt.xticks(rotation=30)
        plt.tight_layout()
        plt.savefig(self.png_path(), bbox_inches='tight')
        plt.clf(); plt.cla(); plt.close('all')


# 已移除脚本入口（统一从框架调用）
