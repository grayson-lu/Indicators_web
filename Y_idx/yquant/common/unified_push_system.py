"""统一推送系统集成模块
整合所有推送优化功能，提供完整的推送解决方案
"""

import asyncio
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import logging
from pathlib import Path
import json
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback

# 导入各个优化模块
from .notification_base import UnifiedNotificationManager, NotificationPlatform, MessageType, NotificationLevel
from yquant.config.notification_config import NotificationConfig
from .enhanced_image_push import EnhancedImagePush, ImageInfo, PushResult as ImagePushResult
from .push_content_optimizer import PushContentOptimizer, MessagePriority, MessageType as ContentMessageType
from .push_management_enhanced import PushManagerEnhanced, PushStatus as ManagementPushStatus
from .platform_extensions import PlatformExtensionManager
from .user_experience_optimizer import (
    UserExperienceOptimizer, 
    PushStatus, 
    PushResult, 
    RealTimeStatusManager,
    ContentPreviewManager,
    StatisticsManager
)

# 配置日志
logger = logging.getLogger(__name__)

class SystemPushStatus(Enum):
    """系统推送状态枚举"""
    INITIALIZING = "initializing"
    READY = "ready"
    PROCESSING = "processing"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    MAINTENANCE = "maintenance"

class PushMode(Enum):
    """推送模式枚举"""
    IMMEDIATE = "immediate"  # 立即推送
    SCHEDULED = "scheduled"  # 定时推送
    BATCH = "batch"  # 批量推送
    SMART = "smart"  # 智能推送（根据历史数据优化时机）

@dataclass
class UnifiedPushRequest:
    """统一推送请求数据类"""
    title: str
    content: str
    platforms: List[str]
    message_type: str = "text"
    priority: str = "medium"
    mode: PushMode = PushMode.IMMEDIATE
    scheduled_time: Optional[datetime] = None
    images: List[str] = None
    custom_data: Dict[str, Any] = None
    retry_count: int = 3
    timeout: int = 30
    
    def __post_init__(self):
        if self.images is None:
            self.images = []
        if self.custom_data is None:
            self.custom_data = {}

@dataclass
class UnifiedPushResponse:
    """统一推送响应数据类"""
    request_id: str
    status: SystemPushStatus
    results: List[Dict[str, Any]]
    total_platforms: int
    success_count: int
    failed_count: int
    start_time: datetime
    end_time: Optional[datetime] = None
    error_message: str = ""
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
    
    @property
    def success_rate(self) -> float:
        """计算成功率"""
        if self.total_platforms == 0:
            return 0.0
        return (self.success_count / self.total_platforms) * 100
    
    @property
    def duration(self) -> float:
        """计算执行时长（秒）"""
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time).total_seconds()

