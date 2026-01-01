'''
截面波动率指标
Volatility Index
统一继承 BaseIndicator，统一方法签名与保存路径，移除主入口
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
from matplotlib.ticker import PercentFormatter
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False
from .base_indicator import BaseIndicator


class 截面波动率(BaseIndicator):
    def indicator_slug(self) -> str:
        """
        返回统一保存前缀（CSV/PNG 文件名使用）
        """
        return "volatility_index"

    def indicator_title(self) -> str:
        """
        返回统一的图表标题
        """
        return "截面波动率指数"

    def stat(self, acc:str, backdays=365, volatility_windows = [30], save_img = True, interval = '1d', start_time = None):
        """
        统计截面波动率指标（统一入口）
        参数:
        - acc/backdays/volatility_windows->windows/interval/start_time 按统一约定
        返回: 指标结果 DataFrame
        """
        windows = volatility_windows
        self.log(f'统计截面波动率, windows = {windows}')
        # 生成模拟数据：symbol, candle_begin_time, close
        end = pd.Timestamp.now(); start = end - pd.Timedelta(days=backdays + 30)
        dates = pd.date_range(start=start, end=end, freq='1D')
        syms = ['BTCUSDT','ETHUSDT','BNBUSDT','ADAUSDT','XRPUSDT','SOLUSDT']
        rows = []
        for t in dates:
            for s in syms:
                base = 100 + np.random.normal(0, 5);
                trend = np.sin(len(rows) * 0.01) * 2
                vol = np.random.normal(0, 1)
                price = max(1, base + trend + vol)
                rows.append({'candle_begin_time': t, 'symbol': s, 'close': price})
        df = pd.DataFrame(rows)
        return self.process_data(df, windows, backdays, interval, start_time)

    def stat_with_data(self, df_dict, acc:str, start_time=None, backdays=365, volatility_windows=[30], save_img=True, interval='1d'):
        """
        使用已有数据统计截面波动率（统一入口）
        - 未传入 df_dict 时自动生成模拟数据
        """
        windows = volatility_windows
        if df_dict is None:
            return self.stat(acc, backdays, windows, save_img, interval, start_time)
        return self.process_data(df_dict, windows, backdays, interval, start_time)

    def process_data(self, df_dict, windows, backdays, interval, start_time):
        """
        处理数据并计算截面波动率（统一签名）
        参数:
        - df_dict: DataFrame 或 dict（键为币种，值为DataFrame）
        - windows: 移动窗口列表（单位天）
        - backdays/interval/start_time: 统一约定
        返回: 指标结果 DataFrame，并通过 self.save_csv 保存
        """
        # 统一为一个 DataFrame
        price_df = None
        if isinstance(df_dict, pd.DataFrame):
            price_df = df_dict
        elif isinstance(df_dict, dict) and df_dict:
            try:
                parts = []
                for sym, _df in df_dict.items():
                    if _df is None or _df.empty:
                        continue
                    tmp = _df.copy()
                    if 'symbol' not in tmp.columns:
                        tmp['symbol'] = sym
                    parts.append(tmp)
                if parts:
                    price_df = pd.concat(parts, ignore_index=True)
            except Exception as e:
                self.warn(f'价格字典合并失败: {e}')
                price_df = None
        if price_df is None or not isinstance(price_df, pd.DataFrame) or price_df.empty:
            self.warn('截面波动率 - 输入数据为空或类型不正确')
            return pd.DataFrame()
        df = price_df.copy()
        df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'])
        df = df.sort_values(['candle_begin_time','symbol'])
        df['ret_1d'] = df.groupby('symbol')['close'].pct_change()
        # 计算截面波动率：每个时间点各币种收益率的标准差
        rows = []
        for t, g in df.groupby('candle_begin_time'):
            row = {'candle_begin_time': t}
            rets = g['ret_1d'].dropna()
            row['截面波动率'] = rets.std() * 100 if len(rets) > 0 else np.nan
            rows.append(row)
        out = pd.DataFrame(rows).sort_values('candle_begin_time')
        # 计算动量与窗口均值
        out['波动率动量'] = out['截面波动率'].diff()
        for w in windows:
            out[f'截面波动率_{w}d'] = out['截面波动率'].rolling(w).mean()
            out[f'波动率动量_{w}d'] = out['波动率动量'].rolling(w).mean()
        if start_time is not None:
            out = out[out['candle_begin_time'] > pd.to_datetime(start_time)]
        self.save_csv(out)
        if not out.empty:
            self.log(out.tail().to_string())
        return out

    def draw_index(self, title, windows, df):
        """
        显示截面波动率指数图（统一签名/统一保存路径）
        参数说明：
            - title: 图表标题
            - windows: 移动窗口列表（单位：天）
            - df: 指标结果的 DataFrame
        功能说明：
            - 根据结果数据绘制多子图，包括截面波动率、波动率动量等；
            - 自动保存图片到统一路径（self.png_path）；
        """
        fig = plt.figure(tight_layout=False, figsize=(32, 16), dpi=80, facecolor='w', edgecolor='k')
        gs = gridspec.GridSpec(30, 12)
        
        # 子图1：截面波动率及其移动均值
        ax1 = fig.add_subplot(gs[0:8, 0:11])
        ax1.plot(df['candle_begin_time'], df['截面波动率'], label='截面波动率', color='blue', linewidth=2)
        for window in windows:
            col_name = f'截面波动率_{window}d'
            if col_name in df.columns:
                ax1.plot(df['candle_begin_time'], df[col_name], label=f'MA{window}d', alpha=0.7)
        ax1.set_ylabel('波动率')
        ax1.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        ax1.grid(True, linestyle='--', alpha=0.3)
        ax1.set_title('截面波动率与移动均值', fontsize='medium', fontweight='bold')

        # 子图2：波动率动量
        ax2 = fig.add_subplot(gs[10:18, 0:11])
        ax2.plot(df['candle_begin_time'], df['波动率动量'], label='波动率动量', color='purple', linewidth=2)
        for window in windows:
            col_name = f'波动率动量_{window}d'
            if col_name in df.columns:
                ax2.plot(df['candle_begin_time'], df[col_name], label=f'动量{window}d', alpha=0.7)
        ax2.set_ylabel('动量')
        ax2.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        ax2.grid(True, linestyle='--', alpha=0.3)
        ax2.set_title('波动率动量', fontsize='medium', fontweight='bold')

        # 子图3：波动率与风险区域
        ax3 = fig.add_subplot(gs[20:28, 0:11])
        ax3.plot(df['candle_begin_time'], df['截面波动率'], label='截面波动率', color='blue', linewidth=2)
        ax3.axhline(y=df['截面波动率'].mean(), color='black', linestyle='-', alpha=0.5, label='均值')
        ax3.axhline(y=df['截面波动率'].mean() + df['截面波动率'].std(), color='orange', linestyle=':', alpha=0.7, label='均值+1σ')
        ax3.axhline(y=df['截面波动率'].mean() - df['截面波动率'].std(), color='green', linestyle=':', alpha=0.7, label='均值-1σ')
        ax3.set_ylabel('波动率')
        ax3.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        ax3.grid(True, linestyle='--', alpha=0.3)
        ax3.set_title('波动率风险区域', fontsize='medium', fontweight='bold')

        # 统一保存到基类路径
        plt.xticks(rotation=30)
        plt.tight_layout()
        png_file = self.png_path()
        plt.savefig(png_file, bbox_inches='tight')
        self.log(f'图表已保存: {png_file}')
        
        plt.close('all')

    def draw_combined_volatility_chart(self, windows, equity_df):
        """
        额外组合图：叠加多个窗口的市场波动率指数与中位数
        输出仍使用 png_path 派生文件名，但不保留多余的清理代码
        """
        if equity_df is None or len(equity_df) == 0:
            self.warn("volatility_index.draw_index - 指标结果数据为空，跳过绘图")
            return
        fig = plt.figure(tight_layout=False, figsize=(32, 16), dpi=80, facecolor='w', edgecolor='k')
        gs = gridspec.GridSpec(2, 1, height_ratios=[3, 1])
        ax1 = fig.add_subplot(gs[0]); ax2 = fig.add_subplot(gs[1], sharex=ax1)
        colors = plt.cm.tab10.colors
        for i, window in enumerate(windows):
            idx_col = f'市场波动率指数_{window}d'
            med_col = f'市场波动率中位数_{window}d'
            if idx_col in equity_df.columns:
                ax1.plot(equity_df['candle_begin_time'], equity_df[idx_col], label=idx_col, color=colors[i], linestyle='-')
            if med_col in equity_df.columns:
                ax1.plot(equity_df['candle_begin_time'], equity_df[med_col], label=med_col, color=colors[i], linestyle='--')
        ax1.legend(loc='upper left'); plt.xticks(rotation=30); plt.grid(True, linestyle='--', alpha=0.3)
        plt.tight_layout()
        combined_path = self.png_path('volatility_index')
        if combined_path.lower().endswith('.png'):
            combined_path = combined_path[:-4] + '_combined.png'
        else:
            combined_path = combined_path + '_combined.png'
        plt.savefig(combined_path, bbox_inches='tight')
        self.log(f'截面波动率指数综合图已保存到 {combined_path}')
        plt.close('all')
