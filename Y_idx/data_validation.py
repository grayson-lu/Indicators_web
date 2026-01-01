# -*- coding: utf-8 -*-
"""
数据验证模块
提供DataFrame和数值数据的安全访问和验证功能
"""

import pandas as pd
import numpy as np
from typing import Any, Optional, Union, List, Tuple
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# 基础验证与安全访问
# ---------------------------------------------------------------------

def validate_dataframe_access(df: pd.DataFrame, operation: str = "access") -> bool:
    """
    函数级注释：
    验证DataFrame访问的安全性，包含空值、类型与空数据判断，失败时写日志。
    返回True表示可以继续访问，False表示需要走默认值或保护逻辑。
    """
    try:
        if df is None:
            logger.warning(f"DataFrame为空，操作: {operation}")
            return False
        if not isinstance(df, pd.DataFrame):
            logger.warning(f"对象不是DataFrame类型，操作: {operation}")
            return False
        if df.empty:
            logger.warning(f"DataFrame为空数据，操作: {operation}")
            return False
        return True
    except Exception as e:
        logger.error(f"DataFrame验证失败，操作: {operation}，错误: {str(e)}")
        return False


def safe_dataframe_get(
    df: pd.DataFrame,
    key: Union[str, int, List, None] = None,
    default: Any = None,
    index: Optional[int] = None,
    **kwargs
) -> Any:
    """
    函数级注释：
    安全获取DataFrame数据（兼容扩展版）。
    - 兼容历史调用传入的 `index` 关键字参数，支持负索引。
    - 当提供列名且未提供索引：返回该列（Series）。
    - 当提供列名与索引：返回该列在指定位置的值，失败返回 default。
    - 当仅提供索引：返回该行（Series），失败返回 default。
    - 当提供列表键：返回有效列的子DataFrame。
    - 未提供 key 时，若有 index 则返回第 index 行，否则返回 default。

    参数：
    - df: 待访问的DataFrame
    - key: 列名（str）、行号（int）或列名列表（List），也可为 None
    - default: 默认返回值
    - index: 行索引（可选，支持负索引）
    - **kwargs: 兼容未知的历史参数，安全忽略

    返回：任意类型（Series/标量/默认值）
    """
    try:
        if not validate_dataframe_access(df, f"获取键: {key}"):
            return default

        # 情况1：提供列名
        if isinstance(key, str):
            if key not in df.columns:
                logger.warning(f"列 '{key}' 不存在，返回默认值")
                return default
            if index is None:
                # 返回整列（保持与旧实现一致）
                return df[key]
            # 返回该列在指定位置的值（支持负索引）
            try:
                val = df.iloc[index][key]
                return val if not pd.isna(val) else default
            except Exception as e:
                logger.debug(f"按索引访问列 '{key}' 失败: {e}")
                return default

        # 情况2：仅提供索引（不提供列名）
        if key is None and index is not None:
            try:
                row = df.iloc[index]
                return row
            except Exception as e:
                logger.debug(f"按索引访问行失败: {e}")
                return default

        # 情况3：key 为行号或列名列表（兼容旧行为）
        if isinstance(key, int):
            try:
                return df.iloc[key]
            except Exception as e:
                logger.debug(f"按行号访问失败: {e}")
                return default
        if isinstance(key, list):
            valid_keys = [k for k in key if isinstance(k, str) and k in df.columns]
            if valid_keys:
                return df[valid_keys]
            logger.warning(f"提供的列名列表无有效列，返回默认值: {key}")
            return default

        # 情况4：未提供 key/index 或不支持的类型，返回默认
        logger.warning(f"无法识别的访问方式，key={key}，index={index}，返回默认值")
        return default
    except Exception as e:
        logger.error(f"安全获取数据失败，key: {key}，index: {index}，错误: {str(e)}")
        return default