class UnifiedPushSystem:
    """统一推送系统主类"""
    
    def __init__(self, config_path: str = None, db_path: str = "unified_push.db"):
        """
        初始化统一推送系统
        
        Args:
            config_path: 配置文件路径
            db_path: 数据库文件路径
        """
        self.config_path = config_path
        self.db_path = db_path
        self.status = SystemPushStatus.INITIALIZING
        
        # 初始化各个组件
        self._init_components()
        
        # 活动任务跟踪
        self.active_tasks: Dict[str, Dict[str, Any]] = {}
        self.task_lock = threading.RLock()
        
        # 线程池
        self.executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="PushWorker")
        
        # 系统监控
        self.system_metrics = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'avg_response_time': 0.0,
            'last_activity': None
        }
        
        self.status = SystemPushStatus.READY
        logger.info("统一推送系统初始化完成")
    
    def _init_components(self):
        """
        初始化各个组件
        """
        try:
            # 加载配置
            if self.config_path and Path(self.config_path).exists():
                self.config = NotificationConfig.load_from_file(self.config_path)
            else:
                self.config = NotificationConfig()
            
            # 初始化核心推送管理器
            self.notification_manager = UnifiedNotificationManager(self.config.get_unified_config())
            
            # 初始化图片推送增强
            self.image_push = EnhancedImagePush()
            
            # 初始化内容优化器
            self.content_optimizer = PushContentOptimizer()
            
            # 初始化推送管理增强
            self.push_manager = PushManagerEnhanced(self.db_path)
            
            # 初始化平台扩展
            self.platform_extensions = PlatformExtensionManager()
            
            # 初始化用户体验优化器
            self.ux_optimizer = UserExperienceOptimizer(self.db_path)
            
            logger.info("所有组件初始化完成")
            
        except Exception as e:
            logger.error(f"组件初始化失败: {str(e)}")
            self.status = SystemPushStatus.FAILED
            raise
    
    async def push(self, request: UnifiedPushRequest) -> UnifiedPushResponse:
        """
        执行统一推送
        
        Args:
            request: 推送请求
            
        Returns:
            UnifiedPushResponse: 推送响应
        """
        request_id = str(uuid.uuid4())
        start_time = datetime.now()
        
        # 更新系统指标
        self.system_metrics['total_requests'] += 1
        self.system_metrics['last_activity'] = start_time
        
        # 创建响应对象
        response = UnifiedPushResponse(
            request_id=request_id,
            status=SystemPushStatus.PROCESSING,
            results=[],
            total_platforms=len(request.platforms),
            success_count=0,
            failed_count=0,
            start_time=start_time
        )
        
        try:
            # 注册任务
            with self.task_lock:
                self.active_tasks[request_id] = {
                    'request': request,
                    'response': response,
                    'start_time': start_time
                }
            
            # 创建UX任务跟踪
            ux_task_id = self.ux_optimizer.create_push_task(
                request.title, 
                request.content, 
                request.platforms
            )
            
            # 根据推送模式处理
            if request.mode == PushMode.IMMEDIATE:
                await self._process_immediate_push(request, response, ux_task_id)
            elif request.mode == PushMode.SCHEDULED:
                await self._process_scheduled_push(request, response, ux_task_id)
            elif request.mode == PushMode.BATCH:
                await self._process_batch_push(request, response, ux_task_id)
            elif request.mode == PushMode.SMART:
                await self._process_smart_push(request, response, ux_task_id)
            
            # 计算最终状态
            response.end_time = datetime.now()
            
            if response.failed_count == 0:
                response.status = SystemPushStatus.SUCCESS
                self.system_metrics['successful_requests'] += 1
            elif response.success_count > 0:
                response.status = SystemPushStatus.PARTIAL_SUCCESS
                self.system_metrics['successful_requests'] += 1
            else:
                response.status = SystemPushStatus.FAILED
                self.system_metrics['failed_requests'] += 1
            
            # 更新平均响应时间
            self._update_avg_response_time(response.duration)
            
            # 更新UX状态
            if response.status == SystemPushStatus.SUCCESS:
                self.ux_optimizer.update_task_status(ux_task_id, PushStatus.SUCCESS)
            elif response.status == SystemPushStatus.PARTIAL_SUCCESS:
                self.ux_optimizer.update_task_status(
                    ux_task_id, 
                    PushStatus.SUCCESS, 
                    f"部分成功: {response.success_count}/{response.total_platforms}"
                )
            else:
                self.ux_optimizer.update_task_status(
                    ux_task_id, 
                    PushStatus.FAILED, 
                    error_message=response.error_message
                )
            
            logger.info(f"推送完成: {request_id}, 状态: {response.status.value}, "
                       f"成功率: {response.success_rate:.1f}%")
            
        except Exception as e:
            response.status = SystemPushStatus.FAILED
            response.error_message = str(e)
            response.end_time = datetime.now()
            self.system_metrics['failed_requests'] += 1
            
            logger.error(f"推送执行失败: {request_id}, 错误: {str(e)}")
            logger.error(traceback.format_exc())
            
        finally:
            # 清理任务
            with self.task_lock:
                if request_id in self.active_tasks:
                    del self.active_tasks[request_id]
        
        return response
    
    async def _process_immediate_push(self, request: UnifiedPushRequest, 
                                    response: UnifiedPushResponse, ux_task_id: str):
        """
        处理立即推送
        
        Args:
            request: 推送请求
            response: 推送响应
            ux_task_id: UX任务ID
        """
        self.ux_optimizer.update_task_status(ux_task_id, PushStatus.PROCESSING, "开始立即推送")
        
        # 优化推送内容
        optimized_content = await self._optimize_content(request)
        
        # 处理图片（如果有）
        image_results = []
        if request.images:
            self.ux_optimizer.update_task_status(ux_task_id, PushStatus.PROCESSING, "处理图片")
            image_results = await self._process_images(request.images, request.platforms)
        
        # 并发推送到各平台
        self.ux_optimizer.update_task_status(ux_task_id, PushStatus.PROCESSING, "推送到各平台")
        
        tasks = []
        for i, platform in enumerate(request.platforms):
            task = self._push_to_platform(
                platform, 
                optimized_content, 
                request, 
                image_results,
                ux_task_id,
                i + 1
            )
            tasks.append(task)
        
        # 等待所有推送完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                response.results.append({
                    'platform': request.platforms[i],
                    'status': 'failed',
                    'error': str(result)
                })
                response.failed_count += 1
            else:
                response.results.append(result)
                if result.get('status') == 'success':
                    response.success_count += 1
                else:
                    response.failed_count += 1
    
    async def _process_scheduled_push(self, request: UnifiedPushRequest, 
                                    response: UnifiedPushResponse, ux_task_id: str):
        """
        处理定时推送
        
        Args:
            request: 推送请求
            response: 推送响应
            ux_task_id: UX任务ID
        """
        if not request.scheduled_time:
            raise ValueError("定时推送需要指定 scheduled_time")
        
        self.ux_optimizer.update_task_status(
            ux_task_id, 
            PushStatus.PROCESSING, 
            f"等待定时推送: {request.scheduled_time}"
        )
        
        # 计算等待时间
        now = datetime.now()
        if request.scheduled_time <= now:
            # 立即执行
            await self._process_immediate_push(request, response, ux_task_id)
        else:
            # 等待到指定时间
            wait_seconds = (request.scheduled_time - now).total_seconds()
            await asyncio.sleep(wait_seconds)
            await self._process_immediate_push(request, response, ux_task_id)
    
    async def _process_batch_push(self, request: UnifiedPushRequest, 
                                response: UnifiedPushResponse, ux_task_id: str):
        """
        处理批量推送
        
        Args:
            request: 推送请求
            response: 推送响应
            ux_task_id: UX任务ID
        """
        self.ux_optimizer.update_task_status(ux_task_id, PushStatus.PROCESSING, "批量推送处理")
        
        # 批量推送：分组处理，避免同时推送过多
        batch_size = 3  # 每批处理3个平台
        
        for i in range(0, len(request.platforms), batch_size):
            batch_platforms = request.platforms[i:i + batch_size]
            
            # 创建批次请求
            batch_request = UnifiedPushRequest(
                title=request.title,
                content=request.content,
                platforms=batch_platforms,
                message_type=request.message_type,
                priority=request.priority,
                mode=PushMode.IMMEDIATE,
                images=request.images,
                custom_data=request.custom_data
            )
            
            # 处理批次
            batch_response = UnifiedPushResponse(
                request_id=f"{response.request_id}_batch_{i//batch_size + 1}",
                status=SystemPushStatus.PROCESSING,
                results=[],
                total_platforms=len(batch_platforms),
                success_count=0,
                failed_count=0,
                start_time=datetime.now()
            )
            
            await self._process_immediate_push(batch_request, batch_response, ux_task_id)
            
            # 合并结果
            response.results.extend(batch_response.results)
            response.success_count += batch_response.success_count
            response.failed_count += batch_response.failed_count
            
            # 批次间隔
            if i + batch_size < len(request.platforms):
                await asyncio.sleep(1)  # 1秒间隔
    
    async def _process_smart_push(self, request: UnifiedPushRequest, 
                                response: UnifiedPushResponse, ux_task_id: str):
        """
        处理智能推送
        
        Args:
            request: 推送请求
            response: 推送响应
            ux_task_id: UX任务ID
        """
        self.ux_optimizer.update_task_status(ux_task_id, PushStatus.PROCESSING, "智能推送分析")
        
        # 获取历史统计数据
        stats = self.ux_optimizer.get_statistics(7)  # 最近7天
        
        # 根据历史数据优化推送策略
        current_hour = datetime.now().hour
        
        # 检查当前时间段的历史成功率
        hour_key = f"{current_hour:02d}"
        hour_activity = stats.hourly_stats.get(hour_key, 0)
        
        # 如果当前时间段活动较少，可能成功率更高
        if hour_activity < 10:  # 活动较少的时间段
            # 立即推送
            await self._process_immediate_push(request, response, ux_task_id)
        else:
            # 使用批量推送减少系统负载
            await self._process_batch_push(request, response, ux_task_id)
    
    async def _optimize_content(self, request: UnifiedPushRequest) -> Dict[str, str]:
        """
        优化推送内容
        
        Args:
            request: 推送请求
            
        Returns:
            Dict[str, str]: 优化后的内容
        """
        try:
            # 根据消息类型和优先级优化内容
            priority = MessagePriority(request.priority) if request.priority in [p.value for p in MessagePriority] else MessagePriority.MEDIUM
            msg_type = ContentMessageType(request.message_type) if request.message_type in [t.value for t in ContentMessageType] else ContentMessageType.TEXT
            
            optimized = self.content_optimizer.create_message(
                title=request.title,
                content=request.content,
                msg_type=msg_type,
                priority=priority,
                custom_data=request.custom_data
            )
            
            return {
                'title': optimized.get('title', request.title),
                'content': optimized.get('content', request.content),
                'formatted_content': optimized.get('formatted_content', request.content)
            }
            
        except Exception as e:
            logger.warning(f"内容优化失败，使用原始内容: {str(e)}")
            return {
                'title': request.title,
                'content': request.content,
                'formatted_content': request.content
            }
    
    async def _process_images(self, image_paths: List[str], platforms: List[str]) -> List[Dict[str, Any]]:
        """
        处理图片
        
        Args:
            image_paths: 图片路径列表
            platforms: 目标平台列表
            
        Returns:
            List[Dict[str, Any]]: 图片处理结果
        """
        try:
            # 批量处理图片
            results = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self.image_push.batch_push_images,
                image_paths,
                platforms
            )
            
            return [asdict(result) for result in results]
            
        except Exception as e:
            logger.error(f"图片处理失败: {str(e)}")
            return []
    
    async def _push_to_platform(self, platform: str, content: Dict[str, str], 
                              request: UnifiedPushRequest, image_results: List[Dict[str, Any]],
                              ux_task_id: str, step_num: int) -> Dict[str, Any]:
        """
        推送到指定平台
        
        Args:
            platform: 平台名称
            content: 优化后的内容
            request: 原始请求
            image_results: 图片处理结果
            ux_task_id: UX任务ID
            step_num: 步骤编号
            
        Returns:
            Dict[str, Any]: 推送结果
        """
        start_time = time.time()
        
        try:
            # 更新进度
            self.ux_optimizer.ux_optimizer.status_manager.update_task_progress(
                ux_task_id, step_num, f"推送到 {platform}"
            )
            
            # 选择推送方法
            if platform.lower() in ['dingtalk', 'wechat']:
                # 使用核心推送管理器
                result = await self._push_via_core_manager(platform, content, request)
            else:
                # 使用平台扩展
                result = await self._push_via_extensions(platform, content, request)
            
            # 记录成功结果
            response_time = time.time() - start_time
            
            push_result = PushResult(
                task_id=ux_task_id,
                platform=platform,
                status=PushStatus.SUCCESS,
                response_time=response_time
            )
            
            self.ux_optimizer.record_push_result(
                push_result, 
                request.title, 
                len(request.content)
            )
            
            return {
                'platform': platform,
                'status': 'success',
                'response_time': response_time,
                'result': result
            }
            
        except Exception as e:
            # 记录失败结果
            response_time = time.time() - start_time
            error_msg = str(e)
            
            push_result = PushResult(
                task_id=ux_task_id,
                platform=platform,
                status=PushStatus.FAILED,
                response_time=response_time,
                error_message=error_msg
            )
            
            self.ux_optimizer.record_push_result(
                push_result, 
                request.title, 
                len(request.content)
            )
            
            logger.error(f"推送到 {platform} 失败: {error_msg}")
            
            return {
                'platform': platform,
                'status': 'failed',
                'response_time': response_time,
                'error': error_msg
            }
    
    async def _push_via_core_manager(self, platform: str, content: Dict[str, str], 
                                   request: UnifiedPushRequest) -> Dict[str, Any]:
        """
        通过核心推送管理器推送
        
        Args:
            platform: 平台名称
            content: 内容
            request: 请求
            
        Returns:
            Dict[str, Any]: 推送结果
        """
        # 转换平台名称
        platform_map = {
            'dingtalk': NotificationPlatform.DINGTALK,
            'wechat': NotificationPlatform.WECHAT_WORK,
            'wechat_work': NotificationPlatform.WECHAT_WORK,
            'wecom': NotificationPlatform.WECHAT_WORK,
            'feishu': NotificationPlatform.FEISHU
        }
        
        target_platform = platform_map.get(platform.lower())
        if not target_platform:
            raise ValueError(f"不支持的平台: {platform}")
        
        # 确定消息类型
        if request.message_type == 'markdown':
            msg_type = MessageType.MARKDOWN
        elif request.message_type == 'image':
            msg_type = MessageType.IMAGE
        else:
            msg_type = MessageType.TEXT
        
        # 执行推送
        result = await asyncio.get_event_loop().run_in_executor(
            self.executor,
            self.notification_manager.send_to_platform,
            target_platform,
            msg_type,
            content['formatted_content']
        )
        
        return {'core_result': result}
    
    async def _push_via_extensions(self, platform: str, content: Dict[str, str], 
                                 request: UnifiedPushRequest) -> Dict[str, Any]:
        """
        通过平台扩展推送
        
        Args:
            platform: 平台名称
            content: 内容
            request: 请求
            
        Returns:
            Dict[str, Any]: 推送结果
        """
        # 执行扩展平台推送
        result = await asyncio.get_event_loop().run_in_executor(
            self.executor,
            self.platform_extensions.broadcast_message,
            content['title'],
            content['formatted_content'],
            [platform]
        )
        
        return {'extension_result': result}
    
    def _update_avg_response_time(self, duration: float):
        """
        更新平均响应时间
        
        Args:
            duration: 本次响应时间
        """
        current_avg = self.system_metrics['avg_response_time']
        total_requests = self.system_metrics['total_requests']
        
        # 计算新的平均值
        new_avg = ((current_avg * (total_requests - 1)) + duration) / total_requests
        self.system_metrics['avg_response_time'] = new_avg
    
    def get_system_status(self) -> Dict[str, Any]:
        """
        获取系统状态
        
        Returns:
            Dict[str, Any]: 系统状态信息
        """
        with self.task_lock:
            active_task_count = len(self.active_tasks)
        
        return {
            'status': self.status.value,
            'active_tasks': active_task_count,
            'metrics': self.system_metrics.copy(),
            'components': {
                'notification_manager': bool(self.notification_manager),
                'image_push': bool(self.image_push),
                'content_optimizer': bool(self.content_optimizer),
                'push_manager': bool(self.push_manager),
                'platform_extensions': bool(self.platform_extensions),
                'ux_optimizer': bool(self.ux_optimizer)
            }
        }
    
    def get_active_tasks(self) -> List[Dict[str, Any]]:
        """
        获取活动任务列表
        
        Returns:
            List[Dict[str, Any]]: 活动任务信息
        """
        with self.task_lock:
            tasks = []
            for task_id, task_info in self.active_tasks.items():
                tasks.append({
                    'task_id': task_id,
                    'title': task_info['request'].title,
                    'platforms': task_info['request'].platforms,
                    'start_time': task_info['start_time'],
                    'duration': (datetime.now() - task_info['start_time']).total_seconds()
                })
            return tasks
    
    def preview_push(self, request: UnifiedPushRequest) -> Dict[str, str]:
        """
        预览推送内容
        
        Args:
            request: 推送请求
            
        Returns:
            Dict[str, str]: 各平台预览内容
        """
        previews = {}
        
        for platform in request.platforms:
            try:
                preview = self.ux_optimizer.preview_content(
                    request.title, 
                    request.content, 
                    platform
                )
                previews[platform] = preview
            except Exception as e:
                previews[platform] = f"预览失败: {str(e)}"
        
        return previews
    
    def get_statistics(self, days: int = 7) -> Dict[str, Any]:
        """
        获取推送统计
        
        Args:
            days: 统计天数
            
        Returns:
            Dict[str, Any]: 统计数据
        """
        stats = self.ux_optimizer.get_statistics(days)
        
        return {
            'system_metrics': self.system_metrics.copy(),
            'push_statistics': asdict(stats)
        }
    
    def start_web_interface(self, host='127.0.0.1', port=5000, debug=False):
        """
        启动Web管理界面
        
        Args:
            host: 主机地址
            port: 端口号
            debug: 调试模式
        """
        logger.info(f"启动统一推送系统Web界面: http://{host}:{port}")
        self.ux_optimizer.start_web_interface(host, port, debug)
    
    def shutdown(self):
        """
        关闭系统
        """
        logger.info("正在关闭统一推送系统...")
        
        self.status = SystemPushStatus.MAINTENANCE
        
        # 等待活动任务完成
        with self.task_lock:
            if self.active_tasks:
                logger.info(f"等待 {len(self.active_tasks)} 个活动任务完成...")
        
        # 关闭线程池
        self.executor.shutdown(wait=True)
        
        # 关闭各组件
        if hasattr(self, 'ux_optimizer'):
            self.ux_optimizer.shutdown()
        
        logger.info("统一推送系统已关闭")

