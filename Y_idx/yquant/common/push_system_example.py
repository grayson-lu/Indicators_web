"""统一推送系统使用示例
演示如何使用统一推送系统的各种功能
"""

import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path

# 导入统一推送系统
from .unified_push_system import (
    UnifiedPushSystem,
    UnifiedPushRequest,
    PushMode,
    SystemPushStatus,
    create_push_system,
    quick_push
)

class PushSystemDemo:
    """推送系统演示类"""
    
    def __init__(self):
        """初始化演示"""
        self.system = None
        self.demo_images = [
            "demo_chart1.png",
            "demo_chart2.png",
            "demo_report.jpg"
        ]
    
    async def setup_system(self):
        """设置推送系统"""
        print("🚀 初始化统一推送系统...")
        
        # 创建系统实例
        self.system = create_push_system(
            config_path="notification_config.json",
            db_path="demo_push.db"
        )
        
        # 检查系统状态
        status = self.system.get_system_status()
        print(f"✅ 系统状态: {status['status']}")
        print(f"📊 组件状态: {status['components']}")
        
        return self.system
    
    async def demo_immediate_push(self):
        """演示立即推送"""
        print("\n📤 演示立即推送功能...")
        
        request = UnifiedPushRequest(
            title="📈 市场行情提醒",
            content="""当前市场概况：
• BTC价格: $45,230 (+2.3%)
• ETH价格: $3,120 (+1.8%)
• 总市值: $1.85T
• 恐慌贪婪指数: 65 (贪婪)

建议关注主流币种走势，注意风险控制。""",
            platforms=["dingtalk", "wechat"],
            message_type="markdown",
            priority="high",
            mode=PushMode.IMMEDIATE,
            images=self.demo_images[:2],  # 包含2张图片
            custom_data={
                "source": "market_monitor",
                "alert_type": "price_change",
                "threshold": 2.0
            }
        )
        
        # 预览推送内容
        print("👀 预览推送内容:")
        previews = self.system.preview_push(request)
        for platform, preview in previews.items():
            print(f"  {platform}: {preview[:100]}...")
        
        # 执行推送
        print("🚀 执行推送...")
        response = await self.system.push(request)
        
        # 显示结果
        self._print_push_result(response)
        
        return response
    
    async def demo_scheduled_push(self):
        """演示定时推送"""
        print("\n⏰ 演示定时推送功能...")
        
        # 设置5秒后推送
        scheduled_time = datetime.now() + timedelta(seconds=5)
        
        request = UnifiedPushRequest(
            title="📊 定时报告",
            content="这是一条定时推送的消息，将在指定时间发送。",
            platforms=["dingtalk"],
            priority="medium",
            mode=PushMode.SCHEDULED,
            scheduled_time=scheduled_time
        )
        
        print(f"⏳ 将在 {scheduled_time.strftime('%H:%M:%S')} 推送")
        
        response = await self.system.push(request)
        self._print_push_result(response)
        
        return response
    
    async def demo_batch_push(self):
        """演示批量推送"""
        print("\n📦 演示批量推送功能...")
        
        request = UnifiedPushRequest(
            title="🔄 批量通知",
            content="这是一条批量推送消息，将分批发送到多个平台。",
            platforms=["dingtalk", "wechat", "email", "webhook"],
            priority="low",
            mode=PushMode.BATCH,
            images=[self.demo_images[0]]  # 包含1张图片
        )
        
        response = await self.system.push(request)
        self._print_push_result(response)
        
        return response
    
    async def demo_smart_push(self):
        """演示智能推送"""
        print("\n🧠 演示智能推送功能...")
        
        request = UnifiedPushRequest(
            title="🤖 智能推送",
            content="系统将根据历史数据和当前状况智能选择最佳推送策略。",
            platforms=["dingtalk", "wechat"],
            priority="medium",
            mode=PushMode.SMART
        )
        
        response = await self.system.push(request)
        self._print_push_result(response)
        
        return response
    
    async def demo_image_push(self):
        """演示图片推送"""
        print("\n🖼️ 演示图片推送功能...")
        
        # 创建示例图片（如果不存在）
        await self._create_demo_images()
        
        request = UnifiedPushRequest(
            title="📸 图片推送测试",
            content="以下是系统生成的图表和报告图片：",
            platforms=["dingtalk", "wechat"],
            message_type="image",
            priority="medium",
            mode=PushMode.IMMEDIATE,
            images=self.demo_images
        )
        
        response = await self.system.push(request)
        self._print_push_result(response)
        
        return response
    
    async def demo_system_monitoring(self):
        """演示系统监控功能"""
        print("\n📊 演示系统监控功能...")
        
        # 获取系统状态
        status = self.system.get_system_status()
        print("🔍 系统状态:")
        print(f"  状态: {status['status']}")
        print(f"  活动任务: {status['active_tasks']}")
        print(f"  总请求数: {status['metrics']['total_requests']}")
        print(f"  成功请求: {status['metrics']['successful_requests']}")
        print(f"  失败请求: {status['metrics']['failed_requests']}")
        print(f"  平均响应时间: {status['metrics']['avg_response_time']:.2f}秒")
        
        # 获取活动任务
        active_tasks = self.system.get_active_tasks()
        if active_tasks:
            print("\n🏃 活动任务:")
            for task in active_tasks:
                print(f"  任务ID: {task['task_id'][:8]}...")
                print(f"  标题: {task['title']}")
                print(f"  平台: {', '.join(task['platforms'])}")
                print(f"  运行时间: {task['duration']:.1f}秒")
        else:
            print("\n✅ 当前无活动任务")
        
        # 获取统计数据
        stats = self.system.get_statistics(7)
        print("\n📈 推送统计 (最近7天):")
        push_stats = stats['push_statistics']
        print(f"  总推送数: {push_stats['total_pushes']}")
        print(f"  成功推送: {push_stats['successful_pushes']}")
        print(f"  失败推送: {push_stats['failed_pushes']}")
        print(f"  成功率: {push_stats['success_rate']:.1f}%")
        print(f"  平均响应时间: {push_stats['avg_response_time']:.2f}秒")
    
    async def demo_concurrent_push(self):
        """演示并发推送"""
        print("\n⚡ 演示并发推送功能...")
        
        # 创建多个并发推送任务
        tasks = []
        
        for i in range(3):
            request = UnifiedPushRequest(
                title=f"🔄 并发推送 #{i+1}",
                content=f"这是第 {i+1} 个并发推送任务，测试系统并发处理能力。",
                platforms=["dingtalk"],
                priority="medium",
                mode=PushMode.IMMEDIATE
            )
            
            task = self.system.push(request)
            tasks.append(task)
        
        # 等待所有任务完成
        print("🚀 启动3个并发推送任务...")
        responses = await asyncio.gather(*tasks)
        
        # 显示结果
        for i, response in enumerate(responses):
            print(f"\n📋 任务 #{i+1} 结果:")
            self._print_push_result(response, detailed=False)
    
    async def demo_error_handling(self):
        """演示错误处理"""
        print("\n❌ 演示错误处理功能...")
        
        # 测试无效平台
        request = UnifiedPushRequest(
            title="🚫 错误测试",
            content="测试推送到无效平台的错误处理。",
            platforms=["invalid_platform", "dingtalk"],
            priority="low",
            mode=PushMode.IMMEDIATE
        )
        
        response = await self.system.push(request)
        self._print_push_result(response)
        
        return response
    
    def _print_push_result(self, response, detailed=True):
        """打印推送结果"""
        status_emoji = {
            SystemPushStatus.SUCCESS: "✅",
            SystemPushStatus.PARTIAL_SUCCESS: "⚠️",
            SystemPushStatus.FAILED: "❌",
            SystemPushStatus.CANCELLED: "🚫"
        }
        
        emoji = status_emoji.get(response.status, "❓")
        
        print(f"\n{emoji} 推送结果:")
        print(f"  请求ID: {response.request_id[:8]}...")
        print(f"  状态: {response.status.value}")
        print(f"  成功率: {response.success_rate:.1f}%")
        print(f"  执行时间: {response.duration:.2f}秒")
        print(f"  成功/总数: {response.success_count}/{response.total_platforms}")
        
        if response.error_message:
            print(f"  错误信息: {response.error_message}")
        
        if response.warnings:
            print(f"  警告: {', '.join(response.warnings)}")
        
        if detailed and response.results:
            print("  详细结果:")
            for result in response.results:
                status_icon = "✅" if result.get('status') == 'success' else "❌"
                platform = result.get('platform', 'unknown')
                print(f"    {status_icon} {platform}")
                if result.get('error'):
                    print(f"      错误: {result['error']}")
    
    async def _create_demo_images(self):
        """创建演示图片（占位符）"""
        for image_path in self.demo_images:
            if not Path(image_path).exists():
                # 创建占位符文件
                with open(image_path, 'w') as f:
                    f.write(f"# 演示图片占位符: {image_path}\n")
                    f.write("# 实际使用时请替换为真实图片文件\n")
    
    async def cleanup(self):
        """清理资源"""
        print("\n🧹 清理演示资源...")
        
        # 删除演示图片
        for image_path in self.demo_images:
            if Path(image_path).exists():
                try:
                    os.remove(image_path)
                except Exception as e:
                    print(f"删除 {image_path} 失败: {e}")
        
        # 关闭系统
        if self.system:
            self.system.shutdown()
        
        print("✅ 清理完成")

