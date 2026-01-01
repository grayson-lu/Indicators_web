#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立推送调度脚本
- 读取数据、拼接 Markdown、通过统一推送管理器发送
- 与 Flask 解耦合，日志独立
- 提供定时任务（每天 08:08）与一次性手动推送（--once）
"""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Dict, Optional

import pandas as pd

# 统一推送系统（仅依赖基础通知模块）
from yquant.common.notification_base import (
    UnifiedNotificationManager,
    MessageType,
    NotificationLevel,
)

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')

logger = logging.getLogger('push_scheduler')


def setup_logger() -> None:
    """配置推送调度脚本的独立日志。
    - 输出到 `logs/push_scheduler.log`
    - 控制台与文件同时记录
    - 与看板日志分离，避免冲突
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, 'push_scheduler.log')

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 文件滚动日志
    file_handler = RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8'
    )
    file_handler.setFormatter(formatter)

    # 控制台输出
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # 避免重复添加 handler
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)


def load_unified_config() -> Dict:
    """加载统一推送配置字典。
    优先顺序：
    1) 读取 `push_scheduler_config.json`（若存在）
    2) 读取环境变量 `WECHAT_WORK_WEBHOOK` / `WECHAT_WEBHOOK` / `DINGTALK_WEBHOOK`
    3) 若均缺失，则返回空配置（推送视为未启用）

    返回格式需符合 `UnifiedNotificationManager` 要求：
    {
      "wechat_work": {"enabled": true, "webhook_url": "..."},
      "dingtalk": {"enabled": true, "webhook_url": "..."}
    }
    """
    import json

    config_path = os.path.join(PROJECT_ROOT, 'push_scheduler_config.json')
    config: Dict = {}

    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            # 兼容键名：wechat / wechat_work
            wechat = raw.get('wechat_work') or raw.get('wechat')
            dingtalk = raw.get('dingtalk')
            if wechat:
                config['wechat_work'] = {
                    'enabled': bool(wechat.get('enabled', True)),
                    'webhook_url': wechat.get('webhook_url', ''),
                    'timeout': wechat.get('timeout', 30),
                    'retry_count': wechat.get('retry_attempts', 3),
                }
            if dingtalk:
                config['dingtalk'] = {
                    'enabled': bool(dingtalk.get('enabled', True)),
                    'webhook_url': dingtalk.get('webhook_url', ''),
                    'timeout': dingtalk.get('timeout', 30),
                    'retry_count': dingtalk.get('retry_attempts', 3),
                }
    except Exception as e:
        logger.warning(f"读取 push_scheduler_config.json 失败：{e}")

    # 环境变量兜底
    env_wechat = os.getenv('WECHAT_WORK_WEBHOOK') or os.getenv('WECHAT_WEBHOOK')
    env_dingtalk = os.getenv('DINGTALK_WEBHOOK')

    if env_wechat and 'wechat_work' not in config:
        config['wechat_work'] = {
            'enabled': True,
            'webhook_url': env_wechat,
            'timeout': 30,
            'retry_count': 3,
        }
    if env_dingtalk and 'dingtalk' not in config:
        config['dingtalk'] = {
            'enabled': True,
            'webhook_url': env_dingtalk,
            'timeout': 30,
            'retry_count': 3,
        }

    return config


def create_notifier() -> Optional[UnifiedNotificationManager]:
    """创建统一推送管理器。
    - 若配置有效则返回实例
    - 若无任何平台启用则返回 None
    """
    try:
        unified_config = load_unified_config()
        if not unified_config:
            logger.info('未检测到推送配置，推送功能将跳过')
            return None
        notifier = UnifiedNotificationManager(unified_config)
        if notifier.is_enabled():
            enabled = [p.value for p in notifier.get_enabled_platforms()]
            logger.info(f"推送已启用，平台: {enabled}")
            return notifier
        logger.info('推送配置存在但未启用任何平台')
        return None
    except Exception as e:
        logger.warning(f"推送管理器初始化失败：{e}")
        return None


def read_latest_y_idx() -> Optional[Dict]:
    """读取 Y 指数最新一行数据。
    - 目标文件：`data/Y_idx.csv`
    - 需要列：`candle_begin_time`、`Y_idx`
    返回：{"date": "YYYY-MM-DD", "y_idx": float}
    若文件缺失或数据无效，则返回 None
    """
    try:
        file_path = os.path.join(DATA_DIR, 'Y_idx.csv')
        if not os.path.exists(file_path):
            logger.warning(f"数据文件不存在：{file_path}")
            return None
        df = pd.read_csv(file_path)
        if df.empty:
            logger.warning("Y_idx.csv 为空")
            return None
        # 规范列名兼容
        date_col = 'candle_begin_time' if 'candle_begin_time' in df.columns else (
            'date' if 'date' in df.columns else None
        )
        if date_col is None or 'Y_idx' not in df.columns:
            logger.warning(f"列缺失，需包含 'candle_begin_time'/'date' 与 'Y_idx'，实际列：{list(df.columns)}")
            return None
        latest = df.iloc[-1]
        # 转换日期
        try:
            date_val = pd.to_datetime(latest[date_col]).strftime('%Y-%m-%d')
        except Exception:
            date_val = str(latest[date_col])
        y_idx_val = float(latest['Y_idx']) if pd.notna(latest['Y_idx']) else None
        if y_idx_val is None:
            logger.warning("最新行 Y_idx 为空")
            return None
        return {'date': date_val, 'y_idx': y_idx_val}
    except Exception as e:
        logger.error(f"读取 Y 指数失败：{e}")
        return None


