"""推送管理增强模块
包含历史记录统计、频率控制、重试降级策略、定时和触发推送功能
"""

import json
import sqlite3
import hashlib
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import logging
from pathlib import Path
import schedule
from collections import defaultdict, deque
import asyncio
from concurrent.futures import ThreadPoolExecutor

# 配置日志
logger = logging.getLogger(__name__)

class PushStatus(Enum):
    """推送状态枚举"""
    PENDING = "pending"
    SENDING = "sending"
    SUCCESS = "success"
    FAILED = "failed"
    RETRY = "retry"
    CANCELLED = "cancelled"
    RATE_LIMITED = "rate_limited"

class TriggerType(Enum):
    """触发类型枚举"""
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    THRESHOLD = "threshold"
    EVENT = "event"
    AUTO = "auto"

@dataclass
class PushRecord:
    """推送记录数据类"""
    id: str
    platform: str
    message_type: str
    priority: str
    title: str
    content: str
    status: PushStatus
    trigger_type: TriggerType
    created_time: str
    sent_time: Optional[str] = None
    response_time: Optional[str] = None
    retry_count: int = 0
    error_message: Optional[str] = None
    user_feedback: Optional[str] = None
    read_status: bool = False
    content_hash: Optional[str] = None

@dataclass
class RateLimitConfig:
    """频率限制配置"""
    max_per_minute: int = 10
    max_per_hour: int = 100
    max_per_day: int = 1000
    burst_limit: int = 5
    cooldown_seconds: int = 60

@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 300.0
    backoff_factor: float = 2.0
    retry_on_errors: List[str] = None

@dataclass
class ScheduledTask:
    """定时任务数据类"""
    id: str
    name: str
    cron_expression: str
    callback: Callable
    enabled: bool = True
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    run_count: int = 0
    error_count: int = 0

class PushFrequencyController:
    """推送频率控制器"""
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.minute_counter = deque(maxlen=config.max_per_minute)
        self.hour_counter = deque(maxlen=config.max_per_hour)
        self.day_counter = deque(maxlen=config.max_per_day)
        self.burst_counter = deque(maxlen=config.burst_limit)
        self.last_reset = time.time()
        self.lock = threading.Lock()
    
    def can_send(self) -> Tuple[bool, str]:
        """
        检查是否可以发送消息
        
        Returns:
            Tuple[bool, str]: (是否可以发送, 限制原因)
        """
        with self.lock:
            now = time.time()
            
            # 清理过期记录
            self._cleanup_counters(now)
            
            # 检查突发限制
            if len(self.burst_counter) >= self.config.burst_limit:
                if now - self.burst_counter[0] < 10:  # 10秒内突发限制
                    return False, "突发频率限制"
            
            # 检查分钟限制
            if len(self.minute_counter) >= self.config.max_per_minute:
                return False, "每分钟频率限制"
            
            # 检查小时限制
            if len(self.hour_counter) >= self.config.max_per_hour:
                return False, "每小时频率限制"
            
            # 检查日限制
            if len(self.day_counter) >= self.config.max_per_day:
                return False, "每日频率限制"
            
            return True, ""
    
    def record_send(self):
        """记录发送事件"""
        with self.lock:
            now = time.time()
            self.burst_counter.append(now)
            self.minute_counter.append(now)
            self.hour_counter.append(now)
            self.day_counter.append(now)
    
    def _cleanup_counters(self, now: float):
        """清理过期的计数器记录"""
        # 清理分钟计数器
        while self.minute_counter and now - self.minute_counter[0] > 60:
            self.minute_counter.popleft()
        
        # 清理小时计数器
        while self.hour_counter and now - self.hour_counter[0] > 3600:
            self.hour_counter.popleft()
        
        # 清理日计数器
        while self.day_counter and now - self.day_counter[0] > 86400:
            self.day_counter.popleft()
    
    def get_status(self) -> Dict[str, Any]:
        """获取频率控制状态"""
        with self.lock:
            now = time.time()
            self._cleanup_counters(now)
            
            return {
                'current_minute': len(self.minute_counter),
                'current_hour': len(self.hour_counter),
                'current_day': len(self.day_counter),
                'burst_count': len(self.burst_counter),
                'limits': {
                    'max_per_minute': self.config.max_per_minute,
                    'max_per_hour': self.config.max_per_hour,
                    'max_per_day': self.config.max_per_day,
                    'burst_limit': self.config.burst_limit
                }
            }