async def run_full_demo():
    """运行完整演示"""
    print("🎯 统一推送系统完整功能演示")
    print("=" * 50)
    
    demo = PushSystemDemo()
    
    try:
        # 设置系统
        await demo.setup_system()
        
        # 运行各种演示
        await demo.demo_immediate_push()
        await asyncio.sleep(1)
        
        await demo.demo_scheduled_push()
        await asyncio.sleep(1)
        
        await demo.demo_batch_push()
        await asyncio.sleep(1)
        
        await demo.demo_smart_push()
        await asyncio.sleep(1)
        
        await demo.demo_image_push()
        await asyncio.sleep(1)
        
        await demo.demo_concurrent_push()
        await asyncio.sleep(1)
        
        await demo.demo_error_handling()
        await asyncio.sleep(1)
        
        # 系统监控
        await demo.demo_system_monitoring()
        
    except Exception as e:
        print(f"❌ 演示过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 清理资源
        await demo.cleanup()
    
    print("\n🎉 演示完成！")

async def run_quick_demo():
    """运行快速演示"""
    print("⚡ 快速推送演示")
    print("=" * 30)
    
    # 使用便捷函数快速推送
    response = await quick_push(
        title="⚡ 快速推送测试",
        content="这是使用便捷函数的快速推送测试。",
        platforms=["dingtalk"],
        priority="medium"
    )
    
    print(f"✅ 快速推送完成: {response.status.value}")
    print(f"📊 成功率: {response.success_rate:.1f}%")

def run_web_interface_demo():
    """运行Web界面演示"""
    print("🌐 启动Web管理界面演示")
    print("=" * 40)
    
    # 创建系统
    system = create_push_system()
    
    try:
        # 启动Web界面
        print("🚀 启动Web界面...")
        print("📱 访问 http://127.0.0.1:5000 查看管理界面")
        print("⏹️ 按 Ctrl+C 停止服务")
        
        system.start_web_interface(
            host='127.0.0.1',
            port=5000,
            debug=True
        )
        
    except KeyboardInterrupt:
        print("\n⏹️ 用户停止服务")
    except Exception as e:
        print(f"❌ Web界面启动失败: {str(e)}")
    finally:
        system.shutdown()
        print("✅ Web界面已关闭")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        
        if mode == "full":
            # 完整演示
            asyncio.run(run_full_demo())
        elif mode == "quick":
            # 快速演示
            asyncio.run(run_quick_demo())
        elif mode == "web":
            # Web界面演示
            run_web_interface_demo()
        else:
            print("❓ 未知模式，支持的模式:")
            print("  python push_system_example.py full   # 完整功能演示")
            print("  python push_system_example.py quick  # 快速推送演示")
            print("  python push_system_example.py web    # Web界面演示")
    else:
        # 默认运行快速演示
        print("🎯 运行默认快速演示 (使用 'full' 参数运行完整演示)")
        asyncio.run(run_quick_demo())