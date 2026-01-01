import pandas as pd
import pandas.api.types
from flask import Flask, render_template, make_response, jsonify, request, send_from_directory
from pyecharts import options as opts
from pyecharts.charts import Line, Grid, Bar, Gauge
from pyecharts.commons.utils import JsCode
import os
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import time
import matplotlib
import traceback
import logging
import numpy as np
from typing import List, Optional, Tuple

# 修复导入路径 - 从indicator目录导入
from indicator.altcoin_index import *
from indicator.market_zdf_index import *
from indicator.volatility_index import *
from indicator.liquidity_index import *
from indicator.market_breadth_index import *
from indicator.market_indicators import *
# 添加新的指标导入
from indicator.onchain_indicators import (
    MVRV指标 as OnchainMVRV指标,
    链上稳定币供应量 as 模拟稳定币供应量,
    交易所净流入流出 as 模拟交易所净流入
)
# 添加所有新指标的导入
from indicator.ad_percentage import *
from indicator.ahr999 import *
from indicator.extreme_move_ratio import *
# from indicator.mvrvy_index import *  # 已废弃，删除
from indicator.up_down_ratio import *
from indicator.cross_section_diff_index import *
from indicator.bid_ask_spread_monitor import *
from indicator.mvrv_indicator import MVRV指标 as 市场MVRV指标
from indicator.stablecoin_supply_monitor import *
from indicator.exchange_flow_monitor import ExchangeFlowMonitor
from indicator.funding_rate_monitor import *
from indicator.y_composite_index import *
from indicator.advanced_indicators import 高级市场指标
from indicator.bbw_indicator import compute_bbw_series

# 添加数据验证模块导入
from data_validation import (
    validate_dataframe_access,
    safe_dataframe_get as safe_dataframe_get_raw,
    validate_numeric_range as validate_numeric_range_bool,
    safe_column_access,
    validate_time_series_data,
    safe_to_list,
    normalize_to_list,
    safe_parse_float,
    clean_time_series,
)

# 添加日志管理模块导入
from log_manager import get_log_manager, cleanup_all_log_managers

# 添加缺失的导入
import ccxt
import yquant.common.binance_utils as binance
from threading import Thread
import yquant.common.common_utils as common
from yquant.config.config import cfg
# 添加统一推送系统导入
# 推送模块移除：统一在 push_scheduler.py 中管理
# 推送配置导入已移除（改由 push_scheduler.py 管理）

# 设置matplotlib使用非交互式后端，避免线程问题
matplotlib.use('Agg')


def validate_numeric_range(value,
                           min_val=None,
                           max_val=None,
                           allow_nan: bool = True,
                           log_warnings: bool = True,
                           name: str | None = None,
                           **kwargs) -> bool:
    """
    函数级注释：
    兼容封装的数值范围验证函数（返回布尔值）。
    - 兼容历史调用传入的 `name` 与多余参数，避免因签名不匹配抛错；
    - 首选调用 data_validation 中的布尔型验证实现；
    - 若出现 TypeError（历史环境签名差异），则降级为本地简单验证逻辑。

    参数:
        value: 待验证的数值或序列
        min_val/max_val: 合理范围边界（可选）
        allow_nan: 是否允许 NaN
        log_warnings: 是否记录告警
        name: 字段名（可选，仅用于日志）
        **kwargs: 兼容未知历史参数，安全忽略

    返回:
        bool: 是否通过范围验证
    """
    try:
        # 优先使用原始实现（布尔返回）
        return validate_numeric_range_bool(
            value, min_val, max_val, allow_nan, log_warnings, name, **kwargs
        )
    except TypeError:
        # 兼容旧环境：使用最小化本地验证逻辑
        try:
            import numpy as _np
            import pandas as _pd
            # 单值
            if isinstance(value, (int, float)) or _np.isscalar(value):
                if _pd.isna(value):
                    return allow_nan
                v = float(value)
                if min_val is not None and v < float(min_val):
                    return False
                if max_val is not None and v > float(max_val):
                    return False
                return True
            # 序列
            if isinstance(value, (_pd.Series, _np.ndarray, list)):
                arr = _np.array(value)
                if not allow_nan and _np.any(_pd.isna(arr)):
                    return False
                valid = arr[~_pd.isna(arr)]
                if len(valid) == 0:
                    return allow_nan
                if min_val is not None and _np.any(valid < float(min_val)):
                    return False
                if max_val is not None and _np.any(valid > float(max_val)):
                    return False
                return True
            # 其它类型不支持
            return False
        except Exception:
            return False


def safe_dataframe_get(df,
                       column: str | None = None,
                       default: float | None = None,
                       index: int | None = None):
    """
    函数级注释：
    兼容封装的安全 DataFrame 获取函数。
    - 兼容历史调用传入的 `index` 关键字参数（支持负索引）；
    - 当提供列名且未提供索引：返回该列最后一个有效值；
    - 当同时提供列名与索引：返回该列在指定位置的值；
    - 当仅提供索引：返回该行（Series），失败时返回 default；
    - 其它情况：回退到原始 safe_dataframe_get_raw 实现（key 语义）。

    参数:
        df: DataFrame
        column: 列名（可选）
        default: 默认返回值（数值型或 None）
        index: 行索引（可选，支持负索引）

    返回:
        任意：数值/Series/默认值
    """
    try:
        if not validate_dataframe_access(df, "兼容安全获取"):
            return default

        # 同时提供列与索引：优先位置访问
        if column is not None and isinstance(column, str):
            if column not in df.columns:
                return default
            if index is None:
                # 取最后一个有效值
                val = df[column].iloc[-1]
                return val if not pd.isna(val) else default
            else:
                # 位置访问（支持负索引）
                try:
                    val = df.iloc[index][column]
                    return val if not pd.isna(val) else default
                except Exception:
                    return default

        # 仅提供索引：返回该行
        if index is not None:
            try:
                row = df.iloc[index]
                return row
            except Exception:
                return default

        # 回退到原始实现（key 语义）：
        # 当 column 为字符串时，将其视为 key；否则尝试使用最后一行索引
        key = column if isinstance(column, str) else -1
        return safe_dataframe_get_raw(df, key, default)

    except Exception:
        return default


def safe_divide(numerator: float, denominator: float, eps: float = 1.0) -> float:
    """
    安全除法，避免分母为 0 导致的无穷大/NaN。
    - 使用 Laplace 平滑：返回 (numerator + eps) / (denominator + eps)
    - 当 denominator=0 时可得到有限值；当 numerator、denominator 同为 0 时结果为 1（中性比值）
    参数:
        numerator: 分子
        denominator: 分母
        eps: 平滑项，默认 1.0（整数计数场景较稳健）
    返回:
        经过平滑的有限浮点值
    """
    num = 0.0 if numerator is None else float(numerator)
    den = 0.0 if denominator is None else float(denominator)
    return (num + eps) / (den + eps)


def sanitize_extreme_move_ratio_df(df):
    """
    清洗极端波动比率数据（extreme_move_ratio.csv 专用）：
    1) 先将所有数值列中的 inf/-inf 统一替换为 NaN（避免后续计算异常）
    2) 若存在计数列（爆拉币种数_*、暴跌币种数_*），则用安全除法重算“爆拉暴跌比率_*”三列：
       - 1d:  (爆拉币种数_1d + 1) / (暴跌币种数_1d + 1)
       - 7d:  (爆拉币种数_7d + 1) / (暴跌币种数_7d + 1)
       - 30d: (爆拉币种数_30d + 1) / (暴跌币种数_30d + 1)
       这样永远不会产生无穷大；当上下都为 0 时结果为 1（中性）。
    3) 本函数是幂等的，多次调用不会产生副作用。
    参数:
        df: 读取到的 DataFrame
    返回:
        已清洗和（必要时）重算比率列的 DataFrame
    """
    import numpy as np
    # 1) 统一处理 inf/-inf
    numeric_cols = safe_to_list(df.select_dtypes(include=[float, int, 'float64', 'int64', 'int32', 'float32']).columns)
    if numeric_cols:
        df[numeric_cols] = df[numeric_cols].replace([np.inf, -np.inf], np.nan)

    # 2) 若存在计数列，重算三条比率列
    pairs = [
        ('爆拉币种数_1d',  '暴跌币种数_1d',  '爆拉暴跌比率_1d'),
        ('爆拉币种数_7d',  '暴跌币种数_7d',  '爆拉暴跌比率_7d'),
        ('爆拉币种数_30d', '暴跌币种数_30d', '爆拉暴跌比率_30d'),
    ]
    for up_col, down_col, ratio_col in pairs:
        if up_col in df.columns and down_col in df.columns:
            # 向量化安全除法（加一平滑）
            up = df[up_col].astype(float).fillna(0.0)
            down = df[down_col].astype(float).fillna(0.0)
            df[ratio_col] = (up + 1.0) / (down + 1.0)

    return df


def parse_datetime_series(raw_series: pd.Series, column_name: str) -> pd.Series:
    """将给定的序列尽可能解析为 pandas datetime 类型。

    解析顺序：
    1. 直接使用 ``pd.to_datetime``（自动识别字符串/ISO 格式）。
    2. 若失败，尝试将数据转换为数值并基于量级推断时间单位：
       - < 1e11: 视作秒级时间戳
       - < 1e14: 视作毫秒级时间戳
       - 其他：退回 ``pd.to_datetime`` 默认行为

    Args:
        raw_series: 原始时间序列
        column_name: 列名（用于日志记录）

    Returns:
        解析后的 ``datetime`` 序列（若解析失败则返回 ``NaT`` 序列）
    """

    if raw_series is None or raw_series.empty:
        return pd.to_datetime([], errors='coerce')

    # 第一步：直接解析
    parsed = pd.to_datetime(raw_series, errors='coerce', infer_datetime_format=True, utc=False)
    if parsed.notna().any():
        return parsed

    # 第二步：尝试按数值解析
    numeric_series = pd.to_numeric(raw_series, errors='coerce')
    if numeric_series.notna().any():
        try:
            max_abs = float(np.nanmax(np.abs(numeric_series.to_numpy())))
        except ValueError:
            max_abs = np.nan

        if not np.isnan(max_abs):
            if max_abs < 1e11:
                parsed = pd.to_datetime(numeric_series, unit='s', errors='coerce')
            elif max_abs < 1e14:
                parsed = pd.to_datetime(numeric_series, unit='ms', errors='coerce')
            else:
                parsed = pd.to_datetime(numeric_series, errors='coerce')

            if parsed.notna().any():
                return parsed

    logger.debug(f"无法解析时间列 {column_name}，将返回 NaT 序列")
    return parsed


def normalize_datetime_column(
    df: pd.DataFrame,
    candidate_columns: Optional[List[str]] = None,
    target_column: str = 'candle_begin_time'
) -> Tuple[pd.DataFrame, Optional[str]]:
    """标准化 DataFrame 中的时间列，优先确保存在 ``target_column``。

    若 ``candidate_columns`` 中存在可解析的时间列，则：
    - 解析为 ``datetime`` 类型
    - 若列名不是 ``target_column``，则重命名为目标列名

    Args:
        df: 输入 DataFrame（函数内部复制，避免就地修改调用方）
        candidate_columns: 可选的时间列名列表
        target_column: 解析后的标准列名

    Returns:
        (新的 DataFrame, 解析成功的列名或 ``None``)
    """

    if df is None or df.empty:
        return df, None

    working_df = df.copy()
    candidates = candidate_columns or [target_column, 'date', 'Date', 'timestamp']

    for col in candidates:
        if col not in working_df.columns:
            continue

        parsed = parse_datetime_series(working_df[col], col)
        if parsed is None or parsed.isna().all():
            continue

        working_df[col] = parsed
        detected_col = col

        if col != target_column:
            working_df = working_df.drop(columns=[target_column], errors='ignore')
            working_df = working_df.rename(columns={col: target_column})
            detected_col = target_column

        return working_df, detected_col

    return working_df, None


def prepare_time_axis(
    df: pd.DataFrame,
    candidate_columns: Optional[List[str]] = None,
    date_format: str = '%Y-%m-%d',
    sort_values: bool = True
) -> Tuple[pd.DataFrame, List[str], Optional[str]]:
    """为图表准备时间序列 x 轴数据，返回整理后的 DataFrame。

    Args:
        df: 原始数据 DataFrame
        candidate_columns: 备选时间列名
        date_format: 格式化字符串
        sort_values: 是否按时间升序排序

    Returns:
        (整理后的 DataFrame, x 轴字符串列表, 使用的时间列名)
    """

    if df is None or df.empty:
        return df, [], None

    prepared_df, detected_col = normalize_datetime_column(df, candidate_columns)

    if detected_col:
        prepared_df = prepared_df.dropna(subset=[detected_col])
        if sort_values:
            prepared_df = prepared_df.sort_values(detected_col).reset_index(drop=True)
        x_axis = safe_to_list(prepared_df[detected_col].dt.strftime(date_format))
        return prepared_df, x_axis, detected_col

    logger.warning(
        f"未在数据中识别到时间列，使用索引作为 x 轴。可选列: {candidate_columns}"
    )
    return prepared_df, safe_to_list(prepared_df.index.astype(str)), None

def ensure_critical_data_files():
    """
    确保关键数据文件存在，如果不存在则创建默认数据
    """
    logger.info("检查关键数据文件...")
    
    critical_files = [
        ('Y_idx.csv', 'Y指数'),
        ('y_composite_index.csv', 'Y综合指数'),
        ('volatility_index.csv', '波动率指数'),
        ('liquidity_index.csv', '流动性指数')
    ]
    
    for filename, desc in critical_files:
        file_path = os.path.join(DATA_DIR, filename)
        if not os.path.exists(file_path):
            logger.warning(f"{desc}数据文件不存在: {file_path}")
            
            # 对Y综合指数特殊处理
            if filename == 'y_composite_index.csv':
                try:
                    read_y_composite_data()  # 触发生成逻辑
                    logger.info(f"已生成{desc}默认数据文件")
                except Exception as e:
                    logger.error(f"生成{desc}默认数据失败: {e}")

# 配置日志系统
def setup_logging():
    """
    设置完整的日志系统
    
    Returns:
        tuple: (logger, detailed_logger, error_logger, access_logger)
    """
    import logging
    from logging.handlers import RotatingFileHandler
    import os
    
    # 创建logs目录
    os.makedirs('logs', exist_ok=True)
    
    # 设置日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    
    # 控制台日志
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    # 详细日志文件
    detailed_handler = RotatingFileHandler(
        'logs/kanban_detailed.log', maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
    )
    detailed_handler.setLevel(logging.DEBUG)
    detailed_handler.setFormatter(formatter)
    
    # 错误日志文件
    error_handler = RotatingFileHandler(
        'logs/kanban_error.log', maxBytes=5*1024*1024, backupCount=3, encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    
    # 访问日志文件
    access_handler = RotatingFileHandler(
        'logs/kanban_access.log', maxBytes=5*1024*1024, backupCount=3, encoding='utf-8'
    )
    access_handler.setLevel(logging.INFO)
    access_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    
    # 配置主logger
    logger = logging.getLogger('kanban')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(console_handler)
    logger.addHandler(detailed_handler)
    logger.addHandler(error_handler)
    
    # 配置访问logger
    access_logger = logging.getLogger('kanban.access')
    access_logger.setLevel(logging.INFO)
    access_logger.addHandler(access_handler)
    
    return logger, access_logger

# 初始化日志系统
logger, access_logger = setup_logging()

# 初始化优化的日志管理器
log_mgr = get_log_manager('kanban')
log_mgr.info("日志管理器初始化完成，启用防重复和性能优化功能")

def log_function_call(func_name, *args, **kwargs):
    """记录函数调用"""
    logger.debug(f"调用函数: {func_name}, 参数: args={args}, kwargs={kwargs}")

def log_performance(func_name, start_time, end_time):
    """记录性能信息"""
    duration = end_time - start_time
    logger.info(f"函数 {func_name} 执行时间: {duration:.2f}秒")

def log_data_status(data_name, df):
    """记录数据状态"""
    if df is None:
        logger.warning(f"数据 {data_name} 为空")
    elif df.empty:
        logger.warning(f"数据 {data_name} 无记录")
    else:
        logger.info(f"数据 {data_name} 加载成功，共 {len(df)} 条记录")

# 创建Flask应用并禁用模板缓存
app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['JSON_AS_ASCII'] = False


def pre_fetch_all_data():
    """
    数据预热函数。
    用途：启动前遍历 indicator 目录，动态导入并执行各指标计算，强制刷新 CSV，减少首屏等待。
    返回值：dict，包含 success（成功数）、fail（失败数）、detail（每个指标的执行结果）。
    异常处理策略：单个指标执行失败仅记录 warning，不影响整体启动流程。
    """
    import os
    import importlib.util
    import inspect
    import traceback

    try:
        from indicator.base_indicator import BaseIndicator
    except Exception as e:
        logger.warning(f"[预热] 导入 BaseIndicator 失败: {e}")
        return {"success": 0, "fail": 0, "detail": []}

    indicator_dir = os.path.join(os.path.dirname(__file__), 'indicator')
    results = {"success": 0, "fail": 0, "detail": []}

    if not os.path.isdir(indicator_dir):
        logger.warning(f"[预热] 指标目录不存在: {indicator_dir}")
        return results

    for fname in os.listdir(indicator_dir):
        # 仅处理 *indicator*.py 文件，排除 __pycache__ 与基类
        if not fname.endswith('.py'):
            continue
        if 'indicator' not in fname:
            continue
        if fname.startswith('_') or fname == 'base_indicator.py':
            continue

        module_path = os.path.join(indicator_dir, fname)
        try:
            spec = importlib.util.spec_from_file_location(f"indicator.{fname[:-3]}", module_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            # 遍历模块内的类，筛选继承自 BaseIndicator 的指标类
            for cls_name, cls_obj in inspect.getmembers(mod, inspect.isclass):
                try:
                    if not issubclass(cls_obj, BaseIndicator) or cls_obj is BaseIndicator:
                        continue
                except Exception:
                    continue

                logger.info("[预热] 正在拉取 %s ...", cls_name)
                try:
                    inst = cls_obj()

                    # 优先调用 stat 方法（通常会在内部调用 process_data 并保存 CSV）
                    if hasattr(inst, 'stat') and callable(getattr(inst, 'stat')):
                        sig = inspect.signature(inst.stat)
                        kwargs = {}
                        for p in sig.parameters.values():
                            if p.name == 'acc':
                                kwargs['acc'] = 'qqdev'
                            elif p.name == 'backdays':
                                kwargs['backdays'] = 365
                            elif p.name == 'windows':
                                kwargs['windows'] = [7, 30]
                            elif p.name == 'interval':
                                kwargs['interval'] = '1d'
                            elif p.name == 'start_time':
                                kwargs['start_time'] = None
                            elif p.name == 'save_img':
                                kwargs['save_img'] = True
                            elif p.name == 'volatility_windows':
                                kwargs['volatility_windows'] = [30]
                        # 调用 stat 执行并保存
                        getattr(inst, 'stat')(**kwargs)

                    # 若无 stat，退化为直接调用 process_data，并尝试保存 CSV
                    elif hasattr(inst, 'process_data') and callable(getattr(inst, 'process_data')):
                        sig = inspect.signature(inst.process_data)
                        kwargs = {}
                        for p in sig.parameters.values():
                            if p.name == 'df_dict':
                                kwargs['df_dict'] = {}
                            elif p.name == 'windows':
                                kwargs['windows'] = [7, 30]
                            elif p.name == 'backdays':
                                kwargs['backdays'] = 365
                            elif p.name == 'interval':
                                kwargs['interval'] = '1d'
                            elif p.name == 'start_time':
                                kwargs['start_time'] = None
                        df = getattr(inst, 'process_data')(**kwargs)
                        try:
                            if df is not None and hasattr(inst, 'save_csv'):
                                inst.save_csv(df)
                        except Exception:
                            pass

                    logger.info("[预热] %s 完成", cls_name)
                    results['success'] += 1
                    results['detail'].append({'name': cls_name, 'status': 'ok'})
                except Exception as e:
                    logger.warning("[预热] %s 失败: %s", cls_name, e)
                    logger.debug(traceback.format_exc())
                    results['fail'] += 1
                    results['detail'].append({'name': cls_name, 'status': 'fail', 'error': str(e)})
        except Exception as e:
            logger.warning("[预热] 模块 %s 导入失败: %s", fname, e)
            results['fail'] += 1
            results['detail'].append({'name': fname, 'status': 'fail', 'error': str(e)})

    return results

# 初始化统一推送管理器
# 推送模块移除：统一在 push_scheduler.py 中管理
notification_config = None
unified_notifier = None

# 定义数据目录
DATA_DIR = 'data'

@app.route('/data/<path:filename>')
def serve_data_file(filename):
    """
    提供 data 目录下静态文件访问（如 PNG 图片/CSV 等）
    
    参数:
        filename (str): data 目录下的相对路径，例如 'extreme_move_ratio.png'
    
    返回:
        Flask Response: 对应文件内容或 404 JSON
    """
    try:
        return send_from_directory(DATA_DIR, filename)
    except Exception as e:
        logger.error(f"静态文件访问失败: {filename} - {e}")
        return jsonify({'error': 'file not found'}), 404

@app.route('/favicon.ico')
def favicon():
    """
    提供站点图标，避免浏览器对 /favicon.ico 的请求导致 404 日志刷屏
    优先从应用 static 目录读取 favicon.ico；若不存在则返回 204 并设置缓存，降低日志噪音
    """
    try:
        icon_dir = os.path.join(app.root_path, 'static')
        icon_path = os.path.join(icon_dir, 'favicon.ico')
        if os.path.exists(icon_path):
            # 提供真实图标并设置较长缓存
            return send_from_directory(icon_dir, 'favicon.ico', mimetype='image/vnd.microsoft.icon', cache_timeout=86400)
        # 无图标文件则返回 204，减少错误噪音，并告知浏览器缓存
        resp = make_response('', 204)
        resp.headers['Cache-Control'] = 'public, max-age=86400'
        return resp
    except Exception as e:
        logger.debug(f"favicon处理失败: {e}")
        return make_response('', 204)

@app.before_request
def before_request():
    """请求前处理"""
    start_time = time.time()
    request.start_time = start_time
    access_logger.info(f"请求开始: {request.method} {request.path} - IP: {request.remote_addr}")

@app.after_request
def after_request(response):
    """请求后处理"""
    if hasattr(request, 'start_time'):
        duration = time.time() - request.start_time
        access_logger.info(f"请求完成: {request.method} {request.path} - 状态: {response.status_code} - 耗时: {duration:.2f}秒")
    return response

@app.errorhandler(404)
def not_found_error(error):
    """
    404错误处理
    - 对常见静态资源 /favicon.ico 降级为 INFO 并返回 204，减少日志噪音
    - 其他路径记录 Referer，便于问题溯源
    """
    path = request.path
    referer = request.headers.get('Referer', '-')
    if path == '/favicon.ico':
        logger.info(f"忽略favicon 404: {path} - IP: {request.remote_addr} - Referer: {referer}")
        resp = make_response('', 204)
        resp.headers['Cache-Control'] = 'public, max-age=86400'
        return resp
    logger.warning(f"404错误: {path} - IP: {request.remote_addr} - Referer: {referer}")
    return jsonify({'error': '页面未找到'}), 404

@app.errorhandler(500)
def internal_error(error):
    """处理500错误（移除推送，仅记录日志）"""
    logger.error(f"服务器内部错误: {error}")
    return jsonify({'error': '服务器内部错误'}), 500

# 推送函数已移除，统一在 push_scheduler.py 中实现

# 推送函数已移除，统一在 push_scheduler.py 中实现

def get_filtered_data(file_path, date_columns=None):
    """
    统一的数据读取函数，自动识别日期列并过滤未来日期
    增强数据清洗能力：处理尾随空列、空字符串、无穷大值等
    
    Args:
        file_path: CSV文件路径
        date_columns: 可能的日期列名列表，如果为None则自动检测
    
    Returns:
        过滤后的DataFrame，如果出错则返回None
    """
    try:
        if not os.path.exists(file_path):
            logger.warning(f"数据文件不存在: {file_path}")
            return None
        
        # 新增：空内容与空白行容错（函数级注释）
        try:
            # 若文件为0字节或仅包含空白字符，则返回空DataFrame，避免"No columns to parse"
            if os.path.getsize(file_path) == 0:
                logger.warning(f"数据文件为空(0字节): {file_path}")
                return pd.DataFrame()
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                head = f.read(1024)
                if head.strip() == '':
                    logger.warning(f"数据文件仅包含空白内容: {file_path}")
                    return pd.DataFrame()
        except Exception as e:
            logger.debug(f"检查文件内容失败（忽略）：{e}")

        # 读取CSV，空/无列优雅退回空DataFrame
        try:
            df = pd.read_csv(file_path)
        except pd.errors.EmptyDataError:
            logger.warning(f"CSV为空或无列可解析：{file_path}")
            return pd.DataFrame()
        except Exception as e:
            if 'No columns to parse' in str(e):
                logger.warning(f"CSV解析失败（无列）：{file_path}")
                return pd.DataFrame()
            raise

        if df.empty:
            logger.warning(f"数据文件为空: {file_path}")
            return None

        # 数据清洗：删除尾随空列（列名为 Unnamed 且全为空的列）
        unnamed_cols = [col for col in df.columns if str(col).startswith('Unnamed')]
        for col in unnamed_cols:
            if df[col].isna().all() or (df[col].astype(str).str.strip() == '').all():
                df = df.drop(columns=[col])
                logger.debug(f"删除空列: {col}")
        
        # 清理列名：去除首尾空格
        df.columns = [str(col).strip() for col in df.columns]
        
        # 标准化空字符串为NaN
        df = df.replace(r'^\s*$', np.nan, regex=True)

        # 处理无穷大值：将 inf 和 -inf 转换为 NaN
        df = df.replace([np.inf, -np.inf], np.nan)

        # 尝试将以字符串形式存储的数值列转换为 float，降低后续指标异常概率
        for col in df.select_dtypes(include=['object']).columns:
            normalized_col = str(col).strip()
            if normalized_col == 'candle_begin_time':
                continue

            series = df[col].astype(str).str.replace(',', '', regex=False).str.strip()
            numeric_series = pd.to_numeric(series, errors='coerce')
            if len(series) == 0:
                continue
            valid_ratio = numeric_series.notna().sum() / len(series)
            if valid_ratio >= 0.7 and numeric_series.notna().sum() >= 3:
                df[col] = numeric_series
                logger.debug(f"列 {col} 已自动转换为数值类型（有效比率 {valid_ratio:.2f}）")
        
        # 追加兜底：对数值列统计 inf/-inf 并统一置为 NaN，增强可观测性
        try:
            numeric_cols = safe_to_list(df.select_dtypes(include=[np.number]).columns)
            if numeric_cols:
                before_inf = int(np.isinf(df[numeric_cols].to_numpy()).sum())
                df[numeric_cols] = df[numeric_cols].replace([np.inf, -np.inf], np.nan)
                after_inf = int(np.isinf(df[numeric_cols].to_numpy()).sum())
                logger.debug(f"已在 {os.path.basename(file_path)} 中替换 inf/-inf 为 NaN: {before_inf} -> {after_inf}")
        except Exception as e:
            logger.warning(f"替换 inf/-inf 过程中出现异常（已忽略）：{e}")
        
        # 针对 extreme_move_ratio.csv 定向修复“爆拉暴跌比率_*”列（加一平滑避免无穷大）
        try:
            if os.path.basename(file_path).lower() == 'extreme_move_ratio.csv':
                df = sanitize_extreme_move_ratio_df(df)
                logger.info("extreme_move_ratio.csv 已完成比率列安全重算（加一平滑），确保无 inf/-inf")
        except Exception as e:
            logger.error(f"extreme_move_ratio 数据清洗失败：{e}")
        
        # 使用数据验证模块进行额外检查
        if not df.empty:
            # 检查数值列的合理性
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            for col in numeric_cols:
                values = df[col].dropna()
                if not values.empty:
                    # 检查异常值但不删除（保持数据完整性）
                    extreme_count = sum(1 for v in values if abs(v) > 1e10)
                    if extreme_count > 0:
                        logger.debug(f"文件 {os.path.basename(file_path)} 列 {col} 中发现 {extreme_count} 个可能的异常值")
                    
                    # 检查是否有无效的数值（移除不支持的参数 log_warnings，增强容错）
                    try:
                        invalid_count = sum(1 for v in values if not validate_numeric_range(v, -1e15, 1e15))
                        if invalid_count > 0:
                            logger.warning(f"{os.path.basename(file_path)} 列 {col} 存在 {invalid_count} 个异常数值")
                    except Exception as e:
                        logger.debug(f"基础数值校验失败（可忽略）: {e}")
        
        # 自动识别日期列
        candidate_cols = date_columns or ['candle_begin_time', 'date', 'Date', 'timestamp']
        df, detected_col = normalize_datetime_column(df, candidate_cols)

        if detected_col:
            try:
                df = df.dropna(subset=[detected_col])
                # 同一时间保留最新数据，避免重复导致的指标抖动
                before_dedup = len(df)
                df = df.sort_values(detected_col)
                df = df.drop_duplicates(subset=[detected_col], keep='last')
                dedup_removed = before_dedup - len(df)
                if dedup_removed > 0:
                    logger.info(
                        f"文件 {os.path.basename(file_path)} 删除重复时间记录 {dedup_removed} 条"
                    )

                tzinfo = getattr(df[detected_col].dt, 'tz', None)
                current_ts = pd.Timestamp.now(tz=tzinfo)
                before_rows = len(df)
                df = df[df[detected_col] <= current_ts]
                removed = before_rows - len(df)
                if removed > 0:
                    logger.warning(
                        f"检测到未来日期数据，已过滤 {removed} 条: {os.path.basename(file_path)}"
                    )

                logger.debug(
                    f"文件 {os.path.basename(file_path)} 过滤后剩余 {len(df)} 行数据"
                )
            except Exception as e:
                logger.warning(f"处理日期列 {detected_col} 时出错: {e}，返回原始数据")
        else:
            logger.debug(
                f"文件 {os.path.basename(file_path)} 未找到日期列，返回原始数据"
            )

        return df
        
    except Exception as e:
        logger.error(f"读取文件 {file_path} 失败: {e}")
        return None

def get_cached_data(file_path: str):
    """
    简化的数据读取函数，增加日志记录，并自动过滤未来日期
    功能说明：
    1) 读取 CSV 并识别日期列（candle_begin_time/date/Date/timestamp）
    2) 自动删除"今天之后"的未来日期数据，防止前端解析异常
    3) 记录过滤数量与性能日志
    返回：pd.DataFrame 或 None
    """
    start_time = time.time()
    log_function_call('get_cached_data', file_path)
    
    try:
        if not os.path.exists(file_path):
            logger.warning(f"数据文件不存在: {file_path}")
            return None
        
        # 新增：空文件容错，避免 pandas 抛出 EmptyDataError
        try:
            if os.path.getsize(file_path) == 0:
                logger.warning(f"数据文件为空(0字节): {file_path}")
                # 返回空DataFrame以便上层逻辑走默认值，避免错误日志污染
                return pd.DataFrame()
            # 新增：仅空白内容容错（如只有换行/空格）
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                head = f.read(1024)
                if head.strip() == '':
                    logger.warning(f"数据文件仅空白内容: {file_path}")
                    return pd.DataFrame()
        except Exception as e:
            # 获取文件大小失败不应阻塞读取，记录调试信息后继续
            logger.debug(f"检查文件大小失败（忽略）：{e}")

        # 尝试读取CSV；若遇到空内容则优雅回退为空DataFrame
        try:
            df = pd.read_csv(file_path)
        except pd.errors.EmptyDataError:
            logger.warning(f"CSV为空，无列可解析：{file_path}")
            return pd.DataFrame()
        except Exception as e:
            # 兜底处理常见的空列错误
            if 'No columns to parse' in str(e):
                logger.warning(f"CSV解析失败（无列）：{file_path}")
                return pd.DataFrame()
            raise

        # 统一替换 inf/-inf → NaN（增强健壮性）
        try:
            numeric_cols = safe_to_list(df.select_dtypes(include=[np.number]).columns)
            if numeric_cols:
                df[numeric_cols] = df[numeric_cols].replace([np.inf, -np.inf], np.nan)
        except Exception as e:
            logger.warning(f"替换 inf/-inf 过程中出现异常（已忽略）：{e}")

        # 针对 extreme_move_ratio.csv 定向清洗（幂等处理，防止无穷大/异常比率）
        try:
            if os.path.basename(file_path).lower() == 'extreme_move_ratio.csv':
                df = sanitize_extreme_move_ratio_df(df)
        except Exception as e:
            logger.error(f"清洗 extreme_move_ratio.csv 失败：{e}")

        # 将可能是字符串的数字列转换为数值，避免后续计算抛异常
        for col in df.select_dtypes(include=['object']).columns:
            if str(col).strip() == 'candle_begin_time':
                continue
            series = df[col].astype(str).str.replace(',', '', regex=False).str.strip()
            numeric_series = pd.to_numeric(series, errors='coerce')
            if len(series) == 0:
                continue
            valid_ratio = numeric_series.notna().sum() / len(series)
            if valid_ratio >= 0.7 and numeric_series.notna().sum() >= 3:
                df[col] = numeric_series
                logger.debug(f"列 {col} 已转换为数值类型（有效比率 {valid_ratio:.2f}）")

        # 处理日期列并过滤未来日期
        candidate_cols = ['candle_begin_time', 'date', 'Date', 'timestamp']
        df, detected_date_col = normalize_datetime_column(df, candidate_cols)

        if detected_date_col:
            # 使用数据验证模块验证时间序列数据
            if not validate_time_series_data(df, detected_date_col):
                logger.warning(f"文件 {os.path.basename(file_path)} 时间序列数据验证失败")

            # 按时间排序，避免出现乱序，并去重
            df = df.dropna(subset=[detected_date_col])
            before_sort = len(df)
            df = df.sort_values(detected_date_col)
            df = df.drop_duplicates(subset=[detected_date_col], keep='last')
            removed_dup = before_sort - len(df)
            if removed_dup > 0:
                logger.info(
                    f"文件 {os.path.basename(file_path)} 删除重复时间记录 {removed_dup} 条"
                )

            # 修复：过滤未来时间戳使用当前时间（保留当日内的数据）
            tzinfo = getattr(df[detected_date_col].dt, 'tz', None)
            current_ts = pd.Timestamp.now(tz=tzinfo)
            before_rows = len(df)
            df = df[df[detected_date_col] <= current_ts]
            removed = before_rows - len(df)
            if removed > 0:
                logger.warning(
                    f"检测到未来日期数据，已过滤 {removed} 条: {os.path.basename(file_path)}"
                )

        # 使用数据验证模块进行DataFrame基本检查
        if not df.empty:
            # 检查关键列的存在性
            if detected_date_col and not validate_dataframe_access(df, detected_date_col):
                logger.error(f"文件 {os.path.basename(file_path)} 日期列访问验证失败")

            # 检查数值列的数据质量
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            for col in numeric_cols:
                if len(df[col].dropna()) > 0:
                    sample_value = df[col].dropna().iloc[0]
                    if not validate_numeric_range(sample_value, -1e15, 1e15):
                        # 统计异常值数量
                        invalid_count = sum(
                            1 for v in df[col].dropna() if not validate_numeric_range(v, -1e15, 1e15)
                        )
                        if invalid_count > 0:
                            logger.debug(
                                f"文件 {os.path.basename(file_path)} 列 {col} 中有 {invalid_count} 个数值超出合理范围"
                            )

        log_data_status(os.path.basename(file_path), df)
        log_performance('get_cached_data', start_time, time.time())
        return df
        
    except Exception as e:
        logger.error(f"读取数据文件失败 {file_path}: {e}")
        return None

def read_y_idx_data():
    """读取Y指数数据"""
    try:
        return get_cached_data(os.path.join(DATA_DIR, 'Y_idx.csv'))
    except Exception as e:
        logger.error(f"读取Y指数数据失败: {e}")
        return None

def read_volatility_data():
    """读取波动率数据"""
    try:
        return get_cached_data(os.path.join(DATA_DIR, 'volatility_index.csv'))
    except Exception as e:
        logger.error(f"读取波动率数据失败: {e}")
        return None

def read_liquidity_data():
    """读取流动性数据"""
    try:
        return get_cached_data(os.path.join(DATA_DIR, 'liquidity_index.csv'))
    except Exception as e:
        logger.error(f"读取流动性数据失败: {e}")
        return None

def read_y_composite_data():
    """
    读取Y综合指数数据文件，如果不存在则尝试生成
    
    Returns:
        DataFrame or None: 从 data/y_composite_index.csv 读取的数据，或生成的默认数据
    """
    file_path = os.path.join(DATA_DIR, 'y_composite_index.csv')
    
    # 首先尝试读取现有文件
    df = get_cached_data(file_path)
    if df is not None:
        return df
    
    # 文件不存在，尝试生成基础数据或返回默认数据
    logger.warning("Y综合指数数据文件不存在，尝试生成默认数据")
    
    try:
        # 尝试基于现有Y指数数据生成简化的综合指数
        y_idx_df = read_y_idx_data()
        if y_idx_df is not None and not y_idx_df.empty:
            # 创建简化的综合指数数据
            composite_df = y_idx_df.copy()
            
            # 重命名列以匹配综合指数格式
            if 'Y_idx' in composite_df.columns:
                composite_df = composite_df.rename(columns={'Y_idx': 'Y指数'})
                
            # 添加默认的综合得分（基于Y指数）
            if 'Y指数' in composite_df.columns:
                composite_df['综合得分_1d'] = composite_df['Y指数']
                composite_df['综合得分_7d'] = composite_df['Y指数'].rolling(7).mean()
                composite_df['综合得分_30d'] = composite_df['Y指数'].rolling(30).mean()
                
                # 添加信号列
                composite_df['综合信号_1d'] = composite_df['综合得分_1d'].apply(
                    lambda x: get_composite_signal_from_score(x) if pd.notna(x) else '中性'
                )
                composite_df['综合信号_7d'] = composite_df['综合得分_7d'].apply(
                    lambda x: get_composite_signal_from_score(x) if pd.notna(x) else '中性'
                )
                composite_df['综合信号_30d'] = composite_df['综合得分_30d'].apply(
                    lambda x: get_composite_signal_from_score(x) if pd.notna(x) else '中性'
                )
            
            # 确保data目录存在
            os.makedirs(DATA_DIR, exist_ok=True)
            
            # 保存简化的综合指数数据
            composite_df.to_csv(file_path, index=False)
            logger.info(f"已生成简化的Y综合指数数据文件: {file_path}")
            
            return composite_df
            
    except Exception as e:
        logger.error(f"生成简化Y综合指数数据失败: {e}")
    
    # 如果都失败了，返回空的DataFrame结构
    logger.warning("无法生成Y综合指数数据，返回空结构")
    return create_empty_y_composite_structure()

def get_composite_signal_from_score(score):
    """
    根据综合得分获取信号（辅助函数）
    
    Args:
        score: 综合得分
        
    Returns:
        str: 信号描述
    """
    try:
        if pd.isna(score):
            return '中性'
        
        if score >= 80:
            return "极度乐观"
        elif score >= 65:
            return "乐观"
        elif score >= 35:
            return "中性"
        elif score >= 20:
            return "悲观"
        else:
            return "极度悲观"
    except:
        return '中性'

def create_empty_y_composite_structure():
    """
    创建空的Y综合指数数据结构
    
    Returns:
        DataFrame: 包含基本列结构的空DataFrame
    """
    try:
        # 生成最近30天的日期
        dates = pd.date_range(start=datetime.now() - timedelta(days=30), 
                             end=datetime.now(), freq='D')
        
        # 创建基础结构
        df = pd.DataFrame({
            'candle_begin_time': dates,
            'Y指数': [50.0] * len(dates),  # 默认中性值
            '综合得分_1d': [50.0] * len(dates),
            '综合得分_7d': [50.0] * len(dates),
            '综合得分_30d': [50.0] * len(dates),
            '综合信号_1d': ['中性'] * len(dates),
            '综合信号_7d': ['中性'] * len(dates),
            '综合信号_30d': ['中性'] * len(dates)
        })
        
        # 确保data目录存在并保存
        os.makedirs(DATA_DIR, exist_ok=True)
        file_path = os.path.join(DATA_DIR, 'y_composite_index.csv')
        df.to_csv(file_path, index=False)
        
        logger.info("已创建默认的Y综合指数数据结构")
        return df
        
    except Exception as e:
        logger.error(f"创建默认Y综合指数数据结构失败: {e}")
        return None

def read_market_breadth_data():
    """读取市场宽度数据"""
    try:
        return get_cached_data(os.path.join(DATA_DIR, 'market_breadth_index.csv'))
    except Exception as e:
        logger.error(f"读取市场宽度数据失败: {e}")
        return None

def read_market_indicators_data():
    """
    读取市场指标数据
    
    Returns:
        dict: 包含各种市场指标数据的字典
    """
    start_time = time.time()
    log_function_call('read_market_indicators_data')
    
    data = {}
    
    # 读取山寨币指数数据
    altcoin_df = get_cached_data(os.path.join(DATA_DIR, 'altcoin_season_index.csv'))
    if altcoin_df is not None:
        if 'Unnamed: 0' in altcoin_df.columns:
            altcoin_df = altcoin_df.rename(columns={'Unnamed: 0': 'date'})
            # 处理重复的date值，保留第一个
            altcoin_df = altcoin_df.drop_duplicates(subset=['date'], keep='first')
            altcoin_df['date'] = pd.to_datetime(altcoin_df['date'], errors='coerce')
        elif altcoin_df.index.name is None and len(altcoin_df.columns) >= 3:
            # 如果第一列是日期但没有列名，重置索引
            altcoin_df = altcoin_df.reset_index()
            altcoin_df = altcoin_df.rename(columns={'index': 'date'})
            # 处理重复的date值，保留第一个
            altcoin_df = altcoin_df.drop_duplicates(subset=['date'], keep='first')
            altcoin_df['date'] = pd.to_datetime(altcoin_df['date'], errors='coerce')
        data['altcoin_season'] = altcoin_df
    
    # 读取恐慌贪婪指数数据
    fear_greed_df = get_cached_data(os.path.join(DATA_DIR, 'fear_greed_index.csv'))
    if fear_greed_df is not None:
        if 'Unnamed: 0' in fear_greed_df.columns:
            fear_greed_df = fear_greed_df.rename(columns={'Unnamed: 0': 'date'})
            fear_greed_df['date'] = pd.to_datetime(fear_greed_df['date'])
        data['fear_greed'] = fear_greed_df
    
    # 读取BTC彩虹价格表数据
    if os.path.exists('data/btc_rainbow_table.txt'):
        try:
            with open('data/btc_rainbow_table.txt', 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            # 解析当前价格和区间名称
            header_line = lines[0].strip()
            current_price = float(header_line.split('$')[1].split(' ')[0])
            level_name = lines[1].strip().split('当前区间: ')[1]
            
            # 解析价格区间
            price_levels = []
            for i in range(3, min(13, len(lines))):
                line = lines[i].strip()
                if '：' in line:
                    prices = line.split('：')[1].split('~')[0]
                    try:
                        price_levels.append(float(prices))
                    except:
                        continue
            
            # 确保有10个价格区间
            if len(price_levels) < 10:
                default_prices = [120000, 90000, 70000, 55000, 42000, 32000, 24000, 18000, 13000, 8000]
                price_levels.extend(default_prices[len(price_levels):])
            
            data['btc_rainbow'] = {
                'current_price': current_price,
                'price_levels': price_levels[:10],
                'level_name': level_name
            }
            
        except Exception as e:
            logger.warning(f"解析BTC彩虹价格表数据失败: {e}")
            data['btc_rainbow'] = {
                'current_price': 65000,
                'price_levels': [120000, 90000, 70000, 55000, 42000, 32000, 24000, 18000, 13000, 8000],
                'level_name': "HODL！"
            }
    
    # 读取横截面差异指数数据
    cross_section_df = get_cached_data(os.path.join(DATA_DIR, 'cross_section_diff_index.csv'))
    if cross_section_df is not None and not cross_section_df.empty:
        required_columns = ['candle_begin_time', '横截面差异指数']
        if all(col in cross_section_df.columns for col in required_columns):
            cross_section_df = cross_section_df.dropna(subset=['横截面差异指数'])
            if not cross_section_df.empty:
                data['cross_section_diff'] = cross_section_df
    
    log_performance('read_market_indicators_data', start_time, time.time())
    return data

def safe_get_latest_value(df, column, format_str=None):
    """
    安全获取最新值 - 增强版本，使用数据验证模块
    
    Args:
        df: 数据框
        column: 列名
        format_str: 格式化字符串
            - 支持两种形式：
              1) 带大括号形式（如 "{:.2f}" 或 "{}"）
              2) 标准 format_spec（如 ".2f"）
    
    Returns:
        str: 格式化后的值或"N/A"
    注意：
        - 若 df/列不存在或值为 NaN，返回 "N/A"
        - 若格式化失败，将回退为 str(value)，避免仅因格式问题导致显示 "N/A"
    """
    try:
        # 使用数据验证模块进行安全访问
        if len(df) > 0:
            value = df[column].iloc[-1] if column in df.columns else None
        else:
            value = None
        
        if value is None:
            return "N/A"
            
        # 数值范围验证（对于数值类型）
        if isinstance(value, (int, float)):
            if not validate_numeric_range(value, -1e15, 1e15):
                return "N/A"
                
        if format_str:
            try:
                # 兼容 "{:.2f}" / "{}" 形式
                if isinstance(format_str, str) and ('{' in format_str and '}' in format_str):
                    return format_str.format(value)
                # 兼容标准 format_spec（如 ".2f"）
                return f"{value:{format_str}}"
            except Exception as e:
                logger.debug(f"格式化失败，回退为字符串: {e}")
                # 格式化失败回退
                return str(value)
        else:
            return str(value)
            
    except Exception as e:
        logger.error(f"safe_get_latest_value失败: {e}")
        return "N/A"

def get_latest_valid_numeric(df: pd.DataFrame, column: str, lookback: int = 365, fallback: float = 0.0) -> float:
    """
    获取指定列最近的有效数值（函数级注释）

    目的:
    - 当CSV末尾为空、字符串或NaN时，避免直接 `iloc[-1]` 取值导致显示为0或"N/A"。
    - 支持最大回溯窗口 `lookback`，并在无有效值时返回 `fallback`。

    参数:
    - df: `pandas.DataFrame`，数据表
    - column: 目标列名
    - lookback: 最大回溯记录数（默认365），非法输入自动纠正
    - fallback: 无有效值时的回退数值（默认0.0）

    返回:
    - `float`: 最近一个非空、可解析为浮点数的值；若不存在则返回 `fallback`
    """
    try:
        if df is None or df.empty or column not in df.columns:
            return float(fallback)
        # 将列转换为数值，非法值置为 NaN
        series = pd.to_numeric(df[column], errors='coerce')

        # 纠正非法的 lookback 参数类型
        try:
            n = int(lookback)
            if n <= 0:
                n = 365
        except Exception:
            n = 365

        cleaned = series.tail(n).dropna()
        if cleaned.empty:
            return float(fallback)
        return float(cleaned.iloc[-1])
    except Exception:
        return float(fallback)

# safe_to_list函数已从data_validation模块导入

def generate_y_idx_chart(df):
    """
    生成Y指数图表 - 再次优化（更顺滑的主线 + 渐变面积 + 清爽配色）
    
    Args:
        df: Y指数数据DataFrame
        
    Returns:
        Line: ECharts线图对象或None
    """
    if df is None or df.empty:
        return None

    prepared_df, x_axis, _ = prepare_time_axis(df)
    if not x_axis:
        logger.warning("Y指数数据缺少有效时间轴，无法生成图表")
        return None

    line = Line()
    line.add_xaxis(x_axis)

    # 计算移动平均线
    df_copy = prepared_df.copy()
    df_copy['Y_idx_ma7'] = df_copy['Y_idx'].rolling(window=7, min_periods=1).mean()
    df_copy['Y_idx_ma30'] = df_copy['Y_idx'].rolling(window=30, min_periods=1).mean()
    
    modern_colors = {
        'primary': '#2E86AB',
        'secondary': '#A23B72',
        'tertiary': '#F18F01',
        'danger': '#C73E1D',
        'warning': '#FF9800',
        'success': '#4CAF50'
    }
    
    # 主线：更粗 + 渐变面积 + 隐藏symbol
    line.add_yaxis(
        series_name="Y指数",
        y_axis=safe_to_list(prepared_df['Y_idx']),
        is_smooth=True,
        is_symbol_show=False,
        linestyle_opts=opts.LineStyleOpts(width=4.5, color=modern_colors['primary'], opacity=0.92),
        itemstyle_opts=opts.ItemStyleOpts(color=modern_colors['primary']),
        areastyle_opts=opts.AreaStyleOpts(
            opacity=0.16,
            color=opts.JsCode(f"""
                new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    {{offset: 0, color: '{modern_colors['primary']}'}},
                    {{offset: 1, color: 'rgba(46, 134, 171, 0.05)'}}
                ])
            """)
        ),
        label_opts=opts.LabelOpts(is_show=False),
    )
    
    # 7日与30日均线：更细，风格对比明显
    line.add_yaxis(
        series_name="7日均线",
        y_axis=safe_to_list(df_copy['Y_idx_ma7']),
        is_smooth=True,
        is_symbol_show=False,
        linestyle_opts=opts.LineStyleOpts(width=2.2, color=modern_colors['secondary'], type_='dashed', opacity=0.82),
        label_opts=opts.LabelOpts(is_show=False),
    )
    line.add_yaxis(
        series_name="30日均线",
        y_axis=safe_to_list(df_copy['Y_idx_ma30']),
        is_smooth=True,
        is_symbol_show=False,
        linestyle_opts=opts.LineStyleOpts(width=2.0, color=modern_colors['tertiary'], type_='dotted', opacity=0.75),
        label_opts=opts.LabelOpts(is_show=False),
    )
    
    # 设置全局配置
    line.set_global_opts(
        title_opts=opts.TitleOpts(
            title="Y指数走势图",
            title_textstyle_opts=opts.TextStyleOpts(
                font_size=20, 
                font_weight="bold",
                color="#2c3e50"
            ),
            subtitle="包含移动平均线的综合分析",
            subtitle_textstyle_opts=opts.TextStyleOpts(
                font_size=12,
                color="#7f8c8d"
            )
        ),
        xaxis_opts=opts.AxisOpts(
            type_="category",
            axislabel_opts=opts.LabelOpts(
                rotate=45,
                color="#666666",
                font_size=10
            ),
            axisline_opts=opts.AxisLineOpts(
                linestyle_opts=opts.LineStyleOpts(color="#e0e0e0", width=1)
            ),
            splitline_opts=opts.SplitLineOpts(
                is_show=True,
                linestyle_opts=opts.LineStyleOpts(color="#f5f5f5", width=1)
            )
        ),
        yaxis_opts=opts.AxisOpts(
            type_="value",
            axislabel_opts=opts.LabelOpts(
                formatter="{value}",
                color="#666666",
                font_size=10
            ),
            axisline_opts=opts.AxisLineOpts(
                linestyle_opts=opts.LineStyleOpts(color="#e0e0e0", width=1)
            ),
            splitline_opts=opts.SplitLineOpts(
                is_show=True,
                linestyle_opts=opts.LineStyleOpts(color="#f5f5f5", width=1)
            ),
            min_=-100,
            max_=400,
        ),
        datazoom_opts=[
            opts.DataZoomOpts(
                range_start=70, 
                range_end=100,
                height=30,
                bottom=60
            ),
            opts.DataZoomOpts(type_="inside")
        ],
        tooltip_opts=opts.TooltipOpts(
            trigger="axis",
            background_color="rgba(255,255,255,0.95)",
            border_color="#e0e0e0",
            border_width=1,
            textstyle_opts=opts.TextStyleOpts(color="#333333")
        ),
        legend_opts=opts.LegendOpts(
            pos_top="8%",
            pos_left="center",
            orient="horizontal",
            textstyle_opts=opts.TextStyleOpts(color="#666666")
        ),
        visualmap_opts=opts.VisualMapOpts(
            is_show=True,
            dimension=1,
            pos_right="2%",
            pos_top="15%",
            pieces=[
                {"min": 200, "max": 400, "color": modern_colors['danger'], "label": "高风险区"},
                {"min": 100, "max": 200, "color": modern_colors['warning'], "label": "中风险区"},
                {"min": 0, "max": 100, "color": "#FFEB3B", "label": "注意区"},
                {"min": -100, "max": 0, "color": modern_colors['success'], "label": "机会区"}
            ],
            textstyle_opts=opts.TextStyleOpts(color="#666666", font_size=10)
        ),
        # 添加背景网格
        grid_opts=opts.GridOpts(
            pos_left="8%",
            pos_right="15%",
            pos_top="20%",
            pos_bottom="15%"
        )
    )
    
    # 添加水平参考线 - 使用更美观的样式
    line.set_series_opts(
        markline_opts=opts.MarkLineOpts(
            data=[
                opts.MarkLineItem(
                    y=200, 
                    name="高风险线", 
                    linestyle_opts=opts.LineStyleOpts(
                        color=modern_colors['danger'], 
                        width=2,
                        type_='solid',
                        opacity=0.8
                    )
                ),
                opts.MarkLineItem(
                    y=100, 
                    name="中风险线", 
                    linestyle_opts=opts.LineStyleOpts(
                        color=modern_colors['warning'], 
                        width=2,
                        type_='dashed',
                        opacity=0.8
                    )
                ),
                opts.MarkLineItem(
                    y=0, 
                    name="机会线", 
                    linestyle_opts=opts.LineStyleOpts(
                        color=modern_colors['success'], 
                        width=2,
                        type_='dotted',
                        opacity=0.8
                    )
                ),
            ],
            label_opts=opts.LabelOpts(
                position="end",
                color="#666666",
                font_size=10
            )
        )
    )
    
    return line

def generate_volatility_chart(df, windows=[7, 30, 90]):
    """
    生成波动率图表
    - 使用 safe_to_list 统一生成 x 轴与 y 轴数据，避免在 list/ndarray/Index/Series 等类型上触发异常
    
    Args:
        df: 波动率数据DataFrame
        windows: 时间窗口列表
        
    Returns:
        Line: ECharts线图对象或None
    """
    if df is None or df.empty:
        return None

    prepared_df, x_axis, _ = prepare_time_axis(df)
    if not x_axis:
        logger.warning("波动率数据缺少有效时间轴，无法生成图表")
        return None

    line = Line()
    line.add_xaxis(x_axis)
    
    # 添加不同窗口期的波动率线
    colors = ["#007AFF", "#34C759", "#FF3B30"]
    for i, window in enumerate(windows):
        col_name = f'市场波动率指数_{window}d'
        if col_name in prepared_df.columns:
            line.add_yaxis(
                series_name=f"市场波动率_{window}日",
                y_axis=safe_to_list(prepared_df[col_name]),
                is_smooth=True,
                linestyle_opts=opts.LineStyleOpts(width=2),
                label_opts=opts.LabelOpts(is_show=False),
                itemstyle_opts=opts.ItemStyleOpts(color=colors[i % len(colors)]),
            )
    
    line.set_global_opts(
        title_opts=opts.TitleOpts(
            title="市场波动率指数",
            title_textstyle_opts=opts.TextStyleOpts(font_size=18, font_weight="bold")
        ),
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
            opts.DataZoomOpts(range_start=70, range_end=100),
            opts.DataZoomOpts(type_="inside")
        ],
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
    )
    
    return line

def generate_liquidity_chart(df):
    """
    生成流动性指数图表
    - 使用 safe_to_list 统一生成 x 轴与 y 轴数据，避免在 list/ndarray/Index/Series 等类型上触发异常
    
    Args:
        df: 流动性数据DataFrame
        
    Returns:
        Line: ECharts线图对象或None
    """
    if df is None or df.empty:
        return None

    prepared_df, x_axis, _ = prepare_time_axis(df)
    if not x_axis:
        logger.warning("流动性数据缺少有效时间轴，无法生成图表")
        return None

    line = Line()
    line.add_xaxis(x_axis)
    
    # 添加30日和90日流动性指数线
    if '综合流动性指数_30d' in prepared_df.columns:
        line.add_yaxis(
            series_name="流动性指数_30日",
            y_axis=safe_to_list(prepared_df['综合流动性指数_30d']),
            is_smooth=True,
            linestyle_opts=opts.LineStyleOpts(width=3),
            label_opts=opts.LabelOpts(is_show=False),
            itemstyle_opts=opts.ItemStyleOpts(color="#007AFF"),
        )
    
    if '综合流动性指数_90d' in prepared_df.columns:
        line.add_yaxis(
            series_name="流动性指数_90日",
            y_axis=safe_to_list(prepared_df['综合流动性指数_90d']),
            is_smooth=True,
            linestyle_opts=opts.LineStyleOpts(width=2),
            label_opts=opts.LabelOpts(is_show=False),
            itemstyle_opts=opts.ItemStyleOpts(color="#34C759"),
        )
    
    line.set_global_opts(
        title_opts=opts.TitleOpts(
            title="流动性指数走势图",
            title_textstyle_opts=opts.TextStyleOpts(font_size=18, font_weight="bold")
        ),
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
            opts.DataZoomOpts(range_start=70, range_end=100),
            opts.DataZoomOpts(type_="inside")
        ],
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
        legend_opts=opts.LegendOpts(pos_top="5%"),
    )
    
    return line

def generate_market_breadth_chart(df):
    """
    生成市场宽度指数图表
    - 使用 safe_to_list 统一生成 x 轴与 y 轴数据
    
    Args:
        df: 市场宽度数据DataFrame
        
    Returns:
        Line: ECharts线图对象或None
    """
    if df is None or df.empty:
        return None

    prepared_df, x_axis, _ = prepare_time_axis(df)
    if not x_axis:
        logger.warning("市场宽度数据缺少有效时间轴，无法生成图表")
        return None

    line = Line()
    line.add_xaxis(x_axis)

    # 添加市场宽度指数线
    if '市场宽度指数' in prepared_df.columns:
        line.add_yaxis(
            series_name="市场宽度指数",
            y_axis=safe_to_list(prepared_df['市场宽度指数']),
            is_smooth=True,
            linestyle_opts=opts.LineStyleOpts(width=3),
            label_opts=opts.LabelOpts(is_show=False),
            itemstyle_opts=opts.ItemStyleOpts(color="#007AFF"),
        )
    
    line.set_global_opts(
        title_opts=opts.TitleOpts(
            title="市场宽度指数走势图",
            title_textstyle_opts=opts.TextStyleOpts(font_size=18, font_weight="bold")
        ),
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
            opts.DataZoomOpts(range_start=70, range_end=100),
            opts.DataZoomOpts(type_="inside")
        ],
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
    )
    
    return line

