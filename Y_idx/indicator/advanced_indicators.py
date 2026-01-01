"""
高级市场指标模块
包含价值指标、技术指标、情绪指标、结构性指标等
基于BaseIndicator基类框架设计
"""
import os
import pandas as pd
import numpy as np
import talib
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import warnings

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from .base_indicator import BaseIndicator
# 交易所与工具依赖（统一数据抓取入口）
import yquant.common.binance_utils as binance
import ccxt
from yquant.db.models.bn_account import BnAccount
from yquant.config.config import cfg
import yquant.common.common_utils as common

# 设置pandas显示选项
pd.set_option('display.unicode.ambiguous_as_wide', True)
pd.set_option('display.unicode.east_asian_width', True)
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 180)

# 设置matplotlib中文字体
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# 忽略警告
warnings.filterwarnings('ignore')


class 高级市场指标(BaseIndicator):
    """高级市场指标 - 包含价值、技术、情绪、结构性等多维度指标"""

    def indicator_slug(self):
        """返回指标标识"""
        return "advanced_indicators"

    def indicator_title(self):
        """返回指标标题"""
        return "高级市场指标"

    def get_default_exchange(self, acc: str):
        """
        获取默认交易所连接（函数级注释）
        参数:
            acc: 账户标识
        返回:
            ccxt.binance 交易所实例
        """
        api: BnAccount = cfg.binance.getApi(acc)
        exchange = ccxt.binance({
            'apiKey': api.api_key,
            'secret': api.api_secret,
            'timeout': cfg.binance.timeout,
            'rateLimit': cfg.binance.rateLimit,
            'verbose': cfg.binance.verbose,
            'hostname': cfg.binance.hostname,
            'enableRateLimit': cfg.binance.enableRateLimit,
            'proxies': cfg.binance.proxies
        })
        return exchange
    
    def stat(self, acc: str, backdays=365, windows=[7, 30, 90], save_img=True, interval='1d', start_time=None):
        """
        统计高级市场指标（函数级注释）
        参数:
            acc: 账户标识（用于交易所连接）
            backdays: 回溯天数
            windows: 统计窗口列表
            save_img: 是否保存图像
            interval: 周期 '1d' 或 '1h'
            start_time: 起始时间过滤
        行为:
            - 抓取交易对K线数据
            - 调用 process_data 聚合为高级指标
            - 使用基类保存CSV并绘图
        返回:
            计算后的结果DataFrame
        """
        self.log(f'统计高级市场指标, windows = {windows}')
        exchange = self.get_default_exchange(acc)
        exchange_rules = binance.u_furture_get_exchangeinfo(exchange)
        symbol_list = [s['symbol'] for s in exchange_rules['symbols']
                       if s.get('status') == 'TRADING' and s.get('quoteAsset') == 'USDT' and s.get('contractType') == 'PERPETUAL']
        run_time = common.cacu_run_time('1h', datetime.now())
        max_day = max(max(windows), backdays)
        if interval == '1h':
            df_dict = binance.u_furture_fetch_all_swap_candle_data(
                exchange, symbol_list, '1h', run_time, 24 * max_day * 2 + 10, True, False, njobs=8)
        elif interval == '1d':
            df_dict = binance.u_furture_fetch_all_swap_candle_data(
                exchange, symbol_list, '1d', run_time, max_day * 2 + 10, True, False, njobs=8)
        else:
            self.warn(f"不支持的 interval: {interval}")
            return pd.DataFrame()
        df = self.process_data(df_dict, windows, backdays, interval, start_time)
        if df is not None and not df.empty:
            self.save_csv(df)
            if save_img:
                self.draw_index(df, start_time=start_time, interval=interval)
        return df

    def stat_with_data(self, df_dict, acc: str, start_time=None, backdays=365, windows=[7, 30, 90], 
                      save_img=True, interval='1d'):
        """
        使用已有数据统计高级市场指标（函数级注释）
        参数:
            df_dict: 预先获取的K线数据
            acc: 账户标识（未直接使用，仅为签名一致）
            start_time: 起始时间过滤
            backdays: 回溯天数
            windows: 窗口列表
            save_img: 是否保存图像
            interval: 周期 '1d' 或 '1h'
        行为:
            - 直接使用传入数据进行计算
            - 使用基类保存CSV并绘图
        返回:
            计算后的结果DataFrame
        """
        self.log(f'使用已有数据统计高级市场指标, windows = {windows}')
        df = self.process_data(df_dict, windows, backdays, interval, start_time)
        if df is not None and not df.empty:
            self.save_csv(df)
            if save_img:
                self.draw_index(df, start_time=start_time, interval=interval)
        return df

    def _calculate_market_cap_weighted_index(self, df_dict: Dict) -> pd.DataFrame:
        """计算市值加权指数"""
        try:
            all_data = []
            for symbol, df in df_dict.items():
                df_copy = df.copy()
                df_copy['symbol'] = symbol
                # 模拟市值 = 价格 * 成交量
                df_copy['market_cap'] = df_copy['close'] * df_copy['volume']
                all_data.append(df_copy)
            
            combined_df = pd.concat(all_data, ignore_index=True)
            
            # 按时间分组计算市值加权指数
            result_data = []
            for time, group in combined_df.groupby('candle_begin_time'):
                total_market_cap = group['market_cap'].sum()
                if total_market_cap > 0:
                    weighted_price = (group['close'] * group['market_cap']).sum() / total_market_cap
                    result_data.append({
                        'candle_begin_time': time,
                        'market_cap_weighted_index': weighted_price
                    })
            
            return pd.DataFrame(result_data)
            
        except Exception as e:
            self.warn(f"计算市值加权指数失败: {e}")
            return pd.DataFrame()
    
    def _calculate_money_flow(self, df_dict: Dict) -> pd.DataFrame:
        """计算资金流向指标"""
        try:
            all_data = []
            for symbol, df in df_dict.items():
                df_copy = df.copy()
                # 计算资金流向：正流入为买盘，负流出为卖盘
                df_copy['money_flow'] = np.where(
                    df_copy['close'] > df_copy['open'],
                    df_copy['volume'] * df_copy['close'],  # 上涨时为流入
                    -df_copy['volume'] * df_copy['close']  # 下跌时为流出
                )
                df_copy['symbol'] = symbol
                all_data.append(df_copy[['candle_begin_time', 'symbol', 'money_flow']])
            
            combined_df = pd.concat(all_data, ignore_index=True)
            
            # 按时间汇总资金流向
            result_data = []
            for time, group in combined_df.groupby('candle_begin_time'):
                net_flow = group['money_flow'].sum()
                inflow = group[group['money_flow'] > 0]['money_flow'].sum()
                outflow = abs(group[group['money_flow'] < 0]['money_flow'].sum())
                
                result_data.append({
                    'candle_begin_time': time,
                    'net_money_flow': net_flow,
                    'money_inflow': inflow,
                    'money_outflow': outflow,
                    'flow_ratio': inflow / (outflow + 1e-10)  # 避免除零
                })
            
            return pd.DataFrame(result_data)
            
        except Exception as e:
            self.warn(f"计算资金流向失败: {e}")
            return pd.DataFrame()
    
    def _calculate_value_deviation(self, df_dict: Dict, btc_price: float = None) -> pd.DataFrame:
        """计算价值偏离度"""
        try:
            # 以BTC为基准计算其他币种的相对价值偏离
            if 'BTCUSDT' not in df_dict:
                return pd.DataFrame()
            
            btc_df = df_dict['BTCUSDT'].copy()
            btc_df['btc_ma30'] = btc_df['close'].rolling(30).mean()
            btc_df['btc_deviation'] = (btc_df['close'] - btc_df['btc_ma30']) / btc_df['btc_ma30']
            
            result_data = []
            for _, row in btc_df.iterrows():
                result_data.append({
                    'candle_begin_time': row['candle_begin_time'],
                    'btc_price': row['close'],
                    'btc_ma30': row['btc_ma30'],
                    'value_deviation': row['btc_deviation']
                })
            
            return pd.DataFrame(result_data)
            
        except Exception as e:
            self.warn(f"计算价值偏离度失败: {e}")
            return pd.DataFrame()
    
    def _calculate_mvrv_ratio(self, df_dict: Dict) -> pd.DataFrame:
        """计算MVRV比率（模拟版本）"""
        try:
            if 'BTCUSDT' not in df_dict:
                return pd.DataFrame()
            
            btc_df = df_dict['BTCUSDT'].copy()
            
            # 模拟MVRV：当前价格 / 成本基础（使用移动平均作为成本基础）
            btc_df['cost_basis'] = btc_df['close'].rolling(365, min_periods=30).mean()
            btc_df['mvrv_ratio'] = btc_df['close'] / btc_df['cost_basis']
            
            result_data = []
            for _, row in btc_df.iterrows():
                if not pd.isna(row['mvrv_ratio']):
                    result_data.append({
                        'candle_begin_time': row['candle_begin_time'],
                        'mvrv_ratio': row['mvrv_ratio'],
                        'mvrv_signal': self._get_mvrv_signal(row['mvrv_ratio'])
                    })
            
            return pd.DataFrame(result_data)
            
        except Exception as e:
            self.warn(f"计算MVRV比率失败: {e}")
            return pd.DataFrame()
    
    def process_data(self, df_dict, windows, backdays, interval, start_time):
        """
        处理数据计算高级市场指标（统一签名）
        参数:
            df_dict: 所有交易对的K线数据字典
            windows: 统计窗口列表
            backdays: 回溯天数（未直接使用）
            interval: 周期 '1d' 或 '1h'
            start_time: 起始时间过滤
        返回:
            计算完成的 DataFrame（不负责保存，由基类处理）
        """
        # 合并所有币种数据
        df_list = [df_dict[symbol] for symbol in df_dict]
        if not df_list:
            self.warn("advanced_indicators.process_data - 初次汇总 df_list 为空")
            return pd.DataFrame()
            
        all_df = pd.concat(df_list)
        all_df.reset_index(inplace=True)

        # 计算各币种的指标
        df_list = []
        for symbol, _df in all_df.groupby('symbol'):
            _df = _df.copy()
            
            # 计算各种技术指标
            self._calculate_technical_metrics(_df, windows)
            
            # 计算成交额（用于筛选活跃币种）
            if interval == '1h':
                _df['成交额'] = _df['quote_volume'].rolling(24 * 7, min_periods=1).sum()
            elif interval == '1d':
                _df['成交额'] = _df['quote_volume'].rolling(7, min_periods=1).sum()
                
            df_list.append(_df)
        
        if not df_list:
            self.warn("advanced_indicators.process_data - 分币种 df_list 为空")
            return pd.DataFrame()
            
        all_df = pd.concat(df_list)
        all_df.reset_index(inplace=True)

        # 计算市场级高级指标
        rows = []
        for candle_begin_time, _df in all_df.groupby('candle_begin_time'):
            _df = _df.copy()
            
            # 筛选活跃币种
            _df['成交额排名'] = _df['成交额'].rank(ascending=False, method='first')
            _df = _df[_df['成交额排名'] <= self.top_n]
            
            if len(_df) == 0:
                continue
                
            row = {'candle_begin_time': candle_begin_time, '总币种数量': len(_df)}
            
            # 计算价值指标
            self._calculate_value_indicators(_df, row, windows)
            
            # 计算技术指标
            self._calculate_tech_indicators(_df, row, windows)
            
            # 计算情绪指标
            self._calculate_sentiment_indicators(_df, row, windows)
            
            # 计算结构性指标
            self._calculate_structure_indicators(_df, row, windows)
            
            rows.append(row)
        
        final_df = pd.DataFrame(rows)
        
        # 时间过滤
        if start_time is not None and not final_df.empty:
            final_df = final_df[final_df['candle_begin_time'] > start_time]
            
        return final_df
    
    def calculate_technical_indicators(self, df_dict: Dict) -> Dict:
        """
        计算技术指标
        
        Args:
            df_dict: 币种数据字典
            
        Returns:
            Dict: 技术指标结果
        """
        try:
            results = {}
            
            # 1. 多空方向信息
            trend_analysis = self._calculate_trend_analysis(df_dict)
            results['trend_analysis'] = trend_analysis
            
            # 2. 短期提交超买超卖
            overbought_oversold = self._calculate_overbought_oversold(df_dict)
            results['overbought_oversold'] = overbought_oversold
            
            # 3. 策略参数动态调整指标
            dynamic_parameters = self._calculate_dynamic_parameters(df_dict)
            results['dynamic_parameters'] = dynamic_parameters
            
            # 4. 轮动与结构性行情识别
            rotation_analysis = self._calculate_rotation_analysis(df_dict)
            results['rotation_analysis'] = rotation_analysis
            
            return results
            
        except Exception as e:
            self.warn(f"计算技术指标失败: {e}")
            return {}
    
    def _calculate_trend_analysis(self, df_dict: Dict) -> pd.DataFrame:
        """计算多空方向分析"""
        try:
            trend_data = []
            
            for symbol, df in df_dict.items():
                df_copy = df.copy()
                
                # 计算多个周期的移动平均线
                df_copy['ma5'] = df_copy['close'].rolling(5).mean()
                df_copy['ma10'] = df_copy['close'].rolling(10).mean()
                df_copy['ma20'] = df_copy['close'].rolling(20).mean()
                df_copy['ma50'] = df_copy['close'].rolling(50).mean()
                
                # 计算趋势强度
                df_copy['trend_strength'] = (
                    (df_copy['close'] > df_copy['ma5']).astype(int) +
                    (df_copy['close'] > df_copy['ma10']).astype(int) +
                    (df_copy['close'] > df_copy['ma20']).astype(int) +
                    (df_copy['close'] > df_copy['ma50']).astype(int)
                ) / 4
                
                # 计算趋势方向
                df_copy['trend_direction'] = np.where(
                    df_copy['trend_strength'] > 0.6, 'bullish',
                    np.where(df_copy['trend_strength'] < 0.4, 'bearish', 'neutral')
                )
                
                trend_data.append(df_copy[['candle_begin_time', 'symbol', 'trend_strength', 'trend_direction']])
            
            combined_df = pd.concat(trend_data, ignore_index=True)
            
            # 计算市场整体趋势
            market_trend = []
            for time, group in combined_df.groupby('candle_begin_time'):
                bullish_count = (group['trend_direction'] == 'bullish').sum()
                bearish_count = (group['trend_direction'] == 'bearish').sum()
                neutral_count = (group['trend_direction'] == 'neutral').sum()
                total_count = len(group)
                
                avg_strength = group['trend_strength'].mean()
                
                market_trend.append({
                    'candle_begin_time': time,
                    'bullish_ratio': bullish_count / total_count,
                    'bearish_ratio': bearish_count / total_count,
                    'neutral_ratio': neutral_count / total_count,
                    'avg_trend_strength': avg_strength,
                    'market_sentiment': self._get_market_sentiment(bullish_count / total_count)
                })
            
            return pd.DataFrame(market_trend)
            
        except Exception as e:
            self.warn(f"计算趋势分析失败: {e}")
            return pd.DataFrame()
    
    def _calculate_overbought_oversold(self, df_dict: Dict) -> pd.DataFrame:
        """计算超买超卖指标"""
        try:
            overbought_data = []
            
            for symbol, df in df_dict.items():
                df_copy = df.copy()
                
                # 计算RSI
                df_copy['rsi'] = talib.RSI(df_copy['close'].values, timeperiod=14)
                
                # 计算随机指标
                df_copy['slowk'], df_copy['slowd'] = talib.STOCH(
                    df_copy['high'].values,
                    df_copy['low'].values,
                    df_copy['close'].values,
                    fastk_period=14,
                    slowk_period=3,
                    slowd_period=3
                )
                
                # 计算威廉指标
                df_copy['willr'] = talib.WILLR(
                    df_copy['high'].values,
                    df_copy['low'].values,
                    df_copy['close'].values,
                    timeperiod=14
                )
                
                # 综合超买超卖信号
                df_copy['overbought_signal'] = (
                    (df_copy['rsi'] > 70).astype(int) +
                    (df_copy['slowk'] > 80).astype(int) +
                    (df_copy['willr'] > -20).astype(int)
                ) / 3
                
                df_copy['oversold_signal'] = (
                    (df_copy['rsi'] < 30).astype(int) +
                    (df_copy['slowk'] < 20).astype(int) +
                    (df_copy['willr'] < -80).astype(int)
                ) / 3
                
                overbought_data.append(df_copy[['candle_begin_time', 'symbol', 'rsi', 'overbought_signal', 'oversold_signal']])
            
            combined_df = pd.concat(overbought_data, ignore_index=True)
            
            # 计算市场整体超买超卖情况
            market_overbought = []
            for time, group in combined_df.groupby('candle_begin_time'):
                avg_rsi = group['rsi'].mean()
                overbought_ratio = (group['overbought_signal'] > 0.6).sum() / len(group)
                oversold_ratio = (group['oversold_signal'] > 0.6).sum() / len(group)
                
                market_overbought.append({
                    'candle_begin_time': time,
                    'avg_rsi': avg_rsi,
                    'overbought_ratio': overbought_ratio,
                    'oversold_ratio': oversold_ratio,
                    'market_condition': self._get_market_condition(avg_rsi, overbought_ratio, oversold_ratio)
                })
            
            return pd.DataFrame(market_overbought)
            
        except Exception as e:
            self.warn(f"计算超买超卖指标失败: {e}")
            return pd.DataFrame()
    
    def _calculate_dynamic_parameters(self, df_dict: Dict) -> pd.DataFrame:
        """计算动态参数调整指标"""
        try:
            # 基于市场波动率动态调整参数
            dynamic_data = []
            
            # 计算市场整体波动率
            all_returns = []
            timestamps = []
            
            for symbol, df in df_dict.items():
                df_copy = df.copy()
                df_copy['returns'] = df_copy['close'].pct_change()
                for _, row in df_copy.iterrows():
                    if not pd.isna(row['returns']):
                        all_returns.append(row['returns'])
                        timestamps.append(row['candle_begin_time'])
            
            # 按时间分组计算动态参数
            returns_df = pd.DataFrame({'candle_begin_time': timestamps, 'returns': all_returns})
            
            for time, group in returns_df.groupby('candle_begin_time'):
                volatility = group['returns'].std()
                
                # 基于波动率调整参数
                if volatility < 0.02:  # 低波动
                    risk_level = "低风险"
                    position_size = 1.0
                    stop_loss = 0.05
                elif volatility < 0.05:  # 中等波动
                    risk_level = "中等风险"
                    position_size = 0.7
                    stop_loss = 0.03
                else:  # 高波动
                    risk_level = "高风险"
                    position_size = 0.5
                    stop_loss = 0.02
                
                dynamic_data.append({
                    'candle_begin_time': time,
                    'market_volatility': volatility,
                    'risk_level': risk_level,
                    'suggested_position_size': position_size,
                    'suggested_stop_loss': stop_loss
                })
            
            return pd.DataFrame(dynamic_data)
            
        except Exception as e:
            self.warn(f"计算动态参数失败: {e}")
            return pd.DataFrame()
    
    def _calculate_rotation_analysis(self, df_dict: Dict) -> pd.DataFrame:
        """计算轮动与结构性行情分析"""
        try:
            rotation_data = []
            
            # 按市值分类（模拟）
            large_cap = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'XRPUSDT']
            mid_cap = ['SOLUSDT', 'DOTUSDT', 'LINKUSDT', 'LTCUSDT', 'AVAXUSDT']
            
            for time_group in pd.date_range(start='2023-01-01', end=datetime.now(), freq='D'):
                large_cap_performance = []
                mid_cap_performance = []
                small_cap_performance = []
                
                for symbol, df in df_dict.items():
                    # 获取当天数据
                    day_data = df[df['candle_begin_time'].dt.date == time_group.date()]
                    if len(day_data) > 0:
                        daily_return = day_data['close'].iloc[-1] / day_data['open'].iloc[0] - 1
                        
                        if symbol in large_cap:
                            large_cap_performance.append(daily_return)
                        elif symbol in mid_cap:
                            mid_cap_performance.append(daily_return)
                        else:
                            small_cap_performance.append(daily_return)
                
                # 计算各类别平均表现
                large_avg = np.mean(large_cap_performance) if large_cap_performance else 0
                mid_avg = np.mean(mid_cap_performance) if mid_cap_performance else 0
                small_avg = np.mean(small_cap_performance) if small_cap_performance else 0
                
                # 判断轮动方向
                rotation_direction = self._get_rotation_direction(large_avg, mid_avg, small_avg)
                
                rotation_data.append({
                    'candle_begin_time': time_group,
                    'large_cap_performance': large_avg,
                    'mid_cap_performance': mid_avg,
                    'small_cap_performance': small_avg,
                    'rotation_direction': rotation_direction
                })
            
            return pd.DataFrame(rotation_data)
            
        except Exception as e:
            self.warn(f"计算轮动分析失败: {e}")
            return pd.DataFrame()
    
    def _get_market_sentiment(self, bullish_ratio: float) -> str:
        """根据多头比例获取市场情绪"""
        if bullish_ratio > 0.7:
            return "极度乐观"
        elif bullish_ratio > 0.6:
            return "乐观"
        elif bullish_ratio > 0.4:
            return "中性"
        elif bullish_ratio > 0.3:
            return "悲观"
        else:
            return "极度悲观"
    
    def _get_market_condition(self, avg_rsi: float, overbought_ratio: float, oversold_ratio: float) -> str:
        """获取市场状态"""
        if overbought_ratio > 0.3:
            return "市场超买"
        elif oversold_ratio > 0.3:
            return "市场超卖"
        elif avg_rsi > 60:
            return "偏强势"
        elif avg_rsi < 40:
            return "偏弱势"
        else:
            return "震荡"
    
    def _get_rotation_direction(self, large: float, mid: float, small: float) -> str:
        """获取轮动方向"""
        performances = [('大盘股', large), ('中盘股', mid), ('小盘股', small)]
        performances.sort(key=lambda x: x[1], reverse=True)
        return f"{performances[0][0]}领涨"

    def _calculate_technical_metrics(self, df, windows):
        """计算币种级技术指标"""
        for window in windows:
            # 移动平均线
            df[f'ma_{window}'] = df['close'].rolling(window).mean()
            
            # 计算收益率
            if window == 1:
                df[f'return_{window}d'] = df['close'].pct_change()
            else:
                df[f'return_{window}d'] = df['close'].pct_change(window)
            
            # 波动率
            df[f'volatility_{window}d'] = df['close'].pct_change().rolling(window).std()
            
            # RSI
            if len(df) >= window + 14:
                df[f'rsi_{window}d'] = talib.RSI(df['close'].values, timeperiod=14)
            
            # MACD
            if len(df) >= window + 26:
                macd, signal, hist = talib.MACD(df['close'].values, fastperiod=12, slowperiod=26, signalperiod=9)
                df[f'macd_{window}d'] = macd
                df[f'macd_signal_{window}d'] = signal

    def _calculate_value_indicators(self, df, row, windows):
        """计算价值指标"""
        for window in windows:
            # 市值加权价格
            total_market_cap = (df['close'] * df['volume']).sum()
            if total_market_cap > 0:
                weighted_price = (df['close'] * df['close'] * df['volume']).sum() / total_market_cap
                row[f'市值加权价格_{window}d'] = weighted_price
            
            # 资金流向
            df[f'money_flow_{window}d'] = np.where(
                df[f'return_{window}d'] > 0,
                df['volume'] * df['close'],
                -df['volume'] * df['close']
            )
            row[f'资金流向_{window}d'] = df[f'money_flow_{window}d'].sum()
            
            # 价值偏离度（相对BTC）
            btc_data = df[df['symbol'] == 'BTCUSDT']
            if len(btc_data) > 0:
                btc_return = btc_data[f'return_{window}d'].iloc[0]
                avg_return = df[f'return_{window}d'].mean()
                row[f'价值偏离度_{window}d'] = avg_return - btc_return if not pd.isna(btc_return) else 0
    
    def calculate_sentiment_indicators(self, df_dict: Dict) -> Dict:
        """
        计算市场情绪指标
        
        Args:
            df_dict: 币种数据字典
            
        Returns:
            Dict: 情绪指标结果
        """
        try:
            results = {}
            
            # 1. 市场情绪与动态监控
            sentiment_monitoring = self._calculate_sentiment_monitoring(df_dict)
            results['sentiment_monitoring'] = sentiment_monitoring
            
            # 2. 恐慌贪婪指数（基于价格行为）
            fear_greed_index = self._calculate_fear_greed_from_price(df_dict)
            results['fear_greed_index'] = fear_greed_index
            
            # 3. 资金流向情绪
            money_flow_sentiment = self._calculate_money_flow_sentiment(df_dict)
            results['money_flow_sentiment'] = money_flow_sentiment
            
            return results
            
        except Exception as e:
            self.warn(f"计算情绪指标失败: {e}")
            return {}
    
    def _calculate_sentiment_monitoring(self, df_dict: Dict) -> pd.DataFrame:
        """计算市场情绪监控指标"""
        try:
            sentiment_data = []
            
            # 计算整体市场情绪指标
            for symbol, df in df_dict.items():
                df_copy = df.copy()
                
                # 计算价格动量
                df_copy['price_momentum'] = df_copy['close'].pct_change(5)
                
                # 计算成交量动量
                df_copy['volume_momentum'] = df_copy['volume'].pct_change(5)
                
                # 计算波动率
                df_copy['volatility'] = df_copy['close'].rolling(10).std() / df_copy['close'].rolling(10).mean()
                
                sentiment_data.append(df_copy[['candle_begin_time', 'symbol', 'price_momentum', 'volume_momentum', 'volatility']])
            
            combined_df = pd.concat(sentiment_data, ignore_index=True)
            
            # 按时间汇总情绪指标
            market_sentiment = []
            for time, group in combined_df.groupby('candle_begin_time'):
                avg_price_momentum = group['price_momentum'].mean()
                avg_volume_momentum = group['volume_momentum'].mean()
                avg_volatility = group['volatility'].mean()
                
                # 综合情绪得分
                sentiment_score = (
                    np.sign(avg_price_momentum) * 0.4 +
                    np.sign(avg_volume_momentum) * 0.3 +
                    (1 - min(avg_volatility, 1)) * 0.3  # 低波动率为正面情绪
                )
                
                market_sentiment.append({
                    'candle_begin_time': time,
                    'price_momentum': avg_price_momentum,
                    'volume_momentum': avg_volume_momentum,
                    'volatility': avg_volatility,
                    'sentiment_score': sentiment_score,
                    'sentiment_level': self._get_sentiment_level(sentiment_score)
                })
            
            return pd.DataFrame(market_sentiment)
            
        except Exception as e:
            self.warn(f"计算情绪监控失败: {e}")
            return pd.DataFrame()
    
    def _calculate_fear_greed_from_price(self, df_dict: Dict) -> pd.DataFrame:
        """基于价格行为计算恐慌贪婪指数"""
        try:
            if 'BTCUSDT' not in df_dict:
                return pd.DataFrame()
            
            btc_df = df_dict['BTCUSDT'].copy()
            
            # 计算多个恐慌贪婪因子
            # 1. 价格相对于移动平均线的位置
            btc_df['ma50'] = btc_df['close'].rolling(50).mean()
            btc_df['price_vs_ma'] = (btc_df['close'] - btc_df['ma50']) / btc_df['ma50']
            
            # 2. 波动率因子
            btc_df['volatility'] = btc_df['close'].rolling(10).std() / btc_df['close'].rolling(10).mean()
            
            # 3. 动量因子
            btc_df['momentum'] = btc_df['close'].pct_change(7)
            
            # 4. 成交量因子
            btc_df['volume_ma'] = btc_df['volume'].rolling(20).mean()
            btc_df['volume_ratio'] = btc_df['volume'] / btc_df['volume_ma']
            
            # 综合计算恐慌贪婪指数 (0-100)
            btc_df['fear_greed_raw'] = (
                np.clip(btc_df['price_vs_ma'] * 100 + 50, 0, 100) * 0.3 +
                np.clip((1 - btc_df['volatility']) * 100, 0, 100) * 0.2 +
                np.clip(btc_df['momentum'] * 1000 + 50, 0, 100) * 0.3 +
                np.clip(btc_df['volume_ratio'] * 25, 0, 100) * 0.2
            )
            
            # 平滑处理
            btc_df['fear_greed_index'] = btc_df['fear_greed_raw'].rolling(3).mean()
            
            result_data = []
            for _, row in btc_df.iterrows():
                if not pd.isna(row['fear_greed_index']):
                    result_data.append({
                        'candle_begin_time': row['candle_begin_time'],
                        'fear_greed_index': row['fear_greed_index'],
                        'fear_greed_level': self._get_fear_greed_level(row['fear_greed_index'])
                    })
            
            return pd.DataFrame(result_data)
            
        except Exception as e:
            self.warn(f"计算恐慌贪婪指数失败: {e}")
            return pd.DataFrame()
    
    def _calculate_money_flow_sentiment(self, df_dict: Dict) -> pd.DataFrame:
        """计算资金流向情绪"""
        try:
            flow_data = []
            
            for symbol, df in df_dict.items():
                df_copy = df.copy()
                
                # 计算资金流向强度
                df_copy['money_flow_raw'] = df_copy['volume'] * df_copy['close']
                df_copy['positive_flow'] = np.where(
                    df_copy['close'] > df_copy['open'],
                    df_copy['money_flow_raw'], 0
                )
                df_copy['negative_flow'] = np.where(
                    df_copy['close'] < df_copy['open'],
                    df_copy['money_flow_raw'], 0
                )
                
                flow_data.append(df_copy[['candle_begin_time', 'symbol', 'positive_flow', 'negative_flow']])
            
            combined_df = pd.concat(flow_data, ignore_index=True)
            
            # 按时间汇总资金流向
            flow_sentiment = []
            for time, group in combined_df.groupby('candle_begin_time'):
                total_positive = group['positive_flow'].sum()
                total_negative = group['negative_flow'].sum()
                
                if total_positive + total_negative > 0:
                    flow_ratio = total_positive / (total_positive + total_negative)
                    flow_strength = (total_positive + total_negative) / len(group)
                    
                    flow_sentiment.append({
                        'candle_begin_time': time,
                        'positive_flow': total_positive,
                        'negative_flow': total_negative,
                        'flow_ratio': flow_ratio,
                        'flow_strength': flow_strength,
                        'flow_sentiment': self._get_flow_sentiment(flow_ratio)
                    })
            
            return pd.DataFrame(flow_sentiment)
            
        except Exception as e:
            self.warn(f"计算资金流向情绪失败: {e}")
            return pd.DataFrame()
    
    def _get_sentiment_level(self, score: float) -> str:
        """获取情绪等级"""
        if score > 0.5:
            return "极度乐观"
        elif score > 0.2:
            return "乐观"
        elif score > -0.2:
            return "中性"
        elif score > -0.5:
            return "悲观"
        else:
            return "极度悲观"
    
    def _get_fear_greed_level(self, index: float) -> str:
        """获取恐慌贪婪等级"""
        if index >= 75:
            return "极度贪婪"
        elif index >= 55:
            return "贪婪"
        elif index >= 45:
            return "中性"
        elif index >= 25:
            return "恐慌"
        else:
            return "极度恐慌"
    
    def _get_flow_sentiment(self, ratio: float) -> str:
        """获取资金流向情绪"""
        if ratio > 0.7:
            return "资金大幅流入"
        elif ratio > 0.6:
            return "资金流入"
        elif ratio > 0.4:
            return "资金平衡"
        elif ratio > 0.3:
            return "资金流出"
        else:
            return "资金大幅流出"