class PushRetryManager:
    """推送重试管理器"""
    
    def __init__(self, config: RetryConfig):
        self.config = config
        self.retry_queue = deque()
        self.executor = ThreadPoolExecutor(max_workers=3)
        self.running = False
        self.retry_thread = None
    
    def start(self):
        """启动重试管理器"""
        if not self.running:
            self.running = True
            self.retry_thread = threading.Thread(target=self._retry_worker, daemon=True)
            self.retry_thread.start()
            logger.info("推送重试管理器已启动")
    
    def stop(self):
        """停止重试管理器"""
        self.running = False
        if self.retry_thread:
            self.retry_thread.join(timeout=5)
        self.executor.shutdown(wait=True)
        logger.info("推送重试管理器已停止")
    
    def add_retry_task(self, record: PushRecord, callback: Callable):
        """
        添加重试任务
        
        Args:
            record: 推送记录
            callback: 重试回调函数
        """
        if record.retry_count < self.config.max_retries:
            delay = min(
                self.config.base_delay * (self.config.backoff_factor ** record.retry_count),
                self.config.max_delay
            )
            
            retry_time = time.time() + delay
            self.retry_queue.append((retry_time, record, callback))
            logger.info(f"添加重试任务: {record.id}, 延迟 {delay:.1f} 秒")
        else:
            logger.warning(f"推送记录 {record.id} 已达到最大重试次数")
    
    def _retry_worker(self):
        """重试工作线程"""
        while self.running:
            try:
                now = time.time()
                ready_tasks = []
                
                # 找出准备重试的任务
                while self.retry_queue:
                    retry_time, record, callback = self.retry_queue[0]
                    if retry_time <= now:
                        ready_tasks.append((record, callback))
                        self.retry_queue.popleft()
                    else:
                        break
                
                # 执行重试任务
                for record, callback in ready_tasks:
                    self.executor.submit(self._execute_retry, record, callback)
                
                time.sleep(1)  # 每秒检查一次
                
            except Exception as e:
                logger.error(f"重试工作线程异常: {str(e)}")
                time.sleep(5)
    
    def _execute_retry(self, record: PushRecord, callback: Callable):
        """执行重试任务"""
        try:
            record.retry_count += 1
            record.status = PushStatus.RETRY
            
            logger.info(f"执行重试任务: {record.id} (第 {record.retry_count} 次)")
            
            # 调用重试回调
            success = callback(record)
            
            if success:
                record.status = PushStatus.SUCCESS
                record.sent_time = datetime.now().isoformat()
                logger.info(f"重试成功: {record.id}")
            else:
                record.status = PushStatus.FAILED
                logger.warning(f"重试失败: {record.id}")
                
                # 如果还有重试机会，重新加入队列
                if record.retry_count < self.config.max_retries:
                    self.add_retry_task(record, callback)
                    
        except Exception as e:
            record.status = PushStatus.FAILED
            record.error_message = str(e)
            logger.error(f"重试执行异常: {record.id}, {str(e)}")