def generate_btc_rainbow_chart(data):
    """
    生成BTC彩虹价格表图表
    
    Args:
        data: BTC彩虹价格表数据
        
    Returns:
        Bar: ECharts柱状图对象或None
    """
    if not data or 'price_levels' not in data:
        return None
    
    # 彩虹颜色配置
    rainbow_colors = [
        "#FF0000",  # 红色 - 最高风险
        "#FF4500",  # 橙红色
        "#FF8C00",  # 深橙色
        "#FFD700",  # 金色
        "#FFFF00",  # 黄色
        "#ADFF2F",  # 黄绿色
        "#00FF00",  # 绿色
        "#00CED1",  # 深青色
        "#0000FF",  # 蓝色
        "#8A2BE2"   # 蓝紫色 - 最低风险
    ]
    
    # 区间名称
    level_names = [
        "最大泡沫区域",
        "卖出区域",
        "FOMO强化区域",
        "这是泡沫吗？",
        "HODL！",
        "仍然便宜",
        "积累区域",
        "买入区域",
        "基本上是火拍卖",
        "火拍卖"
    ]
    
    current_price = data.get('current_price', 65000)
    price_levels = data.get('price_levels', [])
    
    # 创建柱状图
    bar = Bar()
    bar.add_xaxis(level_names)
    
    # 计算每个区间的高度（价格差）
    heights = []
    for i in range(len(price_levels)):
        if i == 0:
            heights.append(price_levels[i] - current_price if price_levels[i] > current_price else 0)
        else:
            heights.append(price_levels[i-1] - price_levels[i] if i < len(price_levels) else 0)
    
    # 添加数据系列
    bar.add_yaxis(
        series_name="价格区间",
        y_axis=heights,
        itemstyle_opts=opts.ItemStyleOpts(
            color=JsCode(f"""
                function(params) {{
                    var colors = {rainbow_colors};
                    return colors[params.dataIndex % colors.length];
                }}
            """)
        ),
        label_opts=opts.LabelOpts(
            is_show=True,
            position="top",
            formatter=JsCode("""
                function(params) {
                    return '$' + params.value.toLocaleString();
                }
            """)
        )
    )
    
    bar.set_global_opts(
        title_opts=opts.TitleOpts(
            title=f"BTC彩虹价格表 (当前: ${current_price:,.0f})",
            subtitle=f"当前区间: {data.get('level_name', 'HODL！')}",
            title_textstyle_opts=opts.TextStyleOpts(font_size=18, font_weight="bold")
        ),
        xaxis_opts=opts.AxisOpts(
            axislabel_opts=opts.LabelOpts(rotate=45, font_size=10)
        ),
        yaxis_opts=opts.AxisOpts(
            name="价格 (USD)",
            axislabel_opts=opts.LabelOpts(formatter="${value}")
        ),
        tooltip_opts=opts.TooltipOpts(
            trigger="axis",
            formatter=JsCode("""
                function(params) {
                    return params[0].name + '<br/>价格: $' + params[0].value.toLocaleString();
                }
            """)
        )
    )
    
    return bar

def get_y_idx_status(df):
    """
    根据Y指数值获取状态

    口径匹配：Y_idx = (全市场涨跌幅指数 + 山寨指数) * 100
    阈值说明（经验分位，便于前端语义展示）：
    - danger（高风险）：Y_idx >= 80
    - warning（中风险）：65 <= Y_idx < 80
    - normal（低风险）：45 <= Y_idx < 65
    - bullish（极低风险/看涨）：Y_idx < 45
    
    Args:
        df: Y指数数据框
        
    Returns:
        str: 状态描述
    """
    if df is None or df.empty:
        return 'unknown'
    try:
        latest_value = float(df['Y_idx'].iloc[-1])
        if pd.isna(latest_value):
            return 'normal'
        if latest_value >= 80:
            return 'danger'  # 高风险
        elif latest_value >= 65:
            return 'warning'  # 中风险
        elif latest_value >= 45:
            return 'normal'   # 低风险
        else:
            return 'bullish'  # 极低风险/看涨
    except Exception:
        # 出现异常时回退到中性
        return 'normal'

def calculate_change_percentage(df, column):
    """
    计算百分比变化 - 增强版本，彻底解决异常变化率问题
    
    Args:
        df: DataFrame
        column: 列名
        
    Returns:
        float: 百分比变化
    """
    try:
        if df is None or df.empty or column not in df.columns:
            logger.debug(f"数据为空或列 {column} 不存在")
            return 0.0
        
        # 过滤非空值和无效值
        non_null_values = df[column].dropna()
        if len(non_null_values) < 2:
            logger.debug(f"列 {column} 有效数据点不足2个")
            return 0.0
        
        # 获取最新值和前一个值
        latest_value = safe_parse_float(non_null_values.iloc[-1], default=None)
        previous_value = safe_parse_float(non_null_values.iloc[-2], default=None)
        
        # 检查数值有效性
        if latest_value is None or previous_value is None:
            logger.warning(f"列 {column} 含非数值或无效字符串，跳过变化率计算")
            return 0.0
        
        # 检查数值有效性
        if not (np.isfinite(latest_value) and np.isfinite(previous_value)):
            logger.warning(f"列 {column} 包含无效数值: {previous_value} -> {latest_value}")
            return 0.0
        
        # 如果前一个值为0或接近0，返回0避免除零错误
        if abs(previous_value) < 1e-10:
            logger.debug(f"列 {column} 前一个值接近0: {previous_value}")
            return 0.0
        
        # 计算变化率
        change_pct = ((latest_value - previous_value) / abs(previous_value)) * 100
        
        # 检查计算结果的有效性
        if not np.isfinite(change_pct):
            logger.warning(f"列 {column} 计算出无效变化率: {change_pct}")
            return 0.0
        
        # 增强的异常检测和处理 - 针对不同指标类型优化
        abs_change = abs(change_pct)
        
        # 特殊处理市场宽度指数：允许更大的波动范围
        is_market_breadth = '市场宽度指数' in column or 'market_breadth' in column.lower()
        is_exchange_flow = '净流入' in column or 'flow' in column.lower() or '流入' in column
        is_funding_rate = '资金费率' in column or 'funding' in column.lower()
        
        # 第一层：极端异常（可能是数据错误）
        extreme_threshold = 2000 if is_market_breadth else 1000
        if abs_change > extreme_threshold:
            logger.error(f"检测到极端异常变化率 {change_pct:.2f}% 在列 {column}, 原始值: {previous_value} -> {latest_value}")
            return 0.0
        
        # 第二层：严重异常（可能是数据跳跃）
        severe_threshold = 1000 if is_market_breadth else 500
        if abs_change > severe_threshold:
            logger.warning(f"检测到严重异常变化率 {change_pct:.2f}% 在列 {column}, 原始值: {previous_value} -> {latest_value}")
            # 市场宽度指数允许保留部分变化，其他指标直接归零
            if is_market_breadth:
                # 限制市场宽度指数变化率在±500%
                limited_change = np.sign(change_pct) * min(abs_change, 500.0)
                logger.info(f"市场宽度指数异常变化率限制为: {limited_change:.2f}%")
                return limited_change
            else:
                return 0.0
        
        # 第三层：中等异常（需要限制范围）
        moderate_threshold = 300 if is_market_breadth else 95
        if abs_change > moderate_threshold:
            logger.warning(f"检测到异常变化率 {change_pct:.2f}% 在列 {column}, 原始值: {previous_value} -> {latest_value}")
            
            if is_market_breadth:
                # 市场宽度指数限制在±200%
                limited_change = np.sign(change_pct) * min(abs_change, 200.0)
                logger.info(f"市场宽度指数变化率限制为: {limited_change:.2f}%")
                return limited_change
            elif is_exchange_flow:
                logger.warning(f"交易所流入数据异常变化率 {change_pct:.2f}%，限制为±50%")
                return np.sign(change_pct) * 50.0
            elif is_funding_rate:
                # 资金费率限制在±100%
                return np.sign(change_pct) * min(abs_change, 100.0)
            else:
                # 其他指标限制在±80%
                return np.sign(change_pct) * 80.0
        
        # 第四层：较大异常（需要限制）
        large_threshold = 100 if is_market_breadth else 50
        if abs_change > large_threshold:
            logger.info(f"检测到较大变化率 {change_pct:.2f}% 在列 {column}, 原始值: {previous_value} -> {latest_value}")
            
            if is_market_breadth:
                # 市场宽度指数在这个范围内允许通过
                return change_pct
            elif is_exchange_flow:
                # 交易所净流入数据限制在±30%
                return np.sign(change_pct) * min(abs_change, 30.0)
            elif is_funding_rate:
                # 资金费率限制在±60%
                return np.sign(change_pct) * min(abs_change, 60.0)
            else:
                return change_pct
        
        # 返回处理后的变化率，保留2位小数
        return round(change_pct, 2)
        
    except Exception as e:
        logger.error(f"计算变化百分比失败 - 列: {column}, 错误: {e}")
        return 0.0

def calculate_7_30_day_comparison(df, column, mode='percentage'):
    """
    增强版7日和30日数据对比计算（修复版）
    - 修复 off-by-one 错误：7日使用 t-7（iloc[-8]），30日使用 t-30（iloc[-31]）
    - 优先按“日期回溯到 t-7 / t-30（及之前最近一条记录）”来计算，若日期列缺失或无法解析则回退到位置索引
    - 保留并复用异常检测机制（本次放宽点差模式阈值，并对 Y 指数定制更宽阈值）：
        * 百分比模式：当 current/historical 比值 > 50 或 < 1/50 时，判定为异常（direction = 'anomaly'）
        * 点差模式：默认绝对差阈值 80；针对 Y 指数阈值放宽至 200，避免“正常大波动”被误判
    参数:
        df: 数据框（需包含 column 列）
        column: 用于对比的列名（例如 'Y_idx'、'市场净流入_1d'）
        mode: 计算模式，'percentage'(相对百分比) 或 'point'(绝对百分点/点差)
    返回:
        dict: {
            'day_7': {'change': float, 'direction': 'up'|'down'|'flat'|'anomaly'},
            'day_30': {'change': float, 'direction': 'up'|'down'|'flat'|'anomaly'}
        }
    """
    try:
        # 处理数值输入的简化测试模式
        if not isinstance(df, pd.DataFrame):
            # 如果传入的是数值，直接返回默认值（用于测试）
            return {
                'day_7': {'change': 0, 'direction': 'flat'},
                'day_30': {'change': 0, 'direction': 'flat'}
            }
        
        if df is None or df.empty or column not in df.columns:
            return {
                'day_7': {'change': 0, 'direction': 'flat'},
                'day_30': {'change': 0, 'direction': 'flat'}
            }
        
        # 1) 选择日期列并排序
        date_col = None
        for col in ['candle_begin_time', 'date', 'Date', 'timestamp']:
            if col in df.columns:
                date_col = col
                break
        
        if date_col is None:
            # 无日期列则按索引排序并使用位置索引回退
            df_sorted = df.copy().sort_index()
            has_datetime = False
        else:
            df_sorted = df.sort_values(date_col).reset_index(drop=True)
            # 尝试将日期列转换为 datetime
            has_datetime = True
            try:
                df_sorted[date_col] = pd.to_datetime(df_sorted[date_col])
            except Exception:
                has_datetime = False
        
        # 使用安全数据访问获取当前值
        if len(df_sorted) > 0:
            current_value = df_sorted[column].iloc[-1] if column in df_sorted.columns else None
        else:
            current_value = None
        if current_value is None:
            logger.error(f"无法获取列 {column} 的当前值")
            return {
                'day_7': {'change': 0, 'direction': 'flat'},
                'day_30': {'change': 0, 'direction': 'flat'}
            }
        
        # 数值范围验证
        if not validate_numeric_range(current_value, -1e15, 1e15):
            logger.warning(f"当前值超出合理范围: {current_value}")
            return {
                'day_7': {'change': 0, 'direction': 'anomaly'},
                'day_30': {'change': 0, 'direction': 'anomaly'}
            }
            
        current_value = float(current_value)
        
        # 2) 异常检测函数
        def is_data_anomaly(current, historical):
            """
            函数说明：
            - 根据模式进行异常判断
            - 百分比模式：仍旧使用倍率法，极端倍率判为异常
            - 点差模式：使用更宽松的绝对差阈值；针对 Y 指数进一步放宽，避免误报
            """
            if pd.isna(historical) or np.isinf(historical) or historical == 0 or pd.isna(current) or np.isinf(current):
                return True
            if mode == 'point':
                col_lower = str(column).lower()
                # 默认点差阈值（适用于百分比型/百分点型序列，范围常在0-100）
                threshold = 80.0
                # 对 Y 指数序列放宽阈值：其波动幅度可能 > 100
                if 'y_idx' in col_lower or 'y指数' in col_lower:
                    threshold = 200.0
                try:
                    abs_diff = abs(float(current) - float(historical))
                except Exception:
                    return True
                return abs_diff > threshold
            else:
                # 百分比模式：检测相对比值是否异常
                try:
                    ratio = abs(float(current) / float(historical))
                except Exception:
                    return True
                return ratio > 50 or ratio < 0.02
        
        # 3) 按日期回溯获取 n 天前值（失败时回退位置索引）- 增强版
        def get_value_n_days_ago(n_days: int):
            """
            返回 t-n_days（含）之前最近一条记录的 column 值；
            若无法通过日期定位，则使用位置索引 iloc[-(n_days+1)] 回退。
            增强了边界检查和错误处理，使用数据验证模块。
            """
            # 使用局部变量避免作用域问题
            local_has_datetime = has_datetime
            
            try:
                # 使用数据验证模块进行DataFrame访问验证
                if not validate_dataframe_access(df_sorted, column):
                    logger.debug(f"DataFrame访问验证失败，无法获取 {n_days} 天前数据")
                    return None
                
                # 过滤有效数据
                valid_data = df_sorted[df_sorted[column].notna()]
                if valid_data.empty:
                    logger.debug(f"列 {column} 无有效数据，无法获取 {n_days} 天前数据")
                    return None
                
                # 时间序列数据验证
                if local_has_datetime and date_col in df_sorted.columns:
                    if not validate_time_series_data(df_sorted, date_col):
                        logger.debug(f"时间序列数据验证失败，回退到位置索引")
                        local_has_datetime = False
                
                # 日期定位方式
                if local_has_datetime and date_col in df_sorted.columns:
                    try:
                        # 获取最新日期
                        latest_date = df_sorted[date_col].iloc[-1]
                        target_date = latest_date - pd.Timedelta(days=n_days)
                        
                        # 查找目标日期及之前的数据
                        hist_df = df_sorted[df_sorted[date_col] <= target_date]
                        if not hist_df.empty:
                            # 进一步过滤有效数据
                            hist_valid = hist_df[hist_df[column].notna()]
                            if not hist_valid.empty:
                                # 使用安全数据访问函数
                                if len(hist_valid) > 0:
                                    value = hist_valid[column].iloc[-1] if column in hist_valid.columns else None
                                else:
                                    value = None
                                if value is not None and validate_numeric_range(value, -1e15, 1e15):
                                    logger.debug(f"通过日期定位获取 {n_days} 天前数据: {value}")
                                    return float(value)
                                else:
                                    logger.debug(f"日期定位获取的数据无效或超出范围: {value}")
                    except Exception as e:
                        logger.debug(f"日期定位失败: {e}，回退到位置索引")
                
                # 位置索引回退方式（使用安全访问函数）
                total_rows = len(valid_data)
                required_index = n_days + 1  # t-n 天对应 iloc[-(n+1)]
                
                if total_rows >= required_index:
                    try:
                        # 使用安全数据访问函数
                        if len(valid_data) >= required_index:
                            value = valid_data[column].iloc[-required_index] if column in valid_data.columns else None
                        else:
                            value = None
                        if value is not None:
                            # 数值范围验证
                            if validate_numeric_range(value, -1e15, 1e15):
                                logger.debug(f"通过位置索引获取 {n_days} 天前数据: {value} (索引: -{required_index})")
                                return float(value)
                            else:
                                logger.warning(f"{n_days}天前数据超出合理范围: {value}")
                                return None
                        else:
                            logger.warning(f"安全访问返回空值，索引: -{required_index}")
                            return None
                    except (ValueError, TypeError) as e:
                        logger.warning(f"位置索引获取 {n_days} 天前数据失败: {e}")
                        return None
                else:
                    logger.debug(f"数据不足：需要 {required_index} 行数据，实际只有 {total_rows} 行")
                    return None
                
            except Exception as e:
                logger.error(f"获取 {n_days} 天前数据时发生异常: {e}")
                return None
            
            return None
        
        # 4) 7日对比（t 与 t-7）- 增强版
        day_7_change = 0.0
        day_7_direction = 'flat'
        hist_7 = get_value_n_days_ago(7)
        
        if hist_7 is not None:
            try:
                # 数据有效性检查
                if pd.isna(hist_7) or np.isinf(hist_7) or pd.isna(current_value) or np.isinf(current_value):
                    logger.debug(f"7日对比数据无效: 当前值={current_value}, 7日前值={hist_7}")
                    day_7_direction = 'anomaly'
                elif not is_data_anomaly(current_value, hist_7):
                    if mode == 'point':
                        # 百分点模式：计算绝对百分点变化
                        change = current_value - hist_7
                        # 动态限制：根据数据类型调整阈值
                        if 'market_breadth' in column.lower() or 'breadth' in column.lower():
                            change = max(-30.0, min(30.0, change))  # 市场宽度指数放宽限制
                        else:
                            change = max(-20.0, min(20.0, change))  # 其他指标保持原限制
                    else:
                        # 百分比模式：计算相对百分比变化
                        if abs(hist_7) < 1e-10:  # 避免除零错误
                            logger.debug(f"7日前值过小，无法计算百分比变化: {hist_7}")
                            day_7_direction = 'anomaly'
                        else:
                            change = ((current_value - hist_7) / abs(hist_7)) * 100.0
                            # 动态限制：根据数据类型调整阈值
                            if 'funding' in column.lower() or 'rate' in column.lower():
                                change = max(-200.0, min(200.0, change))  # 资金费率类指标放宽限制
                            else:
                                change = max(-50.0, min(50.0, change))  # 其他指标保持原限制
                    
                    # 额外的合理性检查
                    if abs(change) > 500:  # 超过500%的变化视为异常
                        logger.warning(f"7日变化率过大: {change}, 当前值: {current_value}, 7日前值: {hist_7}")
                        day_7_direction = 'anomaly'
                    else:
                        day_7_change = round(change, 2)
                        day_7_direction = 'up' if change > 0.1 else ('down' if change < -0.1 else 'flat')
                        logger.debug(f"7日对比成功: 变化={day_7_change}, 方向={day_7_direction}")
                else:
                    logger.debug(f"7日数据异常检测触发: 当前值={current_value}, 7日前值={hist_7}")
                    day_7_direction = 'anomaly'
                    
            except Exception as e:
                logger.error(f"7日对比计算异常: {e}")
                day_7_direction = 'anomaly'
        else:
            logger.debug(f"无法获取7日前数据，列: {column}")
        # 否则保持默认 flat
        
        # 5) 30日对比（t 与 t-30）- 增强版
        day_30_change = 0.0
        day_30_direction = 'flat'
        hist_30 = get_value_n_days_ago(30)
        
        if hist_30 is not None:
            try:
                # 数据有效性检查
                if pd.isna(hist_30) or np.isinf(hist_30) or pd.isna(current_value) or np.isinf(current_value):
                    logger.debug(f"30日对比数据无效: 当前值={current_value}, 30日前值={hist_30}")
                    day_30_direction = 'anomaly'
                elif not is_data_anomaly(current_value, hist_30):
                    if mode == 'point':
                        # 百分点模式：计算绝对百分点变化
                        change = current_value - hist_30
                        # 动态限制：根据数据类型调整阈值
                        if 'market_breadth' in column.lower() or 'breadth' in column.lower():
                            change = max(-60.0, min(60.0, change))  # 市场宽度指数放宽限制
                        else:
                            change = max(-50.0, min(50.0, change))  # 其他指标保持原限制
                    else:
                        # 百分比模式：计算相对百分比变化
                        if abs(hist_30) < 1e-10:  # 避免除零错误
                            logger.debug(f"30日前值过小，无法计算百分比变化: {hist_30}")
                            day_30_direction = 'anomaly'
                        else:
                            change = ((current_value - hist_30) / abs(hist_30)) * 100.0
                            # 动态限制：根据数据类型调整阈值
                            if 'funding' in column.lower() or 'rate' in column.lower():
                                change = max(-300.0, min(300.0, change))  # 资金费率类指标放宽限制
                            elif 'mvrv' in column.lower() or 'supply' in column.lower():
                                change = max(-150.0, min(150.0, change))  # MVRV和供应量类指标适中限制
                            else:
                                change = max(-100.0, min(100.0, change))  # 其他指标保持原限制
                    
                    # 额外的合理性检查
                    if abs(change) > 1000:  # 超过1000%的变化视为异常
                        logger.warning(f"30日变化率过大: {change}, 当前值: {current_value}, 30日前值: {hist_30}")
                        day_30_direction = 'anomaly'
                    else:
                        day_30_change = round(change, 2)
                        day_30_direction = 'up' if change > 0.1 else ('down' if change < -0.1 else 'flat')
                        logger.debug(f"30日对比成功: 变化={day_30_change}, 方向={day_30_direction}")
                else:
                    logger.debug(f"30日数据异常检测触发: 当前值={current_value}, 30日前值={hist_30}")
                    day_30_direction = 'anomaly'
                    
            except Exception as e:
                logger.error(f"30日对比计算异常: {e}")
                day_30_direction = 'anomaly'
        else:
            logger.debug(f"无法获取30日前数据，列: {column}")
        # 否则保持默认 flat
        
        return {
            'day_7': {'change': day_7_change, 'direction': day_7_direction},
            'day_30': {'change': day_30_change, 'direction': day_30_direction}
        }
        
    except Exception as e:
        logger.warning(f"计算7/30日对比时出错: {e}")
        return {
            'day_7': {'change': 0, 'direction': 'flat'},
            'day_30': {'change': 0, 'direction': 'flat'}
        }

def read_mvrv_data():
    """
    读取MVRV数据（函数级注释）

    目的:
    - 优先使用 `mvrv_index.csv` 作为主数据源。
    - 当 `mvrv_index.csv` 为空或不含任何可解析的有效数值时，自动回退到 `mvrv_indicator.csv`。

    返回:
    - `pandas.DataFrame`：可用的MVRV数据表；若全部读取失败则返回 `None`。
    """
    try:
        idx_df = get_cached_data(os.path.join(DATA_DIR, 'mvrv_index.csv'))
    except Exception as e:
        logger.warning(f"读取 mvrv_index.csv 失败，尝试回退: {e}")
        idx_df = None

    def _has_usable_mvrv(df: pd.DataFrame) -> bool:
        """内部辅助: 判断数据表是否含有可用的MVRV数值列（函数级注释）"""
        try:
            if df is None or df.empty:
                return False
            candidates = ['MVRV', 'mvrv_365d', 'mvrv_90d', 'mvrv_30d']
            for col in candidates:
                if col in df.columns:
                    s = pd.to_numeric(df[col], errors='coerce').dropna()
                    if not s.empty:
                        return True
            return False
        except Exception:
            return False

    if not _has_usable_mvrv(idx_df):
        try:
            alt_df = get_cached_data(os.path.join(DATA_DIR, 'mvrv_indicator.csv'))
            if alt_df is not None and not alt_df.empty:
                logger.info("mvrv_index.csv 为空或无效，已回退到 mvrv_indicator.csv")
                return alt_df
            else:
                logger.warning("mvrv_indicator.csv 空或不可用")
                return idx_df
        except Exception as e:
            logger.error(f"读取 mvrv_indicator.csv 失败: {e}")
            return idx_df

    return idx_df

def read_stablecoin_supply_data():
    """读取稳定币供应量数据"""
    try:
        return get_cached_data(os.path.join(DATA_DIR, 'stablecoin_supply.csv'))
    except Exception as e:
        logger.error(f"读取稳定币供应量数据失败: {e}")
        return None


def map_stablecoin_signal_to_status(signal: str) -> str:
    """
    将稳定币供应量的原始信号映射为概览卡片所需的状态文本。

    参数:
        signal (str): 原始信号，可能的取值包括：
            - 早期版本: '增长'、'收缩'、'中性'
            - 当前CSV: '快速扩张'、'稳定增长'、'基本稳定'、'轻微收缩'、'快速收缩'、'无数据'

    返回:
        str: 概览卡片状态文本，'看涨'、'看跌'、'中性' 或 '未知'
    """
    mapping = {
        # 当前CSV的分类
        '快速扩张': '看涨',
        '稳定增长': '看涨',
        '基本稳定': '中性',
        '轻微收缩': '看跌',
        '快速收缩': '看跌',
        '无数据': '未知',
        # 兼容历史分类
        '增长': '看涨',
        '收缩': '看跌',
        '中性': '中性',
    }
    return mapping.get(str(signal), '中性')


def map_extreme_ratio_signal_to_status(up_count, down_count, total_count):
    """
    将极值比率的原始信号映射为概览卡片所需的状态文本
    
    Args:
        up_count: 上涨币种数量
        down_count: 下跌币种数量  
        total_count: 总币种数量
        
    Returns:
        str: 前端期望的状态值（"看涨"/"看跌"/"中性"/"未知"）
    """
    if total_count == 0:
        return '未知'
    
    up_ratio = (up_count / total_count) * 100
    down_ratio = (down_count / total_count) * 100
    
    # 根据上涨下跌比例判断市场状态
    if up_ratio > down_ratio * 1.5:  # 上涨占比显著高于下跌
        return '看涨'
    elif down_ratio > up_ratio * 1.5:  # 下跌占比显著高于上涨
        return '看跌'
    else:
        return '中性'

def map_up_down_ratio_status(up_ratio: float, down_ratio: float) -> str:
    """
    根据涨跌比重判断市场状态

    参数:
        up_ratio (float): 上涨比重(百分比, 0-100)
        down_ratio (float): 下跌比重(百分比, 0-100)

    返回:
        str: 市场状态文本（'看涨'/'看跌'/'中性'/'未知'）
    """
    try:
        if up_ratio is None or down_ratio is None:
            return '未知'
        # 简单阈值：谁显著占优就给对应状态，否则中性
        if up_ratio > down_ratio * 1.5:
            return '看涨'
        elif down_ratio > up_ratio * 1.5:
            return '看跌'
        else:
            return '中性'
    except Exception:
        return '未知'

def map_cross_section_level_to_status(level_text: str) -> str:
    """
    将横截面差异指数的分化程度文本映射为状态
    
    参数:
        level_text (str): 市场分化程度文本
        
    返回:
        str: 状态文本（'高分化'/'中分化'/'低分化'/'中性'/'未知'）
    """
    try:
        level_str = str(level_text).strip()
        if '高' in level_str or '极高' in level_str:
            return '高分化'
        elif '中' in level_str or '中等' in level_str:
            return '中分化'
        elif '低' in level_str or '极低' in level_str:
            return '低分化'
        elif '正常' in level_str:
            return '中性'
        else:
            return '未知'
    except Exception:
        return '未知'

def read_exchange_flow_data():
    """读取交易所净流入流出数据"""
    try:
        return get_cached_data(os.path.join(DATA_DIR, 'exchange_flow.csv'))
    except Exception as e:
        logger.error(f"读取交易所净流入流出数据失败: {e}")
        return None

# 删除重复定义，保留统一签名的实现（见上）

# 新增：记录最近一次自动刷新时间
EXCHANGE_FLOW_LAST_REFRESH = None

def ensure_exchange_flow_recent(max_age_days: int = 1, min_interval_minutes: int = 180) -> bool:
    """
    确保交易所净流入数据不过期（函数级注释）
    行为：
    - 当数据缺失或超过 max_age_days 过期时，拉取市场数据并生成 data/exchange_flow.csv
    - 使用 交易所净流入流出.process_data(...)（稳定存在的方法）生成并保存CSV
    参数:
        max_age_days: 允许的最大数据延迟天数（超过则尝试自动刷新）
        min_interval_minutes: 自动刷新调用的最小时间间隔（分钟），避免高频拉取
    返回:
        bool: 是否触发了刷新（True 表示已刷新，False 表示无需或限流）
    """
    try:
        df = read_exchange_flow_data()
        latest_date = None
        if df is not None and not df.empty and 'candle_begin_time' in df.columns:
            latest_date = pd.to_datetime(df['candle_begin_time'].iloc[-1])

        now = pd.Timestamp.now()
        need_refresh = latest_date is None or ((now - latest_date).days > max_age_days)

        # 限流：min_interval_minutes 内不重复刷新
        global EXCHANGE_FLOW_LAST_REFRESH
        if not need_refresh:
            return False
        if EXCHANGE_FLOW_LAST_REFRESH:
            delta_min = (now.to_pydatetime() - EXCHANGE_FLOW_LAST_REFRESH).total_seconds() / 60.0
            if delta_min < min_interval_minutes:
                return False

        logger.info("触发交易所净流入数据自动刷新")
        acc = 'qqdev'
        backdays = 365
        start_time_data = datetime.now() - timedelta(days=backdays)

        # 构建交易所（复用稳健配置）
        try:
            exchange = ccxt.binance(cfg.binance.get_exchange_config())
        except Exception as e:
            logger.warning(f"主配置失败: {e}，尝试备用配置")
            try:
                exchange = ccxt.binance(cfg.binance.get_backup_config())
            except Exception as e2:
                logger.warning(f"备用配置失败: {e2}，回退到默认配置")
                exchange = ccxt.binance({
                    'enableRateLimit': True,
                    'timeout': 60000,
                    'options': {'defaultType': 'future'}
                })

        # 拉取市场数据并更新净流入CSV
        symbol_list = binance.get_usdt_swap_symbols_robust(exchange)
        run_time = common.cacu_run_time('1d', datetime.now())
        max_day = max(30, backdays)
        df_dict = binance.u_furture_fetch_all_swap_candle_data(
            exchange, symbol_list, '1d', run_time, max_day * 2 + 10, True, False, njobs=60
        )

        new_exchange_flow_obj = ExchangeFlowMonitor()
        df_new = new_exchange_flow_obj.process_data(
            df_dict=df_dict,
            windows=[1, 7, 30],
            backdays=backdays,
            interval='1d',
            start_time=start_time_data
        )
        if df_new is not None and not df_new.empty:
            new_exchange_flow_obj.save_csv(df_new)

        EXCHANGE_FLOW_LAST_REFRESH = datetime.now()
        logger.info("交易所净流入数据自动刷新完成")
        return True
    except Exception as e:
        logger.error(f"自动刷新交易所净流入失败: {e}")
        return False

