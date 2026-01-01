"""用户体验优化模块
包含实时状态反馈、内容预览、Web界面配置和效果统计分析功能
"""

import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import logging
from pathlib import Path
import asyncio
import websockets
from concurrent.futures import ThreadPoolExecutor
import uuid
from collections import defaultdict, deque
import statistics
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import plotly.graph_objs as go
import plotly.utils
from jinja2 import Template

# 配置日志
logger = logging.getLogger(__name__)

class PushStatus(Enum):
    """推送状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"

class NotificationLevel(Enum):
    """通知级别枚举"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"

@dataclass
class PushTask:
    """推送任务数据类"""
    task_id: str
    title: str
    content: str
    platforms: List[str]
    status: PushStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: str = ""
    progress: int = 0
    total_steps: int = 1
    current_step: str = ""
    
@dataclass
class PushResult:
    """推送结果数据类"""
    task_id: str
    platform: str
    status: PushStatus
    response_time: float
    error_message: str = ""
    response_data: Dict[str, Any] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

@dataclass
class PushStatistics:
    """推送统计数据类"""
    total_pushes: int
    success_count: int
    failed_count: int
    success_rate: float
    avg_response_time: float
    platform_stats: Dict[str, Dict[str, Any]]
    hourly_stats: Dict[str, int]
    daily_stats: Dict[str, int]
    
