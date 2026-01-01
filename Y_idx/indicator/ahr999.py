'''
AHR999指标
比特币囤币指标，由微博用户ahr999创建
AHR999 = (BTC价格 / BTC 200日定投成本) * (BTC价格 / BTC拟合价格)
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
# 顶部导入与路径修正（片段）
import os
import sys
# 将项目根目录加入 sys.path，解决 `No module named 'yquant'`
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib
matplotlib.use('Agg')  # 使用无界面后端，避免服务器无显示环境导致绘图报错
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

pd.set_option('display.unicode.ambiguous_as_wide', True)
pd.set_option('display.unicode.east_asian_width', True)
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 180)



from .base_indicator import BaseIndicator

class AHR999(BaseIndicator):

    def indicator_slug(self) -> str:
        """
        指标保存文件前缀
        """
        return 'ahr999'

    def indicator_title(self) -> str:
        """
        指标图表标题
        """
        return 'AHR999指标'

    def process_data(self, df_dict, windows, backdays, interval, start_time):
        '''
        处理数据计算AHR999指标
        '''
        if 'BTCUSDT' not in df_dict:
            self.warn("ahr999.process_data - 缺少BTCUSDT数据，无法计算AHR999指标")
            return pd.DataFrame()

        btc_df = df_dict['BTCUSDT'].copy()
        btc_df.reset_index(inplace=True)

        # 计算AHR999指标的各个组成部分
        for window in windows:
            # 1. 计算200日定投成本（200日移动平均）
            btc_df[f'ma_{window}'] = btc_df['close'].rolling(window=window, min_periods=1).mean()
            
            # 2. 计算拟合价格（使用指数增长模型拟合）
            btc_df[f'fitted_price_{window}'] = self.calculate_fitted_price(btc_df, window)
            
            # 3. 计算AHR999指标
            btc_df[f'price_to_ma_ratio_{window}'] = btc_df['close'] / btc_df[f'ma_{window}']
            btc_df[f'price_to_fitted_ratio_{window}'] = btc_df['close'] / btc_df[f'fitted_price_{window}']
            btc_df[f'ahr999_{window}'] = btc_df[f'price_to_ma_ratio_{window}'] * btc_df[f'price_to_fitted_ratio_{window}']
            
            # 4. 计算AHR999信号
            btc_df[f'ahr999_signal_{window}'] = btc_df[f'ahr999_{window}'].apply(self.get_ahr999_signal)
            
            # 5. 计算相对强度
            btc_df[f'ahr999_strength_{window}'] = btc_df[f'ahr999_{window}'].rolling(30).rank(pct=True)

        # 选择需要的列
        result_columns = ['candle_begin_time', 'close']
        for window in windows:
            result_columns.extend([
                f'ma_{window}', f'fitted_price_{window}', f'ahr999_{window}',
                f'ahr999_signal_{window}', f'ahr999_strength_{window}',
                f'price_to_ma_ratio_{window}', f'price_to_fitted_ratio_{window}'
            ])

        final_df = btc_df[result_columns].copy()
        
        if start_time is not None:
            final_df = final_df[final_df['candle_begin_time'] > start_time]

        # 统一保存到基类路径
        self.save_csv(final_df)
        self.log(final_df.tail().to_string())
        return final_df



    def calculate_fitted_price(self, df, window):
        '''
        计算BTC拟合价格（使用指数增长模型）
        '''
        try:
            # 创建时间序列（以天为单位）
            df_copy = df.copy()
            df_copy['days'] = range(len(df_copy))
            
            # 使用指数增长模型：price = a * exp(b * days)
            # 简化版本：使用对数线性回归
            valid_data = df_copy[df_copy['close'] > 0].copy()
            if len(valid_data) < window:
                return df_copy['close'].rolling(window, min_periods=1).mean()
            
            # 计算拟合价格
            fitted_prices = []
            for i in range(len(df_copy)):
                if i < window:
                    # 前期使用移动平均
                    fitted_price = df_copy['close'].iloc[:i+1].mean()
                else:
                    # 使用指数增长拟合
                    recent_data = valid_data.iloc[max(0, i-window):i+1]
                    if len(recent_data) > 10:
                        try:
                            # 简化的指数增长模型
                            log_prices = np.log(recent_data['close'])
                            days = recent_data['days']
                            
                            # 线性回归 log(price) = a + b * days
                            coeffs = np.polyfit(days, log_prices, 1)
                            fitted_log_price = coeffs[0] * df_copy['days'].iloc[i] + coeffs[1]
                            fitted_price = np.exp(fitted_log_price)
                        except:
                            fitted_price = recent_data['close'].mean()
                    else:
                        fitted_price = recent_data['close'].mean()
                
                fitted_prices.append(fitted_price)
            
            return pd.Series(fitted_prices, index=df_copy.index)
            
        except Exception as e:
            self.warn(f"ahr999.calculate_fitted_price 计算拟合价格失败: {e}")
            return df['close'].rolling(window, min_periods=1).mean()

    def get_ahr999_signal(self, ahr999_value):
        '''
        根据AHR999值获取投资建议信号
        '''
        if pd.isna(ahr999_value):
            return "无数据"
        elif ahr999_value < 0.45:
            return "抄底"
        elif ahr999_value < 1.2:
            return "定投"
        elif ahr999_value < 5:
            return "观望"
        else:
            return "逃顶"

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

    def draw_index(self, title, windows, equity_df):
        """
        显示AHR999指标图
        """
        # 移除这些导入，因为已经在文件顶部导入了
        # from matplotlib import pyplot as plt
        # import matplotlib.gridspec as gridspec
        # matplotlib.use('Agg')  # 这行也移除，因为已经在顶部设置了

        plt.rcParams['font.sans-serif'] = ['SimHei']
        plt.rcParams['axes.unicode_minus'] = False

        fig = plt.figure(tight_layout=False, figsize=(32, 12), dpi=80, facecolor='w', edgecolor='k')
        gs = gridspec.GridSpec(20, 12)
        
        # 上图：价格和移动平均
        ax1 = fig.add_subplot(gs[0:8, 0:11])
        ax1.plot(equity_df['candle_begin_time'], equity_df['close'], label='BTC价格', linewidth=2)
        for window in windows:
            ax1.plot(equity_df['candle_begin_time'], equity_df[f'ma_{window}'], 
                    label=f'{window}日移动平均', linestyle='--')
            ax1.plot(equity_df['candle_begin_time'], equity_df[f'fitted_price_{window}'], 
                    label=f'拟合价格_{window}', linestyle=':')
        
        ax1.set_ylabel('价格 (USDT)')
        ax1.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        ax1.grid(True, linestyle='--', alpha=0.3)
        ax1.set_title('BTC价格与移动平均', fontsize='medium', fontweight='bold')
    
        # 下图：AHR999指标
        ax2 = fig.add_subplot(gs[10:18, 0:11])
        for window in windows:
            ax2.plot(equity_df['candle_begin_time'], equity_df[f'ahr999_{window}'], 
                    label=f'AHR999_{window}', linewidth=2)
        
        # 添加参考线
        ax2.axhline(y=0.45, color='g', linestyle=':', alpha=0.7, label='抄底线(0.45)')
        ax2.axhline(y=1.2, color='orange', linestyle=':', alpha=0.7, label='定投线(1.2)')
        ax2.axhline(y=5, color='r', linestyle=':', alpha=0.7, label='逃顶线(5)')
        
        ax2.set_ylabel('AHR999指标')
        ax2.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        ax2.grid(True, linestyle='--', alpha=0.3)
        ax2.set_title('AHR999指标', fontsize='medium', fontweight='bold')
        
        plt.xticks(rotation=30)
        plt.tight_layout()
        plt.savefig(self.png_path(), bbox_inches='tight')
        plt.clf()
        plt.cla()
        plt.close('all')


if __name__ == '__main__':
    ahr999_indicator = AHR999()
    ahr999_indicator.stat(acc='qqdev', start_time='2021-01-01', backdays=7, windows=[200], save_img=True)
