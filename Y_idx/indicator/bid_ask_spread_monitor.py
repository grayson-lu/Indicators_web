'''
盘口价差监控指标
Bid-Ask Spread Monitor
监控市场流动性和交易成本
通过买卖价差分析市场微观结构
'''
import os

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

# 设置matplotlib使用非交互式后端，避免线程问题

# 已移除data目录创建，统一由 BaseIndicator 管理

class 盘口价差监控(BaseIndicator):

    def indicator_slug(self) -> str:
        """
        指标保存文件前缀
        """
        return 'bid_ask_spread'

    def indicator_title(self) -> str:
        """
        指标图表标题
        """
        return '盘口价差监控指标'

    def process_data(self, df_dict, windows, backdays, interval, start_time):
        """
        处理数据计算盘口价差监控指标
        参数:
        - df_dict: 币种到K线DataFrame的映射
        - windows: 计算窗口列表（如 [1,7,30]）
        - backdays: 回溯天数（保留原签名）
        - interval: 时间粒度（'1d' 或 '1h'）
        - start_time: 起始筛选时间
        返回:
        - final_df: 市场层面的价差统计汇总
        说明:
        - 保持原有计算逻辑不变
        - 活跃筛选统一使用 self.top_n 的成交额排名过滤
        - 使用 self.warn/self.log 输出日志
        """
        # 全币种数据合成一个df
        df_list = []
        for symbol in df_dict:
            df = df_dict[symbol]
            df_list.append(df)
        # 修复：检查 df_list 并正确 concat
        if not df_list:
            self.warn("bid_ask_spread_monitor.process_data - 初次汇总时 df_list 为空，返回空DataFrame")
            return pd.DataFrame()
        all_df = pd.concat(df_list)
        all_df.reset_index(inplace=True)

        # 按币种分组计算价差相关指标
        df_list = []
        for symbol, _df in all_df.groupby('symbol'):
            # 模拟买卖价差（使用高低价差作为近似）
            _df['bid_ask_spread'] = _df['high'] - _df['low']
            _df['mid_price'] = (_df['high'] + _df['low']) / 2
            
            # 计算相对价差（价差/中间价）
            _df['relative_spread'] = _df['bid_ask_spread'] / _df['mid_price']
            
            # 计算价差波动率
            _df['spread_volatility'] = _df['relative_spread'].rolling(7).std()
            
            # 计算各窗口期的价差指标
            for window in windows:
                # 平均相对价差
                _df[f'avg_relative_spread_{window}d'] = _df['relative_spread'].rolling(window).mean()
                
                # 价差标准差
                _df[f'spread_std_{window}d'] = _df['relative_spread'].rolling(window).std()
                
                # 价差变异系数
                _df[f'spread_cv_{window}d'] = _df[f'spread_std_{window}d'] / _df[f'avg_relative_spread_{window}d']
                
                # 最大价差
                _df[f'max_spread_{window}d'] = _df['relative_spread'].rolling(window).max()
                
                # 最小价差
                _df[f'min_spread_{window}d'] = _df['relative_spread'].rolling(window).min()
                
                # 价差趋势（价差变化率）
                _df[f'spread_trend_{window}d'] = _df[f'avg_relative_spread_{window}d'].pct_change()
                
                # 流动性评分（价差越小，流动性越好）
                _df[f'liquidity_score_{window}d'] = 1 / (1 + _df[f'avg_relative_spread_{window}d'] * 1000)
            
            # 添加成交额统计
            if interval == '1h':
                _df['成交额'] = _df['quote_volume'].rolling(24 * 7, min_periods=1).sum()
            elif interval == '1d':
                _df['成交额'] = _df['quote_volume'].rolling(7, min_periods=1).sum()
            
            df_list.append(_df)
        # 修复：检查 df_list 并正确 concat
        if not df_list:
            self.warn("bid_ask_spread_monitor.process_data - 分币种计算后 df_list 为空，返回空DataFrame")
            return pd.DataFrame()
        all_df = pd.concat(df_list)
        all_df.reset_index(inplace=True)

        # 计算市场整体价差监控指标
        dfs = []
        for candle_begin_time, _df in all_df.groupby('candle_begin_time'):
            _df = _df.copy()

            # 过滤成交额前n的币种
            _df['成交额排名'] = _df['成交额'].rank(ascending=False, method='first')
            _df = _df[_df['成交额排名'] <= self.top_n]
            
            if len(_df) == 0:
                continue

            row = {'candle_begin_time': candle_begin_time}
            row['币种数量'] = len(_df)
            
            for window in windows:
                # 市场平均价差指标
                valid_spread = _df[f'avg_relative_spread_{window}d'].dropna()
                valid_std = _df[f'spread_std_{window}d'].dropna()
                valid_cv = _df[f'spread_cv_{window}d'].dropna()
                valid_liquidity = _df[f'liquidity_score_{window}d'].dropna()
                
                if len(valid_spread) > 0:
                    # 市场平均相对价差
                    row[f'市场平均价差_{window}d'] = valid_spread.mean() * 10000  # 转换为基点
                    row[f'市场价差中位数_{window}d'] = valid_spread.median() * 10000
                    
                    # 市场价差波动性
                    row[f'市场价差标准差_{window}d'] = valid_std.mean() * 10000
                    row[f'市场价差变异系数_{window}d'] = valid_cv.mean()
                    
                    # 市场流动性评分
                    row[f'市场流动性评分_{window}d'] = valid_liquidity.mean() * 100
                    
                    # 价差分布统计
                    high_spread_count = len(_df[_df[f'avg_relative_spread_{window}d'] > valid_spread.quantile(0.75)])
                    low_spread_count = len(_df[_df[f'avg_relative_spread_{window}d'] < valid_spread.quantile(0.25)])
                    
                    row[f'高价差币种数_{window}d'] = high_spread_count
                    row[f'低价差币种数_{window}d'] = low_spread_count
                    row[f'高价差币种占比_{window}d'] = (high_spread_count / len(_df)) * 100
                    row[f'低价差币种占比_{window}d'] = (low_spread_count / len(_df)) * 100
                    
                    # 流动性等级分布
                    excellent_liquidity = len(_df[_df[f'liquidity_score_{window}d'] > 0.8])
                    good_liquidity = len(_df[(_df[f'liquidity_score_{window}d'] > 0.6) & (_df[f'liquidity_score_{window}d'] <= 0.8)])
                    poor_liquidity = len(_df[_df[f'liquidity_score_{window}d'] <= 0.6])
                    
                    row[f'优秀流动性币种数_{window}d'] = excellent_liquidity
                    row[f'良好流动性币种数_{window}d'] = good_liquidity
                    row[f'较差流动性币种数_{window}d'] = poor_liquidity
                    
                    row[f'优秀流动性占比_{window}d'] = (excellent_liquidity / len(_df)) * 100
                    row[f'良好流动性占比_{window}d'] = (good_liquidity / len(_df)) * 100
                    row[f'较差流动性占比_{window}d'] = (poor_liquidity / len(_df)) * 100
                    
                    # 市场流动性状态
                    avg_spread_bp = valid_spread.mean() * 10000
                    row[f'市场流动性状态_{window}d'] = self.get_liquidity_status(avg_spread_bp)
                    
                    # 价差风险等级
                    spread_risk = valid_std.mean() * 10000
                    row[f'价差风险等级_{window}d'] = self.get_spread_risk_level(spread_risk)
                    
                    # 交易成本指标
                    row[f'平均交易成本_{window}d'] = valid_spread.mean() * 10000 / 2  # 单边成本
                    
                else:
                    # 填充默认值
                    for col in [f'市场平均价差_{window}d', f'市场价差中位数_{window}d', 
                               f'市场价差标准差_{window}d', f'市场价差变异系数_{window}d',
                               f'市场流动性评分_{window}d', f'高价差币种数_{window}d',
                               f'低价差币种数_{window}d', f'高价差币种占比_{window}d',
                               f'低价差币种占比_{window}d', f'平均交易成本_{window}d']:
                        row[col] = np.nan
                    row[f'市场流动性状态_{window}d'] = "无数据"
                    row[f'价差风险等级_{window}d'] = "无数据"
            
            dfs.append(pd.DataFrame([row]))

        final_df = pd.concat(dfs, ignore_index=True)
        
        if start_time is not None:
            final_df = final_df[final_df['candle_begin_time'] > start_time]

        return final_df

    def draw_index(self, title, windows, equity_df):
        """
        绘制盘口价差监控指标图
        参数:
        - title: 图表标题
        - windows: 计算窗口列表（如 [1,7,30]）
        - equity_df: 指标结果数据表
        说明:
        - 上图展示市场平均价差，中图展示流动性评分，下图展示流动性质量分布
        - 统一使用 self.png_path() 保存图表
        """
        fig = plt.figure(tight_layout=False, figsize=(32, 16), dpi=80, facecolor='w', edgecolor='k')
        gs = gridspec.GridSpec(30, 12)
        
        # 上图：市场平均价差
        ax1 = fig.add_subplot(gs[0:8, 0:11])
        for window in windows:
            ax1.plot(equity_df['candle_begin_time'], equity_df[f'市场平均价差_{window}d'], 
                    label=f'平均价差_{window}d')
        
        ax1.axhline(y=50, color='r', linestyle=':', alpha=0.7, label='极差流动性(50bp)')
        ax1.axhline(y=20, color='orange', linestyle=':', alpha=0.7, label='较差流动性(20bp)')
        ax1.axhline(y=10, color='yellow', linestyle=':', alpha=0.7, label='一般流动性(10bp)')
        ax1.axhline(y=5, color='gray', linestyle='-', alpha=0.5, label='良好流动性(5bp)')
        
        ax1.set_ylabel('价差 (基点)')
        ax1.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        ax1.grid(True, linestyle='--', alpha=0.3)
        ax1.set_title('市场平均买卖价差', fontsize='medium', fontweight='bold')

        # 中图：流动性评分
        ax2 = fig.add_subplot(gs[10:18, 0:11])
        for window in windows:
            ax2.plot(equity_df['candle_begin_time'], equity_df[f'市场流动性评分_{window}d'], 
                    label=f'流动性评分_{window}d')
        
        ax2.axhline(y=80, color='g', linestyle=':', alpha=0.7, label='优秀流动性(80)')
        ax2.axhline(y=60, color='yellow', linestyle=':', alpha=0.7, label='良好流动性(60)')
        ax2.axhline(y=40, color='orange', linestyle=':', alpha=0.7, label='一般流动性(40)')
        ax2.axhline(y=20, color='r', linestyle=':', alpha=0.7, label='较差流动性(20)')
        
        ax2.set_ylabel('流动性评分')
        ax2.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        ax2.grid(True, linestyle='--', alpha=0.3)
        ax2.set_title('市场流动性评分', fontsize='medium', fontweight='bold')

        # 下图：流动性分布
        ax3 = fig.add_subplot(gs[20:28, 0:11])
        for window in windows:
            ax3.plot(equity_df['candle_begin_time'], equity_df[f'优秀流动性占比_{window}d'], 
                    label=f'优秀流动性占比_{window}d', color='green')
            ax3.plot(equity_df['candle_begin_time'], equity_df[f'较差流动性占比_{window}d'], 
                    label=f'较差流动性占比_{window}d', color='red', linestyle='--')
        
        ax3.set_ylabel('占比 (%)')
        ax3.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        ax3.grid(True, linestyle='--', alpha=0.3)
        ax3.set_title('流动性质量分布', fontsize='medium', fontweight='bold')
        
        plt.xticks(rotation=30)
        plt.tight_layout()
        plt.savefig(self.png_path(), bbox_inches='tight')
        plt.clf()
        plt.cla()
        plt.close('all')


# 已移除脚本入口（统一从框架调用）