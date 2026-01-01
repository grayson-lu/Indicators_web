"""
横截面差异指数 Cross-Section Difference Index
衡量不同币种之间24小时涨跌表现的分化程度
统一流程：stat -> process_data -> save_csv -> draw_index
"""
import os
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from .base_indicator import BaseIndicator
from yquant.config.config import cfg

pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 180)

class CrossSectionDiffIndex(BaseIndicator):
    def indicator_slug(self) -> str:
        """
        指标保存文件前缀（与CSV/PNG文件名一致）
        """
        return 'cross_section_diff_index'

    def indicator_title(self) -> str:
        """指标图表标题"""
        return '横截面差异指数'

    def _get_proxies(self):
        """
        获取请求代理配置（函数级注释）
        优先环境变量HTTP_PROXY/HTTPS_PROXY，其次cfg.binance.proxies，最后示例http://127.0.0.1:7890
        返回可用于requests的proxies字典或None
        """
        http_p = os.environ.get('HTTP_PROXY')
        https_p = os.environ.get('HTTPS_PROXY')
        if http_p or https_p:
            return {'http': http_p or https_p, 'https': https_p or http_p}
        try:
            if getattr(cfg.binance, 'proxies', None):
                return cfg.binance.proxies
        except Exception:
            pass
        return {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}

    def _endpoints(self):
        """提供Binance 24h行情域名回退顺序"""
        return [
            'https://api.binance.com/api/v3/ticker/24hr',
            'https://api.binance.us/api/v3/ticker/24hr',
            'https://api1.binance.com/api/v3/ticker/24hr',
        ]

    def _fetch_24h(self, timeout=15, max_retry=5, base_delay=1.0):
        """
        拉取Binance 24h行情（函数级注释）
        - 域名回退：api.binance.com -> api.binance.us -> api1.binance.com
        - 指数退避重试：最多5次，基础延迟1s
        返回：DataFrame或None
        """
        proxies = self._get_proxies()
        last_err = None
        for att in range(1, max_retry + 1):
            for url in self._endpoints():
                try:
                    r = requests.get(url, timeout=timeout, proxies=proxies)
                    r.raise_for_status()
                    df = pd.DataFrame(r.json())
                    return df
                except Exception as e:
                    last_err = e
                    continue
            time.sleep(base_delay * (2 ** (att - 1)))
        self.warn(f"24h行情获取失败: {last_err}")
        return None

    def _filter_usdt_spot(self, df: pd.DataFrame):
        """
        过滤现货USDT交易对并排除杠杆代币UP/DOWN（函数级注释）
        """
        if df is None or df.empty:
            return pd.DataFrame()
        if 'symbol' not in df.columns or 'priceChangePercent' not in df.columns:
            return pd.DataFrame()
        s = df['symbol'].astype(str)
        keep = s.str.endswith('USDT') & (~s.str.contains('UP|DOWN', regex=True))
        out = df.loc[keep].copy()
        out['priceChangePercent'] = pd.to_numeric(out['priceChangePercent'], errors='coerce')
        out = out.dropna(subset=['priceChangePercent'])
        out = out[out['priceChangePercent'].abs() < 200]
        return out

    def stat(self, acc: str = 'qqdev', backdays=365, windows=[7, 30, 90], save_img=True, interval='1d', start_time=None):
        """
        统计横截面差异指数（函数级注释）
        行为：抓取24h行情 -> 过滤USDT -> 调用process_data -> 追加保存CSV -> 绘图
        异常：网络失败时读取本地CSV作为回退
        """
        tickers = self._fetch_24h()
        tickers = self._filter_usdt_spot(tickers)
        if tickers is None or tickers.empty:
            # 缓存回退
            try:
                df_hist = pd.read_csv(self.csv_path())
                if save_img:
                    self.draw_index(df_hist, start_time=start_time, interval=interval)
                return df_hist.tail(1)
            except Exception:
                self.warn('无可用网络数据且本地缓存不存在')
                return pd.DataFrame()
        df = self.process_data({'_tickers': tickers}, windows, backdays, interval, start_time)
        if df is None or df.empty:
            self.warn('process_data返回空')
            return pd.DataFrame()
        # 读取历史并追加、计算EMA7
        path = self.csv_path()
        if os.path.exists(path):
            hist = pd.read_csv(path)
            hist = pd.concat([hist, df], ignore_index=True)
            hist = hist.drop_duplicates(subset=['candle_begin_time'], keep='last')
        else:
            hist = df.copy()
        # EMA7平滑
        hist['diff_ema7'] = pd.to_numeric(hist.get('diff_raw', np.nan), errors='coerce').ewm(span=7, adjust=False).mean()
        hist['index_ema7'] = pd.to_numeric(hist.get('横截面差异指数', np.nan), errors='coerce').ewm(span=7, adjust=False).mean()
        self.save_csv(hist)
        if save_img:
            self.draw_index(hist, start_time=start_time, interval=interval)
        return df

    def process_data(self, df_dict, windows, backdays, interval, start_time):
        """
        处理数据计算横截面指标（函数级注释）
        输入：df_dict包含'_tickers'键，对应24h行情DataFrame
        输出：仅当前日一行的结果，包含candle_begin_time与核心指标
        """
        tickers = df_dict.get('_tickers')
        if tickers is None or tickers.empty:
            return pd.DataFrame()
        now_ts = datetime.now().strftime('%Y-%m-%d 00:00:00')
        ser = pd.to_numeric(tickers['priceChangePercent'], errors='coerce').dropna()
        if ser.empty:
            return pd.DataFrame()
        pct_rank = ser.rank(pct=True)
        top5 = ser[pct_rank >= 0.95]
        bot5 = ser[pct_rank <= 0.05]
        top10 = ser[pct_rank >= 0.90]
        bot10 = ser[pct_rank <= 0.10]
        diff_raw = (np.median(top5) - np.median(bot5)) if len(top5) and len(bot5) else np.nan
        diff_raw_10 = (top10.mean() - bot10.mean()) if len(top10) and len(bot10) else np.nan
        # 分布指标
        returns_std = ser.std()
        q75, q25 = ser.quantile(0.75), ser.quantile(0.25)
        iqr = q75 - q25
        gini = self.calculate_gini_coefficient(ser.values)
        skewness = ser.skew()
        kurtosis = ser.kurtosis()
        # 综合差异指数（加权）
        diff_index = 0.4 * abs(returns_std) + 0.3 * abs(iqr) + 0.3 * (abs(gini) * 100)
        # 强弱统计
        mean_r = ser.mean()
        strong = (ser > mean_r + returns_std).sum()
        weak = (ser < mean_r - returns_std).sum()
        neutral = len(ser) - strong - weak
        row = {
            'candle_begin_time': now_ts,
            '样本数量': len(ser),
            'diff_raw': diff_raw,
            'diff_raw_10': diff_raw_10,
            '收益率标准差': returns_std,
            '四分位距': iqr,
            '基尼系数': gini,
            '收益率偏度': skewness,
            '收益率峰度': kurtosis,
            '横截面差异指数': diff_index,
            '市场分化程度': self.get_differentiation_level(diff_index),
            '强势币种占比': strong / len(ser) * 100,
            '弱势币种占比': weak / len(ser) * 100,
            '中性币种占比': neutral / len(ser) * 100,
        }
        return pd.DataFrame([row])

    def calculate_gini_coefficient(self, returns: np.ndarray) -> float:
        """
        计算基尼系数（函数级注释）
        输入：收益率数组；输出：0-1之间的基尼系数
        """
        try:
            x = returns - np.nanmin(returns) + 1e-10
            x = np.sort(x)
            n = len(x)
            cumsum = np.cumsum(x)
            g = (n + 1 - 2 * np.sum(cumsum) / cumsum[-1]) / n
            return float(max(0, min(1, g)))
        except Exception:
            return 0.0

    def get_differentiation_level(self, diff_index: float) -> str:
        """
        根据差异指数给出分化评级（函数级注释）
        """
        if diff_index > 15:
            return '极度分化'
        elif diff_index > 10:
            return '高度分化'
        elif diff_index > 7:
            return '中度分化'
        elif diff_index > 4:
            return '轻度分化'
        else:
            return '趋同'

    def draw_index(self, df: pd.DataFrame, start_time=None, interval: str = '1d'):
        """
        绘制横截面差异指数图（函数级注释）
        显示：综合差异指数、收益率离散度与强弱占比
        保存到data/<slug>.png
        """
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
        if df is None or df.empty:
            self.warn('draw_index - 数据为空，跳过绘图')
            return
        fig = plt.figure(tight_layout=False, figsize=(28, 14), dpi=80)
        gs = gridspec.GridSpec(20, 12)
        ax1 = fig.add_subplot(gs[0:6, 0:11])
        ax1.plot(df['candle_begin_time'], df['横截面差异指数'], label='差异指数', color='tab:blue')
        if 'index_ema7' in df.columns:
            ax1.plot(df['candle_begin_time'], df['index_ema7'], label='EMA7', color='tab:orange')
        ax1.axhline(y=15, color='r', linestyle=':', alpha=0.7, label='极度分化(15)')
        ax1.axhline(y=10, color='orange', linestyle=':', alpha=0.7, label='高度分化(10)')
        ax1.axhline(y=7, color='yellow', linestyle=':', alpha=0.7, label='中度分化(7)')
        ax1.axhline(y=4, color='gray', linestyle='--', alpha=0.5, label='轻度分化(4)')
        ax1.set_ylabel('差异指数')
        ax1.set_title(self.indicator_title())
        ax1.legend(loc='upper left')
        ax1.grid(True, linestyle='--', alpha=0.3)
        ax2 = fig.add_subplot(gs[7:13, 0:11])
        ax2.plot(df['candle_begin_time'], df['收益率标准差'], label='标准差')
        ax2.plot(df['candle_begin_time'], df['四分位距'], label='四分位距', linestyle='--')
        ax2.set_ylabel('离散度')
        ax2.legend(loc='upper left')
        ax2.grid(True, linestyle='--', alpha=0.3)
        ax3 = fig.add_subplot(gs[14:19, 0:11])
        ax3.plot(df['candle_begin_time'], df['强势币种占比'], label='强势占比', color='red')
        ax3.plot(df['candle_begin_time'], df['弱势币种占比'], label='弱势占比', color='green', linestyle='--')
        ax3.set_ylabel('占比(%)')
        ax3.legend(loc='upper left')
        ax3.grid(True, linestyle='--', alpha=0.3)
        out = self.png_path()
        plt.savefig(out)
        self.log(f"已保存PNG: {out}")

# 模块级便捷入口：与其他文件保持一致风格
def process_data():
    """
    模块级包装入口（函数级注释）
    直接执行一次统计并输出结果行，便于快速调用
    """
    return CrossSectionDiffIndex().stat(acc='qqdev', save_img=True)