def build_daily_markdown(data: Dict) -> str:
    """拼接每日市场概况 Markdown 文本。
    参数：data = {"date": "YYYY-MM-DD", "y_idx": float}
    返回：Markdown 字符串
    """
    date_str = data.get('date', datetime.now().strftime('%Y-%m-%d'))
    y_idx_val = data.get('y_idx', 0.0)
    content = (
        f"📊 **Y 指数每日概况**\n\n"
        f"📅 **日期**: {date_str}\n"
        f"📈 **Y 指数**: {y_idx_val:.2f}\n\n"
        f"🔄 每日 08:08 自动推送\n"
    )
    return content


def send_daily_summary() -> bool:
    """发送每日市场概况。
    - 内部自行创建 `UnifiedNotificationManager`
    - 若推送未启用，则记录日志并返回 False
    返回：发送是否触发（不代表平台成功）
    """
    notifier = create_notifier()
    if not notifier or not notifier.is_enabled():
        logger.info('推送未启用或配置无效，跳过每日概况发送')
        return False

    latest = read_latest_y_idx()
    if not latest:
        logger.warning('无法获取 Y 指数最新数据，跳过发送')
        return False

    content = build_daily_markdown(latest)

    try:
        results = notifier.send_to_all(
            MessageType.MARKDOWN,
            content,
            NotificationLevel.INFO
        )
        success_count = sum(1 for r in results.values() if getattr(r, 'success', False))
        total = len(results)
        logger.info(f"每日概况推送完成：成功 {success_count}/{total}")
        return True
    except Exception as e:
        logger.error(f"每日概况推送异常：{e}")
        return False


def send_error_notification(message: str) -> bool:
    """发送错误通知。
    - 内部自行创建 `UnifiedNotificationManager`
    - 使用 Markdown 格式发送错误信息
    返回：发送是否触发（不代表平台成功）
    """
    notifier = create_notifier()
    if not notifier or not notifier.is_enabled():
        logger.info('推送未启用或配置无效，跳过错误通知发送')
        return False

    content = (
        f"❌ **系统错误通知**\n\n"
        f"🕐 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"❗ 错误: {message}\n\n"
        f"请及时检查系统状态"
    )
    try:
        notifier.send_to_all(
            MessageType.MARKDOWN,
            content,
            NotificationLevel.ERROR
        )
        logger.info('错误通知已触发发送')
        return True
    except Exception as e:
        logger.error(f"错误通知推送异常：{e}")
        return False


def start_scheduler():
    """启动 APScheduler 定时任务（每日 08:08）。
    返回：已启动的调度器实例；若 APScheduler 不可用则返回 None
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except Exception as e:
        logger.error(f"APScheduler 模块不可用：{e}，仅支持 --once 模式")
        return None

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=send_daily_summary,
        trigger='cron',
        hour=8,
        minute=8,
        id='daily_summary_push'
    )
    scheduler.start()
    logger.info('推送调度器已启动（每日 08:08）')
    return scheduler


def main(argv=None) -> int:
    """主入口。
    - `--once`：立刻推送一次并退出
    - 默认：启动调度器常驻运行
    返回：进程退出码（0 正常，非 0 表示异常）
    """
    setup_logger()
    args = argv or sys.argv[1:]
    if args and args[0] == '--once':
        logger.info('收到 --once 指令，开始一次性推送')
        ok = send_daily_summary()
        logger.info('一次性推送流程结束')
        return 0

    try:
        scheduler = start_scheduler()
        if scheduler is None:
            logger.error('调度器启动失败（缺少 APScheduler），请安装后重试或使用 --once')
            return 1
        logger.info('推送调度器运行中，按 Ctrl+C 退出')
        # 保持进程常驻
        import time
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info('收到中断信号，准备退出')
        try:
            if scheduler:
                scheduler.shutdown()
        except Exception:
            pass
        return 0
    except Exception as e:
        logger.error(f"推送调度器运行异常：{e}")
        # 发送错误通知（可选）
        try:
            send_error_notification(str(e))
        except Exception:
            pass
        return 1


if __name__ == '__main__':
    sys.exit(main())