class RealTimeStatusManager:
    """实时状态管理器"""
    
    def __init__(self):
        self.tasks: Dict[str, PushTask] = {}
        self.results: Dict[str, List[PushResult]] = defaultdict(list)
        self.subscribers: Dict[str, Callable] = {}
        self.lock = threading.RLock()
        self.websocket_clients = set()
        
    def create_task(self, title: str, content: str, platforms: List[str]) -> str:
        """
        创建推送任务
        
        Args:
            title: 任务标题
            content: 任务内容
            platforms: 目标平台列表
            
        Returns:
            str: 任务ID
        """
        task_id = str(uuid.uuid4())
        
        with self.lock:
            task = PushTask(
                task_id=task_id,
                title=title,
                content=content,
                platforms=platforms,
                status=PushStatus.PENDING,
                created_at=datetime.now(),
                total_steps=len(platforms)
            )
            
            self.tasks[task_id] = task
            
        # 通知订阅者
        self._notify_subscribers("task_created", {"task_id": task_id, "task": asdict(task)})
        
        logger.info(f"创建推送任务: {task_id}")
        return task_id
    
    def update_task_status(self, task_id: str, status: PushStatus, 
                          current_step: str = "", error_message: str = ""):
        """
        更新任务状态
        
        Args:
            task_id: 任务ID
            status: 新状态
            current_step: 当前步骤描述
            error_message: 错误信息
        """
        with self.lock:
            if task_id not in self.tasks:
                return
            
            task = self.tasks[task_id]
            old_status = task.status
            task.status = status
            task.current_step = current_step
            
            if error_message:
                task.error_message = error_message
            
            if status == PushStatus.PROCESSING and old_status == PushStatus.PENDING:
                task.started_at = datetime.now()
            elif status in [PushStatus.SUCCESS, PushStatus.FAILED, PushStatus.CANCELLED]:
                task.completed_at = datetime.now()
                task.progress = task.total_steps
        
        # 通知订阅者
        self._notify_subscribers("task_updated", {
            "task_id": task_id, 
            "status": status.value,
            "current_step": current_step,
            "progress": self.tasks[task_id].progress,
            "error_message": error_message
        })
        
        logger.info(f"任务状态更新: {task_id} -> {status.value}")
    
    def update_task_progress(self, task_id: str, completed_steps: int, current_step: str = ""):
        """
        更新任务进度
        
        Args:
            task_id: 任务ID
            completed_steps: 已完成步骤数
            current_step: 当前步骤描述
        """
        with self.lock:
            if task_id not in self.tasks:
                return
            
            task = self.tasks[task_id]
            task.progress = min(completed_steps, task.total_steps)
            task.current_step = current_step
        
        # 通知订阅者
        self._notify_subscribers("task_progress", {
            "task_id": task_id,
            "progress": completed_steps,
            "total_steps": self.tasks[task_id].total_steps,
            "current_step": current_step
        })
    
    def add_result(self, result: PushResult):
        """
        添加推送结果
        
        Args:
            result: 推送结果
        """
        with self.lock:
            self.results[result.task_id].append(result)
        
        # 通知订阅者
        self._notify_subscribers("result_added", {
            "task_id": result.task_id,
            "platform": result.platform,
            "status": result.status.value,
            "response_time": result.response_time
        })
    
    def get_task(self, task_id: str) -> Optional[PushTask]:
        """
        获取任务信息
        
        Args:
            task_id: 任务ID
            
        Returns:
            Optional[PushTask]: 任务信息
        """
        with self.lock:
            return self.tasks.get(task_id)
    
    def get_task_results(self, task_id: str) -> List[PushResult]:
        """
        获取任务结果
        
        Args:
            task_id: 任务ID
            
        Returns:
            List[PushResult]: 结果列表
        """
        with self.lock:
            return self.results.get(task_id, [])
    
    def get_recent_tasks(self, limit: int = 50) -> List[PushTask]:
        """
        获取最近的任务
        
        Args:
            limit: 限制数量
            
        Returns:
            List[PushTask]: 任务列表
        """
        with self.lock:
            tasks = sorted(self.tasks.values(), key=lambda x: x.created_at, reverse=True)
            return tasks[:limit]
    
    def subscribe(self, subscriber_id: str, callback: Callable):
        """
        订阅状态更新
        
        Args:
            subscriber_id: 订阅者ID
            callback: 回调函数
        """
        self.subscribers[subscriber_id] = callback
        logger.info(f"添加状态订阅者: {subscriber_id}")
    
    def unsubscribe(self, subscriber_id: str):
        """
        取消订阅
        
        Args:
            subscriber_id: 订阅者ID
        """
        if subscriber_id in self.subscribers:
            del self.subscribers[subscriber_id]
            logger.info(f"移除状态订阅者: {subscriber_id}")
    
    def _notify_subscribers(self, event_type: str, data: Dict[str, Any]):
        """
        通知所有订阅者
        
        Args:
            event_type: 事件类型
            data: 事件数据
        """
        notification = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
        
        # 通知回调订阅者
        for subscriber_id, callback in list(self.subscribers.items()):
            try:
                callback(notification)
            except Exception as e:
                logger.error(f"通知订阅者失败 {subscriber_id}: {str(e)}")
        
        # 通知WebSocket客户端
        self._notify_websocket_clients(notification)
    
    def _notify_websocket_clients(self, notification: Dict[str, Any]):
        """
        通知WebSocket客户端
        
        Args:
            notification: 通知数据
        """
        if self.websocket_clients:
            message = json.dumps(notification, default=str)
            for client in list(self.websocket_clients):
                try:
                    asyncio.create_task(client.send(message))
                except Exception as e:
                    logger.error(f"WebSocket通知失败: {str(e)}")
                    self.websocket_clients.discard(client)

