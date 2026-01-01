'''
市场指标模块
包含：BTC彩虹价表、山寨币月季年度指数、贪婪恐慌指数、BTC/ETH Dominance指数
'''
import os
import requests
import json
import pandas as pd
import numpy as np
from datetime import datetime
from pyecharts import options as opts
from pyecharts.charts import Line, Grid, Bar, Pie, Gauge
from pyecharts.components import Table
from .base_indicator import BaseIndicator

# 模块级工具函数：将输入转换为 list 的安全封装
def safe_to_list(data):
    """
    将数据安全地转为 Python 列表
    - 兼容 list、pandas Series/Index、numpy ndarray 以及其他可迭代对象
    - 对于标量返回单元素列表，对 None 返回空列表
    """
    if data is None:
        return []
    if hasattr(data, 'tolist'):
        return data.tolist()
    if isinstance(data, list):
        return data
    if hasattr(data, '__iter__') and not isinstance(data, (str, bytes)):
        return list(data)
    return [data]
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['SimHei']  
plt.rcParams['axes.unicode_minus'] = False

# 设置matplotlib使用非交互式后端，避免线程问题

# 代理设置，如果需要
proxies = None


# 目录创建由 BaseIndicator 统一处理
class CrossSectionDiffIndex(BaseIndicator):
    """横截面差异指数计算类（接入基类）"""

    def indicator_slug(self) -> str:
        """指标保存文件前缀（函数级注释）"""
        return 'cross_section_diff'

    def indicator_title(self) -> str:
        """指标图表标题（函数级注释）"""
        return '横截面差异指数'

    def __init__(self):
        pass
    
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
            from yquant.config.config import cfg as _cfg
            if getattr(_cfg.binance, 'proxies', None):
                return _cfg.binance.proxies
        except Exception:
            pass
        return {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}

    def _endpoints(self):
        """提供Binance 24h行情域名回退顺序（函数级注释）"""
        return [
            'https://api.binance.com/api/v3/ticker/24hr',
            'https://api.binance.us/api/v3/ticker/24hr',
            'https://api1.binance.com/api/v3/ticker/24hr',
        ]

    def _fetch_24h(self, timeout=12, max_retry=4, base_delay=1.0):
        """
        拉取Binance 24h行情（函数级注释）
        - 域名回退：api.binance.com -> api.binance.us -> api1.binance.com
        - 指数退避重试：最多4次，基础延迟1s
        返回：DataFrame或None
        """
        import time
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
    
    def detect_and_replace_anomalies(self, df, window_size=5, threshold=0.5):
        """
        检测并替换异常值（函数级注释）
        参数:
        - df: 包含横截面差异指数的数据框
        - window_size: 参考窗口大小
        - threshold: 判断异常的偏差阈值
        返回: 处理后的 DataFrame
        """
        # 确保数据按时间排序
        df = df.sort_values('candle_begin_time')
        
        # 创建一个新列用于存储处理后的值
        df['横截面差异指数_处理后'] = df['横截面差异指数']
        
        # 从第window_size+1行开始检查
        for i in range(window_size, len(df)):
            # 获取前window_size天的数据
            prev_values = df['横截面差异指数'].iloc[i-window_size:i]
            
            # 计算参考值(中位数)
            reference_value = prev_values.median()
            
            # 计算当前值与参考值的偏差
            current_value = df['横截面差异指数'].iloc[i]
            
            # 避免除以零
            if reference_value != 0:
                deviation = abs(current_value - reference_value) / abs(reference_value)
            else:
                deviation = abs(current_value - reference_value) / 1.0  # 使用1作为基准
            
            # 如果偏差超过阈值，则替换为参考值
            if deviation > threshold:
                self.warn(f"检测到异常值: 日期={df['candle_begin_time'].iloc[i]}, 原始值={current_value:.2f}, 参考值={reference_value:.2f}, 偏差={deviation:.2%}")
                df.loc[df.index[i], '横截面差异指数_处理后'] = reference_value
                df.loc[df.index[i], '是否异常值'] = True
            else:
                df.loc[df.index[i], '是否异常值'] = False
        
        return df
    
    def calculate_cross_section_diff(self, df_dict):
        """
        计算横截面差异指数（函数级注释）
        参数:
        - df_dict: 币种数据字典，键为币种名称，值为DataFrame
        返回: 包含横截面差异指数的 DataFrame
        """
        import pandas as pd
        import numpy as np
        
        self.log("开始计算横截面差异指数...")
        
        # 只使用现货币种数据
        spot_symbols = [s for s in df_dict.keys() if s.endswith('USDT') and not s.endswith('_PERP')]
        
        self.log(f"找到现货币种: {len(spot_symbols)}个")
        
        # 如果没有足够的现货币种，尝试使用Binance 24h行情作为回退
        if len(spot_symbols) < 20:
            self.warn(f"没有足够的现货币种进行横截面差异指数计算，只有{len(spot_symbols)}个")
            tickers = self._fetch_24h()
            tickers = self._filter_usdt_spot(tickers)
            if tickers is None or tickers.empty:
                # 进一步回退：尝试读取本地CSV
                try:
                    cached = pd.read_csv(self.csv_path())
                    # 只返回最新一行以维持流程
                    return cached.tail(1)
                except Exception:
                    return pd.DataFrame()
            # 使用24h涨跌幅直接计算当日横截面差异（无时间序列，仅一行）
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
            now_ts = datetime.now().strftime('%Y-%m-%d 00:00:00')
            row = {
                'candle_begin_time': now_ts,
                '横截面差异指数': 0.5 * diff_raw + 0.5 * diff_raw_10,
                'top5_median': np.median(top5) if len(top5) else np.nan,
                'bottom5_median': np.median(bot5) if len(bot5) else np.nan,
                'top10_mean': top10.mean() if len(top10) else np.nan,
                'bottom10_mean': bot10.mean() if len(bot10) else np.nan
            }
            return pd.DataFrame([row])
        
        # 计算所有现货币种的日收益率
        all_returns = []
        timestamps = None
        
        for symbol in spot_symbols:
            try:
                df = df_dict[symbol].copy()
                
                # 检查数据是否有效
                if len(df) < 10:
                    continue
                
                # 确保时间戳是datetime格式
                df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'])
                
                # 确保close列是数值型
                df['close'] = pd.to_numeric(df['close'], errors='coerce')
                
                # 检查是否有无效值
                if df['close'].isna().any():
                    df = df.dropna(subset=['close'])
                
                # 计算日线收益率
                df['daily_return'] = df['close'].pct_change(1) * 100  # 转为百分比
                
                # 移除开始的NaN值
                df = df.dropna(subset=['daily_return'])
                
                # 保存结果
                all_returns.append(df[['candle_begin_time', 'daily_return']].rename(columns={'daily_return': symbol.replace('USDT', '')}))
                
                # 保存时间戳以便后续合并
                if timestamps is None:
                    timestamps = df['candle_begin_time']
                
            except Exception as e:
                print(f"处理 {symbol} 时出错: {str(e)}")
        
        # 如果没有足够的数据，返回空DataFrame
        if not all_returns or len(all_returns) < 10:
            print(f"没有足够的数据计算横截面差异指数，只有 {len(all_returns)} 个有效币种")
            return pd.DataFrame()
        
        print(f"成功处理 {len(all_returns)} 个币种")
        
        # 合并所有币种的收益率
        result = all_returns[0]
        for df in all_returns[1:]:
            result = pd.merge(result, df, on='candle_begin_time', how='outer')
        
        print(f"合并后的数据形状: {result.shape}")
        
        # 计算每个时间点的横截面差异指数
        diff_data = []
        
        for _, row in result.iterrows():
            time = row['candle_begin_time']
            returns = [v for k, v in row.items() if k != 'candle_begin_time' and not pd.isna(v)]
            
            if len(returns) < 10:  # 确保有足够的数据
                continue
                
            # 排序
            returns.sort()
            
            # 计算top5和bottom5的中位数
            top5_count = min(5, len(returns) // 2)
            bottom5_count = min(5, len(returns) // 2)
            
            top5_median = np.median(returns[-top5_count:]) if top5_count > 0 else 0
            bottom5_median = np.median(returns[:bottom5_count]) if bottom5_count > 0 else 0
            
            # 计算top10和bottom10的均值
            top10_count = min(10, len(returns) // 2)
            bottom10_count = min(10, len(returns) // 2)
            
            top10_mean = np.mean(returns[-top10_count:]) if top10_count > 0 else 0
            bottom10_mean = np.mean(returns[:bottom10_count]) if bottom10_count > 0 else 0
            
            # 计算横截面差异指数
            cross_section_diff = (top5_median - bottom5_median) * 0.5 + (top10_mean - bottom10_mean) * 0.5
            
            diff_data.append({
                'candle_begin_time': time,
                '横截面差异指数': cross_section_diff,
                'top5_median': top5_median,
                'bottom5_median': bottom5_median,
                'top10_mean': top10_mean,
                'bottom10_mean': bottom10_mean
            })
        
        # 创建最终DataFrame
        final_df = pd.DataFrame(diff_data)
        
        print(f"横截面差异指数计算结果: {len(final_df)} 个时间点")
        
        # 计算7天EMA
        if len(final_df) > 0:
            # 确保数据按时间排序
            final_df = final_df.sort_values('candle_begin_time')
            # 计算EMA (7天)
            span = min(7, len(final_df) // 2)  # 确保span不超过数据长度的一半
            final_df['横截面差异指数_EMA7'] = final_df['横截面差异指数'].ewm(span=span).mean()
            
            # 计算统计指标
            median = final_df['横截面差异指数'].median()
            q1 = final_df['横截面差异指数'].quantile(0.25)  # 25%分位数
            q3 = final_df['横截面差异指数'].quantile(0.75)  # 75%分位数
            std = final_df['横截面差异指数'].std()
            
            # 保存统计指标
            final_df.attrs['median'] = median
            final_df.attrs['q1'] = q1
            final_df.attrs['q3'] = q3
            final_df.attrs['std'] = std
            
            # 打印统计指标
            print(f"横截面差异指数中位数: {median:.2f}")
            print(f"横截面差异指数25%分位数: {q1:.2f}")
            print(f"横截面差异指数75%分位数: {q3:.2f}")
            print(f"横截面差异指数标准差: {std:.2f}")
            print(f"建议判定线: 中位数±标准差 = {median-std:.2f} 和 {median+std:.2f}")
            
            # 检查计算结果
            print(f"横截面差异指数范围: {final_df['横截面差异指数'].min()} 到 {final_df['横截面差异指数'].max()}")
            print(f"EMA7范围: {final_df['横截面差异指数_EMA7'].min()} 到 {final_df['横截面差异指数_EMA7'].max()}")
            
            # 在保存结果之前添加异常值检测和替换
            if len(final_df) > 5:  # 确保有足够的历史数据
                print("执行异常值检测和替换...")
                final_df = self.detect_and_replace_anomalies(final_df, window_size=5, threshold=0.5)
                
                # 输出异常值统计
                anomaly_count = final_df['是否异常值'].sum() if '是否异常值' in final_df.columns else 0
                if anomaly_count > 0:
                    print(f"检测到 {anomaly_count} 个异常值并已替换")
                    
                # 使用处理后的值更新原始列
                if '横截面差异指数_处理后' in final_df.columns:
                    final_df['横截面差异指数'] = final_df['横截面差异指数_处理后']
                    final_df.drop('横截面差异指数_处理后', axis=1, inplace=True)
        
        return final_df
    
    def process_data(self, df_dict, windows=[20], backdays=365, interval='1d', start_time=None):
        """
        核心指标计算入口（函数级注释）
        参数:
        - df_dict: 币种数据字典
        - windows/backdays/interval/start_time: 统一签名占位参数
        返回: 计算得到的 DataFrame；同时统一保存 CSV
        """
        result_df = self.calculate_cross_section_diff(df_dict)
        if result_df is None or len(result_df) == 0:
            self.warn("横截面差异指数计算失败，无足够数据")
            return result_df
        # 使用基类统一保存
        self.save_csv(result_df)
        self.log(f"横截面差异指数计算完成，样例:\n{result_df.tail().to_string()}")
        return result_df

    def draw_index(self, df, start_time=None, interval='1d'):
        """
        绘制横截面差异指数曲线并保存（函数级注释）
        参数:
        - df: 指标结果数据框
        - start_time: 起始时间（可选）
        - interval: 周期字符串（用于标题展示）
        """
        if df is None or df.empty:
            self.warn('draw_index - 数据为空，跳过绘图')
            return
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(df['candle_begin_time'], df['横截面差异指数'], label='横截面差异指数', color='tab:blue')
        if '横截面差异指数_EMA7' in df.columns:
            ax.plot(df['candle_begin_time'], df['横截面差异指数_EMA7'], label='EMA7', color='tab:orange', alpha=0.8)
        ax.axhline(0, color='k', linestyle='--', alpha=0.4)
        ax.set_title(f"{self.indicator_title()} ({interval})")
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.savefig(self.png_path(), bbox_inches='tight')
        plt.close()

class MarketIndicators(BaseIndicator):
    def __init__(self):
        """初始化市场指标类（接入基类）"""
        super().__init__()
        self.data = {}

    def indicator_slug(self) -> str:
        """指标保存文件前缀（函数级注释）"""
        return 'market_indicators'

    def indicator_title(self) -> str:
        """指标图表标题（函数级注释）"""
        return '市场指标综合图表'

    def get_all_indicators(self):
        """获取所有市场指标（函数级注释）"""
        self.get_altcoin_season_index()
        self.get_btc_rainbow_table()
        self.get_fear_greed_index()
        self.get_btc_eth_dominance()
        return self.data

    def get_altcoin_season_index(self):
        """获取山寨币季度指数 Altcoin season index（函数级注释）"""
        try:
            url = 'https://www.blockchaincenter.net/altcoin-season-index/'
            response = requests.get(url, proxies=proxies).text
            
            # 获取季度指数
            response_altcoin_season = response.split('chartdata[90] = ')[1].split(';\n\t\t\t\tchartdata2')[0]  # 截取所需的数据
            dic = json.loads(response_altcoin_season)  # 转成json格式
            df_altcoin_season = pd.DataFrame(dic['values']['all'], index=dic['labels']['all'],
                                            columns=['Altcoin Season'], dtype='float32')
            df_altcoin_season.index = pd.to_datetime(df_altcoin_season.index)
            
            # 获取月度指数
            response_altcoin_month = response.split('chartdata[30] = ')[1].split(';\n\t\t\t\tchartdata2')[0]  # 截取所需的数据
            dic = json.loads(response_altcoin_month)
            df_altcoin_month = pd.DataFrame(dic['values']['all'], index=dic['labels']['all'], columns=['Altcoin Month'],
                                        dtype='float32')
            df_altcoin_month.index = pd.to_datetime(df_altcoin_month.index)
            
            # 获取年度指数
            response_altcoin_year = response.split('chartdata[365] = ')[1].split(';\n\t\t\t\tchartdata2')[0]  # 截取所需的数据
            dic = json.loads(response_altcoin_year)
            df_altcoin_year = pd.DataFrame(dic['values']['all'], index=dic['labels']['all'], columns=['Altcoin Year'],
                                        dtype='float32')
            df_altcoin_year.index = pd.to_datetime(df_altcoin_year.index)
            
            # 合并数据
            df_altcoin = pd.merge(df_altcoin_month, df_altcoin_season, left_index=True, right_index=True, how='outer')
            df_altcoin = pd.merge(df_altcoin, df_altcoin_year, left_index=True, right_index=True, how='outer')
            
            # 保存数据由 process_data 统一处理
            self.data['altcoin_season'] = {
                'month': df_altcoin_month.iat[-1, 0],
                'season': df_altcoin_season.iat[-1, 0],
                'year': df_altcoin_year.iat[-1, 0],
                'df': df_altcoin
            }
            # 绘制图表
            self.draw_altcoin_season_chart(df_altcoin)
            return df_altcoin
        except Exception as e:
            self.warn(f"获取山寨币季度指数失败: {str(e)}")
            return None
    
    def get_btc_rainbow_table(self):
        """获取BTC彩虹价表（函数级注释）"""
        try:
            # 尝试从主要数据源获取
            url = 'https://www.blockchaincenter.net/bitcoin-rainbow-chart/'
            # 简单重试机制 + 代理（函数级注释）
            resp_text = None
            last_err = None
            _proxies = proxies or getattr(cfg.binance, 'proxies', None) if 'cfg' in globals() else None
            for att in range(1, 4):
                try:
                    resp = requests.get(url, proxies=_proxies, timeout=10)
                    resp.raise_for_status()
                    resp_text = resp.text
                    break
                except Exception as e:
                    last_err = e
                    continue
            if resp_text is None:
                raise RuntimeError(f"主要数据源获取失败: {last_err}")
            response = resp_text
            
            # 使用正则稳健解析Chart.js数据集，避免脆弱的split链（函数级注释）
            import re

            def parse_datasets(html):
                """
                解析Chart.js数据集为 (label, values) 列表（函数级注释）
                - 兼容不同空白与属性顺序
                - 过滤空值，转换为浮点数
                """
                pattern = re.compile(r'label:\s*"([^"]+)"[^{}]*?data:\s*\[([^\]]+)\]', re.S)
                results = []
                for label, data_str in pattern.findall(html):
                    raw_vals = [s.strip() for s in data_str.replace('"', '').split(',')]
                    vals = []
                    for s in raw_vals:
                        if not s or s.lower() == 'null':
                            continue
                        try:
                            vals.append(float(s))
                        except ValueError:
                            continue
                    results.append((label, vals))
                return results

            datasets = parse_datasets(response)

            def last_value_by_keyword(dsets, keyword):
                """
                按label关键字提取对应数据集最后一个数值（函数级注释）
                """
                for lbl, vals in dsets:
                    if keyword.lower() in lbl.lower():
                        if vals:
                            return float(vals[-1])
                return None

            # 提取当前价格
            current_price = last_value_by_keyword(datasets, 'Bitcoin Price')
            if current_price is None:
                raise ValueError('未找到 Bitcoin Price 数据集')

            # 彩虹分区从上到下的关键字顺序
            rainbow_keywords = [
                'Maximum', 'Sell.', 'FOMO', 'Is this', 'HODL',
                'Still cheap', 'Accumulate', 'BUY!', 'Basically a fire sale', 'Below Firesale'
            ]
            price = []
            for kw in rainbow_keywords:
                val = last_value_by_keyword(datasets, kw)
                if val is None:
                    raise ValueError(f'未找到彩虹区间数据集: {kw}')
                price.append(int(val))
            # ... existing code ...
        except Exception as e:
            print(f"从主要数据源获取BTC彩虹价表失败: {str(e)}")
            print("使用备用数据源或固定价格区间...")
            
            # 尝试从CoinGecko获取当前BTC价格 + 使用固定彩虹区间作为备用
            try:
                url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
                # 重试机制以缓解偶发连接重置（函数级注释）
                data = None
                last_err = None
                for att in range(1, 4):
                    try:
                        r = requests.get(url, timeout=10)
                        r.raise_for_status()
                        data = r.json()
                        break
                    except Exception as e2:
                        last_err = e2
                        continue
                if data is None:
                    raise RuntimeError(str(last_err))
                response = data
                current_price = float(response['bitcoin']['usd'])
                print(f"从CoinGecko获取BTC价格成功: ${current_price}")
            except Exception as e2:
                print(f"从CoinGecko获取BTC价格失败: {str(e2)}")
                # 如果CoinGecko也失败，使用固定价格
                current_price = 65000  # 使用一个合理的BTC价格作为默认值
                print(f"使用默认BTC价格: ${current_price}")
            
            # 使用固定的彩虹价格区间（基于对数回归模型）
            # 这些价格区间会随时间变化，但我们可以使用一个近期合理的估计
            price = [
                120000,  # 全都是泡沫
                90000,   # 卖掉
                70000,   # FOMO
                55000,   # 这是泡沫吗
                42000,   # HODL
                32000,   # 仍然便宜
                24000,   # 积攒
                18000,   # 买买买
                13000,   # 清仓大甩卖
                8000     # 底部
            ]
        
        # 确定当前区间
        current_level = 0
        if current_price > price[0]:
            current_level = 10
        elif current_price > price[1]:
            current_level = 9
        elif current_price > price[2]:
            current_level = 8
        elif current_price > price[3]:
            current_level = 7
        elif current_price > price[4]:
            current_level = 6
        elif current_price > price[5]:
            current_level = 5
        elif current_price > price[6]:
            current_level = 4
        elif current_price > price[7]:
            current_level = 3
        elif current_price > price[8]:
            current_level = 2
        elif current_price > price[9]:
            current_level = 1
        else:
            current_level = 0
        
        level_names = [
            "跌破底板了！！！",
            "基本算清仓大甩卖了！",
            "买买买！",
            "积攒！",
            "仍然便宜",
            "拿住！！！",
            "这是泡沫吗？",
            "FOMO情绪加剧",
            "卖掉。说认真的，卖掉！",
            "全都是泡沫！！！",
            "突破天际！！！"
        ]
        
        # 保存数据
        self.data['btc_rainbow'] = {
            'current_price': current_price,
            'price_levels': price,
            'current_level': current_level,
            'level_name': level_names[current_level]
        }
        
        # 绘制图表
        self.draw_btc_rainbow_chart(current_price, price, current_level, level_names)
        return self.data['btc_rainbow']
    
    def get_fear_greed_index(self):
        """获取贪婪恐慌指数"""
        try:
            url = 'https://api.alternative.me/fng/?limit=33'  # 官网提供的api接口
            response = requests.get(url, proxies=proxies).text
            response = json.loads(response)  # 由str转成dict
            
            # 获取指数数据
            data_list = []
            for item in response['data']:
                data_list.append({
                    'timestamp': int(item['timestamp']),
                    'date': datetime.fromtimestamp(int(item['timestamp'])),
                    'value': int(item['value']),
                    'value_classification': item['value_classification']
                })
            
            df = pd.DataFrame(data_list)
            # 保存数据由 process_data 统一处理
            
            # 保存数据
            self.data['fear_greed'] = {
                'today': int(response['data'][0]['value']),
                'yesterday': int(response['data'][1]['value']),
                'last_week': int(response['data'][7]['value']),
                'last_month': int(response['data'][30]['value']),
                'classification': response['data'][0]['value_classification'],
                'df': df
            }
            
            # 绘制图表
            self.draw_fear_greed_chart(df)
            return df
        except Exception as e:
            print(f"获取贪婪恐慌指数失败: {str(e)}")
            return None
    
    def get_btc_eth_dominance(self):
        """获取BTC/ETH Dominance指数（函数级注释）
        - 增加timeout与简易重试
        - 失败时回退到None或保留此前缓存
        """
        try:
            url = 'https://coinmarketcap.com/charts/'
            _proxies = proxies or getattr(cfg.binance, 'proxies', None) if 'cfg' in globals() else None
            resp_text = None
            last_err = None
            for att in range(1, 4):
                try:
                    resp = requests.get(url, proxies=_proxies, timeout=10)
                    resp.raise_for_status()
                    resp_text = resp.text
                    break
                except Exception as e:
                    last_err = e
                    continue
            if resp_text is None:
                raise RuntimeError(f"Dominance页面获取失败: {last_err}")
            response = resp_text
            
            btcDominance = float(response.split('"btcDominance":')[1].split(',"btcDominanceChange"')[0])  # 截取文本中的指数并转成float
            ethDominance = float(response.split('"ethDominance":')[1].split(',"etherscanGas"')[0])  # 截取文本中的指数并转成float
            
            # 保存数据
            self.data['dominance'] = {
                'btc': btcDominance,
                'eth': ethDominance
            }
            
            # 绘制图表
            self.draw_dominance_chart(btcDominance, ethDominance)
            return self.data['dominance']
        except Exception as e:
            print(f"获取BTC/ETH Dominance指数失败: {str(e)}")
            # 回退：保留None，或尝试从已有数据中读取最后一次值
            try:
                # 假设process_data最终会将所有指标汇总到CSV，此处尝试读取
                cached = pd.read_csv(self.csv_path())
                last = cached.tail(1)
                if 'btc_dominance' in last.columns and 'eth_dominance' in last.columns:
                    btc_d = float(last['btc_dominance'].iloc[0])
                    eth_d = float(last['eth_dominance'].iloc[0])
                    self.data['dominance'] = {'btc': btc_d, 'eth': eth_d}
                    return self.data['dominance']
            except Exception:
                pass
            return None
    
    def draw_altcoin_season_chart(self, df):
        """绘制山寨币季度指数图表（函数级注释）"""
        plt.figure(figsize=(16, 8))
        plt.plot(df.index, df['Altcoin Month'], label='月度指数')
        plt.plot(df.index, df['Altcoin Season'], label='季度指数')
        plt.plot(df.index, df['Altcoin Year'], label='年度指数')
        
        plt.axhline(y=75, color='r', linestyle='--', alpha=0.5)
        plt.axhline(y=25, color='g', linestyle='--', alpha=0.5)
        
        plt.title('山寨币指数', fontsize=16)
        plt.xlabel('日期')
        plt.ylabel('指数值')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(self.png_path('altcoin_season_index'))
        plt.close()
    
    def draw_btc_rainbow_chart(self, current_price, price_levels, current_level, level_names):
        """绘制BTC彩虹价表图表（函数级注释）"""
        # 创建彩虹色带
        colors = ['#ff0000', '#ff4500', '#ffa500', '#ffff00', '#9acd32', '#32cd32', '#00bfff', '#0000ff', '#9400d3', '#4b0082']
        labels = [
            "全都是泡沫！！！",
            "卖掉。说认真的，卖掉！",
            "FOMO情绪加剧",
            "这是泡沫吗？",
            "拿住！！！",
            "仍然便宜",
            "积攒！",
            "买买买！",
            "基本算清仓大甩卖了！",
            "跌破底板了！！！"
        ]
        
        # 创建一个仪表盘样式的图表
        gauge = Gauge(init_opts=opts.InitOpts(width="100%", height="600px"))
        gauge.add(
            "BTC彩虹价格表",
            [("当前价格", current_price)],
            min_=0,
            max_=max(price_levels) * 1.2,
            split_number=10,
            axisline_opts=opts.AxisLineOpts(
                linestyle_opts=opts.LineStyleOpts(
                    color=list(zip([price_levels[i] / (max(price_levels) * 1.2) for i in range(len(price_levels)-1, -1, -1)], colors)),
                    width=30
                )
            ),
            detail_label_opts=opts.LabelOpts(formatter="${value}"),
        )
        
        gauge.set_global_opts(
            title_opts=opts.TitleOpts(
                title="BTC彩虹价格表", 
                subtitle=f"当前价格: ${current_price:.2f} - {level_names[current_level]}"
            ),
            tooltip_opts=opts.TooltipOpts(is_show=True, formatter="{a} <br/>{b} : ${c}"),
            legend_opts=opts.LegendOpts(
                is_show=True,
                orient="vertical",
                pos_right="5%",
                pos_top="middle"
            )
        )
        
        # 保存为HTML文件（统一路径生成）
        output_html = self.png_path('btc_rainbow_chart').replace('.png', '.html')
        gauge.render(output_html)
        self.log(f"已生成BTC彩虹价格HTML: {output_html}")
        
        # 同时保存静态图片版本 - 使用matplotlib绘制更详细的图表
        plt.figure(figsize=(12, 8))
        plt.title(f"BTC彩虹价格表 - 当前价格: ${current_price:.2f}\n当前区间: {level_names[current_level]}", fontsize=16)
        
        for i in range(len(price_levels)-1):
            plt.axhspan(price_levels[i+1], price_levels[i], alpha=0.3, color=colors[i], label=f"{labels[i]} (${price_levels[i+1]} ~ ${price_levels[i]})")
        
        plt.axhline(y=current_price, color='black', linestyle='-', linewidth=2)
        plt.text(0.02, current_price, f"当前价格: ${current_price:.2f}", fontsize=12, verticalalignment='bottom')
        
        plt.yscale('log')
        plt.ylim(price_levels[-1] * 0.5, price_levels[0] * 2)
        
        plt.legend(loc='upper left', bbox_to_anchor=(1.05, 1), borderaxespad=0.)
        
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(self.png_path('btc_rainbow_table'), bbox_inches='tight')
        plt.close()
        
        # 创建文本表格展示价格区间
        tag = [''] * 9
        tag[10 - current_level - 1] = '<———' if current_level > 0 and current_level < 10 else ''
        
        price_table = f"BTC彩虹价格表 - 当前价格: ${current_price:.2f}\n"
        price_table += f"当前区间: {level_names[current_level]}\n\n"
        price_table += f"FL9：{price_levels[1]}~{price_levels[0]}u {tag[0]}\n"
        price_table += f"FL8：{price_levels[2]}~{price_levels[1]}u {tag[1]}\n"
        price_table += f"FL7：{price_levels[3]}~{price_levels[2]}u {tag[2]}\n"
        price_table += f"FL6：{price_levels[4]}~{price_levels[3]}u {tag[3]}\n"
        price_table += f"FL5：{price_levels[5]}~{price_levels[4]}u {tag[4]}\n"
        price_table += f"FL4：{price_levels[6]}~{price_levels[5]}u {tag[5]}\n"
        price_table += f"FL3：{price_levels[7]}~{price_levels[6]}u {tag[6]}\n"
        price_table += f"FL2：{price_levels[8]}~{price_levels[7]}u {tag[7]}\n"
        price_table += f"FL1：{price_levels[9]}~{price_levels[8]}u {tag[8]}\n"
        
        output_txt = self.png_path('btc_rainbow_table').replace('.png', '.txt')
        with open(output_txt, 'w', encoding='utf-8') as f:
            f.write(price_table)
        
        return gauge.render_embed()
    
    def draw_fear_greed_chart(self, df):
        """绘制贪婪恐慌指数图表（函数级注释）"""
        plt.figure(figsize=(16, 8))
        plt.plot(df['date'], df['value'], marker='o', linestyle='-')
        
        plt.axhspan(0, 25, alpha=0.2, color='red', label='极度恐慌')
        plt.axhspan(25, 46, alpha=0.2, color='orange', label='恐慌')
        plt.axhspan(46, 55, alpha=0.2, color='yellow', label='中性')
        plt.axhspan(55, 75, alpha=0.2, color='lightgreen', label='贪婪')
        plt.axhspan(75, 100, alpha=0.2, color='green', label='极度贪婪')
        
        plt.title('贪婪恐慌指数', fontsize=16)
        plt.xlabel('日期')
        plt.ylabel('指数值')
        plt.ylim(0, 100)
        plt.grid(True, alpha=0.3)
        plt.legend(loc='upper left')
        plt.tight_layout()
        plt.savefig(self.png_path('fear_greed_index'))
        plt.close()
        
        gauge = Gauge()
        gauge.add(
            "贪婪恐慌指数",
            [("当前指数", df['value'].iloc[0])],
            min_=0,
            max_=100,
            split_number=10,
            axisline_opts=opts.AxisLineOpts(
                linestyle_opts=opts.LineStyleOpts(
                    color=[(0.25, "#FF4500"), (0.46, "#FFA500"), (0.55, "#FFFF00"), (0.75, "#90EE90"), (1, "#006400")],
                    width=30
                )
            ),
        )
        
        gauge.set_global_opts(
            title_opts=opts.TitleOpts(title="贪婪恐慌指数"),
            tooltip_opts=opts.TooltipOpts(is_show=True, formatter="{a} <br/>{b} : {c}"),
        )
        
        gauge.render(self.png_path('fear_greed_gauge').replace('.png', '.html'))
    
    def draw_dominance_chart(self, btc_dominance, eth_dominance):
        """绘制BTC/ETH Dominance指数图表"""
        # 创建饼图
        pie = Pie()
        pie.add(
            "",
            [
                ["BTC", btc_dominance],
                ["ETH", eth_dominance],
                ["其他", 100 - btc_dominance - eth_dominance]
            ],
            radius=["40%", "75%"],
        )
        
        pie.set_global_opts(
            title_opts=opts.TitleOpts(title="BTC/ETH统治力指数"),
            legend_opts=opts.LegendOpts(orient="vertical", pos_top="15%", pos_left="2%"),
        )
        
        pie.set_series_opts(
            label_opts=opts.LabelOpts(formatter="{b}: {c}%"),
        )
        
        pie.render(self.png_path('dominance_pie').replace('.png', '.html'))
    
    def generate_market_indicators_charts(self):
        """生成市场指标图表"""
        # 获取所有指标数据
        self.get_all_indicators()
        
        # 创建综合指标仪表盘
        line = Line()
        if 'fear_greed' in self.data and 'df' in self.data['fear_greed']:
            df = self.data['fear_greed']['df']
            line.add_xaxis(safe_to_list(df['date'].dt.strftime('%Y-%m-%d')))
            line.add_yaxis(
                series_name="贪婪恐慌指数",
                y_axis=safe_to_list(df['value']),
                is_smooth=True,
                linestyle_opts=opts.LineStyleOpts(width=2),
                label_opts=opts.LabelOpts(is_show=False),
            )
        
        if 'altcoin_season' in self.data and 'df' in self.data['altcoin_season']:
            df = self.data['altcoin_season']['df']
            line.add_xaxis(safe_to_list(df.index.strftime('%Y-%m-%d')))
            line.add_yaxis(
                series_name="山寨币月度指数",
                y_axis=safe_to_list(df['Altcoin Month']),
                is_smooth=True,
                linestyle_opts=opts.LineStyleOpts(width=2),
                label_opts=opts.LabelOpts(is_show=False),
            )
            line.add_yaxis(
                series_name="山寨币季度指数",
                y_axis=safe_to_list(df['Altcoin Season']),
                is_smooth=True,
                linestyle_opts=opts.LineStyleOpts(width=2),
                label_opts=opts.LabelOpts(is_show=False),
            )
            line.add_yaxis(
                series_name="山寨币年度指数",
                y_axis=safe_to_list(df['Altcoin Year']),
                is_smooth=True,
                linestyle_opts=opts.LineStyleOpts(width=2),
                label_opts=opts.LabelOpts(is_show=False),
            )
        
        line.set_global_opts(
            title_opts=opts.TitleOpts(title="市场指标综合图表"),
            xaxis_opts=opts.AxisOpts(
                type_="category",
                axislabel_opts=opts.LabelOpts(rotate=45)
            ),
            yaxis_opts=opts.AxisOpts(
                type_="value",
                axislabel_opts=opts.LabelOpts(formatter="{value}"),
                splitline_opts=opts.SplitLineOpts(is_show=True),
            ),
            datazoom_opts=[
                opts.DataZoomOpts(range_start=0, range_end=100),
                opts.DataZoomOpts(type_="inside")
            ],
            tooltip_opts=opts.TooltipOpts(trigger="axis"),
        )
        
        line.render(self.png_path().replace('.png', '.html'))
        return line

    def process_data(self, df_dict, windows=[20], backdays=365, interval='1d', start_time=None):
        """
        市场指标综合计算入口（函数级注释）
        参数:
        - df_dict: 外部行情字典（该类不依赖，作为统一签名占位）
        - windows/backdays/interval/start_time: 统一签名占位参数
        行为:
        - 拉取各项市场指标，构建单行快照DataFrame
        - 使用基类保存到`data/market_indicators.csv`
        返回: 单行快照DataFrame
        """
        # 拉取并缓存各项指标
        self.get_all_indicators()
        # 构建单行快照
        snapshot = {
            'candle_begin_time': pd.Timestamp.now(),
            'fear_greed_today': self.data.get('fear_greed', {}).get('today'),
            'fear_greed_classification': self.data.get('fear_greed', {}).get('classification'),
            'altcoin_month': self.data.get('altcoin_season', {}).get('month'),
            'altcoin_season': self.data.get('altcoin_season', {}).get('season'),
            'altcoin_year': self.data.get('altcoin_season', {}).get('year'),
            'btc_dominance': self.data.get('dominance', {}).get('btc'),
            'eth_dominance': self.data.get('dominance', {}).get('eth'),
            'btc_rainbow_current_price': self.data.get('btc_rainbow', {}).get('current_price'),
            'btc_rainbow_current_level': self.data.get('btc_rainbow', {}).get('current_level'),
            'btc_rainbow_level_name': self.data.get('btc_rainbow', {}).get('level_name'),
        }
        df = pd.DataFrame([snapshot])
        # 使用基类统一保存
        self.save_csv(df)
        return df

    def draw_index(self, df, start_time=None, interval='1d'):
        """
        绘制综合市场指标仪表盘（函数级注释）
        参数:
        - df: 指标结果数据框（该类绘图基于内部缓存数据）
        - start_time: 起始时间（可选）
        - interval: 周期字符串（用于标题展示）
        行为:
        - 生成并保存综合图表HTML到统一路径
        返回: 图表对象
        """
        chart = self.generate_market_indicators_charts()
        chart.render(self.png_path().replace('.png', '.html'))
        return chart

    def stat(self, windows=[20], backdays=365, interval='1d', start_time=None):
        """
        统一入口：拉取并绘制综合市场指标（函数级注释）
        参数:
        - windows/backdays/interval/start_time: 统一签名参数
        行为:
        - 调用process_data生成快照并绘图
        返回: 快照DataFrame
        """
        df = self.process_data(df_dict=None, windows=windows, backdays=backdays, interval=interval, start_time=start_time)
        self.draw_index(df, start_time=start_time, interval=interval)
        return df

    def stat_with_data(self, df_dict, windows=[20], backdays=365, interval='1d', start_time=None):
        """
        统一入口（带数据字典）：兼容外部调用（函数级注释）
        参数:
        - df_dict: 外部行情数据字典（该类不强依赖）
        - windows/backdays/interval/start_time: 统一签名参数
        行为:
        - 调用process_data生成快照并绘图
        返回: 快照DataFrame
        """
        df = self.process_data(df_dict=df_dict, windows=windows, backdays=backdays, interval=interval, start_time=start_time)
        self.draw_index(df, start_time=start_time, interval=interval)
        return df