# 便捷函数
def create_push_system(config_path: str = None, db_path: str = "unified_push.db") -> UnifiedPushSystem:
    """
    创建统一推送系统实例
    
    Args:
        config_path: 配置文件路径
        db_path: 数据库文件路径
        
    Returns:
        UnifiedPushSystem: 系统实例
    """
    return UnifiedPushSystem(config_path, db_path)

async def quick_push(title: str, content: str, platforms: List[str], 
                    images: List[str] = None, priority: str = "medium") -> UnifiedPushResponse:
    """
    快速推送函数
    
    Args:
        title: 标题
        content: 内容
        platforms: 目标平台
        images: 图片列表
        priority: 优先级
        
    Returns:
        UnifiedPushResponse: 推送结果
    """
    system = create_push_system()
    
    request = UnifiedPushRequest(
        title=title,
        content=content,
        platforms=platforms,
        images=images or [],
        priority=priority
    )
    
    try:
        return await system.push(request)
    finally:
        system.shutdown()

if __name__ == "__main__":
    # 示例用法
    async def main():
        # 创建推送系统
        system = create_push_system()
        
        # 创建推送请求
        request = UnifiedPushRequest(
            title="系统通知",
            content="这是一条测试消息",
            platforms=["dingtalk", "wechat"],
            priority="high",
            mode=PushMode.IMMEDIATE
        )
        
        # 预览内容
        previews = system.preview_push(request)
        print("预览内容:", previews)
        
        # 执行推送
        response = await system.push(request)
        print(f"推送结果: {response.status.value}, 成功率: {response.success_rate:.1f}%")
        
        # 获取统计
        stats = system.get_statistics()
        print("系统统计:", stats)
        
        # 关闭系统
        system.shutdown()
    
    # 运行示例
    asyncio.run(main())