class ContentPreviewManager:
    """内容预览管理器"""
    
    def __init__(self):
        self.templates = {
            "text": "{{content}}",
            "markdown": "# {{title}}\n\n{{content}}",
            "html": "<h1>{{title}}</h1><p>{{content}}</p>",
            "email": "<html><body><h2>{{title}}</h2><div>{{content}}</div></body></html>"
        }
        
    def preview_content(self, title: str, content: str, 
                       template_type: str = "text", 
                       custom_data: Dict[str, Any] = None) -> str:
        """
        预览推送内容
        
        Args:
            title: 标题
            content: 内容
            template_type: 模板类型
            custom_data: 自定义数据
            
        Returns:
            str: 预览内容
        """
        try:
            template_str = self.templates.get(template_type, self.templates["text"])
            template = Template(template_str)
            
            data = {
                "title": title,
                "content": content,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            if custom_data:
                data.update(custom_data)
            
            return template.render(**data)
            
        except Exception as e:
            logger.error(f"内容预览失败: {str(e)}")
            return f"预览失败: {str(e)}"
    
    def add_template(self, name: str, template_str: str):
        """
        添加自定义模板
        
        Args:
            name: 模板名称
            template_str: 模板字符串
        """
        self.templates[name] = template_str
        logger.info(f"添加预览模板: {name}")
    
    def get_available_templates(self) -> List[str]:
        """
        获取可用模板列表
        
        Returns:
            List[str]: 模板名称列表
        """
        return list(self.templates.keys())
    
    def preview_for_platform(self, title: str, content: str, platform: str,
                           custom_data: Dict[str, Any] = None) -> str:
        """
        为特定平台预览内容
        
        Args:
            title: 标题
            content: 内容
            platform: 平台名称
            custom_data: 自定义数据
            
        Returns:
            str: 预览内容
        """
        # 根据平台选择合适的模板
        platform_templates = {
            "dingtalk": "markdown",
            "wechat": "markdown",
            "email": "email",
            "webhook": "text"
        }
        
        template_type = platform_templates.get(platform.lower(), "text")
        return self.preview_content(title, content, template_type, custom_data)

class StatisticsManager:
    """统计管理器"""
    
    def __init__(self, db_path: str = "push_statistics.db"):
        self.db_path = db_path
        self.init_database()
        self.cache = {}
        self.cache_timeout = 300  # 5分钟缓存
        self.last_cache_update = 0
        
    def init_database(self):
        """
        初始化数据库
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS push_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    status TEXT NOT NULL,
                    response_time REAL NOT NULL,
                    error_message TEXT,
                    timestamp DATETIME NOT NULL,
                    title TEXT,
                    content_length INTEGER
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON push_records(timestamp)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_platform ON push_records(platform)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON push_records(status)
            """)
    
    def record_push(self, result: PushResult, title: str = "", content_length: int = 0):
        """
        记录推送结果
        
        Args:
            result: 推送结果
            title: 推送标题
            content_length: 内容长度
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO push_records 
                    (task_id, platform, status, response_time, error_message, timestamp, title, content_length)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    result.task_id,
                    result.platform,
                    result.status.value,
                    result.response_time,
                    result.error_message,
                    result.timestamp,
                    title,
                    content_length
                ))
            
            # 清除缓存
            self.cache.clear()
            
        except Exception as e:
            logger.error(f"记录推送统计失败: {str(e)}")
    
    def get_statistics(self, days: int = 7) -> PushStatistics:
        """
        获取推送统计
        
        Args:
            days: 统计天数
            
        Returns:
            PushStatistics: 统计数据
        """
        cache_key = f"stats_{days}"
        current_time = time.time()
        
        # 检查缓存
        if (cache_key in self.cache and 
            current_time - self.last_cache_update < self.cache_timeout):
            return self.cache[cache_key]
        
        try:
            start_date = datetime.now() - timedelta(days=days)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # 基础统计
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_pushes,
                        SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_count,
                        AVG(response_time) as avg_response_time
                    FROM push_records 
                    WHERE timestamp >= ?
                """, (start_date,))
                
                row = cursor.fetchone()
                total_pushes = row['total_pushes'] or 0
                success_count = row['success_count'] or 0
                failed_count = row['failed_count'] or 0
                avg_response_time = row['avg_response_time'] or 0
                
                success_rate = (success_count / total_pushes * 100) if total_pushes > 0 else 0
                
                # 平台统计
                platform_cursor = conn.execute("""
                    SELECT 
                        platform,
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
                        AVG(response_time) as avg_time
                    FROM push_records 
                    WHERE timestamp >= ?
                    GROUP BY platform
                """, (start_date,))
                
                platform_stats = {}
                for row in platform_cursor:
                    platform_stats[row['platform']] = {
                        'total': row['total'],
                        'success': row['success'],
                        'success_rate': (row['success'] / row['total'] * 100) if row['total'] > 0 else 0,
                        'avg_response_time': row['avg_time'] or 0
                    }
                
                # 小时统计
                hourly_cursor = conn.execute("""
                    SELECT 
                        strftime('%H', timestamp) as hour,
                        COUNT(*) as count
                    FROM push_records 
                    WHERE timestamp >= ?
                    GROUP BY strftime('%H', timestamp)
                    ORDER BY hour
                """, (start_date,))
                
                hourly_stats = {f"{i:02d}": 0 for i in range(24)}
                for row in hourly_cursor:
                    hourly_stats[row['hour']] = row['count']
                
                # 日统计
                daily_cursor = conn.execute("""
                    SELECT 
                        DATE(timestamp) as date,
                        COUNT(*) as count
                    FROM push_records 
                    WHERE timestamp >= ?
                    GROUP BY DATE(timestamp)
                    ORDER BY date
                """, (start_date,))
                
                daily_stats = {}
                for row in daily_cursor:
                    daily_stats[row['date']] = row['count']
                
                # 创建统计对象
                stats = PushStatistics(
                    total_pushes=total_pushes,
                    success_count=success_count,
                    failed_count=failed_count,
                    success_rate=success_rate,
                    avg_response_time=avg_response_time,
                    platform_stats=platform_stats,
                    hourly_stats=hourly_stats,
                    daily_stats=daily_stats
                )
                
                # 更新缓存
                self.cache[cache_key] = stats
                self.last_cache_update = current_time
                
                return stats
                
        except Exception as e:
            logger.error(f"获取统计数据失败: {str(e)}")
            # 返回空统计
            return PushStatistics(
                total_pushes=0,
                success_count=0,
                failed_count=0,
                success_rate=0,
                avg_response_time=0,
                platform_stats={},
                hourly_stats={},
                daily_stats={}
            )
    
    def get_trend_data(self, days: int = 30) -> Dict[str, Any]:
        """
        获取趋势数据
        
        Args:
            days: 统计天数
            
        Returns:
            Dict: 趋势数据
        """
        try:
            start_date = datetime.now() - timedelta(days=days)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # 每日趋势
                cursor = conn.execute("""
                    SELECT 
                        DATE(timestamp) as date,
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
                        AVG(response_time) as avg_time
                    FROM push_records 
                    WHERE timestamp >= ?
                    GROUP BY DATE(timestamp)
                    ORDER BY date
                """, (start_date,))
                
                trend_data = {
                    'dates': [],
                    'total_counts': [],
                    'success_counts': [],
                    'success_rates': [],
                    'response_times': []
                }
                
                for row in cursor:
                    trend_data['dates'].append(row['date'])
                    trend_data['total_counts'].append(row['total'])
                    trend_data['success_counts'].append(row['success'])
                    
                    success_rate = (row['success'] / row['total'] * 100) if row['total'] > 0 else 0
                    trend_data['success_rates'].append(success_rate)
                    trend_data['response_times'].append(row['avg_time'] or 0)
                
                return trend_data
                
        except Exception as e:
            logger.error(f"获取趋势数据失败: {str(e)}")
            return {
                'dates': [],
                'total_counts': [],
                'success_counts': [],
                'success_rates': [],
                'response_times': []
            }
    
    def cleanup_old_records(self, days: int = 90):
        """
        清理旧记录
        
        Args:
            days: 保留天数
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    DELETE FROM push_records WHERE timestamp < ?
                """, (cutoff_date,))
                
                deleted_count = cursor.rowcount
                logger.info(f"清理旧记录: {deleted_count} 条")
                
                # 清除缓存
                self.cache.clear()
                
        except Exception as e:
            logger.error(f"清理旧记录失败: {str(e)}")