def run_with_timeout(func, args=(), kwargs=None, timeout_sec: int = 8):
    """
    在后台线程中执行函数并设置最大等待时间，避免阻塞。

    参数:
        func: 可调用对象
        args: 位置参数元组
        kwargs: 关键字参数字典
        timeout_sec: 主线程等待的最大秒数

    返回:
        dict: {"completed": bool, "result": Any or None}

    说明:
        - 若在超时前执行完成，返回 completed=True 和执行结果
        - 若超时未完成，返回 completed=False，并让后台线程继续运行，不阻塞请求
    """
    try:
        kwargs = kwargs or {}
        result_box = {"result": None}

        def _target():
            try:
                result_box["result"] = func(*args, **kwargs)
            except Exception as e:
                logger.warning(f"后台任务执行失败: {e}")

        t = Thread(target=_target, daemon=True)
        t.start()
        t.join(timeout_sec)
        if t.is_alive():
            logger.info(f"后台任务超时({timeout_sec}s)，继续在后台执行，不阻塞响应")
            return {"completed": False, "result": None}
        return {"completed": True, "result": result_box["result"]}
    except Exception as e:
        logger.warning(f"run_with_timeout异常: {e}")
        return {"completed": False, "result": None}

def read_funding_rate_monitor_data():
    """
    读取资金费率监控数据文件 data/funding_rate_monitor.csv。
    返回值:
        - pd.DataFrame: 若成功读取则返回按时间升序的数据表；
        - 空 DataFrame: 读取失败或文件不存在时返回空表。
    说明:
        - 关键列包含:
            - 'candle_begin_time' 时间戳
            - '平均资金费率' (小数表示的百分比, 如 0.001=0.1%)
            - '多空力量对比' (百分比数值, 如 65 表示65%)
            - '费率波动状态' (分类文本)
    """
    try:
        file_path = os.path.join(DATA_DIR, 'funding_rate_monitor.csv')
        df = get_cached_data(file_path)
        if df is None or df.empty:
            return pd.DataFrame()

        # 统一列名清理（兼容异常CSV）
        df.columns = [str(c).strip() for c in df.columns]

        # 强制转换关键数值列
        for col in ['平均资金费率', '平均资金费率_7d', '平均资金费率_30d', '多空力量对比']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # 时间排序
        if 'candle_begin_time' in df.columns:
            df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'], errors='coerce')
            df = df.dropna(subset=['candle_begin_time'])
            df = df.sort_values('candle_begin_time').reset_index(drop=True)

        # 删除“平均资金费率”为全空的行
        if '平均资金费率' in df.columns:
            df = df.dropna(subset=['平均资金费率'])

        return df
    except Exception as e:
        logger.warning(f"读取资金费率监控数据失败: {e}")
        return pd.DataFrame()

def read_altcoin_data():
    """
    读取山寨币指数数据
    
    Returns:
        pd.DataFrame: 山寨币指数数据，包含日期和指数值
    """
    try:
        file_path = os.path.join(DATA_DIR, 'altcoin_index.csv')
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            if 'candle_begin_time' in df.columns:
                df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'])
            elif 'Unnamed: 0' in df.columns:
                df = df.rename(columns={'Unnamed: 0': 'date'})
                df['date'] = pd.to_datetime(df['date'])
            return df
        else:
            logger.warning(f"山寨币指数数据文件不存在: {file_path}")
            return None
    except Exception as e:
        logger.error(f"读取山寨币指数数据失败: {e}")
        return None

