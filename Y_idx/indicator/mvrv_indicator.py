'''
MVRV指标
Market Value to Realized Value
市场价值与实现价值比率
用于评估比特币和加密货币的估值水平
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


class MVRV指标(BaseIndicator):

    def indicator_slug(self) -> str:
        """
        指标保存文件前缀（函数级注释）
        返回统一的文件名前缀，用于 CSV/PNG。
        """
        return 'mvrv_indicator'

    def indicator_title(self) -> str:
        """
        指标图表标题（函数级注释）
        用于绘图标题展示。
        """
        return 'MVRV指标'

    def stat(self, acc: str, backdays=365, windows=[30, 90, 180, 365], save_img=True, interval='1d', start_time=None):
        '''
        统计MVRV指标（函数级注释）
        参数:
        - acc: 账户标识，用于获取交易所连接
        - backdays: 回溯天数
        - windows: 统计窗口列表
        - save_img: 是否保存图像
        - interval: 时间粒度 '1d' 或 '1h'
        - start_time: 开始时间过滤
        行为:
        - 抓取交易对K线数据，计算MVRV相关指标
        - 保存CSV与PNG（若开启）
        返回: 指标结果 DataFrame
        '''
        self.log(f'统计MVRV指标, windows = {windows}')
        exchange = self.get_default_exchange(acc)
        exchange_rules = binance.u_furture_get_exchangeinfo(exchange)
        symbol_list = [s['symbol'] for s in exchange_rules['symbols']
                       if s.get('status') == 'TRADING' and s.get('quoteAsset') == 'USDT' and s.get('contractType') == 'PERPETUAL']
        run_time = common.cacu_run_time('1h', datetime.now())
        max_day = max(max(windows), backdays)

        if interval == '1h':
            df_dict = binance.u_furture_fetch_all_swap_candle_data(exchange, symbol_list, '1h', run_time, 24 * max_day * 2 + 10, True, False, njobs=8)
        elif interval == '1d':
            df_dict = binance.u_furture_fetch_all_swap_candle_data(exchange, symbol_list, '1d', run_time, max_day * 2 + 10, True, False, njobs=8)
        else:
            self.warn(f"不支持的 interval: {interval}")
            return pd.DataFrame()

        df = self.process_data(df_dict, windows, backdays, interval, start_time)
        if df is not None and not df.empty:
            self.save_csv(df)
            if save_img:
                self.draw_index(df, start_time=start_time, interval=interval)
        return df

    def stat_with_data(self, df_dict, acc: str, start_time=None, backdays=365, windows=[30, 90, 180, 365], save_img=True, interval='1d'):
        '''
        使用已获取的数据统计MVRV指标（函数级注释）
        参数同 stat
        '''
        self.log(f'使用已有数据统计MVRV指标, windows = {windows}')
        df = self.process_data(df_dict, windows, backdays, interval, start_time)
        if df is not None and not df.empty:
            self.save_csv(df)
            if save_img:
                self.draw_index(df, start_time=start_time, interval=interval)
        return df

    def process_data(self, df_dict, windows, backdays, interval, start_time):
        '''
        处理数据计算MVRV指标（函数级注释）
        参数:
        - df_dict: {symbol: DataFrame} 的字典
        - windows: 统计窗口列表
        - backdays: 回溯天数（用于外部抓取范围）
        - interval: 时间粒度
        - start_time: 开始时间过滤
        行为:
        - 分币种计算MVRV系列指标与成交额
        - 按时间点筛选成交额前 self.top_n 的币种聚合为市场指标
        返回: 指标结果 DataFrame
        '''
        # 全币种数据合成一个df
        df_list = []
        for symbol in df_dict:
            df = df_dict[symbol]
            df_list.append(df)
        # 修复：检查 df_list 并正确 concat
        if not df_list:
            self.warn("mvrv_indicator.process_data - 初次汇总时 df_list 为空，返回空DataFrame")
            return pd.DataFrame()
        all_df = pd.concat(df_list)
        all_df.reset_index(inplace=True)

        # 按币种分组计算MVRV相关指标
        df_list = []
        for symbol, _df in all_df.groupby('symbol'):
            # 统一时间序列与数值类型
            _df = _df.copy()
            _df['candle_begin_time'] = pd.to_datetime(_df['candle_begin_time'], errors='coerce')
            _df = _df.dropna(subset=['candle_begin_time']).sort_values('candle_begin_time')
            _df['close'] = pd.to_numeric(_df['close'], errors='coerce')
            _df['volume'] = pd.to_numeric(_df['volume'], errors='coerce').fillna(0)

            # 计算成交量加权平均价格作为实现价值的近似（加入稳健性保护）
            vol_sum_30 = _df['volume'].rolling(30, min_periods=30).sum()
            pv_sum_30 = (_df['volume'] * _df['close']).rolling(30, min_periods=30).sum()
            _df['vwap'] = np.where(vol_sum_30 > 0, pv_sum_30 / vol_sum_30, np.nan)
            
            # 计算各窗口期的MVRV指标
            for window in windows:
                # 方法1：使用移动平均作为实现价值（严格窗口）
                _df[f'realized_value_ma_{window}d'] = _df['close'].rolling(window, min_periods=window).mean()
                _df[f'mvrv_ma_{window}d'] = _df['close'] / _df[f'realized_value_ma_{window}d']

                # 方法2：使用成交量加权平均价格作为实现价值（严格窗口 + 除零保护）
                vol_sum = _df['volume'].rolling(window, min_periods=window).sum()
                pv_sum = (_df['volume'] * _df['close']).rolling(window, min_periods=window).sum()
                _df[f'realized_value_vwap_{window}d'] = np.where(vol_sum > 0, pv_sum / vol_sum, np.nan)
                _df[f'mvrv_vwap_{window}d'] = _df['close'] / _df[f'realized_value_vwap_{window}d']

                # 方法3：使用成本基础模型（累积成交量加权）
                _df[f'cost_basis_{window}d'] = self.calculate_cost_basis(_df, window)
                _df[f'mvrv_cost_{window}d'] = _df['close'] / _df[f'cost_basis_{window}d']

                # 计算MVRV Z-Score（std 为 0 时返回 NaN）
                mvrv_mean = _df[f'mvrv_ma_{window}d'].rolling(window, min_periods=window).mean()
                mvrv_std = _df[f'mvrv_ma_{window}d'].rolling(window, min_periods=window).std()
                _df[f'mvrv_zscore_{window}d'] = (_df[f'mvrv_ma_{window}d'] - mvrv_mean) / mvrv_std.replace(0, np.nan)

                # 计算MVRV历史百分位（扩展窗口，时间因果）
                _df[f'mvrv_percentile_{window}d'] = _df[f'mvrv_ma_{window}d'].expanding(min_periods=window).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1])

                # 计算MVRV趋势（严格窗口）
                _df[f'mvrv_trend_{window}d'] = _df[f'mvrv_ma_{window}d'].rolling(7, min_periods=7).mean().pct_change()

                # 计算MVRV信号
                _df[f'mvrv_signal_{window}d'] = _df[f'mvrv_ma_{window}d'].apply(self.get_mvrv_signal)

                # 计算超买超卖区域
                _df[f'mvrv_overbought_{window}d'] = (_df[f'mvrv_ma_{window}d'] > 3.7).astype(int)
                _df[f'mvrv_oversold_{window}d'] = (_df[f'mvrv_ma_{window}d'] < 1.0).astype(int)
            
            # 添加成交额统计
            if interval == '1h':
                _df['成交额'] = _df['quote_volume'].rolling(24 * 7, min_periods=1).sum()
            elif interval == '1d':
                _df['成交额'] = _df['quote_volume'].rolling(7, min_periods=1).sum()
            
            df_list.append(_df)
        # 修复：检查 df_list 并正确 concat
        if not df_list:
            self.warn("mvrv_indicator.process_data - 分币种计算后 df_list 为空，返回空DataFrame")
            return pd.DataFrame()
        all_df = pd.concat(df_list)
        all_df.reset_index(inplace=True)

        # 计算市场整体MVRV指标
        dfs = []
        for candle_begin_time, _df in all_df.groupby('candle_begin_time'):
            _df = _df.copy()

            # 过滤成交额前n的币种
            _df['成交额排名'] = _df['成交额'].rank(ascending=False, method='first')
            _df = _df[_df['成交额排名'] <= self.top_n]  # 只考虑成交额排名前top_n的币种
            
            if len(_df) == 0:
                continue

            row = {'candle_begin_time': candle_begin_time}
            row['币种数量'] = len(_df)
            
            for window in windows:
                # 市场平均MVRV指标
                valid_mvrv_ma = _df[f'mvrv_ma_{window}d'].dropna()
                valid_mvrv_vwap = _df[f'mvrv_vwap_{window}d'].dropna()
                valid_mvrv_cost = _df[f'mvrv_cost_{window}d'].dropna()
                valid_zscore = _df[f'mvrv_zscore_{window}d'].dropna()
                valid_percentile = _df[f'mvrv_percentile_{window}d'].dropna()
                
                if len(valid_mvrv_ma) > 0:
                    # 市场平均MVRV比率
                    row[f'市场MVRV_MA_{window}d'] = valid_mvrv_ma.mean()
                    row[f'市场MVRV_VWAP_{window}d'] = valid_mvrv_vwap.mean()
                    row[f'市场MVRV_Cost_{window}d'] = valid_mvrv_cost.mean()
                    
                    # 市场MVRV中位数
                    row[f'市场MVRV中位数_{window}d'] = valid_mvrv_ma.median()
                    
                    # 市场MVRV Z-Score
                    row[f'市场MVRV_ZScore_{window}d'] = valid_zscore.mean()
                    
                    # 市场MVRV百分位数
                    row[f'市场MVRV百分位_{window}d'] = valid_percentile.mean() * 100
                    
                    # 超买超卖统计
                    overbought_count = _df[f'mvrv_overbought_{window}d'].sum()
                    oversold_count = _df[f'mvrv_oversold_{window}d'].sum()
                    
                    row[f'超买币种数_{window}d'] = overbought_count
                    row[f'超卖币种数_{window}d'] = oversold_count
                    row[f'超买币种占比_{window}d'] = (overbought_count / len(_df)) * 100
                    row[f'超卖币种占比_{window}d'] = (oversold_count / len(_df)) * 100
                    
                    # MVRV分布统计
                    high_mvrv = len(_df[_df[f'mvrv_ma_{window}d'] > 2.5])
                    medium_mvrv = len(_df[(_df[f'mvrv_ma_{window}d'] >= 1.5) & (_df[f'mvrv_ma_{window}d'] <= 2.5)])
                    low_mvrv = len(_df[_df[f'mvrv_ma_{window}d'] < 1.5])
                    
                    row[f'高MVRV币种数_{window}d'] = high_mvrv
                    row[f'中MVRV币种数_{window}d'] = medium_mvrv
                    row[f'低MVRV币种数_{window}d'] = low_mvrv
                    
                    row[f'高MVRV占比_{window}d'] = (high_mvrv / len(_df)) * 100
                    row[f'中MVRV占比_{window}d'] = (medium_mvrv / len(_df)) * 100
                    row[f'低MVRV占比_{window}d'] = (low_mvrv / len(_df)) * 100
                    
                    # 市场MVRV信号
                    avg_mvrv = valid_mvrv_ma.mean()
                    row[f'市场MVRV信号_{window}d'] = self.get_mvrv_signal(avg_mvrv)
                    
                    # 市场估值状态
                    row[f'市场估值状态_{window}d'] = self.get_valuation_status(avg_mvrv, valid_percentile.mean())
                    
                else:
                    # 填充默认值
                    for col in [f'市场MVRV_MA_{window}d', f'市场MVRV_VWAP_{window}d', 
                               f'市场MVRV_Cost_{window}d', f'市场MVRV中位数_{window}d',
                               f'市场MVRV_ZScore_{window}d', f'市场MVRV百分位_{window}d']:
                        row[col] = np.nan
                    row[f'市场MVRV信号_{window}d'] = "无数据"
                    row[f'市场估值状态_{window}d'] = "无数据"
            
            dfs.append(pd.DataFrame([row]))

        final_df = pd.concat(dfs, ignore_index=True)
        
        if start_time is not None:
            final_df = final_df[final_df['candle_begin_time'] > start_time]

        # 保存到统一路径
        self.save_csv(final_df)
        self.log(f"MVRV指标结果样例:\n{final_df.tail(3)}")

        return final_df

    def calculate_cost_basis(self, df, window):
        '''
        计算成本基础（累积成交量加权平均价格）
        '''
        try:
            cost_basis = []
            for i in range(len(df)):
                if i < window:
                    # 前期使用简单平均
                    cost_basis.append(df['close'].iloc[:i+1].mean())
                else:
                    # 使用成交量加权
                    recent_data = df.iloc[i-window+1:i+1]
                    if recent_data['volume'].sum() > 0:
                        weighted_price = (recent_data['close'] * recent_data['volume']).sum() / recent_data['volume'].sum()
                        cost_basis.append(weighted_price)
                    else:
                        cost_basis.append(recent_data['close'].mean())
            
            return pd.Series(cost_basis, index=df.index)
        except:
            return df['close'].rolling(window, min_periods=1).mean()

    def get_mvrv_signal(self, mvrv_value):
        '''
        根据MVRV值获取投资信号
        '''
        if pd.isna(mvrv_value):
            return "无数据"
        elif mvrv_value < 1.0:
            return "极度低估"
        elif mvrv_value < 1.5:
            return "低估"
        elif mvrv_value < 2.5:
            return "合理"
        elif mvrv_value < 3.7:
            return "高估"
        else:
            return "极度高估"

    def get_valuation_status(self, mvrv_value, percentile):
        '''
        根据MVRV值和百分位数获取估值状态
        '''
        if pd.isna(mvrv_value) or pd.isna(percentile):
            return "无数据"
        
        if mvrv_value > 3.7 and percentile > 90:
            return "泡沫区域"
        elif mvrv_value > 2.5 and percentile > 75:
            return "高估区域"
        elif mvrv_value < 1.0 and percentile < 25:
            return "价值区域"
        elif mvrv_value < 1.5 and percentile < 50:
            return "低估区域"
        else:
            return "合理区域"

    def get_default_exchange(self, acc: str):
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

    def draw_index(self, df: pd.DataFrame, start_time=None, interval: str = '1d'):
        """
        绘制MVRV指标图（函数级注释）
        参数:
        - df: 指标结果数据
        - start_time: 用于标题或过滤展示（可选）
        - interval: 时间粒度（用于标题展示）
        行为:
        - 绘制市场MVRV比率、百分位数与估值分布，并保存到 self.png_path()
        """
        if df is None or df.empty:
            self.warn('draw_index - df 为空，跳过绘图')
            return

        # 推断窗口列表（从列名提取）
        windows = []
        for col in df.columns:
            if col.startswith('市场MVRV_MA_') and col.endswith('d'):
                try:
                    w = int(col.split('_')[-1].replace('d', ''))
                    windows.append(w)
                except Exception:
                    pass
        windows = sorted(set(windows))
        if not windows:
            self.warn('draw_index - 未找到窗口数据')
            return

        fig = plt.figure(tight_layout=False, figsize=(32, 16), dpi=80, facecolor='w', edgecolor='k')
        gs = gridspec.GridSpec(30, 12)
        
        # 上图：MVRV比率
        ax1 = fig.add_subplot(gs[0:8, 0:11])
        for window in windows[:3]:
            ax1.plot(df['candle_begin_time'], df[f'市场MVRV_MA_{window}d'], label=f'MVRV_MA_{window}d')
        ax1.axhline(y=3.7, color='r', linestyle=':', alpha=0.7, label='极度高估(3.7)')
        ax1.axhline(y=2.5, color='orange', linestyle=':', alpha=0.7, label='高估(2.5)')
        ax1.axhline(y=1.5, color='yellow', linestyle=':', alpha=0.7, label='合理上限(1.5)')
        ax1.axhline(y=1.0, color='gray', linestyle='-', alpha=0.5, label='公允价值(1.0)')
        ax1.set_ylabel('MVRV比率')
        ax1.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        ax1.grid(True, linestyle='--', alpha=0.3)
        ax1.set_title('市场MVRV比率', fontsize='medium', fontweight='bold')

        # 中图：MVRV百分位数
        ax2 = fig.add_subplot(gs[10:18, 0:11])
        for window in windows[:3]:
            ax2.plot(df['candle_begin_time'], df[f'市场MVRV百分位_{window}d'], label=f'MVRV百分位_{window}d')
        ax2.axhline(y=90, color='r', linestyle=':', alpha=0.7, label='极高百分位(90%)')
        ax2.axhline(y=75, color='orange', linestyle=':', alpha=0.7, label='高百分位(75%)')
        ax2.axhline(y=50, color='gray', linestyle='-', alpha=0.5, label='中位数(50%)')
        ax2.axhline(y=25, color='lightgreen', linestyle=':', alpha=0.7, label='低百分位(25%)')
        ax2.axhline(y=10, color='g', linestyle=':', alpha=0.7, label='极低百分位(10%)')
        ax2.set_ylabel('百分位数 (%)')
        ax2.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        ax2.grid(True, linestyle='--', alpha=0.3)
        ax2.set_title('MVRV历史百分位数', fontsize='medium', fontweight='bold')

        # 下图：估值分布
        ax3 = fig.add_subplot(gs[20:28, 0:11])
        for window in windows[:2]:
            ax3.plot(df['candle_begin_time'], df[f'高MVRV占比_{window}d'], label=f'高估占比_{window}d', color='red')
            ax3.plot(df['candle_begin_time'], df[f'低MVRV占比_{window}d'], label=f'低估占比_{window}d', color='green', linestyle='--')
        ax3.set_ylabel('占比 (%)')
        ax3.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        ax3.grid(True, linestyle='--', alpha=0.3)
        ax3.set_title('市场估值分布', fontsize='medium', fontweight='bold')
        
        plt.xticks(rotation=30)
        plt.tight_layout()
        plt.savefig(self.png_path(), bbox_inches='tight')
        plt.clf()
        plt.cla()
        plt.close('all')


if __name__ == '__main__':
    mvrv_indicator = MVRV指标()
    mvrv_indicator.stat(acc='qqdev', start_time='2021-01-01', backdays=7, windows=[30, 90, 180, 365], save_img=True)