class WebInterfaceManager:
    """Web界面管理器"""
    
    def __init__(self, status_manager: RealTimeStatusManager,
                 preview_manager: ContentPreviewManager,
                 stats_manager: StatisticsManager):
        self.status_manager = status_manager
        self.preview_manager = preview_manager
        self.stats_manager = stats_manager
        
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        self.app.config['SECRET_KEY'] = 'push_system_secret_key'
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
        
        self._setup_routes()
        self._setup_socketio()
    
    def _setup_routes(self):
        """设置路由"""
        
        @self.app.route('/')
        def index():
            """主页"""
            return render_template('dashboard.html')
        
        @self.app.route('/api/tasks')
        def get_tasks():
            """获取任务列表"""
            limit = request.args.get('limit', 50, type=int)
            tasks = self.status_manager.get_recent_tasks(limit)
            
            return jsonify({
                'tasks': [asdict(task) for task in tasks]
            })
        
        @self.app.route('/api/task/<task_id>')
        def get_task(task_id):
            """获取任务详情"""
            task = self.status_manager.get_task(task_id)
            results = self.status_manager.get_task_results(task_id)
            
            if not task:
                return jsonify({'error': '任务不存在'}), 404
            
            return jsonify({
                'task': asdict(task),
                'results': [asdict(result) for result in results]
            })
        
        @self.app.route('/api/preview', methods=['POST'])
        def preview_content():
            """预览内容"""
            data = request.get_json()
            
            title = data.get('title', '')
            content = data.get('content', '')
            template_type = data.get('template_type', 'text')
            platform = data.get('platform', '')
            custom_data = data.get('custom_data', {})
            
            if platform:
                preview = self.preview_manager.preview_for_platform(
                    title, content, platform, custom_data
                )
            else:
                preview = self.preview_manager.preview_content(
                    title, content, template_type, custom_data
                )
            
            return jsonify({'preview': preview})
        
        @self.app.route('/api/statistics')
        def get_statistics():
            """获取统计数据"""
            days = request.args.get('days', 7, type=int)
            stats = self.stats_manager.get_statistics(days)
            
            return jsonify(asdict(stats))
        
        @self.app.route('/api/trends')
        def get_trends():
            """获取趋势数据"""
            days = request.args.get('days', 30, type=int)
            trends = self.stats_manager.get_trend_data(days)
            
            return jsonify(trends)
        
        @self.app.route('/api/charts/success_rate')
        def get_success_rate_chart():
            """获取成功率图表"""
            days = request.args.get('days', 7, type=int)
            trends = self.stats_manager.get_trend_data(days)
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=trends['dates'],
                y=trends['success_rates'],
                mode='lines+markers',
                name='成功率 (%)',
                line=dict(color='#28a745')
            ))
            
            fig.update_layout(
                title='推送成功率趋势',
                xaxis_title='日期',
                yaxis_title='成功率 (%)',
                hovermode='x unified'
            )
            
            return jsonify(plotly.utils.PlotlyJSONEncoder().encode(fig))
        
        @self.app.route('/api/charts/response_time')
        def get_response_time_chart():
            """获取响应时间图表"""
            days = request.args.get('days', 7, type=int)
            trends = self.stats_manager.get_trend_data(days)
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=trends['dates'],
                y=trends['response_times'],
                mode='lines+markers',
                name='响应时间 (秒)',
                line=dict(color='#007bff')
            ))
            
            fig.update_layout(
                title='平均响应时间趋势',
                xaxis_title='日期',
                yaxis_title='响应时间 (秒)',
                hovermode='x unified'
            )
            
            return jsonify(plotly.utils.PlotlyJSONEncoder().encode(fig))
        
        @self.app.route('/api/charts/platform_stats')
        def get_platform_stats_chart():
            """获取平台统计图表"""
            days = request.args.get('days', 7, type=int)
            stats = self.stats_manager.get_statistics(days)
            
            platforms = list(stats.platform_stats.keys())
            success_rates = [stats.platform_stats[p]['success_rate'] for p in platforms]
            
            fig = go.Figure(data=[
                go.Bar(x=platforms, y=success_rates, name='成功率 (%)')
            ])
            
            fig.update_layout(
                title='各平台推送成功率',
                xaxis_title='平台',
                yaxis_title='成功率 (%)',
                showlegend=False
            )
            
            return jsonify(plotly.utils.PlotlyJSONEncoder().encode(fig))
    
    def _setup_socketio(self):
        """设置SocketIO事件"""
        
        @self.socketio.on('connect')
        def handle_connect():
            """客户端连接"""
            logger.info(f"WebSocket客户端连接: {request.sid}")
            emit('connected', {'message': '连接成功'})
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            """客户端断开连接"""
            logger.info(f"WebSocket客户端断开: {request.sid}")
        
        @self.socketio.on('subscribe_status')
        def handle_subscribe_status():
            """订阅状态更新"""
            def status_callback(notification):
                self.socketio.emit('status_update', notification, room=request.sid)
            
            self.status_manager.subscribe(request.sid, status_callback)
            emit('subscribed', {'message': '已订阅状态更新'})
        
        @self.socketio.on('unsubscribe_status')
        def handle_unsubscribe_status():
            """取消订阅状态更新"""
            self.status_manager.unsubscribe(request.sid)
            emit('unsubscribed', {'message': '已取消订阅'})
    
    def run(self, host='127.0.0.1', port=5000, debug=False):
        """运行Web服务器"""
        logger.info(f"启动Web界面: http://{host}:{port}")
        self.socketio.run(self.app, host=host, port=port, debug=debug)