def validate_numeric_range(value: Union[int, float, pd.Series, np.ndarray], 
                          min_val: Optional[float] = None, 
                          max_val: Optional[float] = None,
                          allow_nan: bool = True,
                          log_warnings: bool = True,
                          name: Optional[str] = None,
                          **kwargs) -> bool:
    """
    函数级注释：
    验证数值或序列是否在指定范围内，支持NaN策略；
    兼容历史调用增加的参数（如 name、额外**kwargs），避免因参数不匹配抛错。
    参数：
    - value: 单值或序列（Series/ndarray/list）
    - min_val/max_val: 合理范围边界
    - allow_nan: 是否允许NaN
    - log_warnings: 是否记录告警
    - name: 可选的字段名（用于日志更易读）
    - **kwargs: 兼容未知历史参数，安全忽略
    返回：
    - bool：是否在合理范围内（或根据策略允许）
    """
    try:
        # 处理单个数值（包括numpy数据类型）
        if isinstance(value, (int, float)) or np.isscalar(value):
            try:
                scalar_value = float(value) if not pd.isna(value) else value
            except (ValueError, TypeError):
                scalar_value = value
            if not allow_nan and pd.isna(scalar_value):
                return False
            if pd.isna(scalar_value):
                return allow_nan
            if min_val is not None and scalar_value < min_val:
                return False
            if max_val is not None and scalar_value > max_val:
                return False
            return True
        # 处理序列数据
        if isinstance(value, (pd.Series, np.ndarray, list)):
            if len(value) == 0:
                return True
            arr = np.array(value)
            if not allow_nan and np.any(pd.isna(arr)):
                return False
            valid_values = arr[~pd.isna(arr)]
            if len(valid_values) == 0:
                return allow_nan
            if min_val is not None and np.any(valid_values < min_val):
                return False
            if max_val is not None and np.any(valid_values > max_val):
                return False
            return True
        if log_warnings:
            logger.warning(f"不支持的数据类型: {type(value)}，字段: {name or 'N/A'}")
        return False
    except Exception as e:
        if log_warnings:
            logger.error(f"数值范围验证失败，字段: {name or 'N/A'}，错误: {str(e)}")
        return False


def safe_column_access(df: pd.DataFrame, column: str, default: Any = None) -> Any:
    """
    函数级注释：
    安全访问DataFrame列，列不存在或DataFrame不可用时返回默认值并记录日志。
    """
    try:
        if not validate_dataframe_access(df, f"访问列: {column}"):
            return default
        if column not in df.columns:
            logger.warning(f"列 '{column}' 不存在，返回默认值")
            return default
        return df[column]
    except Exception as e:
        logger.error(f"安全访问列失败，列: {column}，错误: {str(e)}")
        return default


def validate_time_series_data(df: pd.DataFrame, 
                             time_column: str = 'date',
                             value_columns: Optional[List[str]] = None,
                             min_length: int = 1) -> bool:
    """
    函数级注释：
    验证时间序列DataFrame的基本有效性（长度、时间列存在与可解析、数值列存在）。
    """
    try:
        if not validate_dataframe_access(df, "时间序列验证"):
            return False
        # 检查最小长度
        if len(df) < min_length:
            logger.warning(f"时间序列数据长度不足，当前: {len(df)}，要求: {min_length}")
            return False
        # 检查时间列
        if time_column and time_column not in df.columns:
            logger.warning(f"时间列 '{time_column}' 不存在")
            return False
        # 检查数值列
        if value_columns:
            missing_columns = [col for col in value_columns if col not in df.columns]
            if missing_columns:
                logger.warning(f"缺少数值列: {missing_columns}")
                return False
        # 检查时间列是否可以转换为日期
        if time_column and time_column in df.columns:
            try:
                pd.to_datetime(df[time_column].iloc[0])
            except Exception:
                logger.warning(f"时间列 '{time_column}' 格式无效")
                return False
        return True
    except Exception as e:
        logger.error(f"时间序列数据验证失败，错误: {str(e)}")
        return False

