# -*- coding: utf-8 -*-
"""
日志管理模块
提供统一的日志管理功能
"""

import logging
import os
from typing import Dict, Optional
from logging.handlers import RotatingFileHandler
import atexit

# 全局日志管理器字典
_log_managers: Dict[str, logging.Logger] = {}

def get_log_manager(name: str, 
                   log_file: Optional[str] = None,
                   level: int = logging.INFO,
                   max_bytes: int = 10*1024*1024,  # 10MB
                   backup_count: int = 5) -> logging.Logger:
    """
    获取或创建日志管理器
    
    Args:
        name: 日志器名称
        log_file: 日志文件路径，如果为None则使用name.log
        level: 日志级别
        max_bytes: 单个日志文件最大字节数
        backup_count: 备份文件数量
    
    Returns:
        logging.Logger: 配置好的日志器
    """
    global _log_managers
    
    # 如果已存在，直接返回
    if name in _log_managers:
        return _log_managers[name]
    
    # 创建新的日志器
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 避免重复添加处理器
    if logger.handlers:
        logger.handlers.clear()
    
    # 设置日志文件路径
    if log_file is None:
        log_file = f"{name}.log"
    
    # 确保日志目录存在
    log_dir = os.path.dirname(log_file) if os.path.dirname(log_file) else '.'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    # 创建文件处理器（带轮转）
    try:
        file_handler = RotatingFileHandler(
            log_file, 
            maxBytes=max_bytes, 
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        
        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        
        # 设置格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # 添加处理器
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
    except Exception as e:
        # 如果文件处理器创建失败，至少保证控制台输出
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        logger.warning(f"无法创建日志文件处理器: {e}，仅使用控制台输出")
    
    # 防止日志传播到根日志器
    logger.propagate = False
    
    # 保存到全局字典
    _log_managers[name] = logger
    
    return logger

def cleanup_all_log_managers():
    """
    清理所有日志管理器，关闭文件处理器
    """
    global _log_managers
    
    for name, logger in _log_managers.items():
        try:
            # 关闭所有处理器
            for handler in logger.handlers[:]:
                handler.close()
                logger.removeHandler(handler)
        except Exception as e:
            print(f"清理日志管理器 {name} 时出错: {e}")
    
    # 清空字典
    _log_managers.clear()

def get_logger(name: str) -> logging.Logger:
    """
    获取日志器的简化接口
    
    Args:
        name: 日志器名称
    
    Returns:
        logging.Logger: 日志器实例
    """
    return get_log_manager(name)

def set_log_level(name: str, level: int):
    """
    设置指定日志器的级别
    
    Args:
        name: 日志器名称
        level: 日志级别
    """
    if name in _log_managers:
        logger = _log_managers[name]
        logger.setLevel(level)
        for handler in logger.handlers:
            handler.setLevel(level)

# 注册程序退出时的清理函数
atexit.register(cleanup_all_log_managers)

# 提供一些常用的日志级别常量
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL