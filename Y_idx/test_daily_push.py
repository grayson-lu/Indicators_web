#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试企业微信每日推送模块
"""

import os
import sys
import time
import json
import logging
from datetime import datetime
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from daily_wechat_push import DailyWechatPushSystem, DailyMarketDataCollector, RichContentGenerator

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_data_collector():
    """测试数据收集器"""
    print("🧪 测试数据收集器...")
    
    try:
        collector = DailyMarketDataCollector()
        
        # 测试各个数据收集方法
        print("📊 测试Y指数数据收集...")
        y_data = collector.get_y_index_data()
        print(f"Y指数数据: {y_data}")
        
        print("😊 测试市场情绪数据收集...")
        sentiment_data = collector.get_market_sentiment()
        print(f"市场情绪数据: {sentiment_data}")
        
        print("📈 测试市场宽度数据收集...")
        breadth_data = collector.get_market_breadth()
        print(f"市场宽度数据: {breadth_data}")
        
        print("⛓️ 测试链上指标数据收集...")
        chain_data = collector.get_chain_metrics()
        print(f"链上指标数据: {chain_data}")
        
        print("📊 测试波动率数据收集...")
        vol_data = collector.get_volatility_data()
        print(f"波动率数据: {vol_data}")
        
        print("🔄 测试完整数据收集...")
        all_data = collector.collect_all_data()
        print(f"完整数据: {json.dumps(all_data, ensure_ascii=False, indent=2)}")
        
        return True
        
    except Exception as e:
        print(f"❌ 数据收集器测试失败: {e}")
        return False

def test_content_generator():
    """测试内容生成器"""
    print("\n🧪 测试内容生成器...")
    
    try:
        generator = RichContentGenerator()
        
        # 测试百分比格式化
        print("📊 测试百分比格式化...")
        print(f"上涨5.67%: {generator.format_percentage(5.67)}")
        print(f"下跌-3.21%: {generator.format_percentage(-3.21)}")
        print(f"持平0%: {generator.format_percentage(0)}")
        
        # 测试情绪表情
        print("😊 测试情绪表情...")
        print(f"恐慌: {generator.get_sentiment_emoji('恐慌')}")
        print(f"贪婪: {generator.get_sentiment_emoji('贪婪')}")
        print(f"中性: {generator.get_sentiment_emoji('中性')}")
        
        # 测试报告生成
        print("📝 测试报告生成...")
        test_data = {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "status": "success",
            "y_index": {
                "current_value": 123.45,
                "change_1d": 2.34,
                "change_7d": 5.67,
                "change_30d": -1.23,
                "date": "2024-01-01"
            },
            "sentiment": {
                "fear_greed_index": 65.0,
                "sentiment_level": "贪婪",
                "extreme_coins_ratio": 12.34,
                "ahp999_index": 1.234
            },
            "breadth": {
                "new_high_ratio": 8.76,
                "new_low_ratio": 3.21,
                "advance_decline_ratio": 1.85,
                "ad_percentage": 64.7
            },
            "chain": {
                "mvrv_ratio": 2.85,
                "stablecoin_supply": 123456789,
                "exchange_netflow": 5678901,
                "funding_rate_avg": 0.0156
            },
            "volatility": {
                "volatility_30d": 65.4,
                "volatility_7d": 72.1,
                "market_liquidity": 8.5
            }
        }
        
        markdown_content = generator.generate_markdown_report(test_data)
        print("生成的Markdown内容:")
        print("-" * 50)
        print(markdown_content)
        print("-" * 50)
        
        return True
        
    except Exception as e:
        print(f"❌ 内容生成器测试失败: {e}")
        return False

def test_push_system(webhook_url=None):
    """测试推送系统"""
    print("\n🧪 测试推送系统...")
    
    try:
        if not webhook_url:
            webhook_url = input("请输入企业微信Webhook地址 (留空跳过推送测试): ").strip()
        
        if not webhook_url:
            print("⚠️ 跳过推送测试")
            return True
        
        # 初始化推送系统
        print("🔧 初始化推送系统...")
        push_system = DailyWechatPushSystem(webhook_url)
        
        # 测试连接
        print("🔗 测试连接...")
        connection_test = push_system.test_connection()
        print(f"连接测试结果: {'✅ 成功' if connection_test else '❌ 失败'}")
        
        if not connection_test:
            return False
        
        # 测试简单文本推送
        print("📨 测试简单文本推送...")
        text_result = push_system.send_simple_text("🧪 企业微信推送系统测试消息\n测试时间: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        print(f"文本推送结果: {'✅ 成功' if text_result.success else '❌ 失败'} - {text_result.message}")
        
        # 测试Markdown推送
        print("📝 测试Markdown推送...")
        md_content = """## 🧪 测试Markdown消息

**加粗文本** *斜体文本* ~~删除线~~

- 列表项1
- 列表项2
- 列表项3

> 引用内容

[链接文字](https://example.com)

测试时间: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        md_result = push_system.send_markdown(md_content)
        print(f"Markdown推送结果: {'✅ 成功' if md_result.success else '❌ 失败'} - {md_result.message}")
        
        # 测试完整报告推送
        print("📊 测试完整报告推送...")
        report_result = push_system.send_daily_report()
        print(f"报告推送结果: {'✅ 成功' if report_result.success else '❌ 失败'} - {report_result.message}")
        
        return text_result.success or md_result.success or report_result.success
        
    except Exception as e:
        print(f"❌ 推送系统测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_error_handling():
    """测试错误处理"""
    print("\n🧪 测试错误处理...")
    
    try:
        # 测试无效Webhook
        print("🔗 测试无效Webhook...")
        try:
            push_system = DailyWechatPushSystem("https://invalid-webhook-url.com")
            result = push_system.test_connection()
            print(f"无效Webhook测试结果: {'✅ 正确处理' if not result else '❌ 未正确处理'}")
        except Exception as e:
            print(f"无效Webhook异常处理: {e}")
        
        # 测试数据缺失
        print("📊 测试数据缺失处理...")
        collector = DailyMarketDataCollector()
        
        # 模拟数据文件不存在
        original_dir = collector.data_dir
        collector.data_dir = Path("non_existent_dir")
        
        result = collector.collect_all_data()
        print(f"数据缺失处理结果: {'✅ 正确处理' if result.get('status') == 'success' else '❌ 处理异常'}")
        
        # 恢复原始目录
        collector.data_dir = original_dir
        
        return True
        
    except Exception as e:
        print(f"❌ 错误处理测试失败: {e}")
        return False

def test_performance():
    """测试性能"""
    print("\n🧪 测试性能...")
    
    try:
        collector = DailyMarketDataCollector()
        generator = RichContentGenerator()
        
        # 测试数据收集性能
        print("📊 测试数据收集性能...")
        start_time = time.time()
        data = collector.collect_all_data()
        collect_time = time.time() - start_time
        print(f"数据收集耗时: {collect_time:.3f}秒")
        
        # 测试内容生成性能
        print("📝 测试内容生成性能...")
        start_time = time.time()
        content = generator.generate_markdown_report(data)
        generate_time = time.time() - start_time
        print(f"内容生成耗时: {generate_time:.3f}秒")
        print(f"生成内容长度: {len(content)} 字符")
        
        # 性能评估
        total_time = collect_time + generate_time
        print(f"总耗时: {total_time:.3f}秒")
        
        if total_time < 5.0:
            print("✅ 性能优秀 (< 5秒)")
        elif total_time < 10.0:
            print("✅ 性能良好 (< 10秒)")
        else:
            print("⚠️ 性能需要优化 (> 10秒)")
        
        return True
        
    except Exception as e:
        print(f"❌ 性能测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 开始企业微信每日推送系统测试")
    print("=" * 60)
    
    test_results = {}
    
    # 运行所有测试
    test_results['数据收集器'] = test_data_collector()
    test_results['内容生成器'] = test_content_generator()
    
    # 询问是否进行推送测试
    webhook_url = None
    do_push_test = input("\n是否进行推送测试? (y/n): ").lower().strip() == 'y'
    if do_push_test:
        test_results['推送系统'] = test_push_system()
    else:
        test_results['推送系统'] = None
        print("⚠️ 跳过推送测试")
    
    test_results['错误处理'] = test_error_handling()
    test_results['性能测试'] = test_performance()
    
    # 显示测试结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    
    for test_name, result in test_results.items():
        if result is None:
            status = "⚠️ 跳过"
        elif result:
            status = "✅ 通过"
        else:
            status = "❌ 失败"
        
        print(f"{test_name:12} {status}")
    
    # 总体评估
    passed_tests = sum(1 for r in test_results.values() if r is True)
    total_tests = sum(1 for r in test_results.values() if r is not None)
    
    print(f"\n总体: {passed_tests}/{total_tests} 测试通过")
    
    if passed_tests == total_tests:
        print("🎉 所有测试通过！系统运行正常")
        return 0
    else:
        print("⚠️ 部分测试失败，请检查相关配置和数据")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)