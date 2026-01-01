#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最终数据状态报告生成器
汇总所有数据分析和修复结果，生成综合状态报告
"""

import os
import json
from datetime import datetime
import pandas as pd

def load_analysis_reports():
    """
    加载所有分析报告
    
    Returns:
        dict: 所有报告数据
    """
    reports = {}
    
    # 加载基础分析报告
    if os.path.exists('data_analysis_report.json'):
        with open('data_analysis_report.json', 'r', encoding='utf-8') as f:
            reports['basic_analysis'] = json.load(f)
    
    # 加载问题分析报告
    if os.path.exists('data_issues_report.json'):
        with open('data_issues_report.json', 'r', encoding='utf-8') as f:
            reports['issues_analysis'] = json.load(f)
    
    # 加载修复报告
    if os.path.exists('data_repair_report.json'):
        with open('data_repair_report.json', 'r', encoding='utf-8') as f:
            reports['repair_report'] = json.load(f)
    
    return reports

def analyze_current_data_status():
    """
    分析当前数据状态
    
    Returns:
        dict: 当前状态分析
    """
    data_dir = 'data'
    if not os.path.exists(data_dir):
        return {'error': 'data目录不存在'}
    
    import glob
    csv_files = glob.glob(os.path.join(data_dir, '*.csv'))
    
    current_status = {
        'total_files': len(csv_files),
        'files_by_category': {
            'core_indicators': [],  # 核心指标
            'market_metrics': [],   # 市场指标
            'technical_indicators': [],  # 技术指标
            'other_data': []        # 其他数据
        },
        'data_freshness': {},
        'file_sizes': {},
        'row_counts': {}
    }
    
    # 文件分类
    core_files = ['Y_idx.csv', 'mvrv_indicator.csv', 'fear_greed_index.csv']
    market_files = ['altcoin_index.csv', 'market_breadth_index.csv', 'stablecoin_supply.csv']
    technical_files = ['ahr999.csv', 'volatility_index.csv', 'up_down_ratio.csv']
    
    for file_path in csv_files:
        file_name = os.path.basename(file_path)
        
        # 分类
        if file_name in core_files:
            current_status['files_by_category']['core_indicators'].append(file_name)
        elif file_name in market_files:
            current_status['files_by_category']['market_metrics'].append(file_name)
        elif file_name in technical_files:
            current_status['files_by_category']['technical_indicators'].append(file_name)
        else:
            current_status['files_by_category']['other_data'].append(file_name)
        
        # 获取文件信息
        try:
            file_stat = os.stat(file_path)
            current_status['file_sizes'][file_name] = round(file_stat.st_size / 1024, 2)  # KB
            current_status['data_freshness'][file_name] = datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            # 获取行数
            df = pd.read_csv(file_path)
            current_status['row_counts'][file_name] = len(df)
            
        except Exception as e:
            current_status['file_sizes'][file_name] = 'ERROR'
            current_status['data_freshness'][file_name] = 'ERROR'
            current_status['row_counts'][file_name] = 'ERROR'
    
    return current_status

def generate_final_report():
    """
    生成最终综合报告
    
    Returns:
        dict: 最终报告
    """
    # 加载所有报告
    reports = load_analysis_reports()
    
    # 分析当前状态
    current_status = analyze_current_data_status()
    
    # 生成综合报告
    final_report = {
        'report_metadata': {
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'report_version': '1.0',
            'analysis_scope': 'Complete data integrity analysis'
        },
        'executive_summary': {},
        'current_data_status': current_status,
        'historical_analysis': reports.get('basic_analysis', {}),
        'identified_issues': reports.get('issues_analysis', {}),
        'repair_actions': reports.get('repair_report', {}),
        'recommendations': [],
        'action_items': []
    }
    
    # 生成执行摘要
    exec_summary = {
        'total_data_files': current_status.get('total_files', 0),
        'core_indicators_count': len(current_status.get('files_by_category', {}).get('core_indicators', [])),
        'data_health_status': 'GOOD',  # 默认状态
        'critical_issues_found': 0,
        'issues_resolved': 0,
        'data_coverage_days': 0,
        'last_update': None
    }
    
    # 从历史分析中提取信息
    if 'basic_analysis' in reports and 'summary' in reports['basic_analysis']:
        basic_summary = reports['basic_analysis']['summary']
        exec_summary['data_coverage_days'] = (datetime.strptime(basic_summary.get('newest_data', '2025-01-01'), '%Y-%m-%d') - 
                                            datetime.strptime(basic_summary.get('oldest_data', '2025-01-01'), '%Y-%m-%d')).days
        exec_summary['last_update'] = basic_summary.get('last_updated')
    
    # 从问题分析中提取信息
    if 'issues_analysis' in reports and 'summary' in reports['issues_analysis']:
        issues_summary = reports['issues_analysis']['summary']
        exec_summary['critical_issues_found'] = len(issues_summary.get('critical_files', []))
        
        # 确定健康状态
        if exec_summary['critical_issues_found'] > 0:
            exec_summary['data_health_status'] = 'CRITICAL'
        elif issues_summary.get('files_with_issues', 0) > 0:
            exec_summary['data_health_status'] = 'WARNING'
        else:
            exec_summary['data_health_status'] = 'GOOD'
    
    # 从修复报告中提取信息
    if 'repair_report' in reports and 'summary' in reports['repair_report']:
        repair_summary = reports['repair_report']['summary']
        exec_summary['issues_resolved'] = repair_summary.get('total_fixes_applied', 0)
    
    final_report['executive_summary'] = exec_summary
    
    # 生成建议
    recommendations = []
    action_items = []
    
    # 基于分析结果生成建议
    if exec_summary['critical_issues_found'] > 0:
        recommendations.append("立即关注严重数据质量问题")
        action_items.append("检查并修复所有标记为CRITICAL的数据文件")
    
    if exec_summary['data_coverage_days'] < 300:
        recommendations.append("数据历史覆盖范围较短，建议扩展历史数据")
        action_items.append("收集更多历史数据以提高分析准确性")
    
    # 检查核心指标完整性
    core_indicators = current_status.get('files_by_category', {}).get('core_indicators', [])
    expected_core = ['Y_idx.csv', 'mvrv_indicator.csv']
    missing_core = [f for f in expected_core if f not in core_indicators]
    
    if missing_core:
        recommendations.append(f"缺少核心指标文件: {', '.join(missing_core)}")
        action_items.append("确保所有核心指标数据文件都存在且数据完整")
    
    # 检查数据更新时效性
    if exec_summary['last_update']:
        last_update = datetime.strptime(exec_summary['last_update'], '%Y-%m-%d %H:%M:%S')
        days_since_update = (datetime.now() - last_update).days
        if days_since_update > 1:
            recommendations.append(f"数据已{days_since_update}天未更新")
            action_items.append("建立数据自动更新机制")
    
    # 检查恐慌贪婪指数
    if 'fear_greed_index.csv' in current_status.get('row_counts', {}):
        fear_greed_rows = current_status['row_counts']['fear_greed_index.csv']
        if fear_greed_rows == 0 or fear_greed_rows == 'ERROR':
            recommendations.append("恐慌贪婪指数数据为空或有错误")
            action_items.append("重新获取恐慌贪婪指数数据")
    
    final_report['recommendations'] = recommendations
    final_report['action_items'] = action_items
    
    return final_report

def print_final_report(report):
    """
    打印最终报告
    
    Args:
        report (dict): 最终报告
    """
    print("\n" + "="*100)
    print("🔍 Y指数项目数据完整性分析 - 最终报告")
    print("="*100)
    
    metadata = report['report_metadata']
    print(f"📅 报告生成时间: {metadata['generated_at']}")
    print(f"📊 分析版本: {metadata['report_version']}")
    
    # 执行摘要
    exec_summary = report['executive_summary']
    print(f"\n📋 执行摘要")
    print("-"*50)
    print(f"📁 数据文件总数: {exec_summary.get('total_data_files', 'N/A')}")
    print(f"🎯 核心指标文件: {exec_summary.get('core_indicators_count', 'N/A')}")
    
    # 健康状态显示
    health_status = exec_summary.get('data_health_status', 'UNKNOWN')
    if health_status == 'GOOD':
        status_icon = "✅"
    elif health_status == 'WARNING':
        status_icon = "⚠️"
    elif health_status == 'CRITICAL':
        status_icon = "🚨"
    else:
        status_icon = "❓"
    
    print(f"🏥 数据健康状态: {status_icon} {health_status}")
    print(f"🔍 发现严重问题: {exec_summary.get('critical_issues_found', 'N/A')}个")
    print(f"🔧 已修复问题: {exec_summary.get('issues_resolved', 'N/A')}个")
    print(f"📈 数据覆盖天数: {exec_summary.get('data_coverage_days', 'N/A')}天")
    print(f"🕐 最后更新时间: {exec_summary.get('last_update', 'N/A')}")
    
    # 当前数据状态
    current_status = report['current_data_status']
    if 'files_by_category' in current_status:
        print(f"\n📊 数据文件分类")
        print("-"*50)
        categories = current_status['files_by_category']
        print(f"🎯 核心指标 ({len(categories.get('core_indicators', []))}个): {', '.join(categories.get('core_indicators', []))}")
        print(f"📈 市场指标 ({len(categories.get('market_metrics', []))}个): {', '.join(categories.get('market_metrics', [])[:3])}{'...' if len(categories.get('market_metrics', [])) > 3 else ''}")
        print(f"🔧 技术指标 ({len(categories.get('technical_indicators', []))}个): {', '.join(categories.get('technical_indicators', [])[:3])}{'...' if len(categories.get('technical_indicators', [])) > 3 else ''}")
        print(f"📋 其他数据 ({len(categories.get('other_data', []))}个): {', '.join(categories.get('other_data', [])[:3])}{'...' if len(categories.get('other_data', [])) > 3 else ''}")
    
    # 关键发现
    print(f"\n🔍 关键发现")
    print("-"*50)
    
    # 从修复报告中提取关键信息
    if 'repair_actions' in report and 'detailed_results' in report['repair_actions']:
        repair_results = report['repair_actions']['detailed_results']
        for result in repair_results:
            if result.get('fixes'):
                print(f"🔧 {result['file_name']}: {len(result['fixes'])}个问题已修复")
    
    # 从问题分析中提取关键信息
    if 'identified_issues' in report and 'summary' in report['identified_issues']:
        issues_summary = report['identified_issues']['summary']
        if issues_summary.get('critical_files'):
            print(f"🚨 严重问题文件: {', '.join(issues_summary['critical_files'])}")
        if issues_summary.get('problematic_files'):
            print(f"⚠️  问题文件: {', '.join(issues_summary['problematic_files'][:3])}{'...' if len(issues_summary['problematic_files']) > 3 else ''}")
    
    # 建议和行动项
    if report.get('recommendations'):
        print(f"\n💡 建议")
        print("-"*50)
        for i, rec in enumerate(report['recommendations'], 1):
            print(f"{i}. {rec}")
    
    if report.get('action_items'):
        print(f"\n📋 行动项")
        print("-"*50)
        for i, action in enumerate(report['action_items'], 1):
            print(f"{i}. {action}")
    
    # 总结
    print(f"\n📝 总结")
    print("-"*50)
    if health_status == 'GOOD':
        print("✅ 数据整体状态良好，可以正常使用。")
    elif health_status == 'WARNING':
        print("⚠️  数据存在一些问题，建议关注并及时修复。")
    elif health_status == 'CRITICAL':
        print("🚨 数据存在严重问题，需要立即处理。")
    else:
        print("❓ 数据状态未知，需要进一步分析。")
    
    print("\n" + "="*100)

if __name__ == '__main__':
    # 生成最终报告
    print("正在生成最终数据状态报告...")
    final_report = generate_final_report()
    
    # 打印报告
    print_final_report(final_report)
    
    # 保存报告
    with open('final_data_status_report.json', 'w', encoding='utf-8') as f:
        json.dump(final_report, f, ensure_ascii=False, indent=2, default=str)
    
    print("\n📄 完整报告已保存到 final_data_status_report.json")
    print("\n🎉 数据完整性分析完成！")