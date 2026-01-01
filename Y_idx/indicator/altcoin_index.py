'''
山寨指数
参考：https://www.blockchaincenter.net/altcoin-season-index/
月度/季度/年度指标：过去周期内山寨币相对BTC表现
山寨指数 = 全市场前N活跃币种中，涨跌幅超过BTC的比例
'''
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from .base_indicator import BaseIndicator

# 设置pandas显示选项
pd.set_option('display.unicode.ambiguous_as_wide', True)
pd.set_option('display.unicode.east_asian_width', True)
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 180)

# 设置matplotlib中文字体
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False


class 山寨指数(BaseIndicator):
    def indicator_slug(self):
        """
        返回统一的保存前缀（CSV/PNG 文件名使用）
        """
        return "altcoin_index"

    def indicator_title(self):
        """
        返回统一的图表标题
        """
        return "山寨指数"

    def stat(self, acc: str, backdays=365, windows=[30], interval='1d', start_time=None):
        """
        统计山寨指数（统一入口）
        参数:
        - acc: 账户标识（保持统一签名）
        - backdays: 回溯天数
        - windows: 指标窗口列表（本指标使用涨跌幅周期）
        - interval: 周期 '1d' 或 '1h'
        - start_time: 起始时间过滤
        返回: 指标结果 DataFrame
        行为:
        - 生成模拟的行情数据（包含close/quote_volume），符合同步接口
        - 调用 process_data 统一计算与保存
        """
        self.log(f'统计山寨指数, windows = {windows}, interval = {interval}')
        end = pd.Timestamp.now(); start = end - pd.Timedelta(days=backdays + 30)
        freq = '1H' if interval == '1h' else '1D'
        dates = pd.date_range(start=start, end=end, freq=freq)
        symbols = ['BTCUSDT','ETHUSDT','BNBUSDT','ADAUSDT','XRPUSDT','SOLUSDT','DOTUSDT','MATICUSDT']
        df_dict = {}
        for s in symbols:
            base = 100 + np.random.normal(0, 5)
            prices = []
            qvols = []
            price = base
            for i, t in enumerate(dates):
                drift = np.sin(i * 0.01) * 0.5
                shock = np.random.normal(0, 1)
                price = max(0.5, price + drift + shock)
                prices.append(price)
                q = max(1, np.random.lognormal(mean=3, sigma=0.6)) * price
                qvols.append(q)
            df = pd.DataFrame({
                'candle_begin_time': dates,
                'symbol': s,
                'close': prices,
                'quote_volume': qvols,
            })
            df_dict[s] = df
        return self.process_data(df_dict, windows, backdays, interval, start_time)

    def stat_with_data(self, df_dict, acc: str, start_time=None, backdays=365, windows=[30], interval='1d'):
        """
        使用已有数据统计山寨指数（统一入口）
        参数:
        - df_dict: 预先获取的K线数据字典
        - 其余与 stat 相同
        返回: 指标结果 DataFrame
        """
        self.log(f'使用已有数据统计山寨指数, windows = {windows}, interval = {interval}')
        if not isinstance(df_dict, dict) or len(df_dict) == 0:
            return self.stat(acc=acc, backdays=backdays, windows=windows, interval=interval, start_time=start_time)
        return self.process_data(df_dict, windows, backdays, interval, start_time)

    def process_data(self, df_dict, windows, backdays, interval, start_time):
        """
        处理数据并计算山寨指数（统一签名）
        参数:
        - df_dict: 所有交易对的K线数据字典
        - windows: 指标窗口列表（涨跌幅周期，例如[30]表示30日）
        - backdays: 回溯天数（未直接使用）
        - interval: 周期 '1d' 或 '1h'
        - start_time: 起始时间过滤
        返回: 计算完成的 DataFrame（统一通过 self.save_csv 保存）
        """
        # 合并所有币种数据
        df_list = [df_dict[symbol] for symbol in df_dict]
        if not df_list:
            self.warn("altcoin_index.process_data - 初次汇总 df_list 为空")
            return pd.DataFrame()
            
        all_df = pd.concat(df_list)
        all_df.reset_index(inplace=True)

        # 分币种计算N日涨跌幅，并计算成交额
        df_list = []
        for symbol, _df in all_df.groupby('symbol'):
            _df = _df.copy()
            
            # 计算各窗口期的涨跌幅
            for statday in windows:
                _df[f'涨跌幅{statday}d'] = _df['close'].pct_change(statday)
            
            # 计算成交额（用于筛选活跃币种）
            if interval == '1h':
                _df['成交额'] = _df['quote_volume'].rolling(24 * 2, min_periods=1).sum()
            elif interval == '1d':
                _df['成交额'] = _df['quote_volume'].rolling(2, min_periods=1).sum()
                
            df_list.append(_df)
        
        if not df_list:
            self.warn("altcoin_index.process_data - 分币种 df_list 为空")
            return pd.DataFrame()
            
        all_df = pd.concat(df_list)
        all_df.reset_index(inplace=True)

        # 计算山寨指数
        rows = []
        for candle_begin_time, _df in all_df.groupby('candle_begin_time'):
            _df = _df.copy()
            
            # 筛选活跃币种（统一使用 self.top_n）
            _df['成交额排名'] = _df['成交额'].rank(ascending=False, method='first')
            _df = _df[_df['成交额排名'] <= self.top_n]
            
            if len(_df) == 0:
                continue
                
            altcoin_index_sum = 0
            btc_rank = 0
            total_rank = len(_df)
            
            for statday in windows:
                # 计算涨跌幅排名
                _df[f'涨跌幅排名{statday}d'] = _df[f'涨跌幅{statday}d'].rank(ascending=False, method='first')
                
                # 获取BTC排名
                btc_data = _df[_df['symbol'] == 'BTCUSDT']
                if len(btc_data) > 0:
                    btc_rank = btc_data[f'涨跌幅排名{statday}d'].iloc[0]
                    if pd.isna(btc_rank) or btc_rank > total_rank:
                        btc_rank = total_rank
                else:
                    btc_rank = total_rank
                
                # 计算山寨指数分量
                altcoin_index_sum += round(btc_rank / total_rank, 2)
            
            # 计算最终山寨指数
            altcoin_index = altcoin_index_sum / len(windows)
            
            rows.append({
                'candle_begin_time': candle_begin_time,
                'BTC排名': btc_rank,
                '全币种数量': total_rank,
                '山寨指数': altcoin_index
            })
        
        final_df = pd.DataFrame(rows)
        
        # 时间过滤
        if start_time is not None and not final_df.empty:
            final_df = final_df[final_df['candle_begin_time'] > pd.to_datetime(start_time)]
        
        # 统一保存与日志
        self.save_csv(final_df)
        if not final_df.empty:
            self.log(final_df.tail().to_string())
        return final_df

    def draw_index(self, title, windows, df):
        """
        绘制山寨指数曲线并保存到统一路径（统一签名）
        参数:
        - title: 图表标题
        - windows: 指标窗口列表
        - df: 指标结果数据
        """
        fig = plt.figure(tight_layout=False, figsize=(24, 8), dpi=80, facecolor='w', edgecolor='k')
        gs = gridspec.GridSpec(10, 12)
        ax = fig.add_subplot(gs[0:10, 0:11])
        
        # 绘制山寨指数曲线
        if not df.empty and '山寨指数' in df.columns:
            ax.plot(df['candle_begin_time'], df['山寨指数'], label='山寨指数', color='orange', linewidth=2)
        
        # 添加参考线
        ax.axhline(y=0.5, color='red', linestyle='--', alpha=0.7, label='中性线(0.5)')
        ax.axhline(y=0.75, color='green', linestyle='--', alpha=0.7, label='山寨季阈值(0.75)')
        
        ax.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        plt.xticks(rotation=30)
        plt.grid(True, linestyle='--', alpha=0.3)
        plt.title(title, fontsize='large', fontweight='bold', color='blue', loc='center')
        plt.tight_layout()
        
        # 使用基类统一路径保存
        plt.savefig(self.png_path(), bbox_inches='tight')
        plt.close('all')