class PushHistoryManager:
    """推送历史管理器"""
    
    def __init__(self, db_path: str = "push_history.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """初始化数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS push_records (
                    id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    created_time TEXT NOT NULL,
                    sent_time TEXT,
                    response_time TEXT,
                    retry_count INTEGER DEFAULT 0,
                    error_message TEXT,
                    user_feedback TEXT,
                    read_status BOOLEAN DEFAULT FALSE,
                    content_hash TEXT
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_time ON push_records(created_time)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_platform_status ON push_records(platform, status)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_content_hash ON push_records(content_hash)
            """)
    
    def save_record(self, record: PushRecord):
        """保存推送记录"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO push_records 
                (id, platform, message_type, priority, title, content, status, trigger_type,
                 created_time, sent_time, response_time, retry_count, error_message, 
                 user_feedback, read_status, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.id, record.platform, record.message_type, record.priority,
                record.title, record.content, record.status.value, record.trigger_type.value,
                record.created_time, record.sent_time, record.response_time, record.retry_count,
                record.error_message, record.user_feedback, record.read_status, record.content_hash
            ))
    
    def get_records(self, limit: int = 100, offset: int = 0, 
                   filters: Dict[str, Any] = None) -> List[PushRecord]:
        """获取推送记录"""
        query = "SELECT * FROM push_records"
        params = []
        
        if filters:
            conditions = []
            for key, value in filters.items():
                if key in ['platform', 'status', 'message_type', 'priority']:
                    conditions.append(f"{key} = ?")
                    params.append(value)
                elif key == 'date_from':
                    conditions.append("created_time >= ?")
                    params.append(value)
                elif key == 'date_to':
                    conditions.append("created_time <= ?")
                    params.append(value)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY created_time DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        records = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            
            for row in cursor.fetchall():
                record = PushRecord(
                    id=row['id'],
                    platform=row['platform'],
                    message_type=row['message_type'],
                    priority=row['priority'],
                    title=row['title'],
                    content=row['content'],
                    status=PushStatus(row['status']),
                    trigger_type=TriggerType(row['trigger_type']),
                    created_time=row['created_time'],
                    sent_time=row['sent_time'],
                    response_time=row['response_time'],
                    retry_count=row['retry_count'],
                    error_message=row['error_message'],
                    user_feedback=row['user_feedback'],
                    read_status=bool(row['read_status']),
                    content_hash=row['content_hash']
                )
                records.append(record)
        
        return records
    
    def get_statistics(self, days: int = 30) -> Dict[str, Any]:
        """获取推送统计信息"""
        start_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # 总体统计
            total_stats = conn.execute("""
                SELECT 
                    COUNT(*) as total_count,
                    COUNT(CASE WHEN status = 'success' THEN 1 END) as success_count,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_count,
                    COUNT(CASE WHEN read_status = 1 THEN 1 END) as read_count,
                    AVG(retry_count) as avg_retry_count
                FROM push_records 
                WHERE created_time >= ?
            """, (start_date,)).fetchone()
            
            # 按平台统计
            platform_stats = conn.execute("""
                SELECT 
                    platform,
                    COUNT(*) as count,
                    COUNT(CASE WHEN status = 'success' THEN 1 END) as success_count
                FROM push_records 
                WHERE created_time >= ?
                GROUP BY platform
            """, (start_date,)).fetchall()
            
            # 按消息类型统计
            type_stats = conn.execute("""
                SELECT 
                    message_type,
                    COUNT(*) as count,
                    COUNT(CASE WHEN read_status = 1 THEN 1 END) as read_count
                FROM push_records 
                WHERE created_time >= ?
                GROUP BY message_type
            """, (start_date,)).fetchall()
            
            # 每日统计
            daily_stats = conn.execute("""
                SELECT 
                    DATE(created_time) as date,
                    COUNT(*) as count,
                    COUNT(CASE WHEN status = 'success' THEN 1 END) as success_count
                FROM push_records 
                WHERE created_time >= ?
                GROUP BY DATE(created_time)
                ORDER BY date
            """, (start_date,)).fetchall()
        
        return {
            'period_days': days,
            'total_statistics': dict(total_stats) if total_stats else {},
            'platform_statistics': [dict(row) for row in platform_stats],
            'type_statistics': [dict(row) for row in type_stats],
            'daily_statistics': [dict(row) for row in daily_stats],
            'generated_time': datetime.now().isoformat()
        }
    
    def check_duplicate(self, content_hash: str, hours: int = 24) -> bool:
        """
        检查重复内容
        
        Args:
            content_hash: 内容哈希
            hours: 检查时间范围（小时）
            
        Returns:
            bool: 是否存在重复
        """
        start_time = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute("""
                SELECT COUNT(*) FROM push_records 
                WHERE content_hash = ? AND created_time >= ?
            """, (content_hash, start_time)).fetchone()
            
            return result[0] > 0 if result else False

class ScheduledPushManager:
    """定时推送管理器"""
    
    def __init__(self):
        self.tasks: Dict[str, ScheduledTask] = {}
        self.scheduler_thread = None
        self.running = False
    
    def start(self):
        """启动定时任务调度器"""
        if not self.running:
            self.running = True
            self.scheduler_thread = threading.Thread(target=self._scheduler_worker, daemon=True)
            self.scheduler_thread.start()
            logger.info("定时推送管理器已启动")
    
    def stop(self):
        """停止定时任务调度器"""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        logger.info("定时推送管理器已停止")
    
    def add_scheduled_task(self, task: ScheduledTask):
        """添加定时任务"""
        self.tasks[task.id] = task
        logger.info(f"添加定时任务: {task.name} ({task.cron_expression})")
    
    def remove_scheduled_task(self, task_id: str):
        """移除定时任务"""
        if task_id in self.tasks:
            del self.tasks[task_id]
            logger.info(f"移除定时任务: {task_id}")
    
    def _scheduler_worker(self):
        """调度器工作线程"""
        while self.running:
            try:
                now = datetime.now()
                
                for task in self.tasks.values():
                    if task.enabled and self._should_run_task(task, now):
                        self._execute_task(task, now)
                
                time.sleep(60)  # 每分钟检查一次
                
            except Exception as e:
                logger.error(f"定时任务调度异常: {str(e)}")
                time.sleep(60)
    
    def _should_run_task(self, task: ScheduledTask, now: datetime) -> bool:
        """判断任务是否应该运行"""
        # 简化的cron表达式解析（仅支持基本格式）
        # 实际项目中建议使用专业的cron库如croniter
        if not task.last_run:
            return True
        
        last_run = datetime.fromisoformat(task.last_run)
        
        # 简单的时间间隔检查（这里需要根据实际cron表达式实现）
        if task.cron_expression == "@daily":
            return (now - last_run).days >= 1
        elif task.cron_expression == "@hourly":
            return (now - last_run).seconds >= 3600
        elif task.cron_expression.startswith("*/"):
            # 处理 */N 格式
            interval = int(task.cron_expression[2:])
            return (now - last_run).seconds >= interval * 60
        
        return False
    
    def _execute_task(self, task: ScheduledTask, now: datetime):
        """执行定时任务"""
        try:
            logger.info(f"执行定时任务: {task.name}")
            
            task.callback()
            task.run_count += 1
            task.last_run = now.isoformat()
            
            logger.info(f"定时任务执行成功: {task.name}")
            
        except Exception as e:
            task.error_count += 1
            logger.error(f"定时任务执行失败: {task.name}, {str(e)}")
    
    def get_task_status(self) -> Dict[str, Dict]:
        """获取任务状态"""
        status = {}
        for task_id, task in self.tasks.items():
            status[task_id] = {
                'name': task.name,
                'cron_expression': task.cron_expression,
                'enabled': task.enabled,
                'last_run': task.last_run,
                'run_count': task.run_count,
                'error_count': task.error_count
            }
        return status

class EnhancedPushManager:
    """增强推送管理器 - 主管理类"""
    
    def __init__(self, config: Dict = None):
        """
        初始化增强推送管理器
        
        Args:
            config: 配置字典
        """
        self.config = config or {}
        
        # 初始化各个组件
        rate_limit_config = RateLimitConfig(**self.config.get('rate_limit', {}))
        retry_config = RetryConfig(**self.config.get('retry', {}))
        
        self.frequency_controller = PushFrequencyController(rate_limit_config)
        self.retry_manager = PushRetryManager(retry_config)
        self.history_manager = PushHistoryManager(self.config.get('db_path', 'push_history.db'))
        self.scheduled_manager = ScheduledPushManager()
        
        # 防重复配置
        self.duplicate_check_hours = self.config.get('duplicate_check_hours', 24)
        
        # 启动管理器
        self.retry_manager.start()
        self.scheduled_manager.start()
        
        logger.info("增强推送管理器初始化完成")
    
    def generate_content_hash(self, title: str, content: str) -> str:
        """
        生成内容哈希
        
        Args:
            title: 标题
            content: 内容
            
        Returns:
            str: 内容哈希
        """
        combined = f"{title}|{content}"
        return hashlib.md5(combined.encode('utf-8')).hexdigest()
    
    def can_send_message(self, title: str, content: str) -> Tuple[bool, str]:
        """
        检查是否可以发送消息
        
        Args:
            title: 消息标题
            content: 消息内容
            
        Returns:
            Tuple[bool, str]: (是否可以发送, 限制原因)
        """
        # 检查频率限制
        can_send, reason = self.frequency_controller.can_send()
        if not can_send:
            return False, f"频率限制: {reason}"
        
        # 检查重复内容
        content_hash = self.generate_content_hash(title, content)
        if self.history_manager.check_duplicate(content_hash, self.duplicate_check_hours):
            return False, f"重复内容 (最近{self.duplicate_check_hours}小时内已发送)"
        
        return True, ""
    
    def create_push_record(self, platform: str, message_type: str, priority: str,
                          title: str, content: str, trigger_type: TriggerType = TriggerType.MANUAL) -> PushRecord:
        """
        创建推送记录
        
        Args:
            platform: 推送平台
            message_type: 消息类型
            priority: 优先级
            title: 标题
            content: 内容
            trigger_type: 触发类型
            
        Returns:
            PushRecord: 推送记录
        """
        record_id = hashlib.md5(f"{platform}_{title}_{datetime.now().isoformat()}".encode()).hexdigest()[:16]
        content_hash = self.generate_content_hash(title, content)
        
        record = PushRecord(
            id=record_id,
            platform=platform,
            message_type=message_type,
            priority=priority,
            title=title,
            content=content,
            status=PushStatus.PENDING,
            trigger_type=trigger_type,
            created_time=datetime.now().isoformat(),
            content_hash=content_hash
        )
        
        return record
    
    def send_message(self, record: PushRecord, send_callback: Callable) -> bool:
        """
        发送消息
        
        Args:
            record: 推送记录
            send_callback: 发送回调函数
            
        Returns:
            bool: 发送是否成功
        """
        try:
            # 检查是否可以发送
            can_send, reason = self.can_send_message(record.title, record.content)
            if not can_send:
                record.status = PushStatus.RATE_LIMITED
                record.error_message = reason
                self.history_manager.save_record(record)
                logger.warning(f"消息发送被限制: {record.id}, 原因: {reason}")
                return False
            
            # 更新状态为发送中
            record.status = PushStatus.SENDING
            self.history_manager.save_record(record)
            
            # 记录发送频率
            self.frequency_controller.record_send()
            
            # 执行发送
            success = send_callback(record)
            
            if success:
                record.status = PushStatus.SUCCESS
                record.sent_time = datetime.now().isoformat()
                logger.info(f"消息发送成功: {record.id}")
            else:
                record.status = PushStatus.FAILED
                # 添加到重试队列
                self.retry_manager.add_retry_task(record, send_callback)
                logger.warning(f"消息发送失败，已加入重试队列: {record.id}")
            
            self.history_manager.save_record(record)
            return success
            
        except Exception as e:
            record.status = PushStatus.FAILED
            record.error_message = str(e)
            self.history_manager.save_record(record)
            
            # 添加到重试队列
            self.retry_manager.add_retry_task(record, send_callback)
            logger.error(f"消息发送异常: {record.id}, {str(e)}")
            return False
    
    def add_scheduled_push(self, name: str, cron_expression: str, 
                          push_callback: Callable, enabled: bool = True) -> str:
        """
        添加定时推送任务
        
        Args:
            name: 任务名称
            cron_expression: Cron表达式
            push_callback: 推送回调函数
            enabled: 是否启用
            
        Returns:
            str: 任务ID
        """
        task_id = hashlib.md5(f"{name}_{cron_expression}_{datetime.now().isoformat()}".encode()).hexdigest()[:16]
        
        task = ScheduledTask(
            id=task_id,
            name=name,
            cron_expression=cron_expression,
            callback=push_callback,
            enabled=enabled
        )
        
        self.scheduled_manager.add_scheduled_task(task)
        return task_id
    
    def get_push_statistics(self, days: int = 30) -> Dict[str, Any]:
        """
        获取推送统计信息
        
        Args:
            days: 统计天数
            
        Returns:
            Dict: 统计信息
        """
        stats = self.history_manager.get_statistics(days)
        
        # 添加频率控制状态
        stats['rate_limit_status'] = self.frequency_controller.get_status()
        
        # 添加定时任务状态
        stats['scheduled_tasks'] = self.scheduled_manager.get_task_status()
        
        return stats
    
    def cleanup_old_records(self, days: int = 90):
        """
        清理旧记录
        
        Args:
            days: 保留天数
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        with sqlite3.connect(self.history_manager.db_path) as conn:
            result = conn.execute("""
                DELETE FROM push_records WHERE created_time < ?
            """, (cutoff_date,))
            
            deleted_count = result.rowcount
            logger.info(f"清理了 {deleted_count} 条旧推送记录")
    
    def shutdown(self):
        """关闭管理器"""
        self.retry_manager.stop()
        self.scheduled_manager.stop()
        logger.info("增强推送管理器已关闭")