class CTA过滤器():
    """CTA策略过滤器"""
    
    def __init__(self):
        self.name = "CTA过滤器"
    
    def calculate_cta_filters(self, df_dict: Dict) -> Dict:
        """
        计算CTA过滤指标
        
        Args:
            df_dict: 币种数据字典
            
        Returns:
            Dict: CTA过滤结果
        """
        try:
            results = {}
            
            # 1. 趋势过滤器
            trend_filter = self._calculate_trend_filter(df_dict)
            results['trend_filter'] = trend_filter
            
            # 2. 波动率过滤器
            volatility_filter = self._calculate_volatility_filter(df_dict)
            results['volatility_filter'] = volatility_filter
            
            # 3. 动量过滤器
            momentum_filter = self._calculate_momentum_filter(df_dict)
            results['momentum_filter'] = momentum_filter
            
            # 4. 综合信号过滤
            combined_filter = self._calculate_combined_filter(trend_filter, volatility_filter, momentum_filter)
            results['combined_filter'] = combined_filter
            
            return results
            
        except Exception as e:
            self.warn(f"计算CTA过滤器失败: {e}")
            return {}
    
    def _calculate_trend_filter(self, df_dict: Dict) -> pd.DataFrame:
        """计算趋势过滤器"""
        try:
            trend_signals = []
            
            for symbol, df in df_dict.items():
                df_copy = df.copy()
                
                # 多重时间框架趋势分析
                df_copy['ma_short'] = df_copy['close'].rolling(10).mean()
                df_copy['ma_medium'] = df_copy['close'].rolling(20).mean()
                df_copy['ma_long'] = df_copy['close'].rolling(50).mean()
                
                # 趋势强度评分
                df_copy['trend_score'] = (
                    (df_copy['close'] > df_copy['ma_short']).astype(int) * 3 +
                    (df_copy['ma_short'] > df_copy['ma_medium']).astype(int) * 2 +
                    (df_copy['ma_medium'] > df_copy['ma_long']).astype(int) * 1
                )
                
                # 趋势信号
                df_copy['trend_signal'] = np.where(
                    df_copy['trend_score'] >= 5, 'strong_bullish',
                    np.where(df_copy['trend_score'] >= 3, 'bullish',
                    np.where(df_copy['trend_score'] >= 2, 'neutral',
                    np.where(df_copy['trend_score'] >= 1, 'bearish', 'strong_bearish')))
                )
                
                trend_signals.append(df_copy[['candle_begin_time', 'symbol', 'trend_score', 'trend_signal']])
            
            combined_df = pd.concat(trend_signals, ignore_index=True)
            
            # 市场整体趋势过滤
            market_trend = []
            for time, group in combined_df.groupby('candle_begin_time'):
                avg_trend_score = group['trend_score'].mean()
                strong_bullish_count = (group['trend_signal'] == 'strong_bullish').sum()
                bullish_count = (group['trend_signal'] == 'bullish').sum()
                bearish_count = (group['trend_signal'] == 'bearish').sum()
                strong_bearish_count = (group['trend_signal'] == 'strong_bearish').sum()
                
                total_count = len(group)
                
                market_trend.append({
                    'candle_begin_time': time,
                    'avg_trend_score': avg_trend_score,
                    'strong_bullish_ratio': strong_bullish_count / total_count,
                    'bullish_ratio': bullish_count / total_count,
                    'bearish_ratio': bearish_count / total_count,
                    'strong_bearish_ratio': strong_bearish_count / total_count,
                    'market_trend_filter': self._get_market_trend_filter(avg_trend_score)
                })
            
            return pd.DataFrame(market_trend)
            
        except Exception as e:
            self.warn(f"计算趋势过滤器失败: {e}")
            return pd.DataFrame()
    
    def _calculate_volatility_filter(self, df_dict: Dict) -> pd.DataFrame:
        """计算波动率过滤器"""
        try:
            volatility_data = []
            
            for symbol, df in df_dict.items():
                df_copy = df.copy()
                
                # 计算不同周期的波动率
                df_copy['volatility_5d'] = df_copy['close'].rolling(5).std() / df_copy['close'].rolling(5).mean()
                df_copy['volatility_10d'] = df_copy['close'].rolling(10).std() / df_copy['close'].rolling(10).mean()
                df_copy['volatility_20d'] = df_copy['close'].rolling(20).std() / df_copy['close'].rolling(20).mean()
                
                # 波动率状态
                df_copy['volatility_state'] = np.where(
                    df_copy['volatility_10d'] > df_copy['volatility_20d'] * 1.5, 'high_volatility',
                    np.where(df_copy['volatility_10d'] < df_copy['volatility_20d'] * 0.7, 'low_volatility', 'normal_volatility')
                )
                
                volatility_data.append(df_copy[['candle_begin_time', 'symbol', 'volatility_10d', 'volatility_state']])
            
            combined_df = pd.concat(volatility_data, ignore_index=True)
            
            # 市场波动率过滤
            market_volatility = []
            for time, group in combined_df.groupby('candle_begin_time'):
                avg_volatility = group['volatility_10d'].mean()
                high_vol_count = (group['volatility_state'] == 'high_volatility').sum()
                low_vol_count = (group['volatility_state'] == 'low_volatility').sum()
                
                total_count = len(group)
                
                market_volatility.append({
                    'candle_begin_time': time,
                    'avg_volatility': avg_volatility,
                    'high_volatility_ratio': high_vol_count / total_count,
                    'low_volatility_ratio': low_vol_count / total_count,
                    'volatility_filter': self._get_volatility_filter(avg_volatility, high_vol_count / total_count)
                })
            
            return pd.DataFrame(market_volatility)
            
        except Exception as e:
            self.warn(f"计算波动率过滤器失败: {e}")
            return pd.DataFrame()
    
    def _calculate_momentum_filter(self, df_dict: Dict) -> pd.DataFrame:
        """计算动量过滤器"""
        try:
            momentum_data = []
            
            for symbol, df in df_dict.items():
                df_copy = df.copy()
                
                # 计算多周期动量
                df_copy['momentum_3d'] = df_copy['close'].pct_change(3)
                df_copy['momentum_7d'] = df_copy['close'].pct_change(7)
                df_copy['momentum_14d'] = df_copy['close'].pct_change(14)
                
                # 动量强度评分
                df_copy['momentum_score'] = (
                    np.sign(df_copy['momentum_3d']) * 1 +
                    np.sign(df_copy['momentum_7d']) * 2 +
                    np.sign(df_copy['momentum_14d']) * 3
                )
                
                # 动量信号
                df_copy['momentum_signal'] = np.where(
                    df_copy['momentum_score'] >= 4, 'strong_momentum',
                    np.where(df_copy['momentum_score'] >= 1, 'positive_momentum',
                    np.where(df_copy['momentum_score'] >= -1, 'neutral_momentum',
                    np.where(df_copy['momentum_score'] >= -4, 'negative_momentum', 'strong_negative_momentum')))
                )
                
                momentum_data.append(df_copy[['candle_begin_time', 'symbol', 'momentum_score', 'momentum_signal']])
            
            combined_df = pd.concat(momentum_data, ignore_index=True)
            
            # 市场动量过滤
            market_momentum = []
            for time, group in combined_df.groupby('candle_begin_time'):
                avg_momentum_score = group['momentum_score'].mean()
                strong_momentum_count = (group['momentum_signal'] == 'strong_momentum').sum()
                positive_momentum_count = (group['momentum_signal'] == 'positive_momentum').sum()
                
                total_count = len(group)
                
                market_momentum.append({
                    'candle_begin_time': time,
                    'avg_momentum_score': avg_momentum_score,
                    'strong_momentum_ratio': strong_momentum_count / total_count,
                    'positive_momentum_ratio': positive_momentum_count / total_count,
                    'momentum_filter': self._get_momentum_filter(avg_momentum_score)
                })
            
            return pd.DataFrame(market_momentum)
            
        except Exception as e:
            self.warn(f"计算动量过滤器失败: {e}")
            return pd.DataFrame()
    
    def _calculate_combined_filter(self, trend_df: pd.DataFrame, volatility_df: pd.DataFrame, momentum_df: pd.DataFrame) -> pd.DataFrame:
        """计算综合过滤信号"""
        try:
            if trend_df.empty or volatility_df.empty or momentum_df.empty:
                return pd.DataFrame()
            
            # 合并所有过滤器数据
            combined = trend_df.merge(volatility_df, on='candle_begin_time', how='inner')
            combined = combined.merge(momentum_df, on='candle_begin_time', how='inner')
            
            # 计算综合信号
            combined['combined_score'] = (
                combined['avg_trend_score'] * 0.4 +
                (1 - combined['avg_volatility']) * 100 * 0.3 +  # 低波动率为正面
                combined['avg_momentum_score'] * 10 * 0.3
            )
            
            # 综合过滤信号
            combined['combined_filter'] = np.where(
                combined['combined_score'] > 200, 'strong_buy',
                np.where(combined['combined_score'] > 100, 'buy',
                np.where(combined['combined_score'] > -100, 'hold',
                np.where(combined['combined_score'] > -200, 'sell', 'strong_sell')))
            )
            
            return combined[['candle_begin_time', 'combined_score', 'combined_filter']]
            
        except Exception as e:
            self.warn(f"计算综合过滤器失败: {e}")
            return pd.DataFrame()
    
    def _get_market_trend_filter(self, avg_score: float) -> str:
        """获取市场趋势过滤信号"""
        if avg_score >= 4:
            return "强势上涨趋势"
        elif avg_score >= 3:
            return "上涨趋势"
        elif avg_score >= 2:
            return "震荡偏多"
        elif avg_score >= 1:
            return "震荡偏空"
        else:
            return "下跌趋势"
    
    def _get_volatility_filter(self, avg_vol: float, high_vol_ratio: float) -> str:
        """获取波动率过滤信号"""
        if high_vol_ratio > 0.5:
            return "高波动环境-谨慎交易"
        elif avg_vol < 0.02:
            return "低波动环境-适合趋势跟踪"
        else:
            return "正常波动环境"
    
    def _get_momentum_filter(self, avg_score: float) -> str:
        """获取动量过滤信号"""
        if avg_score >= 3:
            return "强劲上涨动量"
        elif avg_score >= 1:
            return "正向动量"
        elif avg_score >= -1:
            return "动量中性"
        elif avg_score >= -3:
            return "负向动量"
        else:
            return "强劲下跌动量"

    def _calculate_tech_indicators(self, df, row, windows):
        """计算技术指标"""
        for window in windows:
            # 趋势强度
            trend_conditions = [
                (df['close'] > df[f'ma_{window}']).astype(int),
                (df['close'] > df['close'].shift(1)).astype(int)
            ]
            
            if f'rsi_{window}d' in df.columns:
                trend_conditions.append((df[f'rsi_{window}d'] > 50).astype(int))
            
            df[f'trend_strength_{window}d'] = np.mean(trend_conditions, axis=0) if trend_conditions else 0.5
            row[f'平均趋势强度_{window}d'] = df[f'trend_strength_{window}d'].mean()
            
            # 超买超卖
            if f'rsi_{window}d' in df.columns:
                overbought_count = (df[f'rsi_{window}d'] > 70).sum()
                oversold_count = (df[f'rsi_{window}d'] < 30).sum()
                total_count = len(df[f'rsi_{window}d'].dropna())
                
                if total_count > 0:
                    row[f'超买比例_{window}d'] = overbought_count / total_count
                    row[f'超卖比例_{window}d'] = oversold_count / total_count
            
            # MACD信号
            if f'macd_{window}d' in df.columns and f'macd_signal_{window}d' in df.columns:
                macd_bullish = (df[f'macd_{window}d'] > df[f'macd_signal_{window}d']).sum()
                macd_total = len(df[f'macd_{window}d'].dropna())
                if macd_total > 0:
                    row[f'MACD看涨比例_{window}d'] = macd_bullish / macd_total

    def _calculate_sentiment_indicators(self, df, row, windows):
        """计算情绪指标"""
        for window in windows:
            # 涨跌比
            up_count = (df[f'return_{window}d'] > 0).sum()
            down_count = (df[f'return_{window}d'] < 0).sum()
            total_count = len(df[f'return_{window}d'].dropna())
            
            if total_count > 0:
                row[f'涨跌比_{window}d'] = up_count / down_count if down_count > 0 else float('inf')
                row[f'上涨比例_{window}d'] = up_count / total_count
            
            # 波动率情绪
            avg_volatility = df[f'volatility_{window}d'].mean()
            if not pd.isna(avg_volatility):
                if avg_volatility < 0.02:
                    sentiment = '平静'
                elif avg_volatility < 0.05:
                    sentiment = '正常'
                elif avg_volatility < 0.08:
                    sentiment = '活跃'
                else:
                    sentiment = '狂热'
                row[f'波动情绪_{window}d'] = sentiment
            
            # 极端波动比例
            extreme_up = (df[f'return_{window}d'] > 0.15).sum()
            extreme_down = (df[f'return_{window}d'] < -0.15).sum()
            if total_count > 0:
                row[f'极端波动比例_{window}d'] = (extreme_up + extreme_down) / total_count

    def _calculate_structure_indicators(self, df, row, windows):
        """计算结构性指标"""
        for window in windows:
            # 市值分层分析
            df['market_cap'] = df['close'] * df['volume']
            df['市值排名'] = df['market_cap'].rank(ascending=False, method='first')
            
            # 分层收益
            large_cap = df[df['市值排名'] <= 10]  # 大市值
            mid_cap = df[(df['市值排名'] > 10) & (df['市值排名'] <= 30)]  # 中市值
            small_cap = df[df['市值排名'] > 30]  # 小市值
            
            if len(large_cap) > 0:
                row[f'大市值平均收益_{window}d'] = large_cap[f'return_{window}d'].mean()
            if len(mid_cap) > 0:
                row[f'中市值平均收益_{window}d'] = mid_cap[f'return_{window}d'].mean()
            if len(small_cap) > 0:
                row[f'小市值平均收益_{window}d'] = small_cap[f'return_{window}d'].mean()
            
            # 轮动强度
            if len(large_cap) > 0 and len(small_cap) > 0:
                large_return = large_cap[f'return_{window}d'].mean()
                small_return = small_cap[f'return_{window}d'].mean()
                row[f'大小盘轮动_{window}d'] = small_return - large_return
    
    def draw_index(self, df: pd.DataFrame, start_time=None, interval: str = '1d'):
        """
        绘制高级市场指标图表并保存到统一路径（函数级注释）
        参数:
            df: 指标结果数据
            start_time: 起始时间（可选）
            interval: 周期（用于标题展示）
        """
        if df is None or df.empty:
            self.warn('draw_index - df 为空，跳过绘图')
            return

        fig = plt.figure(tight_layout=False, figsize=(32, 16), dpi=80, facecolor='w', edgecolor='k')
        gs = gridspec.GridSpec(4, 2)
        
        # 子图1：价值指标
        ax1 = fig.add_subplot(gs[0, 0])
        if '市值加权价格_30d' in df.columns:
            ax1.plot(df['candle_begin_time'], df['市值加权价格_30d'], label='市值加权价格', color='blue')
        if '资金流向_30d' in df.columns:
            ax1_twin = ax1.twinx()
            ax1_twin.plot(df['candle_begin_time'], df['资金流向_30d'], label='资金流向', color='red', alpha=0.7)
        ax1.set_title('价值指标')
        ax1.legend(loc='upper left')
        if 'ax1_twin' in locals():
            ax1_twin.legend(loc='upper right')
        
        # 子图2：技术指标
        ax2 = fig.add_subplot(gs[0, 1])
        if '平均趋势强度_30d' in df.columns:
            ax2.plot(df['candle_begin_time'], df['平均趋势强度_30d'], label='趋势强度', color='green')
        if '超买比例_30d' in df.columns:
            ax2_twin = ax2.twinx()
            ax2_twin.plot(df['candle_begin_time'], df['超买比例_30d'], label='超买比例', color='red', alpha=0.7)
        ax2.set_title('技术指标')
        ax2.legend(loc='upper left')
        if 'ax2_twin' in locals():
            ax2_twin.legend(loc='upper right')
        
        # 子图3：情绪指标
        ax3 = fig.add_subplot(gs[1, 0])
        if '上涨比例_30d' in df.columns:
            ax3.plot(df['candle_begin_time'], df['上涨比例_30d'], label='上涨比例', color='purple')
        if '极端波动比例_30d' in df.columns:
            ax3_twin = ax3.twinx()
            ax3_twin.plot(df['candle_begin_time'], df['极端波动比例_30d'], label='极端波动比例', color='orange', alpha=0.7)
        ax3.set_title('情绪指标')
        ax3.legend(loc='upper left')
        if 'ax3_twin' in locals():
            ax3_twin.legend(loc='upper right')
        
        # 子图4：结构性指标
        ax4 = fig.add_subplot(gs[1, 1])
        if '大市值平均收益_30d' in df.columns:
            ax4.plot(df['candle_begin_time'], df['大市值平均收益_30d'], label='大市值收益', color='red')
        if '小市值平均收益_30d' in df.columns:
            ax4.plot(df['candle_begin_time'], df['小市值平均收益_30d'], label='小市值收益', color='blue')
        if '大小盘轮动_30d' in df.columns:
            ax4_twin = ax4.twinx()
            ax4_twin.plot(df['candle_begin_time'], df['大小盘轮动_30d'], label='大小盘轮动', color='green', alpha=0.7)
        ax4.set_title('结构性指标')
        ax4.legend(loc='upper left')
        if 'ax4_twin' in locals():
            ax4_twin.legend(loc='upper right')
        
        # 子图5：综合评分
        ax5 = fig.add_subplot(gs[2, :])
        for col in ['上涨比例_7d', '上涨比例_30d', '上涨比例_90d']:
            if col in df.columns:
                ax5.plot(df['candle_begin_time'], df[col], label=col, alpha=0.7)
        ax5.set_title('多周期上涨比例对比')
        ax5.legend()
        
        # 子图6：趋势强度对比
        ax6 = fig.add_subplot(gs[3, :])
        for col in ['平均趋势强度_7d', '平均趋势强度_30d', '平均趋势强度_90d']:
            if col in df.columns:
                ax6.plot(df['candle_begin_time'], df[col], label=col, alpha=0.7)
        ax6.set_title('多周期趋势强度对比')
        ax6.legend()
        
        plt.suptitle(self.indicator_title(), fontsize='large', fontweight='bold', color='blue')
        plt.tight_layout()
        
        # 使用基类统一路径保存
        plt.savefig(self.png_path(), bbox_inches='tight')
        plt.clf()
        plt.cla()
        plt.close('all')
    
    def save_indicators_to_csv(self, results: Dict, base_path: str = "."):
        """
        保存指标数据到CSV文件（弃用）
        
        参数:
            results: 指标计算结果（不再逐项单独保存）
            base_path: 保存路径（保留参数以兼容旧调用）
        行为:
            - 统一建议使用基类的 self.save_csv(df) 保存主结果
            - 如需多文件输出，请在上层流程自行处理
        """
        self.warn("save_indicators_to_csv 已弃用，请统一使用 self.save_csv(df) 和 self.png_path() 进行保存")
        return
    
    def generate_summary_report(self, results: Dict) -> str:
        """
        生成指标摘要报告
        
        Args:
            results: 指标计算结果
            
        Returns:
            str: 摘要报告
        """
        try:
            if 'indicators' not in results:
                return "无指标数据"
            
            report = f"""
📊 **高级指标分析报告**
⏰ 生成时间: {results.get('timestamp', datetime.now()).strftime('%Y-%m-%d %H:%M:%S')}

"""
            
            indicators = results['indicators']
            
            # 价值指标摘要
            if 'value' in indicators and indicators['value']:
                report += "💰 **价值指标**:\n"
                value_data = indicators['value']
                if 'mvrv_ratio' in value_data and not value_data['mvrv_ratio'].empty:
                    latest_mvrv = value_data['mvrv_ratio'].iloc[-1]
                    report += f"• MVRV比率: {latest_mvrv['mvrv_ratio']:.2f} ({latest_mvrv['mvrv_signal']})\n"
                
                if 'money_flow' in value_data and not value_data['money_flow'].empty:
                    latest_flow = value_data['money_flow'].iloc[-1]
                    report += f"• 资金流向比率: {latest_flow['flow_ratio']:.2f}\n"
                report += "\n"
            
            # 技术指标摘要
            if 'technical' in indicators and indicators['technical']:
                report += "📈 **技术指标**:\n"
                technical_data = indicators['technical']
                if 'trend_analysis' in technical_data and not technical_data['trend_analysis'].empty:
                    latest_trend = technical_data['trend_analysis'].iloc[-1]
                    report += f"• 市场情绪: {latest_trend['market_sentiment']}\n"
                    report += f"• 多头比例: {latest_trend['bullish_ratio']:.1%}\n"
                
                if 'overbought_oversold' in technical_data and not technical_data['overbought_oversold'].empty:
                    latest_obs = technical_data['overbought_oversold'].iloc[-1]
                    report += f"• 市场状态: {latest_obs['market_condition']}\n"
                report += "\n"
            
            # 情绪指标摘要
            if 'sentiment' in indicators and indicators['sentiment']:
                report += "😊 **情绪指标**:\n"
                sentiment_data = indicators['sentiment']
                if 'fear_greed_index' in sentiment_data and not sentiment_data['fear_greed_index'].empty:
                    latest_fg = sentiment_data['fear_greed_index'].iloc[-1]
                    report += f"• 恐慌贪婪指数: {latest_fg['fear_greed_index']:.0f} ({latest_fg['fear_greed_level']})\n"
                
                if 'sentiment_monitoring' in sentiment_data and not sentiment_data['sentiment_monitoring'].empty:
                    latest_sentiment = sentiment_data['sentiment_monitoring'].iloc[-1]
                    report += f"• 情绪等级: {latest_sentiment['sentiment_level']}\n"
                report += "\n"
            
            # CTA过滤器摘要
            if 'cta' in indicators and indicators['cta']:
                report += "🎯 **CTA过滤器**:\n"
                cta_data = indicators['cta']
                if 'combined_filter' in cta_data and not cta_data['combined_filter'].empty:
                    latest_cta = cta_data['combined_filter'].iloc[-1]
                    report += f"• 综合信号: {latest_cta['combined_filter']}\n"
                
                if 'trend_filter' in cta_data and not cta_data['trend_filter'].empty:
                    latest_trend_filter = cta_data['trend_filter'].iloc[-1]
                    report += f"• 趋势过滤: {latest_trend_filter['market_trend_filter']}\n"
                report += "\n"
            
            return report
            
        except Exception as e:
            self.warn(f"生成摘要报告失败: {e}")
            return "生成报告失败"


if __name__ == '__main__':
    advanced_indicator = 高级市场指标()
    advanced_indicator.stat(acc='qqdev', start_time='2021-01-01', backdays=90, windows=[7, 30, 90], save_img=True)