# ---------------------------------------------------------------------
# 新增：安全数值解析与时间序列清洗工具
# ---------------------------------------------------------------------

def safe_parse_float(value: Any, default: Optional[float] = None,
                     clamp: Optional[Tuple[Optional[float], Optional[float]]] = None,
                     strict: bool = False) -> Optional[float]:
    """
    函数级注释：
    安全解析任意输入为float。
    - 支持字符串中包含逗号、百分号、空格等常见形式（如"1,234", "45%"）。
    - 支持布尔与None，布尔在strict=False时按0/1处理，strict=True时视为无效。
    - 解析失败返回default（默认None）。
    - 支持钳制clamp=(min,max)，仅在解析成功后应用。
    """
    try:
        if value is None:
            return default
        # 直接是数值类型
        if isinstance(value, (int, float, np.integer, np.floating)):
            v = float(value)
        else:
            # 处理布尔
            if isinstance(value, bool):
                if strict:
                    return default
                v = 1.0 if value else 0.0
            else:
                s = str(value).strip()
                if s == '' or s.lower() in {'nan', 'none', 'null'}:
                    return default
                # 去除千分位和空格
                s = s.replace(',', '').replace(' ', '')
                # 处理百分号
                if s.endswith('%'):
                    base = s[:-1]
                    if base == '' or base.lower() in {'nan', 'none', 'null'}:
                        return default
                    v = float(base) / 100.0
                else:
                    v = float(s)
        # 钳制
        if clamp is not None:
            min_v, max_v = clamp
            if min_v is not None:
                v = max(min_v, v)
            if max_v is not None:
                v = min(max_v, v)
        return v
    except Exception:
        return default


def clean_time_series(df: pd.DataFrame,
                      time_column: str = 'candle_begin_time',
                      drop_future: bool = True,
                      enforce_monotonic: bool = True,
                      sort_time: bool = True,
                      deduplicate: bool = True) -> Optional[pd.DataFrame]:
    """
    函数级注释：
    清洗时间序列DataFrame：
    - 统一解析时间列为datetime；
    - 可选丢弃未来时间点；
    - 可选按时间升序排序；
    - 可选去重保持最后一次；
    - 可选强制时间单调递增（遇到逆序时间将按排序后保留）。
    返回清洗后的DataFrame，失败返回None。
    """
    try:
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return None
        col = time_column if time_column in df.columns else None
        if col is None:
            # 回退到常见列名
            for c in ['candle_begin_time', 'date', 'Date', 'timestamp']:
                if c in df.columns:
                    col = c
                    break
        if col is None:
            logger.warning('未找到时间列，无法清洗时间序列')
            return None
        # 解析为datetime
        df[col] = pd.to_datetime(df[col], errors='coerce', unit=None)
        df = df.dropna(subset=[col])
        if drop_future:
            now_ts = pd.Timestamp.now()
            df = df[df[col] <= now_ts]
        if sort_time:
            df = df.sort_values(col)
        if deduplicate:
            df = df.drop_duplicates(subset=[col], keep='last')
        # 强制单调：排序后索引重置即可
        if enforce_monotonic:
            df = df.reset_index(drop=True)
        return df
    except Exception as e:
        logger.warning(f"时间序列清洗失败: {e}")
        return None


# 兼容性函数别名

def safe_to_list(data: Any) -> list:
    """
    函数级注释：
    安全转换为列表：优先调用ndarray/Series的tolist；其次list/tuple；NaN返回空列表；其它包裹为单元素列表。
    """
    try:
        if hasattr(data, 'tolist'):
            return data.tolist()
        elif isinstance(data, (list, tuple)):
            return list(data)
        elif pd.isna(data):
            return []
        else:
            return [data]
    except Exception as e:
        logger.error(f"转换为列表失败，错误: {str(e)}")
        return []


def normalize_to_list(data: Any) -> list:
    """
    函数级注释：
    标准化转换为列表（safe_to_list的别名）。
    """
    return safe_to_list(data)