def read_altcoin_season_data():
    """
    读取山寨币季节指数数据 - 修复duplicate keys错误
    
    Returns:
        pd.DataFrame: 山寨币季节指数数据
    """
    try:
        file_path = os.path.join(DATA_DIR, 'altcoin_season_index.csv')
        if os.path.exists(file_path):
            # 先读取文件查看结构
            with open(file_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                logger.info(f"山寨币季节指数文件第一行: {first_line}")
            
            # 不使用index_col，直接读取所有数据
            df = pd.read_csv(file_path)
            
            # 处理可能的Unnamed列或第一列作为日期
            if 'Unnamed: 0' in df.columns:
                df = df.rename(columns={'Unnamed: 0': 'date'})
            elif df.columns[0] not in ['date', 'candle_begin_time'] and len(df.columns) >= 3:
                # 第一列可能是日期列但没有列名
                df = df.rename(columns={df.columns[0]: 'date'})
            
            # 确保有date列
            if 'date' not in df.columns:
                logger.error("山寨币季节指数数据中没有找到日期列")
                return None
            
            # 处理重复日期 - 在转换日期之前先清理
            logger.info(f"处理前数据形状: {df.shape}")
            
            # 删除空的日期行
            df = df.dropna(subset=['date'])
            df = df[df['date'].astype(str).str.strip() != '']
            
            # 检查并处理重复日期（保留第一个）
            duplicate_dates = df['date'].duplicated()
            if duplicate_dates.any():
                logger.warning(f"发现 {duplicate_dates.sum()} 个重复日期，将保留第一个")
                df = df[~duplicate_dates]
            
            # 安全地转换日期列
            try:
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
            except Exception as date_error:
                logger.error(f"日期转换失败: {date_error}")
                # 尝试逐行转换
                valid_dates = []
                for idx, date_str in enumerate(df['date']):
                    try:
                        valid_date = pd.to_datetime(date_str)
                        valid_dates.append(True)
                    except:
                        logger.warning(f"无效日期在第{idx}行: {date_str}")
                        valid_dates.append(False)
                
                df = df[valid_dates]
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
            
            # 删除无效日期
            df = df.dropna(subset=['date'])
            
            # 按日期排序
            df = df.sort_values('date')
            
            # 重置索引
            df = df.reset_index(drop=True)
            
            # 强制转换数值列并处理空值
            numeric_columns = ['Altcoin Month', 'Altcoin Season', 'Altcoin Year']
            for col in numeric_columns:
                if col in df.columns:
                    # 将空字符串转为NaN
                    df[col] = df[col].replace('', np.nan)
                    # 强制转换为数值类型
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            logger.info(f"山寨币季节指数数据列名: {safe_to_list(df.columns)}")
            logger.info(f"处理后数据形状: {df.shape}")
            logger.info(f"日期范围: {df['date'].min()} 到 {df['date'].max()}")
            
            return df
        else:
            logger.warning(f"山寨币季节指数数据文件不存在: {file_path}")
            return None
    except Exception as e:
        logger.error(f"读取山寨币季节指数数据失败: {e}")
        logger.error(traceback.format_exc())
        return None

def read_fear_greed_data():
    """
    读取恐慌贪婪指数数据
    
    Returns:
        pd.DataFrame: 恐慌贪婪指数数据
    """
    try:
        file_path = os.path.join(DATA_DIR, 'fear_greed_index.csv')
        if os.path.exists(file_path):
            df = get_filtered_data(file_path)
            if df is not None and not df.empty:
                # 强制转换数值列
                numeric_columns = ['fear_greed_index', 'value', 'score']
                for col in numeric_columns:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
            return df
        else:
            logger.warning(f"恐慌贪婪指数数据文件不存在: {file_path}")
            return None
    except Exception as e:
        logger.error(f"读取恐慌贪婪指数数据失败: {e}")
        return None

def read_bid_ask_spread_data():
    """
    读取盘口价差监控数据，增强数值列处理
    
    Returns:
        pd.DataFrame: 盘口价差监控数据
    """
    try:
        file_path = os.path.join(DATA_DIR, 'bid_ask_spread_monitor.csv')
        if os.path.exists(file_path):
            df = get_filtered_data(file_path)
            if df is not None and not df.empty:
                # 强制转换关键数值列
                numeric_columns = [
                    '市场平均价差_1d', '市场价差标准差_1d', '市场价差变异系数_1d',
                    '平均价差(bp)', '价差波动率(bp)', '平均价差_1d', 'avg_spread_1d',
                    '价差标准差_1d', 'spread_std_1d', '平均价差'
                ]
                for col in numeric_columns:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                        
                # 时间排序
                if 'candle_begin_time' in df.columns:
                    df = df.sort_values('candle_begin_time').reset_index(drop=True)
                    
            return df
        else:
            logger.warning(f"盘口价差监控数据文件不存在: {file_path}")
            return None
    except Exception as e:
        logger.error(f"读取盘口价差监控数据失败: {e}")
        return None

def read_extreme_move_ratio_data():
    """
    读取极值比率数据，特别处理 inf 值
    
    Returns:
        pd.DataFrame: 极值比率数据
    """
    try:
        file_path = os.path.join(DATA_DIR, 'extreme_move_ratio.csv')
        if os.path.exists(file_path):
            df = get_filtered_data(file_path)
            if df is not None and not df.empty:
                # 强制转换数值列，特别处理包含比率的列
                numeric_columns = [
                    '爆拉暴跌比率_1d', '爆拉暴跌比率_7d', '爆拉暴跌比率_30d',
                    '平均极端程度_1d', '平均极端程度_7d', '平均极端程度_30d',
                    '最大极端程度_1d', '最大极端程度_7d', '最大极端程度_30d'
                ]
                for col in df.columns:
                    # 处理所有数值型列
                    if df[col].dtype == 'object':
                        # 先尝试转换为数值
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    
                # 再次处理无穷大值（get_filtered_data 已经处理过一次，这里是双重保险）
                df = df.replace([np.inf, -np.inf], np.nan)
                
                # 时间排序
                if 'candle_begin_time' in df.columns:
                    df = df.sort_values('candle_begin_time').reset_index(drop=True)
                    
            return df
        else:
            logger.warning(f"极值比率数据文件不存在: {file_path}")
            return None
    except Exception as e:
        logger.error(f"读取极值比率数据失败: {e}")
        return None

def read_or_build_advanced_indicators():
    """
    读取高级指标数据（如市值加权指数）
    优先从 data/advanced_indicators.csv 读取，自动过滤未来日期，规范列名为 market_cap_weighted
    """
    try:
        file_path = os.path.join(DATA_DIR, 'advanced_indicators.csv')
        if os.path.exists(file_path):
            df = get_cached_data(file_path)
            # 规范时间列并过滤未来日期
            if df is not None and not df.empty and 'candle_begin_time' in df.columns:
                df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'], errors='coerce')
                now_ts = pd.Timestamp.now()
                df = df.dropna(subset=['candle_begin_time'])
                df = df[df['candle_begin_time'] <= now_ts].sort_values('candle_begin_time').reset_index(drop=True)
            # 统一列名：market_cap_weighted_index -> market_cap_weighted
            if df is not None and not df.empty:
                if 'market_cap_weighted_index' in df.columns and 'market_cap_weighted' not in df.columns:
                    df = df.rename(columns={'market_cap_weighted_index': 'market_cap_weighted'})
            return df
        else:
            logger.warning(f"高级指标数据文件不存在: {file_path}")
            return None
    except Exception as e:
        logger.warning(f"读取高级指标数据失败: {e}")
        return None

def get_market_sentiment_from_value(value):
    """
    根据数值获取市场情绪
    
    Args:
        value: 数值
        
    Returns:
        str: 情绪描述
    """
    try:
        if pd.isna(value):
            return '未知'
        
        if value > 0.6:
            return '极度乐观'
        elif value > 0.2:
            return '乐观'
        elif value > -0.2:
            return '中性'
        elif value > -0.6:
            return '悲观'
        else:
            return '极度悲观'
    except:
        return '未知'


def map_fear_greed_level(value: float) -> str:
    """
    函数级注释：
    将恐慌贪婪指数数值映射为前端展示的等级文本。
    输入允许为任意类型，内部安全解析为0-100的数值，并进行钳制。
    输出为以下之一：
    - '极度恐慌'（<=25）
    - '恐慌'（26-45）
    - '中性'（46-55）
    - '贪婪'（56-75）
    - '极度贪婪'（>75）
    解析失败返回'未知'。
    """
    v = safe_parse_float(value, default=None, clamp=(0.0, 100.0))
    if v is None:
        return '未知'
    if v <= 25:
        return '极度恐慌'
    elif v <= 45:
        return '恐慌'
    elif v <= 55:
        return '中性'
    elif v <= 75:
        return '贪婪'
    else:
        return '极度贪婪'

def compute_and_save_y_idx_aligned(acc: str = 'qqdev',
                                   start_time: str = '2021-01-01',
                                   backdays: int = 1200,
                                   alt_statdays: list[int] = [30],
                                   zdf_statdays: list[int] = [32],
                                   output_path: str | None = None) -> pd.DataFrame:
    '''
    使用与 y_idx.py 完全一致的口径计算 Y 指数，并保存到 data/Y_idx.csv。

    口径细节：
    - 山寨指数：调用 山寨指数().stat(statdays=[30])
    - 全市场涨跌幅指数：调用 全市场涨跌幅().stat(statdays=[32])
    - 合并方式：按 candle_begin_time 内连接，时间升序
    - 计算公式：Y_idx = (全市场涨跌幅指数 + 山寨指数) * 100
    - 输出路径：默认为 data/Y_idx.csv（Windows 下自动适配路径分隔符）

    参数:
    - acc: 交易账户代号，透传给 stat
    - start_time: 起始时间，透传给 stat
    - backdays: 回看天数，透传给 stat
    - alt_statdays: 山寨指数统计窗口（默认 [30]）
    - zdf_statdays: 全市场涨跌幅指数统计窗口（默认 [32]）
    - output_path: 输出 CSV 路径，默认 data/Y_idx.csv

    返回:
    - 包含 ['candle_begin_time','Y_idx'] 的 DataFrame
    '''
    try:
        logger.info('开始按y_idx.py口径计算Y指数')
        if output_path is None:
            output_path = os.path.join('data', 'Y_idx.csv')

        altcoin_index = 山寨指数()
        df1 = altcoin_index.stat(acc=acc, start_time=start_time, backdays=backdays, statdays=alt_statdays, save_img=False)

        marketzdf_index = 全市场涨跌幅()
        df2 = marketzdf_index.stat(acc=acc, start_time=start_time, backdays=backdays, statdays=zdf_statdays, save_img=False)

        # 转为DataFrame并进行时间序列清洗
        df1 = clean_time_series(pd.DataFrame(df1), time_column='candle_begin_time')
        df2 = clean_time_series(pd.DataFrame(df2), time_column='candle_begin_time')
        if df1 is None or df2 is None:
            raise ValueError('时间序列清洗失败或缺少时间列')
        if 'candle_begin_time' not in df1.columns or 'candle_begin_time' not in df2.columns:
            raise ValueError('缺少candle_begin_time列')

        # 内连接并按时间升序
        merged_df = pd.merge(df1, df2, on='candle_begin_time', how='inner')
        merged_df = clean_time_series(merged_df, time_column='candle_begin_time')
        if merged_df is None:
            raise ValueError('合并后时间序列清洗失败')

        # 检查必要列
        cols_needed = ['candle_begin_time', '全市场涨跌幅指数', '山寨指数']
        missing = [c for c in cols_needed[1:] if c not in merged_df.columns]
        if missing:
            raise KeyError(f'缺少必要列: {missing}')

        # 计算Y指数
        merged_df = merged_df[cols_needed].copy()
        merged_df['全市场涨跌幅指数'] = pd.to_numeric(merged_df['全市场涨跌幅指数'], errors='coerce')
        merged_df['山寨指数'] = pd.to_numeric(merged_df['山寨指数'], errors='coerce')
        merged_df = merged_df.dropna(subset=['全市场涨跌幅指数', '山寨指数'])
        merged_df['Y_idx'] = (merged_df['全市场涨跌幅指数'] + merged_df['山寨指数']) * 100

        # 保存输出
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        merged_df[['candle_begin_time', 'Y_idx']].to_csv(output_path, index=False)
        logger.info(f'已按口径生成Y指数并保存到: {output_path}，共{len(merged_df)}条记录')
        return merged_df[['candle_begin_time', 'Y_idx']]
    except Exception as e:
        logger.error(f'按口径计算Y指数失败: {e}')
        return pd.DataFrame(columns=['candle_begin_time', 'Y_idx'])


def compute_y_index_section(y_idx_csv_path: str | None = None) -> dict:
    """
    读取 data/Y_idx.csv 并计算 Y 指数的最新值与 1/7/30 天变化（按日期回看）。

    计算逻辑：
    - latest：最后一行的 Y_idx
    - change_1d：与上一条记录的差值（若不足 2 条记录则为 0.0）
    - change_7d：以最新时间点 T 为基准，回看 T-7 天以内“当时或更早最近一条”的值，计算差值
    - change_30d：同理，回看 T-30 天
    - 若历史不足以回看（没有满足条件的历史行），对应变化返回 0.0，确保字段不缺失
    - status：基于阈值映射生成风险标签（danger/warning/normal/bullish）

    参数:
    - y_idx_csv_path: Y 指数 CSV 路径，默认 data/Y_idx.csv

    返回:
    - dict: 包含 value、change_1d、change_7d、change_30d、status 字段
    """
    try:
        if y_idx_csv_path is None:
            y_idx_csv_path = os.path.join(DATA_DIR, 'Y_idx.csv')

        if not os.path.exists(y_idx_csv_path):
            return {'value': None, 'change_1d': 0.0, 'change_7d': 0.0, 'change_30d': 0.0, 'status': 'unknown'}

        df = pd.read_csv(y_idx_csv_path)
        if df is None or df.empty or 'Y_idx' not in df.columns:
            return {'value': None, 'change_1d': 0.0, 'change_7d': 0.0, 'change_30d': 0.0, 'status': 'unknown'}

        # 统一时间类型并排序
        if 'candle_begin_time' not in df.columns:
            return {'value': None, 'change_1d': 0.0, 'change_7d': 0.0, 'change_30d': 0.0, 'status': 'unknown'}

        df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'], errors='coerce')
        df = df.dropna(subset=['candle_begin_time'])
        df = df.sort_values('candle_begin_time').reset_index(drop=True)

        if df.empty:
            return {'value': None, 'change_1d': 0.0, 'change_7d': 0.0, 'change_30d': 0.0, 'status': 'unknown'}

        latest_val = float(df.iloc[-1]['Y_idx'])
        latest_ts = df.iloc[-1]['candle_begin_time']

        # 1 日变化：上一条记录
        prev1_val = float(df.iloc[-2]['Y_idx']) if len(df) >= 2 else latest_val
        change_1d = latest_val - prev1_val

        # 日期回看工具
        def get_prev_value_by_days(days: int):
            target_ts = latest_ts - pd.Timedelta(days=days)
            prev_df = df[df['candle_begin_time'] <= target_ts]
            if prev_df.empty:
                return None
            try:
                return float(prev_df.iloc[-1]['Y_idx'])
            except Exception:
                return None

        prev7_val = get_prev_value_by_days(7)
        prev30_val = get_prev_value_by_days(30)

        change_7d = (latest_val - prev7_val) if prev7_val is not None else 0.0
        change_30d = (latest_val - prev30_val) if prev30_val is not None else 0.0

        # 与 get_y_idx_status 一致的阈值映射
        def map_status(val: float) -> str:
            try:
                if val >= 80:
                    return 'danger'
                elif val >= 65:
                    return 'warning'
                elif val >= 45:
                    return 'normal'
                else:
                    return 'bullish'
            except Exception:
                return 'normal'

        return {
            'value': round(latest_val, 2),
            'change_1d': round(change_1d, 2),
            'change_7d': round(change_7d, 2),
            'change_30d': round(change_30d, 2),
            'status': map_status(latest_val)
        }
    except Exception as e:
        logger.warning(f'计算Y指数1/7/30天变化失败: {e}')
        return {'value': None, 'change_1d': 0.0, 'change_7d': 0.0, 'change_30d': 0.0, 'status': 'unknown'}

def update_market_data():
    """
    更新市场数据 - 优化版本，包含所有新指标
    
    Returns:
        bool: 更新是否成功
    """
    start_time = time.time()
    log_function_call('update_market_data')
    
    try:
        logger.info(f"开始更新数据: {datetime.now()}")
        
        # 设置账户名称
        acc = 'qqdev'
        
        # 创建交易所实例 - 使用增强配置
        try:
            exchange = ccxt.binance(cfg.binance.get_exchange_config())
            logger.info("使用代理配置创建交易所实例")
        except Exception as e:
            logger.warning(f"代理配置失败: {str(e)}，尝试备用配置")
            try:
                exchange = ccxt.binance(cfg.binance.get_backup_config())
                logger.info("使用备用配置创建交易所实例")
            except Exception as e2:
                logger.warning(f"备用配置也失败: {str(e2)}，使用默认配置")
                exchange = ccxt.binance({
                    'enableRateLimit': True,
                    'timeout': 60000,
                    'options': {'defaultType': 'future'}
                })
        
        # 获取交易对列表 - 使用健壮的方法
        symbol_list = binance.get_usdt_swap_symbols_robust(exchange)
        
        if not symbol_list:
            logger.error("无法获取交易对列表，使用备用列表")
            symbol_list = binance.get_usdt_swap_symbols_fallback()
        
        # 计算时间参数
        backdays = 365
        start_time_data = datetime.now() - timedelta(days=backdays)
        run_time = common.cacu_run_time('1h', datetime.now())
        logger.info(f"获取数据中，共{len(symbol_list)}个交易对...")
        
        df_dict = binance.u_furture_fetch_all_swap_candle_data(
            exchange, symbol_list, '1d', run_time, backdays * 2 + 10, True, False, njobs=60
        )
        
        logger.info("数据获取完成，开始计算各指标...")
        
        # 更新Y指数基础数据
        altcoin_obj = 山寨指数()
        df1 = altcoin_obj.stat_with_data(df_dict, acc, start_time_data, backdays, statdays=[30], save_img=True)
        
        marketzdf_obj = 全市场涨跌幅()
        df2 = marketzdf_obj.stat_with_data(df_dict, acc, start_time_data, backdays, statdays=[32], save_img=True)

        # 合并数据并计算Y指数
        df1['candle_begin_time'] = pd.to_datetime(df1['candle_begin_time'])
        df2['candle_begin_time'] = pd.to_datetime(df2['candle_begin_time'])
        
        merged_df = pd.merge(df1, df2, on='candle_begin_time', how='inner')
        merged_df = merged_df.sort_values('candle_begin_time')
        merged_df = merged_df[['candle_begin_time', '全市场涨跌幅指数', '山寨指数']]
        merged_df['Y_idx'] = (merged_df['全市场涨跌幅指数'] + merged_df['山寨指数']) * 100
        
        # 保存Y指数数据到data目录
        try:
            os.makedirs('data', exist_ok=True)
            merged_df[['candle_begin_time', 'Y_idx']].to_csv(os.path.join('data', 'Y_idx.csv'), index=False)
        except Exception as e:
            logger.error(f"保存Y指数数据失败: {e}")
        
        # 更新其他原有指标数据
        volatility_obj = 截面波动率()
        volatility_obj.stat_with_data(df_dict, acc, start_time_data, backdays, 
                                    volatility_windows=[7, 30, 90], save_img=True)
        
        liquidity_obj = 市场流动性()
        liquidity_obj.stat_with_data(df_dict, acc, start_time_data, backdays,
                                   windows=[30, 90], save_img=True)
        
        market_breadth_obj = 市场宽度创新高()
        market_breadth_obj.stat_with_data(df_dict, acc, start_time_data, backdays,
                                        windows=[7, 30, 90, 365], save_img=True)
        
        cross_section_diff_obj = 横截面差异指数()
        cross_section_diff_obj.stat_with_data(df_dict, acc, start_time_data, backdays, save_img=True)
        
        # 更新市场指标数据（山寨币指数、恐慌贪婪指数、BTC彩虹价格表等）
        logger.info("开始更新市场指标数据...")
        try:
            market_indicators_obj = 市场指标()
            market_indicators_obj.get_all_indicators()
            logger.info("市场指标数据更新完成")
        except Exception as e:
            logger.error(f"市场指标数据更新失败: {e}")
        
        # 更新所有新创建的指标
        logger.info("开始更新新创建的指标数据...")
        
        # 1. AD百分比
        try:
            ad_percentage_obj = AD百分比()
            ad_percentage_obj.stat_with_data(df_dict, acc, start_time_data, backdays, save_img=True)
            logger.info("AD百分比指标更新完成")
        except Exception as e:
            logger.error(f"AD百分比指标更新失败: {e}")
        
        # 2. AHR999
        try:
            ahr999_obj = AHR999()
            ahr999_obj.stat_with_data(df_dict, acc, start_time_data, backdays, save_img=True)
            logger.info("AHR999指标更新完成")
        except Exception as e:
            logger.error(f"AHR999指标更新失败: {e}")
        
        # 3. 爆拉暴跌币种占比
        try:
            extreme_move_obj = 爆拉暴跌币种占比()
            extreme_move_obj.stat_with_data(df_dict, acc, start_time_data, backdays, save_img=True)
            logger.info("爆拉暴跌币种占比指标更新完成")
        except Exception as e:
            logger.error(f"爆拉暴跌币种占比指标更新失败: {e}")
        
        # 4. MVRVY指数（已废弃，删除）
        # try:
        #     mvrvy_obj = MVRVY指数()
        #     mvrvy_obj.stat_with_data(df_dict, acc, start_time_data, backdays, save_img=True)
        #     logger.info("MVRVY指数更新完成")
        # except Exception as e:
        #     logger.error(f"MVRVY指数更新失败: {e}")
        
        # 5. 涨跌比重
        try:
            up_down_ratio_obj = 涨跌比重()
            up_down_ratio_obj.stat_with_data(df_dict, acc, start_time_data, backdays, save_img=True)
            logger.info("涨跌比重指标更新完成")
        except Exception as e:
            logger.error(f"涨跌比重指标更新失败: {e}")
        
        # 6. 横截面差异指数（新版本）
        try:
            cross_section_diff_new_obj = 横截面差异指数()
            cross_section_diff_new_obj.stat_with_data(df_dict, acc, start_time_data, backdays, save_img=True)
            logger.info("横截面差异指数（新版本）更新完成")
        except Exception as e:
            logger.error(f"横截面差异指数（新版本）更新失败: {e}")
        
        # 7. 盘口价差监控
        try:
            bid_ask_spread_obj = 盘口价差监控()
            bid_ask_spread_obj.stat_with_data(df_dict, acc, start_time_data, backdays, save_img=True)
            logger.info("盘口价差监控指标更新完成")
        except Exception as e:
            logger.error(f"盘口价差监控指标更新失败: {e}")
        
        # 8. 新MVRV指标
        try:
            new_mvrv_obj = 市场MVRV指标()
            new_mvrv_obj.stat_with_data(df_dict, acc, start_time_data, backdays, save_img=True)
            logger.info("MVRV指标更新完成")
        except Exception as e:
            logger.error(f"MVRV指标更新失败: {e}")
        
        # 9. 链上稳定币总供应量（恢复生成，保证看板不为N/A）
        try:
            stablecoin_supply_monitor_obj = 链上稳定币总供应量()
            stablecoin_supply_monitor_obj.stat_with_data(
                stablecoin_data=None,
                df_dict=df_dict,
                acc=acc,
                start_time=start_time_data,
                backdays=backdays,
                windows=[1, 7, 30],
                save_img=True,
                interval='1d'
            )
            logger.info("链上稳定币总供应量指标更新完成")
        except Exception as e:
            logger.error(f"链上稳定币总供应量指标更新失败: {e}")
        
        # 10. 新交易所净流入流出
        try:
            new_exchange_flow_obj = ExchangeFlowMonitor()
            df_new = new_exchange_flow_obj.process_data(df_dict, windows=[1, 7, 30], backdays=backdays, interval='1d', start_time=start_time_data)
            if df_new is not None and not df_new.empty:
                new_exchange_flow_obj.save_csv(df_new)
                new_exchange_flow_obj.draw_index(df_new, start_time=start_time_data, interval='1d')
            logger.info("交易所净流入流出指标更新完成")
        except Exception as e:
            logger.error(f"交易所净流入流出指标更新失败: {e}")
        
        # 11. 全市场资金费率监控
        try:
            funding_rate_obj = 全市场资金费率监控()
            # 修复：改为关键字参数，避免参数错位
            funding_rate_obj.stat_with_data(
                funding_data=None,
                acc=acc,
                start_time=start_time_data,
                backdays=backdays,
                windows=[1, 7, 30],
                save_img=True,
                interval='8h'
            )
            logger.info("全市场资金费率监控指标更新完成")
        except Exception as e:
            logger.error(f"全市场资金费率监控指标更新失败: {e}")
        
        # 12. Y指数综合指标
        try:
            y_composite_obj = Y指数综合指标()
            # 修复：使用关键字参数，避免参数错位导致类型错误
            y_composite_obj.stat_with_data(
                df_dict=df_dict,
                funding_data=None,            # 传 None 让其内部自行获取或由外部提前提供
                stablecoin_data=None,         # 传 None 让其内部自行获取或由外部提前提供
                acc=acc,
                start_time=start_time_data,
                backdays=backdays,
                windows=[1, 7, 30],
                save_img=True,
                interval="1d"
            )
            logger.info("Y指数综合指标更新完成")
        except Exception as e:
            logger.error(f"Y指数综合指标更新失败: {e}")
            # 添加兜底机制：如果综合指标计算失败，至少确保有基础数据
            try:
                logger.info("尝试生成基础Y综合指数数据作为兜底")
                read_y_composite_data()  # 这会触发我们新增的生成逻辑
            except Exception as fallback_error:
                logger.error(f"生成兜底Y综合指数数据也失败: {fallback_error}")
        
        # 3.x 高级指标：计算市值加权指数并保存为 data/advanced_indicators.csv
        try:
            # 直接使用已实现的高级指标类，计算市值加权指数
            adv = 高级市场指标()
            mcw_df = adv._calculate_market_cap_weighted_index(df_dict)
            if isinstance(mcw_df, pd.DataFrame) and not mcw_df.empty:
                # 统一列名，确保前端/概览读取一致
                if 'market_cap_weighted_index' in mcw_df.columns and 'market_cap_weighted' not in mcw_df.columns:
                    mcw_df = mcw_df.rename(columns={'market_cap_weighted_index': 'market_cap_weighted'})
                if 'candle_begin_time' in mcw_df.columns:
                    mcw_df['candle_begin_time'] = pd.to_datetime(mcw_df['candle_begin_time'], errors='coerce')
                    mcw_df = mcw_df.dropna(subset=['candle_begin_time']).sort_values('candle_begin_time')
                try:
                    os.makedirs(DATA_DIR, exist_ok=True)
                    mcw_df.to_csv(os.path.join(DATA_DIR, 'advanced_indicators.csv'), index=False)
                except Exception as dir_e:
                    logger.error(f"保存高级指标数据失败: {dir_e}")
                logger.info("高级指标-市值加权指数 已生成: data/advanced_indicators.csv")
            else:
                logger.warning("高级指标-市值加权指数 计算结果为空，未生成 advanced_indicators.csv")
        except Exception as e:
            logger.warning(f"高级指标计算或保存失败: {e}")
        
        logger.info("所有指标更新完成")
        log_performance('update_market_data', start_time, time.time())
        
        return True
        
    except Exception as e:
        logger.error(f"更新市场数据失败: {e}")
        # 推送模块移除：仅记录日志
        # 原错误通知已移除
        return False



@app.route('/', methods=['GET', 'POST'])
def index():
    """
    主页路由 - 快速显示页面，数据通过AJAX异步加载
    支持GET和POST方法以避免405错误
    
    Returns:
        str: 渲染的HTML页面
    """
    start_time = time.time()
    log_function_call('index')
    
    try:
        # 如果是POST请求，记录并返回JSON响应
        if request.method == 'POST':
            logger.info(f"收到POST请求到根路径，来源IP: {request.remote_addr}")
            return jsonify({
                'status': 'success',
                'message': '请使用GET方法访问主页',
                'redirect': '/'
            })
        
        # 只做基本的页面渲染，不加载任何数据
        logger.info("主页快速渲染，数据将通过API异步加载")
        
        log_performance('index', start_time, time.time())
        
        # 直接渲染模板，不传递数据
        return render_template('index2p1.html', 
                             update_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    
    except Exception as e:
        logger.error(f"主页加载失败: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': '页面加载失败'}), 500

@app.route('/api/update')
def api_update():
    """
    API路由 - 手动触发数据更新
    
    Returns:
        dict: 更新结果
    """
    try:
        logger.info("收到手动更新请求")
        success = update_market_data()
        
        if success:
            logger.info("手动更新完成")
            return jsonify({'status': 'success', 'message': '数据更新完成'})
        else:
            logger.error("手动更新失败")
            return jsonify({'status': 'error', 'message': '数据更新失败'}), 500
            
    except Exception as e:
        logger.error(f"手动更新异常: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/status')
def api_status():
    """
    API路由 - 获取系统状态
    
    Returns:
        dict: 系统状态信息
    """
    try:
        # 检查数据文件状态
        data_files = ['Y_idx.csv', 'volatility_index.csv', 'liquidity_index.csv', 'market_breadth_index.csv']
        file_status = {}
        
        for file in data_files:
            file_path = os.path.join(DATA_DIR, file)
            if os.path.exists(file_path):
                stat = os.stat(file_path)
                file_status[file] = {
                    'exists': True,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                }
            else:
                file_status[file] = {'exists': False}
        
        # 获取推送状态
        notification_status = {
            'enabled': False,
            'platforms': []
        }
        
        # 推送模块移除：不再返回平台信息
        
        return jsonify({
            'status': 'running',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'data_files': file_status,
            'notifications': notification_status
        })
        
    except Exception as e:
        logger.error(f"获取系统状态失败: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/chart-data')
def api_chart_data():
    """
    API路由 - 获取图表数据
    
    Returns:
        dict: 图表数据
    """
    try:
        chart_type = request.args.get('chart_type', 'y_idx')
        log_function_call('api_chart_data', {'chart_type': chart_type})
        
        start_time = time.time()
        
        # 根据图表类型返回相应数据
        if chart_type == 'y_idx' or chart_type == 'y_index':
            try:
                df = get_filtered_data(os.path.join(DATA_DIR, 'Y_idx.csv'))
                if df is None or df.empty:
                    logger.warning("Y指数数据为空")
                    data = {'error': 'Y指数数据不可用'}
                else:
                    # 确保日期列已正确转换
                    if 'candle_begin_time' in df.columns:
                        df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'])
                    
                    data = {
                        'dates': safe_to_list(df['candle_begin_time'].dt.strftime('%Y-%m-%d')),
                        'values': safe_to_list(df['Y_idx']),
                        'latest_value': float(df['Y_idx'].iloc[-1]),
                        'change_percentage': calculate_change_percentage(df, 'Y_idx'),
                        'status': get_y_idx_status(df)
                    }
                    logger.info(f"Y指数数据加载成功，共{len(df)}条记录，最新值: {data['latest_value']}")
            except Exception as e:
                logger.error(f"读取Y指数数据失败: {e}")
                logger.error(traceback.format_exc())
                data = {'error': 'Y指数数据不可用'}
                
        elif chart_type == 'volatility':
            try:
                df = get_filtered_data(os.path.join(DATA_DIR, 'volatility_index.csv'))
                if df is None or df.empty:
                    logger.warning("波动率数据为空")
                    data = {'error': '波动率数据不可用'}
                else:
                    # 确保日期列已正确转换
                    if 'candle_begin_time' in df.columns:
                        df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'])
                    
                    data = {
                        'dates': safe_to_list(df['candle_begin_time'].dt.strftime('%Y-%m-%d')),
                        'volatility_7d': safe_to_list(df.get('市场波动率指数_7d', [])),
                        'volatility_30d': safe_to_list(df.get('市场波动率指数_30d', [])),
                        'volatility_90d': safe_to_list(df.get('市场波动率指数_90d', []))
                    }
                    logger.info(f"波动率数据加载成功，共{len(df)}条记录")
            except Exception as e:
                logger.error(f"读取波动率数据失败: {e}")
                logger.error(traceback.format_exc())
                data = {'error': '波动率数据不可用'}
                
        elif chart_type == 'liquidity':
            try:
                df = get_filtered_data(os.path.join(DATA_DIR, 'liquidity_index.csv'))
                if df is None or df.empty:
                    logger.warning("流动性数据为空")
                    data = {'error': '流动性数据不可用'}
                else:
                    data = {
                        'dates': safe_to_list(df['candle_begin_time'].dt.strftime('%Y-%m-%d')),
                        'liquidity_30d': safe_to_list(df.get('综合流动性指数_30d', [])),
                        'liquidity_90d': safe_to_list(df.get('综合流动性指数_90d', []))
                    }
            except Exception as e:
                logger.error(f"读取流动性数据失败: {e}")
                data = {'error': '流动性数据不可用'}
                
        elif chart_type == 'market_breadth':
            try:
                df = get_filtered_data(os.path.join(DATA_DIR, 'market_breadth_index.csv'))
                if df is None or df.empty:
                    logger.warning("市场宽度数据为空")
                    data = {'error': '市场宽度数据不可用'}
                else:
                    data = {
                        'dates': safe_to_list(df['candle_begin_time'].dt.strftime('%Y-%m-%d')),
                        'values': safe_to_list(df.get('市场宽度指数', []))
                    }
            except Exception as e:
                logger.error(f"读取市场宽度数据失败: {e}")
                data = {'error': '市场宽度数据不可用'}
        
        # 修复所有图表类型的数据读取
        elif chart_type == 'ad_percentage':
            try:
                # 优先读取独立的 AD 百分比文件
                df = get_filtered_data(os.path.join(DATA_DIR, 'ad_percentage.csv'))
                col_candidates = ['AD百分比_30d', 'AD百分比']  # 兼容不同产出
                
                # 如果 ad_percentage.csv 不存在或不包含目标列，则回退到 market_breadth_index.csv
                if df is None or df.empty or not any(c in df.columns for c in col_candidates):
                    df = get_filtered_data(os.path.join(DATA_DIR, 'market_breadth_index.csv'))
                
                if df is None or df.empty:
                    logger.warning("AD百分比数据为空")
                    data = {'error': 'AD百分比数据不可用'}
                else:
                    # 选择可用列名
                    value_col = next((c for c in col_candidates if c in df.columns), None)
                    if value_col is None:
                        logger.warning(f"AD百分比相关列缺失, 可用列: {list(df.columns)}")
                        data = {'error': 'AD百分比数据不可用'}
                    else:
                        values = safe_to_list(df[value_col])
                        data = {
                            'dates': safe_to_list(df['candle_begin_time'].dt.strftime('%Y-%m-%d')),
                            'values': values
                        }
            except Exception as e:
                logger.error(f"读取AD百分比数据失败: {e}")
                data = {'error': 'AD百分比数据不可用'}
        
        elif chart_type == 'ahr999':
            try:
                df = get_filtered_data(os.path.join(DATA_DIR, 'ahr999.csv'))
                if df is None or df.empty:
                    logger.warning("AHR999数据为空")
                    data = {'error': 'AHR999数据不可用'}
                else:
                    # 修复：优先查找 ahr999_200 列，兼容不同窗口期
                    col_candidates = ['ahr999_200', 'ahr999_100', 'ahr999']
                    value_col = next((c for c in col_candidates if c in df.columns), None)
                    
                    if value_col is None:
                        logger.warning(f"AHR999相关列缺失, 可用列: {list(df.columns)}")
                        data = {'error': 'AHR999数据不可用'}
                    else:
                        # 安全获取列数据，处理可能的列表格式
                        ahr_values = safe_to_list(df[value_col])
                        data = {
                            'dates': safe_to_list(df['candle_begin_time'].dt.strftime('%Y-%m-%d')),
                            'values': ahr_values
                        }
            except Exception as e:
                logger.error(f"读取AHR999数据失败: {e}")
                data = {'error': 'AHR999数据不可用'}
        
        elif chart_type == 'extreme_ratio':
            try:
                df = get_filtered_data(os.path.join(DATA_DIR, 'extreme_move_ratio.csv'))
                if df is None or df.empty:
                    logger.warning("极端移动比率数据为空")
                    data = {'error': '极端移动比率数据不可用'}
                else:
                    up_ratio = safe_to_list(df.get('爆拉币种占比_1d', []))
                    down_ratio = safe_to_list(df.get('暴跌币种占比_1d', []))
                    total_ratio = safe_to_list(df.get('极端波动占比_1d', []))
                    data = {
                        'dates': safe_to_list(df['candle_begin_time'].dt.strftime('%Y-%m-%d')),
                        'up_ratio': up_ratio,
                        'down_ratio': down_ratio,
                        'total_ratio': total_ratio
                    }
            except Exception as e:
                logger.error(f"读取极端移动比率数据失败: {e}")
                data = {'error': '极端移动比率数据不可用'}
        
        # 新增：兼容前端传入 extreme_move 的别名分支（与 extreme_ratio 逻辑相同）
        elif chart_type == 'extreme_move':
            try:
                df = get_filtered_data(os.path.join(DATA_DIR, 'extreme_move_ratio.csv'))
                if df is None or df.empty:
                    logger.warning("极端移动比率数据为空")
                    data = {'error': '极端移动比率数据不可用'}
                else:
                    up_ratio = safe_to_list(df.get('爆拉币种占比_1d', []))
                    down_ratio = safe_to_list(df.get('暴跌币种占比_1d', []))
                    total_ratio = safe_to_list(df.get('极端波动占比_1d', []))
                    data = {
                        'dates': safe_to_list(df['candle_begin_time'].dt.strftime('%Y-%m-%d')),
                        'up_ratio': up_ratio,
                        'down_ratio': down_ratio,
                        'total_ratio': total_ratio
                    }
            except Exception as e:
                logger.error(f"读取极端移动比率数据失败: {e}")
                data = {'error': '极端移动比率数据不可用'}
        
        
        elif chart_type == 'up_down_ratio':
            try:
                df = get_filtered_data(os.path.join(DATA_DIR, 'up_down_ratio.csv'))
                if df is None or df.empty:
                    logger.warning("涨跌比重数据为空")
                    data = {'error': '涨跌比重数据不可用'}
                else:
                    logger.info(f"up_down_ratio 数据加载成功，共{len(df)}行，列名: {list(df.columns)}")
                    
                    # 自适应列名映射：优先 1d -> 7d -> 30d -> 英文兜底
                    up_col = next((c for c in ['上涨比重_1d', '上涨比重_7d', '上涨比重_30d', 'up_ratio'] if c in df.columns), None)
                    down_col = next((c for c in ['下跌比重_1d', '下跌比重_7d', '下跌比重_30d', 'down_ratio'] if c in df.columns), None)
                    ratio_col = next((c for c in ['涨跌比率_1d', '涨跌比率_7d', '涨跌比率_30d', 'ratio'] if c in df.columns), None)

                    logger.info(f"up_down_ratio 列映射 => up: {up_col}, down: {down_col}, ratio: {ratio_col}")
                    
                    # 检查所有列是否找到
                    if not up_col or not down_col or not ratio_col:
                        logger.error(f"缺少必要列: up_col={up_col}, down_col={down_col}, ratio_col={ratio_col}")
                        data = {'error': '涨跌比重数据列名不匹配'}
                    else:
                        # 将列转换为数值类型，异常设为 NaN
                        for col in [up_col, down_col, ratio_col]:
                            if col and col in df.columns:
                                df[col] = pd.to_numeric(df[col], errors='coerce')
                        
                        # 确保日期列格式正确
                        if 'candle_begin_time' in df.columns and not df['candle_begin_time'].dtype.name.startswith('datetime'):
                            df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'])

                        def safe_numeric_to_list(series):
                            """安全地将包含 NaN 的数值 Series 转换为列表，NaN 转为 None"""
                            if series is None or series.empty:
                                return []
                            # 将 NaN 转为 None，避免前端解析异常
                            return [None if pd.isna(v) else float(v) for v in safe_to_list(series)]

                        up_ratio = safe_numeric_to_list(df[up_col]) if up_col else []
                        down_ratio = safe_numeric_to_list(df[down_col]) if down_col else []
                        ratio = safe_numeric_to_list(df[ratio_col]) if ratio_col else []
                        dates = safe_to_list(df['candle_begin_time'].dt.strftime('%Y-%m-%d'))
                        
                        data = {
                            'dates': dates,
                            'up_ratio': up_ratio,
                            'down_ratio': down_ratio,
                            'ratio': ratio
                        }
                        
                        # 添加调试信息
                        logger.info(f"up_down_ratio 返回数据：{len(data['dates'])}个日期，up_ratio前3个值: {data['up_ratio'][:3]}")
                        
            except Exception as e:
                logger.error(f"读取涨跌比重数据失败: {e}")
                data = {'error': '涨跌比重数据不可用'}
        
        elif chart_type == 'cross_section':
            try:
                df = get_filtered_data(os.path.join(DATA_DIR, 'cross_section_diff_index.csv'))
                if df is None or df.empty:
                    logger.warning("横截面差异指数数据为空")
                    data = {'error': '横截面差异指数数据不可用'}
                else:
                    # 映射CSV中文列 -> 前端期望 'values'
                    values_col = next((c for c in [
                        '横截面差异指数_7d', '横截面差异指数_30d', '横截面差异指数_90d',
                        '横截面差异指数', 'cross_section_diff_index'
                    ] if c in df.columns), None)
                    
                    # 确保日期列格式正确
                    if 'candle_begin_time' in df.columns and not df['candle_begin_time'].dtype.name.startswith('datetime'):
                        df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'])
                    
                    data = {
                        'dates': safe_to_list(df['candle_begin_time'].dt.strftime('%Y-%m-%d')),
                        'values': safe_to_list(df.get(values_col, [])) if values_col else []
                    }
            except Exception as e:
                logger.error(f"读取横截面差异指数数据失败: {e}")
                data = {'error': '横截面差异指数数据不可用'}
        
        # 新增：BBW（布林带宽度）图表数据
        elif chart_type == 'bbw':
            """
            返回比特币（BTC）BBW 多时间尺度序列：
            - bbw_daily：当日 BBW（基于 BTC 日线 close 计算，默认布林带窗口 20）
            - bbw_3d：BBW 的 3 日滚动均值
            - bbw_7d：BBW 的 7 日滚动均值
            - bbw_30d：BBW 的 30 日滚动均值
            数据源：data/ahr999.csv 中的 close（BTC 价格）
            """
            try:
                df = get_filtered_data(os.path.join(DATA_DIR, 'ahr999.csv'))
                if df is None or df.empty or 'close' not in df.columns:
                    logger.warning("BBW数据源为空或缺少close列")
                    data = {'error': 'BBW数据不可用'}
                else:
                    bbw_df = compute_bbw_series(df, price_col='close', window=20, k=2.0)
                    if bbw_df is None or bbw_df.empty:
                        data = {'dates': [], 'bbw_daily': [], 'bbw_3d': [], 'bbw_7d': [], 'bbw_30d': []}
                    else:
                        # 确保日期列存在且为 datetime
                        if 'candle_begin_time' in bbw_df.columns and not str(bbw_df['candle_begin_time'].dtype).startswith('datetime'):
                            bbw_df['candle_begin_time'] = pd.to_datetime(bbw_df['candle_begin_time'])
                        bbw_df = bbw_df.dropna(subset=['candle_begin_time']).sort_values('candle_begin_time').reset_index(drop=True)

                        # 生成多时间尺度序列（对 BBW 做滚动均值平滑）
                        bbw_df['bbw_3d'] = bbw_df['BBW'].rolling(window=3, min_periods=1).mean()
                        bbw_df['bbw_7d'] = bbw_df['BBW'].rolling(window=7, min_periods=1).mean()
                        bbw_df['bbw_30d'] = bbw_df['BBW'].rolling(window=30, min_periods=1).mean()

                        dates = safe_to_list(bbw_df['candle_begin_time'].dt.strftime('%Y-%m-%d'))
                        bbw_daily = safe_to_list(bbw_df['BBW'])
                        bbw_3d = safe_to_list(bbw_df['bbw_3d'])
                        bbw_7d = safe_to_list(bbw_df['bbw_7d'])
                        bbw_30d = safe_to_list(bbw_df['bbw_30d'])

                        latest_val = float(bbw_daily[-1]) if bbw_daily else None
                        # 变化率沿用当日 BBW，为复用通用函数做一列名映射
                        tmp_df = bbw_df.rename(columns={'BBW': 'value'})
                        change_pct = calculate_change_percentage(tmp_df, 'value') if len(bbw_daily) > 1 else 0.0

                        data = {
                            'dates': dates,
                            'bbw_daily': bbw_daily,
                            'bbw_3d': bbw_3d,
                            'bbw_7d': bbw_7d,
                            'bbw_30d': bbw_30d,
                            'latest_value': latest_val,
                            'change_percentage': change_pct
                        }
                        logger.info(f"BBW数据加载成功，共{len(bbw_daily)}条，最新值: {latest_val}")
            except Exception as e:
                logger.error(f"读取BBW数据失败: {e}", exc_info=True)
                data = {'error': 'BBW数据不可用'}
        
        elif chart_type == 'spread_monitor':
            try:
                df = get_filtered_data(os.path.join(DATA_DIR, 'bid_ask_spread_monitor.csv'))
                if df is None or df.empty:
                    logger.warning("盘口价差监控数据为空")
                    data = {'error': '盘口价差监控数据不可用'}
                else:
                    # 列名自适应：兼容不同产出版本
                    avg_candidates = ['市场平均价差_1d', '平均价差(bp)', '平均价差_1d', 'avg_spread_1d', '平均价差']
                    vol_candidates = ['市场价差标准差_1d', '价差波动率(bp)', '价差波动率_1d', 'spread_std_1d', '价差标准差_1d']

                    avg_spread_col = next((c for c in avg_candidates if c in df.columns), None)
                    vol_col = next((c for c in vol_candidates if c in df.columns), None)

                    # 确保日期列格式正确
                    if 'candle_begin_time' in df.columns and not df['candle_begin_time'].dtype.name.startswith('datetime'):
                        df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'], errors='coerce')
                    
                    # 删除无效日期和排序
                    df = df.dropna(subset=['candle_begin_time']).sort_values('candle_begin_time')
                    
                    # 确保有足够的数据行
                    if len(df) == 0:
                        logger.warning("过滤后盘口价差监控数据为空")
                        data = {
                            'dates': [],
                            'average_spread': [],
                            'spread_volatility': []
                        }
                    else:
                        dates = safe_to_list(df['candle_begin_time'].dt.strftime('%Y-%m-%d'))
                        # 修复：确保变量存在时才使用，避免 NameError，并添加数值检查
                        # 列名自适应：兼容不同产出版本
                        avg_candidates = ['市场平均价差_1d', '平均价差(bp)', '平均价差_1d', 'avg_spread_1d', '平均价差']
                        vol_candidates = ['市场价差标准差_1d', '价差波动率(bp)', '价差波动率_1d', 'spread_std_1d', '价差标准差_1d']

                        avg_spread_col = next((c for c in avg_candidates if c in df.columns), None)
                        vol_col = next((c for c in vol_candidates if c in df.columns), None)
                        
                        if avg_spread_col and avg_spread_col in df.columns:
                            average_spread = safe_to_list(df[avg_spread_col].fillna(0))
                        else:
                            average_spread = []
                        
                        if vol_col and vol_col in df.columns:
                            spread_volatility = safe_to_list(df[vol_col].fillna(0))
                        else:
                            spread_volatility = []

                        if not avg_spread_col or not vol_col:
                            logger.warning(f"盘口价差监控列缺失，现有列: {safe_to_list(df.columns)}，解析到 avg={avg_spread_col}, vol={vol_col}")

                        data = {
                            'dates': dates,
                            'average_spread': average_spread,
                            'spread_volatility': spread_volatility
                        }

                        logger.info(f"盘口价差监控数据加载成功，共{len(df)}条记录，使用列: avg={avg_spread_col}, vol={vol_col}，日期范围: {dates[0] if dates else 'N/A'} - {dates[-1] if dates else 'N/A'}")
                        
            except Exception as e:
                logger.error(f"读取盘口价差监控数据失败: {e}", exc_info=True)
                data = {'error': '盘口价差监控数据不可用'}
        
        elif chart_type == 'new_mvrv':
            try:
                df = get_filtered_data(os.path.join(DATA_DIR, 'mvrv_indicator.csv'))
                if df is None or df.empty:
                    logger.warning("新MVRV指标数据为空")
                    data = {'error': '新MVRV指标数据不可用'}
                else:
                    data = {
                        'dates': safe_to_list(df['candle_begin_time'].dt.strftime('%Y-%m-%d')),
                        'values': safe_to_list(df.get('市场MVRV_MA_30d', [])),
                        'mvrv_30d': safe_to_list(df.get('市场MVRV_MA_30d', [])),
                        'mvrv_90d': safe_to_list(df.get('市场MVRV_MA_90d', [])),
                        'mvrv_180d': safe_to_list(df.get('市场MVRV_MA_180d', [])),
                        'mvrv_365d': safe_to_list(df.get('市场MVRV_MA_365d', []))
                    }
            except Exception as e:
                logger.error(f"读取新MVRV指标数据失败: {e}")
                data = {'error': '新MVRV指标数据不可用'}
        
        elif chart_type == 'onchain_stablecoin':
            try:
                df = get_filtered_data(os.path.join(DATA_DIR, 'stablecoin_supply.csv'))
                if df is None or df.empty:
                    logger.warning("稳定币供应量数据为空")
                    data = {'error': '链上稳定币数据不可用'}
                else:
                    # 映射CSV列到前端所需字段
                    usdt_col = next((c for c in ['USDT_supply_billion', 'USDT_supply'] if c in df.columns), None)
                    usdc_col = next((c for c in ['USDC_supply_billion', 'USDC_supply'] if c in df.columns), None)
                    dai_col  = next((c for c in ['DAI_supply_billion',  'DAI_supply']  if c in df.columns), None)
                    total_col = next((c for c in ['total_supply_billion', 'total_supply', 'total_stablecoin_supply'] if c in df.columns), None)

                    data = {
                        'dates': safe_to_list(df['candle_begin_time'].dt.strftime('%Y-%m-%d')),
                        'usdt_supply': safe_to_list(df.get(usdt_col, [])) if usdt_col else [],
                        'usdc_supply': safe_to_list(df.get(usdc_col, [])) if usdc_col else [],
                        'dai_supply':  safe_to_list(df.get(dai_col,  [])) if dai_col  else [],
                        'total_supply': safe_to_list(df.get(total_col, [])) if total_col else []
                    }
            except Exception as e:
                logger.error(f"读取稳定币供应量数据失败: {e}")
                data = {'error': '链上稳定币数据不可用'}
        
        elif chart_type == 'new_exchange_flow':
            try:
                df = get_filtered_data(os.path.join(DATA_DIR, 'exchange_flow.csv'))
                if df is None or df.empty:
                    logger.warning("交易所流入流出数据为空")
                    data = {'error': '新交易所流入流出数据不可用'}
                else:
                    data = {
                        'dates': safe_to_list(df['candle_begin_time'].dt.strftime('%Y-%m-%d')),
                        'net_flow_1d': safe_to_list(df.get('市场净流入_1d', [])),
                        'net_flow_7d': safe_to_list(df.get('市场净流入_7d', [])),
                        'net_flow_30d': safe_to_list(df.get('市场净流入_30d', [])),
                        'total_inflow_1d': safe_to_list(df.get('市场总流入_1d', [])),
                        'total_outflow_1d': safe_to_list(df.get('市场总流出_1d', [])),
                        'sentiment_1d': safe_to_list(df.get('市场情绪指标_1d', [])),
                        'liquidity_status_1d': safe_to_list(df.get('流动性状态_1d', []))
                    }
            except Exception as e:
                logger.error(f"读取交易所流入流出数据失败: {e}")
                data = {'error': '新交易所流入流出数据不可用'}
        
        elif chart_type == 'funding_rate':
            try:
                df = get_filtered_data(os.path.join(DATA_DIR, 'funding_rate_monitor.csv'))
                if df is None or df.empty:
                    logger.warning("资金费率数据为空")
                    data = {'error': '资金费率数据不可用'}
                else:
                    # 修复：使用中文列名映射，匹配 funding_rate_monitor.csv 的实际列名
                    data = {
                        'dates': safe_to_list(df['candle_begin_time'].dt.strftime('%Y-%m-%d')),
                        'average_funding_rate': safe_to_list(df.get('平均资金费率', [])),
                        'funding_rate_volatility': safe_to_list(df.get('资金费率标准差', [])),
                        'long_short_ratio': safe_to_list(df.get('多空力量对比', [])),
                        'volatility_status': safe_to_list(df.get('费率波动状态', []))
                    }
                    logger.info(f"资金费率数据加载成功，共{len(df)}条记录")
            except Exception as e:
                logger.error(f"读取资金费率数据失败: {e}")
                data = {'error': '资金费率数据不可用'}
        
        elif chart_type == 'y_composite':
            try:
                # 读取Y综合指数专用文件
                df = read_y_composite_data()
                if df is not None and not df.empty:
                    # 确保日期列已正确转换
                    if 'candle_begin_time' in df.columns:
                        df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'])
                    
                    # 优先选择存在的综合得分列（1d/7d/30d）
                    composite_score_col = None
                    for window in [1, 7, 30]:
                        col_name = f'综合得分_{window}d'
                        if col_name in df.columns:
                            composite_score_col = col_name
                            break
                    if composite_score_col is None and 'Y指数' in df.columns:
                        composite_score_col = 'Y指数'
                    
                    data = {
                        'dates': safe_to_list(df['candle_begin_time'].dt.strftime('%Y-%m-%d')),
                        'values': safe_to_list(df.get('Y指数', [])),
                        'composite_score': safe_to_list(df.get(composite_score_col, df.get('Y指数', [])))
                    }
                    logger.info(f"Y综合指数数据加载成功，共{len(df)}条记录")
                else:
                    # 文件不存在或为空时，尝试从 Y_idx.csv 回退
                    y_idx_df = read_y_idx_data()
                    if y_idx_df is not None and not y_idx_df.empty:
                        logger.warning("Y综合指数文件不存在或为空，使用Y指数数据作为回退")
                        if 'candle_begin_time' in y_idx_df.columns:
                            y_idx_df['candle_begin_time'] = pd.to_datetime(y_idx_df['candle_begin_time'])
                        
                        data = {
                            'dates': safe_to_list(y_idx_df['candle_begin_time'].dt.strftime('%Y-%m-%d')),
                            'values': safe_to_list(y_idx_df.get('Y_idx', [])),
                            'composite_score': safe_to_list(y_idx_df.get('Y_idx', []))
                        }
                        logger.info(f"使用Y指数回退数据，共{len(y_idx_df)}条记录")
                    else:
                        logger.warning("Y综合指数数据为空且Y指数回退失败")
                        data = {'error': 'Y综合指数数据不可用'}
            except Exception as e:
                logger.error(f"读取Y综合指数数据失败: {e}")
                logger.error(traceback.format_exc())
                data = {'error': 'Y综合指数数据不可用'}
        
        elif chart_type == 'fear_greed':
            try:
                df = get_filtered_data(os.path.join(DATA_DIR, 'fear_greed_index.csv'), ['date', 'timestamp'])
                if df is None or df.empty:
                    logger.warning("恐慌贪婪指数数据为空")
                    data = {'error': '恐慌贪婪指数数据不可用'}
                else:
                    # 处理日期列
                    if 'date' in df.columns:
                        df['candle_begin_time'] = pd.to_datetime(df['date'])
                    elif 'timestamp' in df.columns:
                        df['candle_begin_time'] = pd.to_datetime(df['timestamp'], unit='s')
                    
                    data = {
                        'dates': safe_to_list(df['candle_begin_time'].dt.strftime('%Y-%m-%d')),
                        'values': safe_to_list(df.get('value', []))
                    }
            except Exception as e:
                logger.error(f"读取恐慌贪婪指数数据失败: {e}")
                data = {'error': '恐慌贪婪指数数据不可用'}
        
        elif chart_type == 'altcoin':
            try:
                # 读取山寨币指数数据
                df = get_filtered_data(os.path.join(DATA_DIR, 'altcoin_index.csv'))
                season_df = get_filtered_data(os.path.join(DATA_DIR, 'altcoin_season_index.csv'))
                
                if df is None or df.empty:
                    logger.warning("山寨币指数数据为空")
                    data = {'error': '山寨币指数数据不可用'}
                else:
                    # 处理季节指数数据的日期列
                    if season_df is not None and not season_df.empty:
                        if 'Unnamed: 0' in season_df.columns:
                            season_df = season_df.rename(columns={'Unnamed: 0': 'date'})
                            season_df['date'] = pd.to_datetime(season_df['date'])
                        elif season_df.index.name is None and len(season_df.columns) >= 3:
                            season_df = season_df.reset_index()
                            season_df = season_df.rename(columns={'index': 'date'})
                            season_df['date'] = pd.to_datetime(season_df['date'])
                    
                    # 构建返回数据
                    data = {
                        'dates': safe_to_list(df['candle_begin_time'].dt.strftime('%Y-%m-%d')),
                        'values': safe_to_list(df.get('山寨指数', []))
                    }
                    
                    # 添加季节指数数据
                    if season_df is not None and not season_df.empty and 'date' in season_df.columns:
                        season_df = season_df.sort_values('date')
                        season_dates = safe_to_list(season_df['date'].dt.strftime('%Y-%m-%d'))
                        
                        if 'Altcoin Month' in season_df.columns:
                            data['altcoin_month'] = list(zip(season_dates, safe_to_list(season_df['Altcoin Month'].fillna(0))))
                        
                        if 'Altcoin Season' in season_df.columns:
                            data['altcoin_season'] = list(zip(season_dates, safe_to_list(season_df['Altcoin Season'].fillna(0))))
                        
                        if 'Altcoin Year' in season_df.columns:
                            data['altcoin_year'] = list(zip(season_dates, safe_to_list(season_df['Altcoin Year'].fillna(0))))
                    
                    # 将主指数数据也转换为与其他系列一致的格式
                    data['altcoin_index'] = list(zip(data['dates'], data['values']))
                    
            except Exception as e:
                logger.error(f"读取山寨币指数数据失败: {e}")
                data = {'error': '山寨币指数数据不可用'}
        
        elif chart_type == 'market_zdf':
            try:
                df = get_filtered_data(os.path.join(DATA_DIR, 'marketzdf_index.csv'))
                if df is None or df.empty:
                    logger.warning("市场ZDF指数数据为空")
                    data = {'error': '市场ZDF指数数据不可用'}
                else:
                    # dates
                    dates = safe_to_list(df['candle_begin_time'].dt.strftime('%Y-%m-%d'))

                    # 兼容前端期望字段：zdf_index，同时保留 values 以兼容可能的旧前端逻辑
                    if '全市场涨跌幅指数' in df.columns:
                        main_series = safe_to_list(df['全市场涨跌幅指数'].fillna(0))
                    else:
                        main_series = []

                    data = {
                        'dates': dates,
                        'zdf_index': main_series,       # 前端期望字段
                        'values': main_series           # 兼容字段（不影响前端）
                    }

                    # 追加不同周期的涨跌幅指数（如 全市场涨跌幅指数32d），供拓展使用
                    for col in df.columns:
                        if col.startswith('全市场涨跌幅指数') and col.endswith('d'):
                            data[col] = safe_to_list(df[col].fillna(0))

            except Exception as e:
                logger.error(f"读取市场ZDF指数数据失败: {e}")
                data = {'error': '市场ZDF指数数据不可用'}
        
        elif chart_type == 'market_indicators':
            try:
                # 调用已有的 read_market_indicators_data 函数
                indicators_data = read_market_indicators_data()
                
                if indicators_data and len(indicators_data) > 0:
                    # 选择一个主要的指标作为主图表
                    if 'cross_section_diff' in indicators_data:
                        cross_df = indicators_data['cross_section_diff']
                        data = {
                            'dates': safe_to_list(cross_df['candle_begin_time'].dt.strftime('%Y-%m-%d')),
                            'values': safe_to_list(cross_df.get('横截面差异指数', [])),
                            'indicator_type': '横截面差异指数'
                        }
                    elif 'fear_greed' in indicators_data:
                        fear_df = indicators_data['fear_greed']
                        data = {
                            'dates': safe_to_list(fear_df['date'].dt.strftime('%Y-%m-%d')),
                            'values': safe_to_list(fear_df.get('value', [])),
                            'indicator_type': '恐慌贪婪指数'
                        }
                    elif 'altcoin_season' in indicators_data:
                        alt_df = indicators_data['altcoin_season']
                        if 'date' in alt_df.columns:
                            data = {
                                'dates': safe_to_list(alt_df['date'].dt.strftime('%Y-%m-%d')),
                                'values': safe_to_list(alt_df.get('Altcoin Season', [])),
                                'indicator_type': '山寨币季节指数'
                            }
                        else:
                            data = {'error': '综合市场指标数据格式不正确'}
                    else:
                        data = {'error': '综合市场指标数据不可用'}
                else:
                    data = {'error': '综合市场指标数据不可用'}
                    
            except Exception as e:
                logger.error(f"读取综合市场指标数据失败: {e}")
                data = {'error': '山寨币指数数据不可用'}
                
        elif chart_type == 'advanced_indicators':
            try:
                df = read_or_build_advanced_indicators()
                if df is None or df.empty:
                    logger.warning("高级指标数据为空")
                    data = {'error': '高级指标数据不可用'}
                else:
                    col = 'market_cap_weighted' if 'market_cap_weighted' in df.columns else ('market_cap_weighted_index' if 'market_cap_weighted_index' in df.columns else None)
                    if col is None:
                        logger.warning("高级指标缺少可用列: market_cap_weighted 或 market_cap_weighted_index")
                        data = {'error': '高级指标数据列缺失'}
                    else:
                        if 'candle_begin_time' in df.columns:
                            df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'], errors='coerce')
                            df = df.dropna(subset=['candle_begin_time']).sort_values('candle_begin_time')
                        values = safe_to_list(df[col])
                        data = {
                            'dates': safe_to_list(df['candle_begin_time'].dt.strftime('%Y-%m-%d')),
                            'values': values
                        }
                        logger.info(f"高级指标数据加载成功，共{len(df)}条记录")
            except Exception as e:
                logger.error(f"读取高级指标数据失败: {e}")
                data = {'error': '高级指标数据不可用'}
                
        else:
            data = {'error': f'不支持的图表类型: {chart_type}'}
        
        log_performance('api_chart_data', start_time, time.time())
        return jsonify(data)
        
    except Exception as e:
        logger.error(f"获取图表数据失败: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': '获取图表数据失败'}), 500

@app.route('/api/update-onchain-data', methods=['POST'])
def update_onchain_data():
    """
    手动更新链上数据（MVRV、稳定币供应量、交易所净流入流出）
    说明：
    - 统一调用 update_market_data()，触发完整的数据抓取与计算保存流程；
    - update_market_data 内部包含 MVRV、稳定币、交易所净流入流出等指标更新。
    
    Returns:
        JSON响应包含更新状态和结果
    """
    try:
        logger.info("开始手动更新链上数据（统一管道）")
        success = update_market_data()
        if success:
            return jsonify({
                'status': 'success',
                'message': '链上数据更新完成',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        else:
            return jsonify({
                'status': 'error',
                'message': '链上数据更新失败',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }), 500
    except Exception as e:
        logger.error(f"链上数据更新失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'链上数据更新失败: {str(e)}',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 500

@app.route('/update-onchain-data')
def update_onchain_data_simple():
    """
    手动更新链上数据接口（简化触发版）
    功能：
        - 触发 update_market_data() 执行全量指标更新（包含 Y 综合指数）
    返回：
        - 200: 更新成功
        - 500: 更新失败
    """
    try:
        logger.info("开始手动更新链上数据")
        success = update_market_data()
        if success:
            return jsonify({'status': 'success', 'message': '链上数据更新完成'})
        else:
            return jsonify({'status': 'error', 'message': '链上数据更新失败'}), 500
    except Exception as e:
        logger.error(f"手动更新链上数据失败: {e}")
        return jsonify({'status': 'error', 'message': f'更新失败: {str(e)}'}), 500

@app.route('/update-onchain-data/manual', endpoint='update_onchain_data_manual')
def update_onchain_data_manual():
    """
    手动更新链上与市场相关数据（避免与已存在的 update_onchain_data 端点重名）
    返回：
        - 200: 更新成功
        - 500: 更新失败
    """
    try:
        logger.info("开始手动更新链上数据")
        success = update_market_data()
        if success:
            return jsonify({'status': 'success', 'message': '链上数据更新完成'})
        else:
            return jsonify({'status': 'error', 'message': '链上数据更新失败'}), 500
    except Exception as e:
        logger.error(f"手动更新链上数据失败: {e}")
        return jsonify({'status': 'error', 'message': f'更新失败: {str(e)}'}), 500

@app.route('/update-y-composite')
def update_y_composite():
    """
    手动更新Y综合指数数据
    """
    try:
        logger.info("开始手动更新Y综合指数数据")
        
        # 获取基础参数
        acc = 'qqdev'  # 或者从配置中读取
        backdays = 365
        start_time_data = datetime.now() - timedelta(days=backdays)
        
        # 获取市场数据
        exchange = ccxt.binance({
            'timeout': 30000,
            'rateLimit': 1200,
            'enableRateLimit': True,
        })
        
        exchange_rules = binance.u_furture_get_exchangeinfo(exchange)
        symbol_list = list(filter(lambda s: s['status'] == 'TRADING' 
                                and s['quoteAsset'] == 'USDT' 
                                and s['contractType'] == 'PERPETUAL', 
                                exchange_rules['symbols']))
        symbol_list = [s['symbol'] for s in symbol_list]
        
        run_time = common.cacu_run_time('1d', datetime.now())
        max_day = max(1, 7, 30, backdays)
        
        # 获取价格数据
        df_dict = binance.u_furture_fetch_all_swap_candle_data(
            exchange, symbol_list, '1d', run_time, max_day * 2 + 10, 
            True, False, njobs=8
        )
        
        # 更新Y指数综合指标
        y_composite_obj = Y指数综合指标()
        y_composite_obj.stat_with_data(
            df_dict=df_dict,
            funding_data=None,
            stablecoin_data=None,
            acc=acc,
            start_time=start_time_data,
            backdays=backdays,
            windows=[1, 7, 30],
            save_img=True,
            interval="1d"
        )
        
        logger.info("Y综合指数数据更新完成")
        return jsonify({
            'status': 'success', 
            'message': 'Y综合指数数据更新完成',
            'file_generated': 'data/y_composite_index.csv'
        })
        
    except Exception as e:
        logger.error(f"手动更新Y综合指数数据失败: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            'status': 'error', 
            'message': f'更新失败: {str(e)}'
        }), 500

@app.route('/market-charts')
def market_charts():
    """
    市场指标图表页面
    
    显示交易所净流入、恐慌贪婪指数、山寨币指数的图表
    """
    try:
        return render_template('market_charts.html')
    except Exception as e:
        logger.error(f"渲染市场图表页面失败: {e}")
        return "页面加载失败", 500

@app.route('/api/market-overview')
def api_market_overview():
    """
    API路由 - 获取市场概览数据
    
    Returns:
        dict: 包含所有指标的市场概览数据
    """
    try:
        log_function_call('api_market_overview', {})
        start_time = time.time()
        
        overview_data = {}
        
        # 自愈：确保交易所净流入数据不过期（超过1天自动刷新，3小时内限流）
        # 为避免阻塞接口，加入后台执行与8秒超时控制
        try:
            run_with_timeout(ensure_exchange_flow_recent, kwargs={"max_age_days":1, "min_interval_minutes":180}, timeout_sec=3)
        except Exception as e:
            logger.warning(f"自愈刷新交易所净流入失败（已忽略）: {e}")
        
        # Y指数数据（统一前端字段：value/change/signal/compare）
        try:
            # 复用已实现的计算结果（含 value/status/change_7d/30d）
            yidx = compute_y_index_section()
            # 读取原始 Y 指数序列，用于计算百分比变化与 7/30 日对比
            yidx_df = read_y_idx_data()

            # 默认 compare 结构，避免前端空白
            default_compare = {
                'day_7': {'change': 0, 'direction': 'flat'},
                'day_30': {'change': 0, 'direction': 'flat'}
            }

            # 计算百分比变化与对比
            if yidx_df is not None and not yidx_df.empty and 'Y_idx' in yidx_df.columns:
                change_pct = calculate_change_percentage(yidx_df, 'Y_idx')
                compare = calculate_7_30_day_comparison(yidx_df, 'Y_idx', mode='point')
            else:
                change_pct = 0.0
                compare = default_compare

            # 英文状态 -> 中文信号 映射
            status = yidx.get('status', 'unknown') if isinstance(yidx, dict) else 'unknown'
            status_to_signal = {
                'bullish': '看涨',
                'normal': '中性',
                'warning': '看跌',
                'danger': '看跌'
            }
            signal_cn = status_to_signal.get(status, '未知')

            # 组装前端需要的结构：value / change(%) / signal / compare
            y_value = yidx.get('value') if isinstance(yidx, dict) else None
            safe_y_value = safe_parse_float(y_value, default=None, clamp=(0.0, 100.0))
            overview_data['y_index'] = {
                'value': round(safe_y_value, 2) if (safe_y_value is not None and np.isfinite(safe_y_value)) else 'N/A',
                'change': round(change_pct, 2),
                'signal': signal_cn,
                'compare': compare or default_compare
            }
        except Exception as e:
            logger.warning(f"获取Y指数数据失败: {e}")
            overview_data['y_index'] = {
                'value': 'N/A',
                'change': 0.0,
                'signal': '数据错误',
                'compare': {
                    'day_7': {'change': 0, 'direction': 'flat'},
                    'day_30': {'change': 0, 'direction': 'flat'}
                }
            }
        
        # 波动率数据
        try:
            volatility_df = read_volatility_data()
            if volatility_df is not None and not volatility_df.empty:
                latest_7d = safe_get_latest_value(volatility_df, '市场波动率指数_7d', '.4f')
                volatility_change = calculate_change_percentage(volatility_df, '市场波动率指数_7d')
                overview_data['volatility'] = {
                    'value': latest_7d,
                    'change': volatility_change,
                    'status': 'normal',
                    'compare': calculate_7_30_day_comparison(volatility_df, '市场波动率指数_7d')
                }
        except Exception as e:
            logger.warning(f"获取波动率数据失败: {e}")
            overview_data['volatility'] = {'value': 'N/A', 'change': 0, 'status': 'unknown'}
        
        # 流动性数据
        try:
            liquidity_df = read_liquidity_data()
            if liquidity_df is not None and not liquidity_df.empty:
                latest_30d = safe_get_latest_value(liquidity_df, '综合流动性指数_30d', '.4f')
                liquidity_change = calculate_change_percentage(liquidity_df, '综合流动性指数_30d')
                overview_data['liquidity'] = {
                    'value': latest_30d,
                    'change': liquidity_change,
                    'status': 'normal',
                    'compare': calculate_7_30_day_comparison(liquidity_df, '综合流动性指数_30d')
                }
        except Exception as e:
            logger.warning(f"获取流动性数据失败: {e}")
            overview_data['liquidity'] = {'value': 'N/A', 'change': 0, 'status': 'unknown'}
        
        # 市场宽度数据
        try:
            market_breadth_df = read_market_breadth_data()
            if market_breadth_df is not None and not market_breadth_df.empty:
                latest_breadth = safe_get_latest_value(market_breadth_df, '市场宽度指数', '.4f')
                breadth_change = calculate_change_percentage(market_breadth_df, '市场宽度指数')
                overview_data['market_breadth'] = {
                    'value': latest_breadth,
                    'change': breadth_change,
                    'status': 'normal',
                    'compare': calculate_7_30_day_comparison(market_breadth_df, '市场宽度指数')
                }
        except Exception as e:
            logger.warning(f"获取市场宽度数据失败: {e}")
            overview_data['market_breadth'] = {'value': 'N/A', 'change': 0, 'status': 'unknown'}
        
        # 新增 市场涨跌幅指数 卡片数据
        try:
            df = get_filtered_data(os.path.join(DATA_DIR, 'marketzdf_index.csv'))
            if df is not None and not df.empty and '全市场涨跌幅指数' in df.columns:
                # 最新值（格式化为小数点后4位，和其它卡片风格一致）
                latest_value = safe_get_latest_value(df, '全市场涨跌幅指数', '.4f')
                # 变化率（按日）
                change_pct = calculate_change_percentage(df, '全市场涨跌幅指数')
                # 7/30日对比数据生成（标准结构：day_7/day_30 -> {change, direction}）
                compare_data = calculate_7_30_day_comparison(df, '全市场涨跌幅指数')
                overview_data['market_zdf'] = {
                    'value': latest_value,
                    'change': round(change_pct, 2),
                    'status': 'normal',  # 可按需改成基于正负的好/坏映射
                    'compare': compare_data
                }
            else:
                # 异常情况下返回默认compare结构，避免前端空白
                overview_data['market_zdf'] = {
                    'value': 'N/A',
                    'change': 0,
                    'status': 'unknown',
                    'compare': {
                        'day_7': {'change': 0, 'direction': 'flat'},
                        'day_30': {'change': 0, 'direction': 'flat'}
                    }
                }
        except Exception as e:
            logger.warning(f"获取市场涨跌幅指数数据失败: {e}")
            # 错误情况下返回默认compare结构，保证向前端传递标准字段
            overview_data['market_zdf'] = {
                'value': 'N/A',
                'change': 0,
                'status': 'error',
                'compare': {
                    'day_7': {'change': 0, 'direction': 'flat'},
                    'day_30': {'change': 0, 'direction': 'flat'}
                }
            }
        
        # MVRV数据 - 增强容错：自动选择可用列并映射状态
        try:
            mvrv_df = read_mvrv_data()
            if mvrv_df is not None and not mvrv_df.empty:
                # 选择展示列优先级：MVRV -> mvrv_365d -> mvrv_90d -> mvrv_30d
                value_col = None
                for cand in ['MVRV', 'mvrv_365d', 'mvrv_90d', 'mvrv_30d']:
                    if cand in mvrv_df.columns:
                        value_col = cand
                        break

                # 选择状态列优先级：MVRV状态 -> mvrv_composite_signal
                status_col = None
                for cand in ['MVRV状态', 'mvrv_composite_signal']:
                    if cand in mvrv_df.columns:
                        status_col = cand
                        break

                # 若主数据源无有效数值列 或 该列全部为NaN，则回退到 mvrv_indicator.csv
                if value_col is None or mvrv_df[value_col].dropna().empty:
                    alt_df = get_cached_data(os.path.join(DATA_DIR, 'mvrv_indicator.csv'))
                    if alt_df is not None and not alt_df.empty:
                        for cand in ['市场MVRV_MA_30d', '市场MVRV_MA_7d', '市场MVRV_VWAP_30d', '市场MVRV_VWAP_7d', '市场MVRV中位数_30d', '市场MVRV中位数_7d', '市场MVRV百分位_30d', '市场MVRV百分位_7d']:
                            if cand in alt_df.columns and pd.to_numeric(alt_df[cand], errors='coerce').dropna().size:
                                value_col = cand
                                mvrv_df = alt_df  # 使用回退数据源
                                break
                        # 状态列回退选择
                        for cand in ['市场估值状态_30d', '市场估值状态_7d', '市场MVRV信号_30d', '市场MVRV信号_7d']:
                            if cand in mvrv_df.columns:
                                status_col = cand
                                break

                # 仍无有效列则判为无数据
                if value_col is None:
                    raise KeyError('MVRV数据源缺少可用数值列')

                # 基于最后一个有效数值行，避免末尾 NaN 取到 0
                valid_df = mvrv_df[pd.to_numeric(mvrv_df[value_col], errors='coerce').notna()]
                if valid_df is not None and not valid_df.empty:
                    latest_mvrv = get_latest_valid_numeric(valid_df, value_col, lookback=366, fallback=0.0)
                    raw_status = valid_df[status_col].iloc[-1] if status_col else '未知'
                else:
                    latest_mvrv = 0.0
                    raw_status = '未知'

                # 状态到信号映射，兼容不同文本
                signal_mapping = {
                    '低估': '看涨',
                    '极度低估': '看涨',
                    '合理': '中性',
                    '正常': '中性',
                    '高估': '看跌',
                    '极度高估': '看跌'
                }
                signal = signal_mapping.get(str(raw_status), '中性')

                # 变化率与7/30日对比基于选定列；优先使用过滤后的 valid_df
                base_df = valid_df if (valid_df is not None and not valid_df.empty) else mvrv_df
                mvrv_change = calculate_change_percentage(base_df if not base_df.empty else mvrv_df, value_col)
                compare_data = calculate_7_30_day_comparison(base_df, value_col)

                overview_data['mvrv'] = {
                    'value': round(latest_mvrv, 2),
                    'change': round(mvrv_change, 2),
                    'signal': signal,
                    'compare': compare_data
                }
            else:
                # 主数据源为空，直接回退到 mvrv_indicator.csv
                alt_df = get_cached_data(os.path.join(DATA_DIR, 'mvrv_indicator.csv'))
                if alt_df is not None and not alt_df.empty:
                    value_col = None
                    for cand in ['市场MVRV_MA_30d', '市场MVRV_MA_7d', '市场MVRV_VWAP_30d', '市场MVRV_VWAP_7d', '市场MVRV中位数_30d', '市场MVRV中位数_7d', '市场MVRV百分位_30d', '市场MVRV百分位_7d']:
                        if cand in alt_df.columns and pd.to_numeric(alt_df[cand], errors='coerce').dropna().size:
                            value_col = cand
                            break
                    status_col = None
                    for cand in ['市场估值状态_30d', '市场估值状态_7d', '市场MVRV信号_30d', '市场MVRV信号_7d']:
                        if cand in alt_df.columns:
                            status_col = cand
                            break

                    if value_col:
                        valid_df = alt_df[pd.to_numeric(alt_df[value_col], errors='coerce').notna()]
                        latest_mvrv = get_latest_valid_numeric(valid_df, value_col, lookback=366, fallback=0.0)
                        raw_status = valid_df[status_col].iloc[-1] if (status_col and not valid_df.empty) else '未知'
                        signal_mapping = {
                            '低估': '看涨',
                            '极度低估': '看涨',
                            '合理': '中性',
                            '正常': '中性',
                            '高估': '看跌',
                            '极度高估': '看跌'
                        }
                        signal = signal_mapping.get(str(raw_status), '中性')
                        base_df = valid_df if not valid_df.empty else alt_df
                        mvrv_change = calculate_change_percentage(base_df, value_col)
                        compare_data = calculate_7_30_day_comparison(base_df, value_col)
                        overview_data['mvrv'] = {
                            'value': round(latest_mvrv, 2),
                            'change': round(mvrv_change, 2),
                            'signal': signal,
                            'compare': compare_data
                        }
                    else:
                        overview_data['mvrv'] = {
                            'value': 0,
                            'change': 0,
                            'signal': '无数据',
                            'compare': {
                                'day_7': {'change': 0, 'direction': 'flat'},
                                'day_30': {'change': 0, 'direction': 'flat'}
                            }
                        }
                else:
                    overview_data['mvrv'] = {
                        'value': 0,
                        'change': 0,
                        'signal': '无数据',
                        'compare': {
                            'day_7': {'change': 0, 'direction': 'flat'},
                            'day_30': {'change': 0, 'direction': 'flat'}
                        }
                    }
        except Exception as e:
            logger.warning(f"获取MVRV数据失败: {e}")
            overview_data['mvrv'] = {
                'value': 0,
                'change': 0,
                'signal': '数据错误',
                'compare': {
                    'day_7': {'change': 0, 'direction': 'flat'},
                    'day_30': {'change': 0, 'direction': 'flat'}
                }
            }
        
        # 稳定币供应量数据 - 修复字段名匹配前端期望
        try:
            stablecoin_df = read_stablecoin_supply_data()
            if stablecoin_df is not None and not stablecoin_df.empty:
                # 选择展示列：优先使用 total_supply_billion（单位：十亿美元），否则回退 total_supply
                display_col = 'total_supply_billion' if 'total_supply_billion' in stablecoin_df.columns else (
                    'total_supply' if 'total_supply' in stablecoin_df.columns else None
                )
                if not display_col:
                    raise KeyError("stablecoin_supply.csv 缺少 total_supply_billion/total_supply 列")

                # 最新有效值（回溯查找）
                latest_supply = get_latest_valid_numeric(stablecoin_df, display_col, lookback=366)

                # 过滤有效数据后计算变化率与对比
                valid_df = stablecoin_df.copy()
                valid_df = valid_df[pd.to_numeric(valid_df[display_col], errors='coerce').notna()]
                supply_change = calculate_change_percentage(valid_df if not valid_df.empty else stablecoin_df, display_col)

                # 供应状态列优先顺序：7日 > 1日 > 30日
                status_col = None
                for cand in ['供应量状态_7d', '供应量状态_1d', '供应量状态_30d']:
                    if cand in stablecoin_df.columns:
                        status_col = cand
                        break
                raw_status = stablecoin_df[status_col].iloc[-1] if status_col else '无数据'
                level_status = map_stablecoin_signal_to_status(raw_status)

                # 前端 stablecoin-card 期望字段：value / change / level / compare
                overview_data['stablecoin_supply'] = {
                    'value': round(latest_supply, 2) if display_col == 'total_supply_billion' else int(round(latest_supply)),
                    'change': round(supply_change, 2),
                    'level': level_status,
                    'compare': calculate_7_30_day_comparison(valid_df if not valid_df.empty else stablecoin_df, display_col)
                }

                # 兼容 onchain-stablecoin-card（已存在的卡片）
                overview_data['onchain_stablecoin'] = {
                    'value': round(latest_supply, 2) if display_col == 'total_supply_billion' else int(round(latest_supply)),
                    'change': round(supply_change, 2),
                    'status': level_status,
                    'compare': calculate_7_30_day_comparison(valid_df if not valid_df.empty else stablecoin_df, display_col)
                }
            else:
                # CSV为空时的友好回退
                overview_data['stablecoin_supply'] = {
                    'value': 'N/A',
                    'change': 0.0,
                    'level': 'unknown',
                    'compare': {'day_7': {'change': 0, 'direction': 'flat'}, 'day_30': {'change': 0, 'direction': 'flat'}}
                }
                overview_data['onchain_stablecoin'] = {
                    'value': 'N/A',
                    'change': 0.0,
                    'status': 'unavailable',
                    'compare': {'day_7': {'change': 0, 'direction': 'flat'}, 'day_30': {'change': 0, 'direction': 'flat'}}
                }
        except Exception as e:
            logger.warning(f"获取稳定币供应量数据失败: {e}")
            overview_data['stablecoin_supply'] = {
                'value': 'N/A',
                'change': 0.0,
                'level': 'unknown',
                'compare': {'day_7': {'change': 0, 'direction': 'flat'}, 'day_30': {'change': 0, 'direction': 'flat'}}
            }
            overview_data['onchain_stablecoin'] = {
                'value': 'N/A',
                'change': 0.0,
                'status': 'unavailable',
                'compare': {'day_7': {'change': 0, 'direction': 'flat'}, 'day_30': {'change': 0, 'direction': 'flat'}}
            }
        
        # 交易所流入流出数据 - 彻底修复数据异常问题
        try:
            exchange_flow_df = read_exchange_flow_data()
            if exchange_flow_df is not None and not exchange_flow_df.empty:
                # 检查数据是否过期（超过3天）
                latest_date = pd.to_datetime(exchange_flow_df['candle_begin_time'].iloc[-1])
                current_date = pd.Timestamp.now()
                days_diff = (current_date - latest_date).days
                
                if days_diff > 7:
                    logger.warning(f"交易所流入流出数据已过期 {days_diff} 天")

                    # 将十亿美元单位的数值转换为亿美元并返回显示值与原始值
                    def format_exchange_flow_value(value_in_billion_usd):
                        """
                        将十亿美元单位的交易所净流入值转换为亿美元单位显示
                        
                        Returns:
                            tuple: (显示值, 单位字符串, 原始十亿美元值)
                        """
                        try:
                            if value_in_billion_usd is None or pd.isna(value_in_billion_usd):
                                return 0, "亿美元", 0
                            numeric_value = float(value_in_billion_usd)
                            # 转换为亿美元：1十亿美元 = 10亿美元
                            value_in_yi_usd = numeric_value * 10
                            return round(value_in_yi_usd, 2), "亿美元", numeric_value
                        except (ValueError, TypeError, OverflowError) as e:
                            logger.error(f"格式化交易所流入值失败: {value_in_billion_usd}, 错误: {e}")
                            return 0, "亿美元", 0

                    # 使用最近一条有效数据进行显示（但标注“数据过期”）
                    # 使用最近有效值（回溯查找）
                    latest_net_flow = get_latest_valid_numeric(exchange_flow_df, '市场净流入_1d', lookback=366)
                    display_net_flow, unit, raw_value = format_exchange_flow_value(latest_net_flow)
                    flow_change = calculate_change_percentage(exchange_flow_df, '市场净流入_1d')

                    overview_data['exchange_flow'] = {
                        'value': display_net_flow,
                        'unit': unit,
                        'raw_value_billion_usd': raw_value,
                        'net': display_net_flow,
                        'change': round(flow_change, 2),
                        'signal': '数据过期',
                        'compare': calculate_7_30_day_comparison(exchange_flow_df, '市场净流入_1d')
                    }
                else:
                    # 获取原始净流入数据
                    latest_net_flow = get_latest_valid_numeric(exchange_flow_df, '市场净流入_1d', lookback=366)
                    
                    # 数据质量检查 - 检测异常值（调整阈值适应交易所净流入数据的高波动性）
                    if len(exchange_flow_df) >= 2:
                        previous_net_flow = get_latest_valid_numeric(exchange_flow_df.iloc[:-1], '市场净流入_1d', lookback=366)
                        
                        # 检查数据是否异常 - 放宽阈值，因为交易所净流入数据波动性很大
                        if previous_net_flow != 0:
                            ratio = abs(latest_net_flow / previous_net_flow)
                            # 调整阈值：允许更大的波动范围（100倍变化或1%变化）
                            if ratio > 100 or ratio < 0.01:
                                logger.warning(f"检测到交易所净流入数据可能异常: {previous_net_flow} -> {latest_net_flow} (比率: {ratio:.4f})")
                                
                                # 进一步检查：如果绝对值变化超过100亿美元才认为是真正异常
                                abs_change = abs(latest_net_flow - previous_net_flow)
                                if abs_change > 100:  # 100十亿美元的变化才认为异常
                                    logger.error(f"确认数据异常，绝对变化: {abs_change:.2f}十亿美元")
                                    # 使用最近5天的平均值作为替代
                                    recent_values = exchange_flow_df['市场净流入_1d'].tail(5).dropna()
                                    if len(recent_values) > 1:
                                        # 排除当前异常值，计算平均值
                                        recent_values = recent_values.iloc[:-1]
                                        latest_net_flow = recent_values.mean()
                                        logger.info(f"使用最近平均值替代异常数据: {latest_net_flow:.4f}")
                                else:
                                    logger.info(f"数据变化在正常范围内，保持原值: {latest_net_flow:.4f}")
                            else:
                                logger.debug(f"交易所净流入数据正常: {previous_net_flow} -> {latest_net_flow} (比率: {ratio:.4f})")
                    
                    market_sentiment = exchange_flow_df['市场情绪指标_1d'].iloc[-1]
                    
                    # 计算变化率（使用修复后的数据）
                    # 过滤有效数据后计算变化率与对比
                    valid_df = exchange_flow_df.copy()
                    valid_df = valid_df[pd.to_numeric(valid_df['市场净流入_1d'], errors='coerce').notna()]
                    flow_change = calculate_change_percentage(valid_df if not valid_df.empty else exchange_flow_df, '市场净流入_1d')
                    
                    # 信号映射
                    signal_mapping = {
                        '极度乐观': '看涨',
                        '乐观': '看涨', 
                        '中性': '中性',
                        '悲观': '看跌',
                        '极度悲观': '看跌'
                    }
                    signal = signal_mapping.get(market_sentiment, '中性')
                    
                    # 智能单位转换 - 统一转换为亿美元显示
                    def format_exchange_flow_value(value_in_billion_usd):
                        """
                        将十亿美元单位的交易所净流入值转换为亿美元单位显示
                        
                        Args:
                            value_in_billion_usd: 十亿美元单位的数值
                        
                        Returns:
                            tuple: (显示值, 单位字符串, 原始十亿美元值)
                        """
                        try:
                            # 数据有效性检查
                            if value_in_billion_usd is None or pd.isna(value_in_billion_usd):
                                return 0, "亿美元", 0
                            
                            # 转换为数值类型
                            numeric_value = float(value_in_billion_usd)
                            
                            # 转换为亿美元：1十亿美元 = 10亿美元
                            value_in_yi_usd = numeric_value * 10
                            return round(value_in_yi_usd, 2), "亿美元", numeric_value
                        except (ValueError, TypeError, OverflowError) as e:
                            logger.error(f"格式化交易所流入值失败: {value_in_billion_usd}, 错误: {e}")
                            return 0, "亿美元", 0
                        except Exception as e:
                            logger.error(f"格式化交易所流入值时发生未知错误: {e}")
                            return 0, "亿美元", 0
                    
                    # 应用新的格式化函数
                    display_net_flow, unit, raw_value = format_exchange_flow_value(latest_net_flow)
                    
                    logger.info(f"交易所净流入数据: 原始值={raw_value:.6f}十亿美元, 显示值={display_net_flow}{unit}, 变化率={flow_change}%, 信号={signal}")
                    
                    overview_data['exchange_flow'] = {
                        # 修复点1：增加 value 字段
                        'value': display_net_flow,
                        'unit': unit,  # 新增单位字段
                        'raw_value_billion_usd': raw_value,  # 原始十亿美元值
                        # 兼容旧字段
                        'net': display_net_flow,
                        'change': round(flow_change, 2),
                        'signal': signal,
                        # 修复点2：补充 compare 字段（7日/30日对比）
                        'compare': calculate_7_30_day_comparison(valid_df if not valid_df.empty else exchange_flow_df, '市场净流入_1d')
                }
            else:
                # 文件为空：若刚触发刷新则提示刷新中，否则提示无数据
                now = pd.Timestamp.now()
                is_refreshing = False
                try:
                    if EXCHANGE_FLOW_LAST_REFRESH:
                        delta_min = (now.to_pydatetime() - EXCHANGE_FLOW_LAST_REFRESH).total_seconds() / 60.0
                        is_refreshing = delta_min < 15
                except Exception:
                    is_refreshing = False

                overview_data['exchange_flow'] = {
                    'value': 0,
                    'unit': '亿美元',
                    'raw_value_billion_usd': 0,
                    'net': 0,
                    'change': 0,
                    'signal': '刷新中' if is_refreshing else '无数据',
                    'compare': {'day_7': {'change': 0, 'direction': 'flat'}, 'day_30': {'change': 0, 'direction': 'flat'}}
                }
        except Exception as e:
            logger.error(f"获取交易所流入流出数据失败: {e}")
            overview_data['exchange_flow'] = {
                # 修复点1：增加 value 字段
                'value': 0,
                'unit': '亿美元',
                'raw_value_billion_usd': 0,
                'net': 0,
                'change': 0,
                'signal': '数据错误',
                # 修复点2：补充 compare 字段（默认空对比）
                'compare': {'day_7': {'change': 0, 'direction': 'flat'}, 'day_30': {'change': 0, 'direction': 'flat'}}
            }
        
        # 新增：高级指标卡片（取市值加权指数作为展示值）
        try:
            adv_df = read_or_build_advanced_indicators()
            if adv_df is not None and not adv_df.empty:
                # 兼容两种列名
                col = 'market_cap_weighted' if 'market_cap_weighted' in adv_df.columns else (
                      'market_cap_weighted_index' if 'market_cap_weighted_index' in adv_df.columns else None)
                if col:
                    series = adv_df[col].dropna()
                    if not series.empty:
                        latest_val = float(series.iloc[-1])
                        if len(series) >= 2:
                            prev = float(series.iloc[-2])
                            change_pct = round(((latest_val - prev) / (abs(prev) + 1e-10)) * 100, 2)
                        else:
                            change_pct = 0.0
                        # 函数级注释：
                        # 本段为高级指标概览卡片生成核心：
                        # 1) 使用市值加权指数作为主值与日变化
                        # 2) 使用 calculate_7_30_day_comparison 生成标准 compare 结构（day_7/day_30）
                        # 3) compare 字段用于前端 updateCard 的 7/30 日对比渲染
                        overview_data['advanced_indicators'] = {
                            'value': round(latest_val, 2),  # 新增：与前端字段对齐
                            'market_cap_weighted': round(latest_val, 2),
                            'change': change_pct,
                            'status': 'normal',
                            'compare': calculate_7_30_day_comparison(adv_df, col)
                        }
                    else:
                        overview_data['advanced_indicators'] = {
                            'value': 'N/A',  # 新增：补齐 value
                            'market_cap_weighted': 'N/A',
                            'change': 0.0,
                            'status': 'unknown',
                            'compare': {
                                'day_7': {'change': 0, 'direction': 'flat'},
                                'day_30': {'change': 0, 'direction': 'flat'}
                            }
                        }
                else:
                    overview_data['advanced_indicators'] = {
                        'value': 'N/A',  # 新增：补齐 value
                        'market_cap_weighted': 'N/A',
                        'change': 0.0,
                        'status': 'unknown',
                        'compare': {
                            'day_7': {'change': 0, 'direction': 'flat'},
                            'day_30': {'change': 0, 'direction': 'flat'}
                        }
                    }
            else:
                overview_data['advanced_indicators'] = {
                    'value': 'N/A',  # 新增：补齐 value
                    'market_cap_weighted': 'N/A',
                    'change': 0.0,
                    'status': 'unknown',
                    'compare': {
                        'day_7': {'change': 0, 'direction': 'flat'},
                        'day_30': {'change': 0, 'direction': 'flat'}
                    }
                }
        except Exception as e:
            logger.warning(f"获取高级指标数据失败: {e}")
            overview_data['advanced_indicators'] = {
                'value': 'N/A',  # 新增：补齐 value
                'market_cap_weighted': 'N/A',
                'change': 0.0,
                'status': 'unknown',
                'compare': {
                    'day_7': {'change': 0, 'direction': 'flat'},
                    'day_30': {'change': 0, 'direction': 'flat'}
                }
            }
        
        # 山寨币指数数据 - 修复duplicate keys错误
        try:
            altcoin_df = read_altcoin_data()
            altcoin_season_df = read_altcoin_season_data()

            # 新增：在组装前对数据进行去重，避免“cannot assemble with duplicate keys”
            def deduplicate_df(df, keep: str = 'last'):
                """
                函数功能：
                    对输入 DataFrame 进行去重，优先使用日期列（candle_begin_time/date/Date/timestamp）去重；
                    若无日期列，则按整行去重。去重后会重置索引。
                
                参数：
                    df: 待去重的 DataFrame
                    keep: 与 pandas.drop_duplicates 保持一致，默认保留最后一条（'last'）
                
                返回：
                    DataFrame: 去重后的 DataFrame（若 df 为 None 或空则原样返回）
                """
                try:
                    if df is None or df.empty:
                        return df
                    date_candidates = ['candle_begin_time', 'date', 'Date', 'timestamp']
                    date_col = next((c for c in date_candidates if c in df.columns), None)

                    before = len(df)
                    deduped = df.copy()

                    if date_col:
                        try:
                            deduped[date_col] = pd.to_datetime(deduped[date_col], errors='coerce')
                        except Exception:
                            pass
                        deduped = deduped.dropna(subset=[date_col]).sort_values(date_col)
                        deduped = deduped.drop_duplicates(subset=[date_col], keep=keep).reset_index(drop=True)
                        after = len(deduped)
                        if after != before:
                            logger.info(f"山寨数据按日期列 {date_col} 去重完成：{before} -> {after}")
                    else:
                        deduped = deduped.drop_duplicates(keep=keep).reset_index(drop=True)
                        after = len(deduped)
                        if after != before:
                            logger.info(f"山寨数据按整行去重完成：{before} -> {after}")
                    return deduped
                except Exception as e:
                    logger.warning(f"山寨数据去重过程出现异常（已忽略）：{e}")
                    return df

            altcoin_df = deduplicate_df(altcoin_df)
            altcoin_season_df = deduplicate_df(altcoin_season_df)
            
            logger.info(f"山寨币指数数据加载状态: altcoin_df={'有数据' if altcoin_df is not None and not altcoin_df.empty else '无数据'}")
            logger.info(f"山寨币季节数据加载状态: altcoin_season_df={'有数据' if altcoin_season_df is not None and not altcoin_season_df.empty else '无数据'}")
            
            if altcoin_df is not None and not altcoin_df.empty:
                # 修复字段名：使用正确的列名 '山寨指数'
                latest_altcoin = safe_get_latest_value(altcoin_df, '山寨指数', '.2f')
                logger.info(f"山寨指数最新值: {latest_altcoin}")
                
                # 山寨币季节数据 - 增强错误处理
                altcoin_month_value = 'N/A'
                altcoin_season_value = 'N/A'
                altcoin_year_value = 'N/A'
                
                if altcoin_season_df is not None and not altcoin_season_df.empty:
                    try:
                        logger.info(f"山寨币季节数据列名: {altcoin_season_df.columns.tolist()}")
                        logger.info(f"山寨币季节数据最后5行:\n{altcoin_season_df.tail()}")
                        
                        # 获取最新的山寨币季节数据，使用正确的列名
                        # 处理空值问题：从最后一行开始向前查找非空值
                        def get_latest_non_empty_value(df, column, format_str='.0f'):
                            """
                            获取最新的非空值 - 增强版本
                            
                            Args:
                                df: 数据框
                                column: 列名
                                format_str: 格式化字符串
                                
                            Returns:
                                str: 格式化后的值或"N/A"
                            """
                            try:
                                if df is None or df.empty or column not in df.columns:
                                    logger.warning(f"列 {column} 不存在或数据为空")
                                    return 'N/A'
                                
                                # 从最后一行开始向前查找非空值
                                for i in range(len(df) - 1, max(-1, len(df) - 30), -1):  # 最多查找30行
                                    try:
                                        value = df[column].iloc[i]
                                        if pd.notna(value) and str(value).strip() != '' and str(value).strip() != 'nan':
                                            result = format(float(value), format_str)
                                            logger.info(f"找到 {column} 的有效值: {result} (第{i}行)")
                                            return result
                                    except Exception as inner_e:
                                        logger.debug(f"处理第{i}行 {column} 值失败: {value}, 错误: {inner_e}")
                                        continue
                                
                                logger.warning(f"未找到 {column} 的有效值")
                                return 'N/A'
                            except Exception as e:
                                logger.error(f"get_latest_non_empty_value处理 {column} 失败: {e}")
                                return 'N/A'
                        
                        altcoin_month_value = get_latest_non_empty_value(altcoin_season_df, 'Altcoin Month')
                        altcoin_season_value = get_latest_non_empty_value(altcoin_season_df, 'Altcoin Season')
                        altcoin_year_value = get_latest_non_empty_value(altcoin_season_df, 'Altcoin Year')
                        
                    except Exception as season_error:
                        logger.error(f"处理山寨币季节数据失败: {season_error}")
                        logger.error(traceback.format_exc())
                
                logger.info(f"山寨币数据最终结果: 月度={altcoin_month_value}, 季度={altcoin_season_value}, 年度={altcoin_year_value}, 指数={latest_altcoin}")
                
                # 计算变化率时也要增加错误处理
                try:
                    altcoin_change = calculate_change_percentage(altcoin_df, '山寨指数')
                except Exception as change_error:
                    logger.warning(f"计算山寨币指数变化率失败: {change_error}")
                    altcoin_change = 0.0
                
                overview_data['altcoin'] = {
                    'month': altcoin_month_value,
                    'season': altcoin_season_value,
                    'year': altcoin_year_value,
                    'index': latest_altcoin,  # 保留原字段以兼容旧前端或其他使用
                    'value': latest_altcoin,  # 新增：前端读取的数值字段
                    'change': altcoin_change,
                    'signal': 'normal',       # 新增：与原 status 含义一致，供前端使用
                    'compare': calculate_7_30_day_comparison(altcoin_df, '山寨指数'),  # 新增：7日/30日对比
                    'status': 'normal'
                }
            else:
                logger.warning("山寨币指数数据为空，使用默认值")
                overview_data['altcoin'] = {
                    'month': 'N/A',
                    'season': 'N/A', 
                    'year': 'N/A',
                    'index': 'N/A',
                    'value': 'N/A',  # 新增：保证前端不空
                    'change': 0.0,
                    'signal': 'unavailable',  # 新增
                    'compare': {               # 新增：默认空对比
                        'day_7': {'change': 0, 'direction': 'none'},
                        'day_30': {'change': 0, 'direction': 'none'}
                    },
                    'status': 'unavailable'
                }
        except Exception as e:
            logger.error(f"获取山寨币指数数据失败: {e}")
            logger.error(traceback.format_exc())
            overview_data['altcoin'] = {
                'month': 'N/A',
                'season': 'N/A',
                'year': 'N/A',
                'index': 'N/A',
                'value': 'N/A',  # 新增
                'change': 0.0,
                'signal': 'unknown',  # 新增
                'compare': {          # 新增：默认空对比
                    'day_7': {'change': 0, 'direction': 'none'},
                    'day_30': {'change': 0, 'direction': 'none'}
                },
                'status': 'unknown'
            }

        # 恐慌贪婪指数数据
        try:
            fear_greed_df = read_fear_greed_data()
            if fear_greed_df is not None and not fear_greed_df.empty:
                # 修复列名：使用正确的列名 'value'
                if 'value' in fear_greed_df.columns:
                    latest_fear_greed_raw = fear_greed_df['value'].iloc[-1]
                    if pd.notna(latest_fear_greed_raw):
                        fear_greed_value = float(latest_fear_greed_raw)
                        # 统一：使用映射函数
                        level = map_fear_greed_level(fear_greed_value)
                        overview_data['fear_greed'] = {
                            'value': int(fear_greed_value),
                            'level': level,
                            'change': calculate_change_percentage(fear_greed_df, 'value'),
                            'compare': calculate_7_30_day_comparison(fear_greed_df, 'value'),
                            'status': 'normal'
                        }
                    else:
                        overview_data['fear_greed'] = {
                            'value': 'N/A',
                            'level': '未知',
                            'change': 0.0,
                            'compare': {
                                'day_7': {'change': 0, 'direction': 'none'},
                                'day_30': {'change': 0, 'direction': 'none'}
                            },
                            'status': 'unavailable'
                        }
                else:
                    logger.warning(f"恐慌贪婪指数CSV文件中未找到'value'列，可用列: {safe_to_list(fear_greed_df.columns)}")
                    overview_data['fear_greed'] = {
                        'value': 'N/A',
                        'level': '未知',
                        'change': 0,
                        'compare': {
                            'day_7': {'change': 0, 'direction': 'none'},
                            'day_30': {'change': 0, 'direction': 'none'}
                        },
                        'status': 'unavailable'
                    }
            else:
                overview_data['fear_greed'] = {
                    'value': 'N/A',
                    'level': '未知',
                    'change': 0,
                    'compare': {
                        'day_7': {'change': 0, 'direction': 'none'},
                        'day_30': {'change': 0, 'direction': 'none'}
                    },
                    'status': 'unavailable'
                }
        except Exception as e:
            logger.warning(f"获取恐慌贪婪指数数据失败: {e}")
            overview_data['fear_greed'] = {
                'value': 'N/A',
                'level': '未知',
                'change': 0,
                'compare': {
                    'day_7': {'change': 0, 'direction': 'none'},
                    'day_30': {'change': 0, 'direction': 'none'}
                },
                'status': 'unknown'
            }

        # AD百分比数据 - 添加真实数据读取
        try:
            ad_percentage_df = get_cached_data(os.path.join(DATA_DIR, 'ad_percentage.csv'))
            if ad_percentage_df is not None and not ad_percentage_df.empty:
                # 获取最新的AD百分比数据（30天窗口）
                latest_ad_value = safe_get_latest_value(ad_percentage_df, 'AD百分比_30d', '.1f')
                ad_change = calculate_change_percentage(ad_percentage_df, 'AD百分比_30d')
                market_strength = ad_percentage_df['市场强度_30d'].iloc[-1] if '市场强度_30d' in ad_percentage_df.columns else 'unknown'
                
                # 根据AD百分比判断市场状态（英文）并映射中文signal
                ad_value_float = float(latest_ad_value) if latest_ad_value != 'N/A' else 0
                if ad_value_float > 70:
                    status = 'bullish'
                    signal_cn = '看涨'
                elif ad_value_float < 30:
                    status = 'bearish'  
                    signal_cn = '看跌'
                else:
                    status = 'neutral'
                    signal_cn = '中性'
                
                # 使用中文signal；compare 字段以适配前端 index2p1.html
                overview_data['ad_percentage'] = {
                    'value': f"{latest_ad_value}%",
                    'change': round(ad_change, 2),
                    'status': status,
                    'signal': signal_cn,
                    'compare': calculate_7_30_day_comparison(ad_percentage_df, 'AD百分比_30d'),
                    'market_strength': market_strength
                }
            else:
                logger.warning("AD百分比数据为空")
                overview_data['ad_percentage'] = {
                    'value': 'N/A',
                    'change': 0.0,
                    'status': 'unavailable',
                    'signal': '未知',
                    'compare': {
                        'day_7': {'change': 0, 'direction': 'none'},
                        'day_30': {'change': 0, 'direction': 'none'}
                    },
                    'market_strength': 'unknown'
                }
        except Exception as e:
            logger.warning(f"获取AD百分比数据失败: {e}")
            overview_data['ad_percentage'] = {
                'value': 'N/A',
                'change': 0.0,
                'status': 'unknown',
                'signal': '未知',
                'compare': {
                    'day_7': {'change': 0, 'direction': 'none'},
                    'day_30': {'change': 0, 'direction': 'none'}
                },
                'market_strength': 'unknown'
            }

        # 盘口价差监控数据 - 新增概览卡片
        try:
            df = get_filtered_data(os.path.join(DATA_DIR, 'bid_ask_spread_monitor.csv'))
            if df is not None and not df.empty:
                if 'candle_begin_time' in df.columns:
                    df['candle_begin_time'] = pd.to_datetime(df['candle_begin_time'])
                
                preferred_avg_cols = ['市场平均价差_7d', '市场平均价差_1d', '市场平均价差_30d']
                preferred_status_cols = ['市场流动性状态_7d', '市场流动性状态_1d', '市场流动性状态_30d']
                
                avg_col = next((c for c in preferred_avg_cols if c in df.columns), None)
                status_col = next((c for c in preferred_status_cols if c in df.columns), None)
                
                if avg_col is not None:
                    # 取最新非空值
                    latest_value_series = df[avg_col].dropna()
                    if not latest_value_series.empty:
                        latest_value = float(latest_value_series.iloc[-1])
                        change_pct = calculate_change_percentage(df, avg_col)
                        status = 'normal'
                        if status_col and status_col in df.columns:
                            status_series = df[status_col].dropna()
                            if not status_series.empty:
                                status = str(status_series.iloc[-1])
                        
                        # 新增：补齐 level 与 compare 字段（前端 updateCard 新版参数要求）
                        overview_data['spread_monitor'] = {
                            'value': round(latest_value, 2),                 # 单位：基点（bp）
                            'change': round(change_pct, 2),
                            'status': status,                                 # 保留原字段（兼容）
                            'level': str(status),                             # 直接用“市场流动性状态_*d”
                            'compare': calculate_7_30_day_comparison(df, avg_col)  # 统一7/30天对比结构
                        }
                        logger.info(f"盘口价差监控概览：col={avg_col}, status_col={status_col}, value={latest_value}, change={change_pct}, status={status}")
                    else:
                        overview_data['spread_monitor'] = {
                            'value': 'N/A',
                            'change': 0.0,
                            'status': 'unavailable',
                            'level': '未知',
                            'compare': {
                                'day_7': {'change': 0, 'direction': 'none'},
                                'day_30': {'change': 0, 'direction': 'none'}
                            }
                        }
                else:
                    logger.warning(f"盘口价差监控列缺失，现有列: {safe_to_list(df.columns)}")
                    overview_data['spread_monitor'] = {
                        'value': 'N/A',
                        'change': 0.0,
                        'status': 'unavailable',
                        'level': '未知',
                        'compare': {
                            'day_7': {'change': 0, 'direction': 'none'},
                            'day_30': {'change': 0, 'direction': 'none'}
                        }
                    }
            else:
                overview_data['spread_monitor'] = {
                    'value': 'N/A',
                    'change': 0.0,
                    'status': 'unavailable',
                    'level': '未知',
                    'compare': {
                        'day_7': {'change': 0, 'direction': 'none'},
                        'day_30': {'change': 0, 'direction': 'none'}
                    }
                }
        except Exception as e:
            logger.warning(f"获取盘口价差监控数据失败: {e}")
            overview_data['spread_monitor'] = {
                'value': 'N/A',
                'change': 0.0,
                'status': 'unknown',
                'level': '未知',
                'compare': {
                    'day_7': {'change': 0, 'direction': 'none'},
                    'day_30': {'change': 0, 'direction': 'none'}
                }
            }

        # 资金费率监控：读取并填充 funding_rate 字段
        try:
            fr_df = read_funding_rate_monitor_data()
            if fr_df is not None and not fr_df.empty:
                last_row = fr_df.iloc[-1]
                prev_row = fr_df.iloc[-2] if len(fr_df) > 1 else None

                latest_rate = last_row.get('平均资金费率', np.nan)
                prev_rate = prev_row.get('平均资金费率', np.nan) if prev_row is not None else np.nan

                # 计算变化
                change_val = 0.0
                if not pd.isna(latest_rate) and not pd.isna(prev_rate):
                    try:
                        change_val = float(latest_rate) - float(prev_rate)  # 小数差值，前端会加 % 显示为百分点
                    except Exception:
                        change_val = 0.0

                # 信号：依据"多空力量对比"给出简洁描述
                position = '未知'
                long_short = last_row.get('多空力量对比', np.nan)
                try:
                    long_short_val = float(long_short)
                    if long_short_val >= 60:
                        position = '多头主导'
                    elif long_short_val <= 40:
                        position = '空头优势'
                    else:
                        position = '多空平衡'
                except Exception:
                    position = '未知'

                if not pd.isna(latest_rate):
                    # 新增：计算7/30日对比（point 模式：绝对百分点变化）
                    try:
                        fr_compare = calculate_7_30_day_comparison(
                            fr_df, '平均资金费率',
                            mode='point'   # 绝对百分点变化，避免接近0值的过度放大
                        )
                    except Exception:
                        fr_compare = {
                            'day_7': {'change': 0, 'direction': 'none'},
                            'day_30': {'change': 0, 'direction': 'none'}
                        }
                    overview_data['funding_rate'] = {
                        'value': round(float(latest_rate), 4),   # 保持小数表示（前端按现状显示）
                        'change': round(change_val, 4),          # 小数差值，前端加 % 显示
                        'signal': position,
                        'level': position,
                        'compare': fr_compare,
                        'status': 'normal'
                    }
                else:
                    overview_data['funding_rate'] = {
                        'value': 'N/A',
                        'change': 0.0,
                        'signal': 'unknown',
                        'level': 'unknown',
                        'compare': {
                            'day_7': {'change': 0, 'direction': 'none'},
                            'day_30': {'change': 0, 'direction': 'none'}
                        },
                        'status': 'unavailable'
                    }
            else:
                overview_data['funding_rate'] = {
                    'value': 'N/A',
                    'change': 0.0,
                    'signal': 'unknown',
                    'level': 'unknown',
                    'compare': {
                        'day_7': {'change': 0, 'direction': 'none'},
                        'day_30': {'change': 0, 'direction': 'none'}
                    },
                    'status': 'unavailable'
                }
        except Exception as e:
            logger.warning(f"获取资金费率监控数据失败: {e}")
            overview_data['funding_rate'] = {
                'value': 'N/A',
                'change': 0.0,
                'signal': 'unknown',
                'level': 'unknown',
                'compare': {
                    'day_7': {'change': 0, 'direction': 'none'},
                    'day_30': {'change': 0, 'direction': 'none'}
                },
                'status': 'unavailable'
            }

        # AHR999 指标数据
        # 说明：本段负责 AHR999 概览卡片数据的构建。为满足前端 index2p1.html 的显示需求，这里新增 compare 字段用于展示7日与30日的对比。
        try:
            ahr_df = get_cached_data(os.path.join(DATA_DIR, 'ahr999.csv'))
            if ahr_df is not None and not ahr_df.empty:
                # 列名兼容：优先 *_200，没有则退回不带后缀版本
                ahr_col = 'ahr999_200' if 'ahr999_200' in ahr_df.columns else ('ahr999' if 'ahr999' in ahr_df.columns else None)
                signal_col = 'ahr999_signal_200' if 'ahr999_signal_200' in ahr_df.columns else ('ahr999_signal' if 'ahr999_signal' in ahr_df.columns else None)

                if ahr_col is not None:
                    latest_ahr = float(ahr_df[ahr_col].iloc[-1])
                    ahr_change = calculate_change_percentage(ahr_df, ahr_col)

                    # 原始信号映射到统一语义
                    raw_signal = ahr_df[signal_col].iloc[-1] if signal_col and signal_col in ahr_df.columns else '未知'
                    # 可能取值：'抄底'、'定投'、'观望'、'逃顶'
                    signal_map = {
                        '抄底': '看涨',
                        '定投': '看涨',
                        '观望': '中性',
                        '逃顶': '看跌'
                    }
                    signal = signal_map.get(str(raw_signal), '中性')

                    # 安全调用7/30日对比计算
                    try:
                        ahr_compare = calculate_7_30_day_comparison(ahr_df, ahr_col) if ahr_col and ahr_col in ahr_df.columns else {
                            'day_7': {'change': 0, 'direction': 'none'},
                            'day_30': {'change': 0, 'direction': 'none'}
                        }
                    except Exception as e:
                        logger.warning(f"AHR999 7/30日对比计算失败: {e}")
                        ahr_compare = {
                            'day_7': {'change': 0, 'direction': 'none'},
                            'day_30': {'change': 0, 'direction': 'none'}
                        }

                    overview_data['ahr999'] = {
                        'value': round(latest_ahr, 3),
                        'change': round(ahr_change, 2),
                        'signal': signal,
                        'compare': ahr_compare,  # 新增：7日/30日对比
                        'status': 'normal'
                    }
                else:
                    logger.warning(f"AHR999 缺少必要列: {safe_to_list(ahr_df.columns)}")
                    overview_data['ahr999'] = {
                        'value': 'N/A',
                        'change': 0.0,
                        'signal': 'unknown',
                        'compare': {  # 新增：默认空对比，避免前端空白
                            'day_7': {'change': 0, 'direction': 'none'},
                            'day_30': {'change': 0, 'direction': 'none'}
                        },
                        'status': 'unavailable'
                    }
            else:
                overview_data['ahr999'] = {
                    'value': 'N/A',
                    'change': 0.0,
                    'signal': 'unknown',
                    'compare': {  # 新增：默认空对比
                        'day_7': {'change': 0, 'direction': 'none'},
                        'day_30': {'change': 0, 'direction': 'none'}
                    },
                    'status': 'unavailable'
                }
        except Exception as e:
            logger.warning(f"获取 AHR999 数据失败: {e}")
            overview_data['ahr999'] = {
                'value': 'N/A',
                'change': 0.0,
                'signal': 'unknown',
                'compare': {  # 新增：默认空对比
                    'day_7': {'change': 0, 'direction': 'none'},
                    'day_30': {'change': 0, 'direction': 'none'}
                },
                'status': 'unavailable'
            }

        # 新增：BBW（布林带宽度）概览卡片
        try:
            src = get_filtered_data(os.path.join(DATA_DIR, 'ahr999.csv'))
            if src is not None and not src.empty and 'close' in src.columns:
                bbw_df = compute_bbw_series(src, price_col='close', window=20, k=2.0)
                if bbw_df is not None and not bbw_df.empty and 'BBW' in bbw_df.columns:
                    # 确保按时间排序
                    if 'candle_begin_time' in bbw_df.columns and not str(bbw_df['candle_begin_time'].dtype).startswith('datetime'):
                        bbw_df['candle_begin_time'] = pd.to_datetime(bbw_df['candle_begin_time'], errors='coerce')
                        bbw_df = bbw_df.dropna(subset=['candle_begin_time']).sort_values('candle_begin_time')
                    latest_bbw = float(bbw_df['BBW'].iloc[-1])
                    bbw_change = calculate_change_percentage(bbw_df, 'BBW')
                    bbw_compare = calculate_7_30_day_comparison(bbw_df, 'BBW')
                    overview_data['bbw'] = {
                        'value': round(latest_bbw, 4),
                        'change': round(bbw_change, 2),
                        'signal': '中性',
                        'compare': bbw_compare
                    }
                else:
                    overview_data['bbw'] = {
                        'value': 'N/A', 'change': 0.0, 'signal': 'unknown',
                        'compare': {'day_7': {'change': 0, 'direction': 'flat'},
                                    'day_30': {'change': 0, 'direction': 'flat'}}
                    }
            else:
                overview_data['bbw'] = {
                    'value': 'N/A', 'change': 0.0, 'signal': 'unknown',
                    'compare': {'day_7': {'change': 0, 'direction': 'flat'},
                                'day_30': {'change': 0, 'direction': 'flat'}}
                }
        except Exception as e:
            logger.warning(f"获取BBW数据失败: {e}")
            overview_data['bbw'] = {
                'value': 'N/A', 'change': 0.0, 'signal': 'error',
                'compare': {'day_7': {'change': 0, 'direction': 'flat'},
                            'day_30': {'change': 0, 'direction': 'flat'}}
            }

        # 极值比率指标数据 - 新增完整数据读取和处理逻辑
        try:
            extreme_df = get_cached_data(os.path.join(DATA_DIR, 'extreme_move_ratio.csv'))
            if extreme_df is not None and not extreme_df.empty:
                # 获取最新一行数据
                latest_row = extreme_df.iloc[-1]
                
                # 获取1日窗口的极值数据（优先使用1日数据）
                up_count_1d = latest_row.get('爆拉币种数_1d', 0)
                down_count_1d = latest_row.get('暴跌币种数_1d', 0)
                total_count = latest_row.get('总币种数量', 100)  # 默认100个币种
                
                # 计算占比
                up_ratio = round((up_count_1d / total_count) * 100, 1) if total_count > 0 else 0
                down_ratio = round((down_count_1d / total_count) * 100, 1) if total_count > 0 else 0
                
                # 计算变化率（使用极端波动占比）
                extreme_change = calculate_change_percentage(extreme_df, '极端波动占比_1d') if '极端波动占比_1d' in extreme_df.columns else 0.0
                
                # 根据极值比率判断市场状态和等级
                status = map_extreme_ratio_signal_to_status(up_count_1d, down_count_1d, total_count)
                
                # 新增：计算level字段（基于极值占比）
                total_extreme_ratio = up_ratio + down_ratio
                if total_extreme_ratio >= 30:
                    level = "极度活跃"
                elif total_extreme_ratio >= 15:
                    level = "活跃"
                elif total_extreme_ratio >= 5:
                    level = "中性"
                else:
                    level = "平静"
                
                # 新增：7日/30日对比数据（使用极端波动占比列或构造value列）
                compare_col = '极端波动占比_1d' if '极端波动占比_1d' in extreme_df.columns else None
                if compare_col is None and up_ratio is not None and down_ratio is not None:
                    # 构造一个临时列用于对比计算
                    extreme_df['极值比率总占比'] = (extreme_df.get('爆拉币种数_1d', 0) + extreme_df.get('暴跌币种数_1d', 0)) / extreme_df.get('总币种数量', 100) * 100
                    compare_col = '极值比率总占比'
                
                # 安全调用7/30日对比计算
                try:
                    compare_data = calculate_7_30_day_comparison(extreme_df, compare_col) if compare_col and compare_col in extreme_df.columns else {
                        'day_7': {'change': 0, 'direction': 'flat'},
                        'day_30': {'change': 0, 'direction': 'flat'}
                    }
                except Exception as e:
                    logger.warning(f"极值比率7/30日对比计算失败: {e}")
                    compare_data = {
                        'day_7': {'change': 0, 'direction': 'flat'},
                        'day_30': {'change': 0, 'direction': 'flat'}
                    }
                
                overview_data['extreme_ratio'] = {
                    'value': f"{up_ratio}% / {down_ratio}%",  # 新增：格式化为显示值
                    'up_ratio': up_ratio,
                    'down_ratio': down_ratio,
                    'change': round(extreme_change, 2),
                    'status': status,
                    'level': level,  # 新增：等级字段
                    'compare': compare_data  # 新增：7日/30日对比
                }
                
                logger.info(f"极值比率数据: 上涨={up_ratio}%, 下跌={down_ratio}%, 变化={extreme_change}%, 状态={status}, 等级={level}")
            else:
                logger.warning("极值比率数据为空")
                overview_data['extreme_ratio'] = {
                    'value': 'N/A',
                    'up_ratio': 0,
                    'down_ratio': 0,
                    'change': 0.0,
                    'status': 'unavailable',
                    'level': '未知',  # 新增：默认等级
                    'compare': {  # 新增：默认空对比
                        'day_7': {'change': 0, 'direction': 'flat'},
                        'day_30': {'change': 0, 'direction': 'flat'}
                    }
                }
        except Exception as e:
            logger.warning(f"获取极值比率数据失败: {e}")
            overview_data['extreme_ratio'] = {
                'value': 'N/A',
                'up_ratio': 0,
                'down_ratio': 0,
                'change': 0.0,
                'status': 'unknown',
                'level': '未知',  # 新增：默认等级
                'compare': {  # 新增：默认空对比
                    'day_7': {'change': 0, 'direction': 'flat'},
                    'day_30': {'change': 0, 'direction': 'flat'}
                }
            }

        # 涨跌比重指标 - 填充卡片所需字段
        try:
            df = get_cached_data(os.path.join(DATA_DIR, 'up_down_ratio.csv'))
            if df is not None and not df.empty:
                latest_row = df.iloc[-1]

                # 直接读取比重列或用数量计算
                if '上涨比重_1d' in df.columns and '下跌比重_1d' in df.columns:
                    try:
                        up_ratio = round(float(latest_row['上涨比重_1d']), 1)
                    except Exception:
                        up_ratio = 0.0
                    try:
                        down_ratio = round(float(latest_row['下跌比重_1d']), 1)
                    except Exception:
                        down_ratio = 0.0
                else:
                    total = float(latest_row.get('总币种数量', 0) or 0)
                    up_total = float(latest_row.get('上涨总数_1d', 0) or 0)
                    down_total = float(latest_row.get('下跌总数_1d', 0) or 0)
                    up_ratio = round((up_total / total) * 100, 1) if total > 0 else 0.0
                    down_ratio = round((down_total / total) * 100, 1) if total > 0 else 0.0

                change = 0.0
                if '上涨比重_1d' in df.columns:
                    try:
                        change = round(float(calculate_change_percentage(df, '上涨比重_1d')), 2)
                    except Exception:
                        change = 0.0

                status = map_up_down_ratio_status(up_ratio, down_ratio)
                
                # 新增：将status映射为signal字段
                signal_map = {
                    'bullish': '看涨',
                    'bearish': '看跌', 
                    'neutral': '中性',
                    'unavailable': '无数据',
                    'unknown': '未知'
                }
                signal = signal_map.get(status, '中性')
                
                # 新增：格式化value字段为前端显示格式
                value = f"{up_ratio}% / {down_ratio}%"
                
                # 新增：计算7日/30日对比数据
                compare_col = '上涨比重_1d' if '上涨比重_1d' in df.columns else None
                if compare_col is None and up_ratio is not None:
                    # 构造一个临时列用于对比计算
                    df['上涨占比'] = (df.get('上涨总数_1d', 0) / df.get('总币种数量', 100)) * 100
                    compare_col = '上涨占比'
                
                # 安全调用7/30日对比计算
                try:
                    compare_data = calculate_7_30_day_comparison(df, compare_col) if compare_col and compare_col in df.columns else {
                        'day_7': {'change': 0, 'direction': 'flat'},
                        'day_30': {'change': 0, 'direction': 'flat'}
                    }
                except Exception as e:
                    logger.warning(f"涨跌比重7/30日对比计算失败: {e}")
                    compare_data = {
                        'day_7': {'change': 0, 'direction': 'flat'},
                        'day_30': {'change': 0, 'direction': 'flat'}
                    }

                overview_data['up_down_ratio'] = {
                    'value': value,  # 新增：格式化显示值
                    'up_ratio': up_ratio,
                    'down_ratio': down_ratio,
                    'change': change,
                    'status': status,
                    'signal': signal,  # 新增：信号字段
                    'compare': compare_data  # 新增：7日/30日对比
                }
                logger.info(f"涨跌比重: 上涨={up_ratio}%, 下跌={down_ratio}%, 变化={change}%, 状态={status}, 信号={signal}")
            else:
                logger.warning("涨跌比重数据为空")
                overview_data['up_down_ratio'] = {
                    'value': 'N/A',  # 新增：默认显示值
                    'up_ratio': 0.0,
                    'down_ratio': 0.0,
                    'change': 0.0,
                    'status': 'unavailable',
                    'signal': '无数据',  # 新增：默认信号
                    'compare': {  # 新增：默认空对比
                        'day_7': {'change': 0, 'direction': 'flat'},
                        'day_30': {'change': 0, 'direction': 'flat'}
                    }
                }
        except Exception as e:
            logger.warning(f"获取涨跌比重数据失败: {e}")
            overview_data['up_down_ratio'] = {
                'value': 'N/A',  # 新增：默认显示值
                'up_ratio': 0.0,
                'down_ratio': 0.0,
                'change': 0.0,
                'status': 'unknown',
                'signal': '未知',  # 新增：默认信号
                'compare': {  # 新增：默认空对比
                    'day_7': {'change': 0, 'direction': 'flat'},
                    'day_30': {'change': 0, 'direction': 'flat'}
                }
            }

        # 横截面差异指数（概览）
        try:
            df = get_filtered_data(os.path.join(DATA_DIR, 'cross_section_diff_index.csv'))
            if df is not None and not df.empty:
                # 依次优先选择 7d -> 30d -> 90d
                window_candidates = ['7d', '30d', '90d']
                value_col, level_col = None, None
                for w in window_candidates:
                    vc = f'横截面差异指数_{w}'
                    lc = f'市场分化程度_{w}'
                    if vc in df.columns:
                        value_col = vc
                        level_col = lc if lc in df.columns else None
                        break
                
                if value_col:
                    try:
                        latest_value = float(df[value_col].iloc[-1])
                    except Exception:
                        latest_value = 0.0
                    try:
                        change_pct = float(calculate_change_percentage(df, value_col))
                    except Exception:
                        change_pct = 0.0

                    status_text = df[level_col].iloc[-1] if level_col and not df[level_col].empty else '未知'
                    level = map_cross_section_level_to_status(status_text)

                    # ==== 新增：计算7/30天对比数据 ====
                    # 函数级注释：
                    # 本段逻辑基于被选中的横截面差异指数列（优先_7d，其次_30d/_90d），
                    # 使用通用函数 calculate_7_30_day_comparison 计算近7天和近30天的变化幅度与方向，
                    # 并将结果放入 compare 字段，以满足前端 cross-section-card 的展示需求。
                    # 安全调用7/30日对比计算
                    try:
                        compare_data = calculate_7_30_day_comparison(df, value_col) if value_col and value_col in df.columns else {
                            'day_7': {'change': 0, 'direction': 'flat'},
                            'day_30': {'change': 0, 'direction': 'flat'}
                        }
                    except Exception as e:
                        logger.warning(f"横截面差异指数7/30日对比计算失败: {e}")
                        compare_data = {
                            'day_7': {'change': 0, 'direction': 'flat'},
                            'day_30': {'change': 0, 'direction': 'flat'}
                        }
                    
                    overview_data['cross_section'] = {
                        'value': round(latest_value, 2),
                        'change': round(change_pct, 2),
                        'level': level,                 # 新增：供前端 getLevelClass 使用
                        'status': level,                # 保持兼容：也提供 status
                        'compare': compare_data         # 新增：7/30天对比
                    }
                else:
                    logger.warning("横截面差异指数列未找到（_7d/_30d/_90d）")
                    overview_data['cross_section'] = {
                        'value': 'N/A',
                        'change': 0.0,
                        'level': 'unavailable',          # 新增：默认level
                        'status': 'unavailable',
                        'compare': {                     # 新增：默认空对比
                            'day_7': {'change': 0, 'direction': 'flat'},
                            'day_30': {'change': 0, 'direction': 'flat'}
                        }
                    }
            else:
                logger.warning("横截面差异指数数据为空")
                overview_data['cross_section'] = {
                    'value': 'N/A',
                    'change': 0.0,
                    'level': 'unavailable',              # 新增：默认level
                    'status': 'unavailable',
                    'compare': {                         # 新增：默认空对比
                        'day_7': {'change': 0, 'direction': 'flat'},
                        'day_30': {'change': 0, 'direction': 'flat'}
                    }
                }
        except Exception as e:
            logger.warning(f"获取横截面差异指数失败: {e}")
            overview_data['cross_section'] = {
                'value': 'N/A',
                'change': 0.0,
                'level': 'unknown',                      # 新增：默认level
                'status': 'unknown',
                'compare': {                             # 新增：默认空对比
                    'day_7': {'change': 0, 'direction': 'flat'},
                    'day_30': {'change': 0, 'direction': 'flat'}
                }
            }

        # 信号映射函数（移到外层避免重复定义）
        def map_composite_signal_to_status(signal):
            signal_map = {
                '极度乐观': 'high',
                '乐观': 'medium_high', 
                '中性': 'neutral',
                '悲观': 'medium_low',
                '极度悲观': 'low',
                '强烈看多': 'high',
                '看多': 'medium_high',
                '看空': 'medium_low', 
                '强烈看空': 'low',
                '极度看涨': 'high',
                '看涨': 'medium_high',
                '看跌': 'medium_low',
                '极度看跌': 'low',
                'unknown': 'unknown'
            }
            return signal_map.get(str(signal), 'unknown')
        
        def get_y_index_signal_from_value(y_index):
            """
            根据Y指数数值返回对应信号
            
            Args:
                y_index (float): Y指数值(0-100)
                
            Returns:
                str: 强烈看多/看多/中性/看空/强烈看空
            """
            if y_index >= 80:
                return "强烈看多"
            elif y_index >= 65:
                return "看多"
            elif y_index >= 35:
                return "中性"
            elif y_index >= 20:
                return "看空"
            else:
                return "强烈看空"
        
        # Y综合指数数据 - 增强错误处理
        try:
            y_composite_df = read_y_composite_data()
            if y_composite_df is not None and not y_composite_df.empty:
                latest_y_composite = safe_get_latest_value(y_composite_df, 'Y指数', "{:.2f}")
                y_composite_signal = safe_get_latest_value(y_composite_df, '综合信号_1d', "{}")
                
                if latest_y_composite != "N/A":
                    try:
                        y_composite_value = float(latest_y_composite)
                        y_composite_change = calculate_change_percentage(y_composite_df, 'Y指数')
                        y_signal = y_composite_signal if y_composite_signal != "N/A" else '中性'
                        
                        overview_data['y_composite'] = {
                            'value': latest_y_composite,
                            'change': round(y_composite_change, 2),
                            'signal': y_signal,
                            'status': 'success',
                            'compare': calculate_7_30_day_comparison(y_composite_df, 'Y指数')
                        }
                    except ValueError:
                        overview_data['y_composite'] = {
                            'value': 'N/A',
                            'change': 0.0,
                            'signal': '数据异常',
                            'status': 'warning',
                            'compare': {'day_7': {'change': 0, 'direction': 'flat'}, 'day_30': {'change': 0, 'direction': 'flat'}}
                        }
                else:
                    overview_data['y_composite'] = {
                        'value': 'N/A',
                        'change': 0.0,
                        'signal': '数据异常',
                        'status': 'warning',
                        'compare': {'day_7': {'change': 0, 'direction': 'flat'}, 'day_30': {'change': 0, 'direction': 'flat'}}
                    }
            else:
                # 新增兜底：回退至 Y_idx.csv，避免卡片显示 N/A
                y_idx_df = read_y_idx_data()
                if y_idx_df is not None and not y_idx_df.empty:
                    latest_y_index = float(y_idx_df['Y_idx'].iloc[-1])
                    y_index_change = calculate_change_percentage(y_idx_df, 'Y_idx')
                    latest_signal = get_y_index_signal_from_value(latest_y_index)
                    overview_data['y_composite'] = {
                        'value': f"{latest_y_index:.1f}",
                        'change': round(y_index_change, 2),
                        'signal': latest_signal,
                        'status': map_composite_signal_to_status(latest_signal),
                        'compare': calculate_7_30_day_comparison(y_idx_df, 'Y_idx')
                    }
                else:
                    overview_data['y_composite'] = {
                        'value': 'N/A',
                        'change': 0.0,
                        'signal': '暂无数据',
                        'status': 'error',
                        'compare': {'day_7': {'change': 0, 'direction': 'flat'}, 'day_30': {'change': 0, 'direction': 'flat'}}
                    }
        except Exception as e:
            logger.warning(f"获取Y综合指数数据失败: {e}")
            overview_data['y_composite'] = {
                'value': 'N/A',
                'change': 0.0,
                'signal': '读取失败',
                'status': 'error',
                'compare': {'day_7': {'change': 0, 'direction': 'flat'}, 'day_30': {'change': 0, 'direction': 'flat'}}
            }

        # 添加其他指标的默认值（前端需要但暂时没有数据源）
        default_indicators = [
            'new_mvrv',
            'new_exchange_flow', 'y_composite'
        ]
        
        for indicator in default_indicators:
            if indicator not in overview_data:
                overview_data[indicator] = {
                    'value': 'N/A',
                    'change': 0.0,
                    'signal': 'unknown',
                    'status': 'unavailable'
                }
        
        log_performance('api_market_overview', start_time, time.time())
        
        return jsonify({
            'success': True,
            'data': overview_data,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        logger.error(f"获取市场概览数据失败: {e}")
        logger.error(traceback.format_exc())
        # 友好回退：返回占位数据，避免前端显示“数据获取失败”
        try:
            overview_data = {}
            default_indicators = [
                'y_index', 'mvrv', 'volatility', 'liquidity', 'market_breadth',
                'market_zdf', 'stablecoin_supply', 'exchange_flow', 'advanced_indicators',
                'altcoin', 'fear_greed', 'ad_percentage', 'spread_monitor',
                'funding_rate', 'ahr999', 'bbw', 'extreme_ratio', 'up_down_ratio',
                'cross_section', 'y_composite'
            ]
            for indicator in default_indicators:
                overview_data[indicator] = {
                    'value': 'N/A',
                    'change': 0.0,
                    'signal': 'unknown',
                    'status': 'unavailable',
                    'compare': {
                        'day_7': {'change': 0, 'direction': 'flat'},
                        'day_30': {'change': 0, 'direction': 'flat'}
                    }
                }
            return jsonify({
                'success': True,
                'data': overview_data,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        except Exception:
            return jsonify({
                'success': False,
                'error': '获取市场概览数据失败',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }), 500

@app.route('/api/subscriptions')
def api_subscriptions():
    """
    API路由 - 获取订阅数据
    
    Returns:
        dict: 订阅数据列表
    """
    try:
        # 模拟订阅数据，实际应从数据库或配置文件读取
        subscriptions = [
            {
                'id': 1,
                'name': 'Y指数监控',
                'type': 'market_data',
                'status': 'active',
                'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            {
                'id': 2,
                'name': '恐慌贪婪指数',
                'type': 'sentiment',
                'status': 'active',
                'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        ]
        
        return jsonify({
            'success': True,
            'data': subscriptions,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        logger.error(f"获取订阅数据失败: {e}")
        return jsonify({
            'success': False,
            'error': '获取订阅数据失败',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 500

@app.route('/api/open-data-folder')
def api_open_data_folder():
    """
    API路由 - 打开数据文件夹
    
    Returns:
        dict: 操作结果
    """
    try:
        import subprocess
        import platform
        
        # 根据操作系统选择打开文件夹的命令
        if platform.system() == 'Windows':
            subprocess.run(['explorer', DATA_DIR], check=True)
        elif platform.system() == 'Darwin':  # macOS
            subprocess.run(['open', DATA_DIR], check=True)
        else:  # Linux
            subprocess.run(['xdg-open', DATA_DIR], check=True)
            
        return jsonify({
            'success': True,
            'message': '数据文件夹已打开',
            'path': DATA_DIR,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        logger.error(f"打开数据文件夹失败: {e}")
        return jsonify({
            'success': False,
            'error': '打开数据文件夹失败',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 500

@app.route('/api/logs')
def api_logs():
    """
    API路由 - 获取系统日志
    
    Returns:
        dict: 日志数据
    """
    try:
        import glob
        
        # 获取最新的日志文件
        log_files = glob.glob(os.path.join(os.path.dirname(__file__), '*.log'))
        
        logs = []
        for log_file in log_files[-5:]:  # 只取最新的5个日志文件
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()[-100:]  # 只取最后100行
                    logs.extend([
                        {
                            'timestamp': line.split(' - ')[0] if ' - ' in line else '',
                            'level': 'INFO' if 'INFO' in line else 'ERROR' if 'ERROR' in line else 'WARNING' if 'WARNING' in line else 'DEBUG',
                            'message': line.strip(),
                            'file': os.path.basename(log_file)
                        }
                        for line in lines if line.strip()
                    ])
            except Exception as e:
                logger.warning(f"读取日志文件失败 {log_file}: {e}")
                continue
        
        # 按时间戳排序（最新的在前）
        logs.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({
            'success': True,
            'data': logs[:200],  # 最多返回200条日志
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        logger.error(f"获取系统日志失败: {e}")
        return jsonify({
            'success': False,
            'error': '获取系统日志失败',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 500

# 定时任务调度器
scheduler = BackgroundScheduler()


def start_preheat_async():
    """
    后台异步启动数据预热，避免阻塞服务启动。

    设计要点：
    - 在独立守护线程中调用 `pre_fetch_all_data`，不阻塞主线程。
    - 线程异常将被捕获并记录为 warning，不影响服务运行。
    - 适用于首屏体验优化，但不影响 API 的可用性。
    """
    def _worker():
        try:
            logger.info('预热线程启动')
            stats = pre_fetch_all_data()
            logger.info('预热线程完成: 成功=%d 失败=%d', stats.get('success', 0), stats.get('fail', 0))
        except Exception as e:
            logger.warning(f"预热线程异常: {e}")

    try:
        t = Thread(target=_worker, daemon=True)
        t.start()
        logger.info('已启动后台预热线程（daemon）')
    except Exception as e:
        logger.warning(f"启动预热线程失败（忽略）: {e}")


def scheduled_update():
    """定时更新任务（移除推送）"""
    try:
        logger.info("开始定时更新任务")
        success = update_market_data()
        
        if success:
            logger.info("定时更新完成")
        else:
            logger.error("定时更新失败")
            
    except Exception as e:
        logger.error(f"定时更新异常: {e}")

if __name__ == '__main__':
    try:
        # 确保关键数据文件存在
        ensure_critical_data_files()
        # 改为异步预热，避免阻塞启动
        logger.info('====== 异步预热启动（不阻塞） ======')
        start_preheat_async()
        logger.info('====== 继续启动 Flask 服务 ======')
        
        # 在启动时进行一次数据更新（如果需要）
        logger.info("应用启动中...")
        
        # 检查是否需要初始数据更新
        data_files = ['Y_idx.csv', 'volatility_index.csv', 'liquidity_index.csv']
        needs_update = False
        
        for file in data_files:
            file_path = os.path.join(DATA_DIR, file)
            if not os.path.exists(file_path):
                needs_update = True
                logger.info(f"数据文件不存在: {file_path}")
                break
            else:
                # 检查文件是否过期（超过1天）
                stat = os.stat(file_path)
                file_age = time.time() - stat.st_mtime
                if file_age > 24 * 3600:  # 超过1天
                    needs_update = True
                    logger.info(f"数据文件过期: {file_path}")
                    break
        
        if needs_update:
            logger.info("检测到数据需要更新，开始初始化数据（限时）...")
            try:
                # 为启动更新设置最大等待时间，避免阻塞服务启动
                success, err = run_with_timeout(update_market_data, max_wait_seconds=20)
                if success is True:
                    logger.info("初始数据更新完成")
                elif success is False:
                    logger.warning(f"初始数据更新失败（已忽略以保证启动）: {err}")
                else:
                    logger.warning("初始数据更新超时（已忽略以保证启动）")
            except Exception as e:
                logger.error(f"初始数据更新异常: {e}")
                logger.info("服务器将继续启动，数据可稍后手动更新")
        else:
            logger.info("数据文件存在且较新，跳过初始更新")
        
        # 添加定时任务 - 每天8:08更新
        scheduler.add_job(
            func=scheduled_update,
            trigger="cron",
            hour=8,
            minute=8,
            id='daily_update'
        )
        
        # 启动调度器
        scheduler.start()
        logger.info("定时任务调度器已启动")
        
        # 启动Flask应用
        logger.info("启动Flask应用...")
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
        
    except Exception as e:
        error_msg = f"应用启动失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        
        # 推送模块移除：仅记录日志错误，不再发送通知
    finally:
        # 关闭调度器
        if scheduler.running:
            scheduler.shutdown()
            logger.info("定时任务调度器已关闭")
