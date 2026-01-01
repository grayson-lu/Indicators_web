"""
统一指标基类 BaseIndicator
提供标准化接口与通用方法，减少各指标之间的重复代码。
设计目标：
- 统一数据保存路径与文件命名
- 提供一致的日志输出与错误处理包装
- 规范化交易所连接与基础数据获取入口（可被子类复用）
- 约定指标的核心接口：stat/stat_with_data/process_data/draw_index
使用：
- 指标类继承 BaseIndicator，并至少实现：process_data(...) 与 draw_index(...)
- 建议子类覆盖 indicator_slug() 以确定保存文件名（csv/png）
"""
import os
import os
import ccxt
import pandas as pd
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

pd.set_option('display.unicode.ambiguous_as_wide', True)
pd.set_option('display.unicode.east_asian_width', True)
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 180)


class BaseIndicator:
    def __init__(self):
        """
        构造函数
        - 初始化输出目录与通用参数
        - 子类可覆盖默认的 top_n 或其他配置
        """
        self.top_n = 100  # 统一活跃币种筛选规模
        # 确保 data 目录存在
        if not os.path.exists('data'):
            os.makedirs('data')

    def log(self, msg: str):
        """
        标准化日志输出
        - 统一使用 print，后续可替换为 logging
        """
        print(msg)

    def warn(self, msg: str):
        """
        警告日志输出
        """
        print(f"[WARN] {msg}")

    def indicator_slug(self) -> str:
        """
        指标保存文件前缀（子类应覆盖）
        返回值例如："ad_percentage"、"up_down_ratio"
        """
        return self.__class__.__name__.lower()

    def indicator_title(self) -> str:
        """
        指标图表标题（子类可覆盖）
        默认使用 slug
        """
        return self.indicator_slug()

    def csv_path(self) -> str:
        """
        统一 CSV 保存路径
        """
        return os.path.join('data', f"{self.indicator_slug()}.csv")

    def png_path(self, suffix: str = None) -> str:
        """
        统一 PNG 保存路径（可选后缀）
        参数:
        - suffix: 可选后缀，若提供则文件名为 '<slug>-<suffix>.png'
        """
        filename = f"{self.indicator_slug()}.png" if not suffix else f"{self.indicator_slug()}-{suffix}.png"
        return os.path.join('data', filename)

    def save_csv(self, df: pd.DataFrame):
        """
        保存指标结果到 CSV（函数级注释）
        参数:
        - df: 待保存的 DataFrame
        行为:
        - 将 df 保存到统一路径 `data/<slug>.csv`
        - 输出保存路径日志
        """
        path = self.csv_path()
        df.to_csv(path, index=False)
        self.log(f"已保存CSV: {path}")



    # 子类必须实现：
    def process_data(self, df_dict, windows, backdays, interval, start_time):
        """
        子类实现核心计算逻辑（抽象约定）
        必须返回 DataFrame
        """
        raise NotImplementedError

    def draw_index(self, df, start_time=None, interval='1d'):
        """
        子类实现绘图逻辑（抽象约定）
        参数:
            df: 包含指标数据的DataFrame
            start_time: 开始时间
            interval: 时间间隔
        """
        raise NotImplementedError