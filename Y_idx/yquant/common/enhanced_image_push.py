"""增强的图片推送功能模块
支持批量推送、图片压缩优化、Base64编码、预览和缩略图生成
"""

import os
import base64
import hashlib
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Union
from PIL import Image, ImageOps
import io
from pathlib import Path
import logging
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# 配置日志
logger = logging.getLogger(__name__)

@dataclass
class ImageInfo:
    """图片信息数据类"""
    path: str
    filename: str
    size: int
    width: int
    height: int
    format: str
    created_time: str
    hash_md5: str
    compressed_size: Optional[int] = None
    thumbnail_path: Optional[str] = None
    base64_data: Optional[str] = None

@dataclass
class PushResult:
    """推送结果数据类"""
    success: bool
    image_path: str
    platform: str
    message: str
    push_time: str
    file_size: int
    error_details: Optional[str] = None

class EnhancedImagePush:
    """增强的图片推送类"""
    
    def __init__(self, config: Dict = None):
        """
        初始化增强图片推送
        
        Args:
            config: 配置字典，包含压缩质量、缩略图尺寸等参数
        """
        self.config = config or {}
        self.compression_quality = self.config.get('compression_quality', 85)
        self.thumbnail_size = self.config.get('thumbnail_size', (200, 200))
        self.max_file_size = self.config.get('max_file_size', 5 * 1024 * 1024)  # 5MB
        self.supported_formats = self.config.get('supported_formats', ['PNG', 'JPEG', 'JPG', 'GIF', 'BMP'])
        self.output_dir = self.config.get('output_dir', 'output/compressed')
        self.thumbnail_dir = self.config.get('thumbnail_dir', 'output/thumbnails')
        
        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.thumbnail_dir, exist_ok=True)
        
        # 推送历史记录
        self.push_history: List[PushResult] = []
        
    def get_image_info(self, image_path: str) -> Optional[ImageInfo]:
        """
        获取图片详细信息
        
        Args:
            image_path: 图片路径
            
        Returns:
            ImageInfo: 图片信息对象，失败返回None
        """
        try:
            if not os.path.exists(image_path):
                logger.error(f"图片文件不存在: {image_path}")
                return None
                
            with Image.open(image_path) as img:
                # 获取基本信息
                filename = os.path.basename(image_path)
                file_size = os.path.getsize(image_path)
                width, height = img.size
                img_format = img.format or 'UNKNOWN'
                
                # 获取创建时间
                created_time = datetime.fromtimestamp(
                    os.path.getctime(image_path)
                ).strftime('%Y-%m-%d %H:%M:%S')
                
                # 计算MD5哈希
                with open(image_path, 'rb') as f:
                    hash_md5 = hashlib.md5(f.read()).hexdigest()
                
                return ImageInfo(
                    path=image_path,
                    filename=filename,
                    size=file_size,
                    width=width,
                    height=height,
                    format=img_format,
                    created_time=created_time,
                    hash_md5=hash_md5
                )
                
        except Exception as e:
            logger.error(f"获取图片信息失败 {image_path}: {str(e)}")
            return None
    
    def compress_image(self, image_path: str, quality: int = None) -> Optional[str]:
        """
        压缩图片
        
        Args:
            image_path: 原图片路径
            quality: 压缩质量 (1-100)
            
        Returns:
            str: 压缩后图片路径，失败返回None
        """
        try:
            if not os.path.exists(image_path):
                logger.error(f"图片文件不存在: {image_path}")
                return None
                
            quality = quality or self.compression_quality
            filename = os.path.basename(image_path)
            name, ext = os.path.splitext(filename)
            compressed_filename = f"{name}_compressed{ext}"
            compressed_path = os.path.join(self.output_dir, compressed_filename)
            
            with Image.open(image_path) as img:
                # 转换为RGB模式（如果需要）
                if img.mode in ('RGBA', 'LA', 'P'):
                    # 创建白色背景
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                
                # 保存压缩图片
                img.save(compressed_path, 'JPEG', quality=quality, optimize=True)
                
            logger.info(f"图片压缩完成: {image_path} -> {compressed_path}")
            return compressed_path
            
        except Exception as e:
            logger.error(f"图片压缩失败 {image_path}: {str(e)}")
            return None
    
    def generate_thumbnail(self, image_path: str, size: Tuple[int, int] = None) -> Optional[str]:
        """
        生成缩略图
        
        Args:
            image_path: 原图片路径
            size: 缩略图尺寸 (width, height)
            
        Returns:
            str: 缩略图路径，失败返回None
        """
        try:
            if not os.path.exists(image_path):
                logger.error(f"图片文件不存在: {image_path}")
                return None
                
            size = size or self.thumbnail_size
            filename = os.path.basename(image_path)
            name, ext = os.path.splitext(filename)
            thumbnail_filename = f"{name}_thumb{ext}"
            thumbnail_path = os.path.join(self.thumbnail_dir, thumbnail_filename)
            
            with Image.open(image_path) as img:
                # 生成缩略图（保持宽高比）
                img.thumbnail(size, Image.Resampling.LANCZOS)
                
                # 如果是RGBA模式，转换为RGB
                if img.mode == 'RGBA':
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])
                    img = background
                
                img.save(thumbnail_path, 'JPEG', quality=90)
                
            logger.info(f"缩略图生成完成: {image_path} -> {thumbnail_path}")
            return thumbnail_path
            
        except Exception as e:
            logger.error(f"缩略图生成失败 {image_path}: {str(e)}")
            return None
    
    def image_to_base64(self, image_path: str, max_size: int = None) -> Optional[str]:
        """
        将图片转换为Base64编码
        
        Args:
            image_path: 图片路径
            max_size: 最大文件大小限制（字节）
            
        Returns:
            str: Base64编码字符串，失败返回None
        """
        try:
            if not os.path.exists(image_path):
                logger.error(f"图片文件不存在: {image_path}")
                return None
                
            file_size = os.path.getsize(image_path)
            max_size = max_size or self.max_file_size
            
            if file_size > max_size:
                logger.warning(f"图片文件过大 {file_size} > {max_size}，尝试压缩")
                # 尝试压缩图片
                compressed_path = self.compress_image(image_path, quality=70)
                if compressed_path and os.path.getsize(compressed_path) <= max_size:
                    image_path = compressed_path
                else:
                    logger.error(f"压缩后文件仍然过大: {image_path}")
                    return None
            
            with open(image_path, 'rb') as f:
                image_data = f.read()
                base64_data = base64.b64encode(image_data).decode('utf-8')
                
            logger.info(f"图片Base64编码完成: {image_path}")
            return base64_data
            
        except Exception as e:
            logger.error(f"图片Base64编码失败 {image_path}: {str(e)}")
            return None
    
    def process_image_batch(self, image_paths: List[str], 
                           enable_compression: bool = True,
                           enable_thumbnail: bool = True,
                           enable_base64: bool = False) -> List[ImageInfo]:
        """
        批量处理图片
        
        Args:
            image_paths: 图片路径列表
            enable_compression: 是否启用压缩
            enable_thumbnail: 是否生成缩略图
            enable_base64: 是否生成Base64编码
            
        Returns:
            List[ImageInfo]: 处理后的图片信息列表
        """
        processed_images = []
        
        def process_single_image(image_path: str) -> Optional[ImageInfo]:
            """处理单个图片"""
            try:
                # 获取基本信息
                image_info = self.get_image_info(image_path)
                if not image_info:
                    return None
                
                # 压缩图片
                if enable_compression:
                    compressed_path = self.compress_image(image_path)
                    if compressed_path:
                        image_info.compressed_size = os.path.getsize(compressed_path)
                
                # 生成缩略图
                if enable_thumbnail:
                    thumbnail_path = self.generate_thumbnail(image_path)
                    if thumbnail_path:
                        image_info.thumbnail_path = thumbnail_path
                
                # 生成Base64编码
                if enable_base64:
                    base64_data = self.image_to_base64(image_path)
                    if base64_data:
                        image_info.base64_data = base64_data
                
                return image_info
                
            except Exception as e:
                logger.error(f"处理图片失败 {image_path}: {str(e)}")
                return None
        
        # 使用线程池并行处理
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_path = {executor.submit(process_single_image, path): path 
                            for path in image_paths}
            
            for future in as_completed(future_to_path):
                result = future.result()
                if result:
                    processed_images.append(result)
        
        logger.info(f"批量处理完成，成功处理 {len(processed_images)}/{len(image_paths)} 张图片")
        return processed_images
    
    def create_image_summary(self, image_infos: List[ImageInfo]) -> str:
        """
        创建图片汇总信息
        
        Args:
            image_infos: 图片信息列表
            
        Returns:
            str: 格式化的汇总信息
        """
        if not image_infos:
            return "📊 **图片推送汇总**\n\n暂无图片信息"
        
        total_size = sum(info.size for info in image_infos)
        total_compressed_size = sum(info.compressed_size or 0 for info in image_infos)
        
        summary = f"""📊 **图片推送汇总**

📈 **统计信息**:
• 图片数量: {len(image_infos)} 张
• 总文件大小: {total_size:,} bytes ({total_size/1024/1024:.2f} MB)
• 压缩后大小: {total_compressed_size:,} bytes ({total_compressed_size/1024/1024:.2f} MB)
• 压缩率: {((total_size - total_compressed_size) / total_size * 100):.1f}%

📋 **图片列表**:
"""
        
        for i, info in enumerate(image_infos, 1):
            summary += f"\n{i}. **{info.filename}**\n"
            summary += f"   • 尺寸: {info.width}x{info.height}\n"
            summary += f"   • 格式: {info.format}\n"
            summary += f"   • 大小: {info.size:,} bytes\n"
            if info.compressed_size:
                summary += f"   • 压缩后: {info.compressed_size:,} bytes\n"
            summary += f"   • 创建时间: {info.created_time}\n"
        
        summary += f"\n⏰ **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return summary
    
    def record_push_result(self, result: PushResult):
        """
        记录推送结果
        
        Args:
            result: 推送结果
        """
        self.push_history.append(result)
        
        # 保持历史记录数量限制
        max_history = self.config.get('max_history_records', 1000)
        if len(self.push_history) > max_history:
            self.push_history = self.push_history[-max_history:]
    
    def get_push_statistics(self) -> Dict:
        """
        获取推送统计信息
        
        Returns:
            Dict: 统计信息字典
        """
        if not self.push_history:
            return {
                'total_pushes': 0,
                'success_rate': 0,
                'platforms': {},
                'total_file_size': 0,
                'average_file_size': 0
            }
        
        total_pushes = len(self.push_history)
        successful_pushes = sum(1 for r in self.push_history if r.success)
        success_rate = (successful_pushes / total_pushes) * 100
        
        # 按平台统计
        platforms = {}
        for result in self.push_history:
            platform = result.platform
            if platform not in platforms:
                platforms[platform] = {'total': 0, 'success': 0}
            platforms[platform]['total'] += 1
            if result.success:
                platforms[platform]['success'] += 1
        
        # 文件大小统计
        total_file_size = sum(r.file_size for r in self.push_history)
        average_file_size = total_file_size / total_pushes if total_pushes > 0 else 0
        
        return {
            'total_pushes': total_pushes,
            'successful_pushes': successful_pushes,
            'success_rate': success_rate,
            'platforms': platforms,
            'total_file_size': total_file_size,
            'average_file_size': average_file_size,
            'last_push_time': self.push_history[-1].push_time if self.push_history else None
        }
    
    def export_push_history(self, output_path: str = None) -> str:
        """
        导出推送历史记录
        
        Args:
            output_path: 输出文件路径
            
        Returns:
            str: 导出文件路径
        """
        if not output_path:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = f"push_history_{timestamp}.json"
        
        try:
            history_data = {
                'export_time': datetime.now().isoformat(),
                'total_records': len(self.push_history),
                'statistics': self.get_push_statistics(),
                'records': [asdict(result) for result in self.push_history]
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(history_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"推送历史记录导出完成: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"导出推送历史记录失败: {str(e)}")
            raise