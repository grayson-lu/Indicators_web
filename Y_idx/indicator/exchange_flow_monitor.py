'''
交易所净流入流出监控指标
Exchange Flow Monitor
监控资金在交易所的流入流出情况
分析市场情绪和资金动向
'''
import os
import sys
# 修正：移除路径hack，依赖正常包结构
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
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


class ExchangeFlowMonitor(BaseIndicator):
    """
    交易所净流入流出监控指标类
    
    改进的算法逻辑：
    1. 基于成交量加权价格变化计算资金流向
    2. 使用多时间窗口平滑数据，减少噪音
    3. 结合市场深度和流动性指标
    4. 添加异常值检测和数据清洗
    """

    def indicator_slug(self) -> str:
        """
        指标保存文件前缀
        """
        return 'exchange_flow'

    def indicator_title(self) -> str:
        """
        指标图表标题
        """
        return '交易所净流入流出监控'

    def process_data(self, df_dict, windows=[1, 7, 30], backdays=365, interval='1d', start_time=None):
        '''
        处理数据计算交易所净流入流出指标
        
        改进的计算逻辑：
        1. 使用成交量加权平均价格(VWAP)计算资金流向
        2. 基于价格动量和成交量变化判断流入流出
        3. 添加数据平滑和异常值处理
        4. 使用相对强弱指标辅助判断
        '''
        # 全币种数据合成一个df
        df_list = []
        for symbol in df_dict:
            df = df_dict[symbol]
            if df is not None and not df.empty:
                df_list.append(df)
        
        if not df_list:
            self.warn("exchange_flow_monitor.process_data - 没有有效的数据")
            return pd.DataFrame()
            
        # 修复：直接 concat df_list
        all_df = pd.concat(df_list)
        all_df.reset_index(inplace=True)

        # 按币种分组计算流入流出指标
        df_list = []
        for symbol, _df in all_df.groupby('symbol'):
            if len(_df) < 30:  # 数据太少跳过
                continue
                
            _df = _df.copy().sort_values('candle_begin_time')
            
            # 基础指标计算
            _df['price_change'] = _df['close'].pct_change()
            _df['price_change_abs'] = _df['price_change'].abs()
            
            # 成交量相关指标
            _df['volume_ma_7'] = _df['volume'].rolling(7, min_periods=1).mean()
            _df['volume_ma_30'] = _df['volume'].rolling(30, min_periods=1).mean()
            _df['volume_ratio_7'] = _df['volume'] / (_df['volume_ma_7'] + 1e-10)
            _df['volume_ratio_30'] = _df['volume'] / (_df['volume_ma_30'] + 1e-10)
            
            # 价格动量指标
            _df['price_momentum_3'] = _df['close'].pct_change(3)
            _df['price_momentum_7'] = _df['close'].pct_change(7)
            
            # VWAP计算
            _df['vwap'] = (_df['high'] + _df['low'] + _df['close']) / 3
            _df['vwap_volume'] = _df['vwap'] * _df['volume']
            
            # 改进的资金流向计算
            # 1. 基于价格动量和成交量的综合判断
            _df['momentum_score'] = (
                _df['price_change'] * 0.4 +  # 当日价格变化
                _df['price_momentum_3'] * 0.3 +  # 3日动量
                _df['price_momentum_7'] * 0.3   # 7日动量
            )
            
            # 2. 成交量强度评分
            _df['volume_score'] = (
                np.log1p(_df['volume_ratio_7']) * 0.6 +  # 7日成交量比率
                np.log1p(_df['volume_ratio_30']) * 0.4   # 30日成交量比率
            )
            
            # 3. 综合流向评分
            _df['flow_score'] = _df['momentum_score'] * _df['volume_score']
            
            # 4. 计算流入流出金额（基于成交额和流向评分）
            _df['base_flow'] = _df['quote_volume'] * _df['flow_score']
            
            # 5. 数据平滑处理
            _df['flow_smoothed'] = _df['base_flow'].rolling(3, min_periods=1).mean()
            
            # 6. 异常值处理（使用分位数方法）
            q99 = _df['flow_smoothed'].quantile(0.99)
            q01 = _df['flow_smoothed'].quantile(0.01)
            _df['flow_clipped'] = _df['flow_smoothed'].clip(q01, q99)
            
            # 7. 分离流入流出
            _df['inflow'] = np.where(_df['flow_clipped'] > 0, _df['flow_clipped'], 0)
            _df['outflow'] = np.where(_df['flow_clipped'] < 0, -_df['flow_clipped'], 0)
            _df['net_flow'] = _df['inflow'] - _df['outflow']
            
            # 8. 流入流出比率（添加平滑处理）
            _df['flow_ratio'] = (_df['inflow'] + 1e6) / (_df['outflow'] + 1e6)  # 添加小常数避免极值
            _df['flow_ratio'] = _df['flow_ratio'].clip(0.01, 100)  # 限制比率范围
            
            # 计算各窗口期的流入流出指标
            for window in windows:
                # 累计流入流出
                _df[f'total_inflow_{window}d'] = _df['inflow'].rolling(window, min_periods=1).sum()
                _df[f'total_outflow_{window}d'] = _df['outflow'].rolling(window, min_periods=1).sum()
                _df[f'net_flow_{window}d'] = _df['net_flow'].rolling(window, min_periods=1).sum()
                
                # 平均流入流出
                _df[f'avg_inflow_{window}d'] = _df['inflow'].rolling(window, min_periods=1).mean()
                _df[f'avg_outflow_{window}d'] = _df['outflow'].rolling(window, min_periods=1).mean()
                _df[f'avg_net_flow_{window}d'] = _df['net_flow'].rolling(window, min_periods=1).mean()
                
                # 流入流出比率（窗口期）
                total_inflow_window = _df[f'total_inflow_{window}d']
                total_outflow_window = _df[f'total_outflow_{window}d']
                _df[f'flow_ratio_{window}d'] = (total_inflow_window + 1e6) / (total_outflow_window + 1e6)
                _df[f'flow_ratio_{window}d'] = _df[f'flow_ratio_{window}d'].clip(0.1, 10)  # 限制比率范围
                
                # 流入流出强度（相对于历史平均）
                _df[f'inflow_intensity_{window}d'] = _df[f'total_inflow_{window}d'] / (_df[f'total_inflow_{window}d'].rolling(window*2, min_periods=window).mean() + 1e6)
                _df[f'outflow_intensity_{window}d'] = _df[f'total_outflow_{window}d'] / (_df[f'total_outflow_{window}d'].rolling(window*2, min_periods=window).mean() + 1e6)
                
                # 流入流出波动性
                _df[f'flow_volatility_{window}d'] = _df['net_flow'].rolling(window, min_periods=1).std()
                
                # 流入流出趋势
                _df[f'flow_trend_{window}d'] = _df[f'avg_net_flow_{window}d'].pct_change()
            
            df_list.append(_df)
        
        if not df_list:
            self.warn("exchange_flow_monitor.process_data - 处理后没有有效数据")
            return pd.DataFrame()
            
        # 修复：直接 concat df_list
        all_df = pd.concat(df_list)
        all_df.reset_index(drop=True, inplace=True)

        # 计算市场整体流入流出指标
        dfs = []
        for candle_begin_time, _df in all_df.groupby('candle_begin_time'):
            _df = _df.copy()

            # 过滤成交额前100的币种（避免小币种噪音）
            if interval == '1h':
                _df['成交额_7d'] = _df['quote_volume'].rolling(24 * 7, min_periods=1).sum()
            elif interval == '1d':
                _df['成交额_7d'] = _df['quote_volume'].rolling(7, min_periods=1).sum()
            
            _df['成交额排名'] = _df['成交额_7d'].rank(ascending=False, method='first')
            _df = _df[_df['成交额排名'] <= self.top_n]  # 使用统一活跃币种筛选 self.top_n
            
            if len(_df) == 0:
                continue

            row = {'candle_begin_time': candle_begin_time}
            row['币种数量'] = len(_df)
            
            for window in windows:
                # 市场总流入流出
                valid_inflow = _df[f'total_inflow_{window}d'].dropna()
                valid_outflow = _df[f'total_outflow_{window}d'].dropna()
                valid_net_flow = _df[f'net_flow_{window}d'].dropna()
                valid_flow_ratio = _df[f'flow_ratio_{window}d'].dropna()
                
                if len(valid_inflow) > 0:
                    # 市场总流入流出（转换为十亿单位）
                    total_inflow = valid_inflow.sum()
                    total_outflow = valid_outflow.sum()
                    total_net_flow = valid_net_flow.sum()
                    
                    row[f'市场总流入_{window}d'] = total_inflow / 1e9
                    row[f'市场总流出_{window}d'] = total_outflow / 1e9
                    row[f'市场净流入_{window}d'] = total_net_flow / 1e9
                    
                    # 市场平均流入流出（转换为百万单位）
                    row[f'平均流入_{window}d'] = valid_inflow.mean() / 1e6
                    row[f'平均流出_{window}d'] = valid_outflow.mean() / 1e6
                    row[f'平均净流入_{window}d'] = valid_net_flow.mean() / 1e6
                    
                    # 流入流出比率（限制范围）
                    flow_ratio = (total_inflow + 1e6) / (total_outflow + 1e6)
                    row[f'市场流入流出比_{window}d'] = min(max(flow_ratio, 0.1), 10)
                    
                    # 流入流出分布
                    net_inflow_count = len(_df[_df[f'net_flow_{window}d'] > 0])
                    net_outflow_count = len(_df[_df[f'net_flow_{window}d'] < 0])
                    
                    row[f'净流入币种数_{window}d'] = net_inflow_count
                    row[f'净流出币种数_{window}d'] = net_outflow_count
                    row[f'净流入币种占比_{window}d'] = (net_inflow_count / len(_df)) * 100
                    row[f'净流出币种占比_{window}d'] = (net_outflow_count / len(_df)) * 100
                    
                    # 强流入流出统计（调整阈值）
                    strong_inflow = len(_df[_df[f'flow_ratio_{window}d'] > 1.5])  # 流入是流出的1.5倍以上
                    strong_outflow = len(_df[_df[f'flow_ratio_{window}d'] < 0.67])  # 流出是流入的1.5倍以上
                    
                    row[f'强流入币种数_{window}d'] = strong_inflow
                    row[f'强流出币种数_{window}d'] = strong_outflow
                    row[f'强流入币种占比_{window}d'] = (strong_inflow / len(_df)) * 100
                    row[f'强流出币种占比_{window}d'] = (strong_outflow / len(_df)) * 100
                    
                    # 市场情绪指标（调整阈值）
                    net_flow_billions = total_net_flow / 1e9
                    row[f'市场情绪指标_{window}d'] = self.get_market_sentiment(net_flow_billions)
                    
                    # 资金流向强度
                    flow_intensity = abs(total_net_flow) / (total_inflow + total_outflow + 1e6)
                    row[f'资金流向强度_{window}d'] = min(flow_intensity * 100, 100)  # 限制最大值
                    
                    # 流动性状态
                    avg_volatility = _df[f'flow_volatility_{window}d'].mean()
                    row[f'流动性状态_{window}d'] = self.get_liquidity_status(avg_volatility)
                    
                else:
                    # 填充默认值
                    for col in [f'市场总流入_{window}d', f'市场总流出_{window}d', f'市场净流入_{window}d',
                               f'平均流入_{window}d', f'平均流出_{window}d', f'平均净流入_{window}d',
                               f'市场流入流出比_{window}d', f'净流入币种数_{window}d', f'净流出币种数_{window}d',
                               f'净流入币种占比_{window}d', f'净流出币种占比_{window}d', f'资金流向强度_{window}d',
                               f'强流入币种数_{window}d', f'强流出币种数_{window}d', f'强流入币种占比_{window}d', f'强流出币种占比_{window}d']:
                        row[col] = 0.0
                    row[f'市场情绪指标_{window}d'] = "中性"
                    row[f'流动性状态_{window}d'] = "正常"
            
            dfs.append(pd.DataFrame([row]))

        if not dfs:
            print("没有生成有效的汇总数据")
            return pd.DataFrame()
            
        final_df = pd.concat(dfs, ignore_index=True)
        
        if start_time is not None:
            final_df = final_df[final_df['candle_begin_time'] > start_time]

        return final_df

    def get_market_sentiment(self, net_flow):
        '''
        根据净流入获取市场情绪（调整阈值使其更合理）
        
        Args:
            net_flow: 净流入金额（十亿美元）
        '''
        if net_flow > 10:
            return "极度乐观"
        elif net_flow > 5:
            return "乐观"
        elif net_flow > -5:
            return "中性"
        elif net_flow > -10:
            return "悲观"
        else:
            return "极度悲观"

    def get_liquidity_status(self, volatility):
        '''
        根据流动性波动获取状态（调整阈值）
        
        Args:
            volatility: 流动性波动率
        '''
        if pd.isna(volatility):
            return "正常"
        elif volatility < 1e8:
            return "流动性充足"
        elif volatility < 5e8:
            return "流动性正常"
        elif volatility < 1e9:
            return "流动性紧张"
        else:
            return "流动性枯竭"



    def draw_index(self, df, start_time=None, interval='1d'):
        """
        显示交易所净流入流出指标图
        
        Args:
            df: 数据DataFrame
            start_time: 开始时间
            interval: 时间间隔
        """
        if df.empty:
            self.warn("exchange_flow_monitor.draw_index - 数据为空，无法绘制图表")
            return

        # 提取窗口期
        windows = []
        for col in df.columns:
            if col.startswith('市场净流入_') and col.endswith('d'):
                window = int(col.split('_')[1].replace('d', ''))
                windows.append(window)
        
        windows = sorted(list(set(windows)))
        
        if start_time is not None:
            df = df[df['candle_begin_time'] > start_time]

        fig = plt.figure(tight_layout=False, figsize=(32, 16), dpi=80, facecolor='w', edgecolor='k')
        gs = gridspec.GridSpec(30, 12)
        
        # 上图：市场净流入
        ax1 = fig.add_subplot(gs[0:8, 0:11])
        for window in windows:
            col_name = f'市场净流入_{window}d'
            if col_name in df.columns and not df[col_name].isna().all():
                ax1.plot(df['candle_begin_time'], df[col_name], 
                        label=f'净流入_{window}d (十亿)', linewidth=2)
        
        ax1.axhline(y=0, color='black', linestyle='-', alpha=0.5)
        ax1.axhline(y=10, color='green', linestyle=':', alpha=0.7, label='强流入(100亿)')
        ax1.axhline(y=-10, color='red', linestyle=':', alpha=0.7, label='强流出(-100亿)')
        
        ax1.set_ylabel('净流入 (十亿美元)')
        ax1.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        ax1.grid(True, linestyle='--', alpha=0.3)
        ax1.set_title('市场净流入流出', fontsize='medium', fontweight='bold')

        # 中图：流入流出比率
        ax2 = fig.add_subplot(gs[10:18, 0:11])
        for window in windows:
            col_name = f'市场流入流出比_{window}d'
            if col_name in df.columns and not df[col_name].isna().all():
                ax2.plot(df['candle_begin_time'], df[col_name], 
                        label=f'流入流出比_{window}d', linewidth=2)
        
        ax2.axhline(y=1, color='black', linestyle='-', alpha=0.5, label='平衡线')
        ax2.axhline(y=1.5, color='green', linestyle=':', alpha=0.7, label='流入优势')
        ax2.axhline(y=0.67, color='red', linestyle=':', alpha=0.7, label='流出优势')
        
        ax2.set_ylabel('流入流出比')
        ax2.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        ax2.grid(True, linestyle='--', alpha=0.3)
        ax2.set_title('市场流入流出比率', fontsize='medium', fontweight='bold')

        # 下图：净流入币种占比
        ax3 = fig.add_subplot(gs[20:28, 0:11])
        for window in windows:
            inflow_col = f'净流入币种占比_{window}d'
            outflow_col = f'净流出币种占比_{window}d'
            if inflow_col in df.columns and not df[inflow_col].isna().all():
                ax3.plot(df['candle_begin_time'], df[inflow_col], 
                        label=f'净流入占比_{window}d', color='green', linewidth=2)
            if outflow_col in df.columns and not df[outflow_col].isna().all():
                ax3.plot(df['candle_begin_time'], df[outflow_col], 
                        label=f'净流出占比_{window}d', color='red', linestyle='--', linewidth=2)
        
        ax3.axhline(y=50, color='black', linestyle='-', alpha=0.5, label='平衡线(50%)')
        ax3.set_ylabel('占比 (%)')
        ax3.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        ax3.grid(True, linestyle='--', alpha=0.3)
        ax3.set_title('净流入流出币种分布', fontsize='medium', fontweight='bold')
        
        plt.xticks(rotation=30)
        plt.tight_layout()
        plt.savefig(self.png_path(), bbox_inches='tight')
        plt.clf()
        plt.cla()
        plt.close('all')
        self.log(f"交易所净流入流出图表已保存: {self.png_path()}")