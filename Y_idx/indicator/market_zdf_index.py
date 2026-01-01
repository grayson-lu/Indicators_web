'''
全市场涨跌幅指数（规范化重构）
- 接入 BaseIndicator 基类
- 统一 process_data 方法签名 (df_dict, windows, backdays, interval, start_time)
- 使用 self.top_n 进行活跃币种筛选
- 使用基类的保存与路径生成：self.save_csv() / self.png_path()
- 移除重复的交易所连接与模块级 data 目录创建
'''
import yquant.common.binance_utils as binance
import pandas as pd
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from .base_indicator import BaseIndicator
from yquant.db.models.bn_account import BnAccount
from yquant.config.config import cfg
import ccxt
import yquant.common.common_utils as common

pd.set_option('display.unicode.ambiguous_as_wide', True)
pd.set_option('display.unicode.east_asian_width', True)
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 180)


class 全市场涨跌幅(BaseIndicator):
    def indicator_slug(self) -> str:
        """
        指标保存文件前缀（函数级注释）
        返回统一的文件名前缀，用于 CSV/PNG。
        """
        return 'marketzdf_index'

    def indicator_title(self) -> str:
        """
        指标图表标题（函数级注释）
        用于绘图标题展示。
        """
        return '全市场涨跌幅指数'

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

    def stat(self, acc: str, backdays: int = 365, windows = [32], save_img: bool = True,
             interval: str = '1d', start_time = None):
        """
        统计全市场平均涨跌幅（函数级注释）
        参数:
        - acc: 账户标识，用于获取交易所连接
        - backdays: 回溯天数，用于数据抓取范围
        - windows: 统计窗口列表（例如 [32] 表示32日涨跌幅）
        - save_img: 是否保存图像
        - interval: 时间粒度，仅支持 '1d' 或 '1h'
        - start_time: 开始时间过滤（可为字符串或时间戳）
        行为:
        - 抓取交易对K线数据，计算各窗口的市场涨跌幅指数
        - 保存CSV与PNG（若开启）
        返回: 指标结果 DataFrame
        """
        self.log(f'统计全市场平均涨跌幅, windows = {windows}')
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

    def stat_with_data(self, df_dict, acc: str, start_time=None, backdays: int = 365, windows = [32],
                        save_img: bool = True, interval: str = '1d'):
        """
        使用已获取的数据统计全市场涨跌幅（函数级注释）
        参数:
        - df_dict: 预先获取的各交易对K线数据字典
        - 其他参数同 stat
        行为:
        - 直接使用传入数据进行计算并保存
        返回: 指标结果 DataFrame
        """
        self.log(f'使用已有数据统计全市场平均涨跌幅, windows = {windows}')
        df = self.process_data(df_dict, windows, backdays, interval, start_time)
        if df is not None and not df.empty:
            self.save_csv(df)
            if save_img:
                self.draw_index(df, start_time=start_time, interval=interval)
        return df

    def process_data(self, df_dict, windows, backdays, interval, start_time):
        """
        处理数据计算全市场涨跌幅（函数级注释）
        参数:
        - df_dict: {symbol: DataFrame} 的字典，包含K线数据
        - windows: 统计窗口列表
        - backdays: 回溯天数（用于外部数据抓取范围，此处用于窗口最大值计算）
        - interval: 时间粒度 '1d' 或 '1h'
        - start_time: 开始时间过滤
        行为:
        - 先按币种计算各窗口涨跌幅与7日滚动成交额
        - 再按时间点筛选成交额排名前 self.top_n 的币种，聚合为市场指数
        返回: 指标结果 DataFrame
        """
        # 记录最近使用的窗口，供绘图使用
        self._last_windows = list(windows) if isinstance(windows, (list, tuple)) else [windows]

        # 合并所有币种数据
        df_list = []
        for symbol, df in (df_dict or {}).items():
            if df is None or df.empty:
                continue
            df_list.append(df)
        if not df_list:
            self.warn("market_zdf_index.process_data - 初次汇总时 df_list 为空")
            return pd.DataFrame()
        all_df = pd.concat(df_list)
        all_df.reset_index(inplace=True)

        # 按币种分组计算N日涨跌幅与成交额
        df_list = []
        for symbol, _df in all_df.groupby('symbol'):
            _df = _df.copy()
            for w in self._last_windows:
                _df[f'涨跌幅{w}d'] = _df['close'].pct_change(w)
            if interval == '1h':
                _df['成交额'] = _df['quote_volume'].rolling(24 * 7, min_periods=1).sum()  # 7d成交额
            elif interval == '1d':
                _df['成交额'] = _df['quote_volume'].rolling(7, min_periods=1).sum()      # 7d成交额
            else:
                _df['成交额'] = _df['quote_volume']
            df_list.append(_df)
        if not df_list:
            self.warn("market_zdf_index.process_data - 分币种计算后 df_list 为空")
            return pd.DataFrame()
        all_df = pd.concat(df_list)
        all_df.reset_index(inplace=True)

        # 指数聚合：按时间点筛选成交额前 self.top_n
        rows = []
        for candle_begin_time, _df in all_df.groupby('candle_begin_time'):
            _df = _df.copy()
            _df['成交额排名'] = _df['成交额'].rank(ascending=False, method='first')
            _df = _df[_df['成交额排名'] <= self.top_n]

            row = {'candle_begin_time': candle_begin_time}
            total = 0.0
            for w in self._last_windows:
                val = _df[f'涨跌幅{w}d'].mean() if len(_df) > 0 else 0.0
                row[f'全市场涨跌幅指数{w}d'] = val
                total += val
            row['全市场涨跌幅指数'] = total / max(len(self._last_windows), 1)
            rows.append(row)

        final_df = pd.DataFrame(rows)
        if start_time is not None and not final_df.empty:
            try:
                final_df = final_df[final_df['candle_begin_time'] > pd.to_datetime(start_time)]
            except Exception:
                final_df = final_df[final_df['candle_begin_time'] > start_time]
        return final_df

    def draw_index(self, df: pd.DataFrame, start_time=None, interval: str = '1d'):
        """
        绘制全市场涨跌幅指数图（函数级注释）
        参数:
        - df: 指标结果数据
        - start_time: 用于标题或过滤展示（可选）
        - interval: 时间粒度（用于标题展示）
        行为:
        - 绘制各窗口的市场涨跌幅曲线，并保存到 self.png_path()
        """
        if df is None or df.empty:
            self.warn('draw_index - df 为空，跳过绘图')
            return

        # 推断窗口列表
        windows = self._last_windows if hasattr(self, '_last_windows') and self._last_windows else []
        if not windows:
            for col in df.columns:
                if col.startswith('全市场涨跌幅指数') and col.endswith('d'):
                    try:
                        w = int(col.replace('全市场涨跌幅指数', '').replace('d', ''))
                        windows.append(w)
                    except Exception:
                        pass
        windows = sorted(set(windows))

        # 绘图
        fig = plt.figure(tight_layout=False, figsize=(32, 8), dpi=80, facecolor='w', edgecolor='k')
        gs = gridspec.GridSpec(10, 12)
        ax = fig.add_subplot(gs[0:10, 0:11])
        for w in windows:
            col = f'全市场涨跌幅指数{w}d'
            if col in df.columns:
                ax.plot(df['candle_begin_time'], df[col], label=col)
        ax.legend(bbox_to_anchor=(1.02, 0.5), loc='center left', borderaxespad=0)
        plt.xticks(rotation=30)
        plt.grid(True, linestyle='--', alpha=0.3)
        plt.title(self.indicator_title(), fontsize='large', fontweight='bold', color='blue', loc='center')
        plt.tight_layout()
        plt.savefig(self.png_path(), bbox_inches='tight')
        plt.clf()
        plt.cla()
        plt.close('all')


if __name__ == '__main__':
     indicator = 全市场涨跌幅()
     df = indicator.stat(
         acc='qqdev',
         start_time='2021-01-01',
         backdays=1200,
         windows=[32],
         save_img=True,
         interval='1d'
     )
     indicator.log(f"全市场涨跌幅指数结果样例:\n{df.tail()}")