class UserExperienceOptimizer:
    """用户体验优化器主类"""
    
    def __init__(self, db_path: str = "push_statistics.db"):
        self.status_manager = RealTimeStatusManager()
        self.preview_manager = ContentPreviewManager()
        self.stats_manager = StatisticsManager(db_path)
        self.web_manager = WebInterfaceManager(
            self.status_manager, 
            self.preview_manager, 
            self.stats_manager
        )
        
        # 启动定期清理任务
        self._start_cleanup_task()
    
    def create_push_task(self, title: str, content: str, platforms: List[str]) -> str:
        """
        创建推送任务
        
        Args:
            title: 任务标题
            content: 任务内容
            platforms: 目标平台列表
            
        Returns:
            str: 任务ID
        """
        return self.status_manager.create_task(title, content, platforms)
    
    def update_task_status(self, task_id: str, status: PushStatus, 
                          current_step: str = "", error_message: str = ""):
        """
        更新任务状态
        
        Args:
            task_id: 任务ID
            status: 新状态
            current_step: 当前步骤描述
            error_message: 错误信息
        """
        self.status_manager.update_task_status(task_id, status, current_step, error_message)
    
    def record_push_result(self, result: PushResult, title: str = "", content_length: int = 0):
        """
        记录推送结果
        
        Args:
            result: 推送结果
            title: 推送标题
            content_length: 内容长度
        """
        self.status_manager.add_result(result)
        self.stats_manager.record_push(result, title, content_length)
    
    def preview_content(self, title: str, content: str, platform: str = "") -> str:
        """
        预览推送内容
        
        Args:
            title: 标题
            content: 内容
            platform: 平台名称
            
        Returns:
            str: 预览内容
        """
        if platform:
            return self.preview_manager.preview_for_platform(title, content, platform)
        else:
            return self.preview_manager.preview_content(title, content)
    
    def get_statistics(self, days: int = 7) -> PushStatistics:
        """
        获取推送统计
        
        Args:
            days: 统计天数
            
        Returns:
            PushStatistics: 统计数据
        """
        return self.stats_manager.get_statistics(days)
    
    def start_web_interface(self, host='127.0.0.1', port=5000, debug=False):
        """
        启动Web界面
        
        Args:
            host: 主机地址
            port: 端口号
            debug: 调试模式
        """
        self.web_manager.run(host, port, debug)
    
    def _start_cleanup_task(self):
        """
        启动定期清理任务
        """
        def cleanup_worker():
            while True:
                try:
                    # 每天清理一次旧记录
                    self.stats_manager.cleanup_old_records(90)
                    time.sleep(24 * 3600)  # 24小时
                except Exception as e:
                    logger.error(f"清理任务异常: {str(e)}")
                    time.sleep(3600)  # 1小时后重试
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
        logger.info("启动定期清理任务")
    
    def shutdown(self):
        """
        关闭优化器
        """
        logger.info("用户体验优化器已关闭")