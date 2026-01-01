#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据问题深度分析脚本
专门分析数据文件中的异常情况和潜在问题
"""

import os
import pandas as pd
from datetime import datetime, timedelta
import json
import numpy as np

def analyze_time_continuity(df, time_col, file_name):
    """
    分析时间序列数据的连续性
    
    Args:
        df (DataFrame): 数据框
        time_col (str): 时间列名
        file_name (str): 文件名
        
    Returns:
        dict: 连续性分析结果
    """
    try:
        # 转换时间列
        df[time_col] = pd.to_datetime(df[time_col])
        df_sorted = df.sort_values(time_col)
        
        # 计算时间间隔
        time_diffs = df_sorted[time_col].diff().dropna()
        
        # 分析间隔模式
        most_common_interval = time_diffs.mode().iloc[0] if len(time_diffs.mode()) > 0 else None
        
        # 查找异常间隔
        if most_common_interval:
            expected_interval = most_common_interval
            tolerance = timedelta(hours=2)  # 允许2小时误差
            
            abnormal_gaps = []
            for i, diff in enumerate(time_diffs):
                if abs(diff - expected_interval) > tolerance:
                    abnormal_gaps.append({
                        'index': i + 1,
                        'date': df_sorted.iloc[i + 1][time_col].strftime('%Y-%m-%d'),
                        'gap_days': diff.days,
                        'expected_days': expected_interval.days
                    })
        
        # 检查是否有重复日期
        duplicate_dates = df_sorted[df_sorted[time_col].duplicated()]
        
        # 检查是否有未来日期
        future_dates = df_sorted[df_sorted[time_col] > datetime.now()]
        
        # 检查是否有异常早期日期（1970年等）
        early_dates = df_sorted[df_sorted[time_col] < datetime(2020, 1, 1)]
        
        return {
            'file_name': file_name,
            'total_records': len(df),
            'date_range': {
                'start': df_sorted[time_col].min().strftime('%Y-%m-%d'),
                'end': df_sorted[time_col].max().strftime('%Y-%m-%d'),
                'span_days': (df_sorted[time_col].max() - df_sorted[time_col].min()).days
            },
            'expected_interval_days': expected_interval.days if expected_interval else None,
            'abnormal_gaps': abnormal_gaps[:10],  # 只显示前10个异常
            'total_abnormal_gaps': len(abnormal_gaps) if 'abnormal_gaps' in locals() else 0,
            'duplicate_dates_count': len(duplicate_dates),
            'future_dates_count': len(future_dates),
            'early_dates_count': len(early_dates),
            'issues': []
        }
        
    except Exception as e:
        return {
            'file_name': file_name,
            'error': str(e),
            'issues': ['时间列解析失败']
        }

def analyze_data_quality(file_path):
    """
    分析单个文件的数据质量
    
    Args:
        file_path (str): 文件路径
        
    Returns:
        dict: 数据质量分析结果
    """
    file_name = os.path.basename(file_path)
    
    try:
        df = pd.read_csv(file_path)
        
        # 基本信息
        result = {
            'file_name': file_name,
            'row_count': len(df),
            'col_count': len(df.columns),
            'file_size_mb': round(os.path.getsize(file_path) / (1024 * 1024), 2),
            'issues': [],
            'warnings': [],
            'recommendations': []
        }
        
        # 检查空值情况
        null_counts = df.isnull().sum()
        high_null_cols = null_counts[null_counts > len(df) * 0.1].to_dict()  # 超过10%空值的列
        if high_null_cols:
            result['issues'].append(f"高空值列: {list(high_null_cols.keys())}")
            result['high_null_columns'] = high_null_cols
        
        # 检查数据量是否异常
        if len(df) < 30:
            result['issues'].append(f"数据量过少: 仅{len(df)}行")
        elif len(df) < 100:
            result['warnings'].append(f"数据量较少: {len(df)}行")
        
        # 检查时间列
        time_columns = [col for col in df.columns if any(keyword in col.lower() 
                      for keyword in ['time', 'date', 'timestamp'])]
        
        if time_columns:
            time_col = time_columns[0]
            continuity_result = analyze_time_continuity(df, time_col, file_name)
            result['time_analysis'] = continuity_result
            
            # 添加时间相关问题
            if continuity_result.get('total_abnormal_gaps', 0) > 0:
                result['issues'].append(f"发现{continuity_result['total_abnormal_gaps']}个时间间隔异常")
            
            if continuity_result.get('duplicate_dates_count', 0) > 0:
                result['issues'].append(f"发现{continuity_result['duplicate_dates_count']}个重复日期")
            
            if continuity_result.get('future_dates_count', 0) > 0:
                result['issues'].append(f"发现{continuity_result['future_dates_count']}个未来日期")
            
            if continuity_result.get('early_dates_count', 0) > 0:
                result['issues'].append(f"发现{continuity_result['early_dates_count']}个异常早期日期")
        
        # 检查数值列的异常值
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            if col in time_columns:
                continue
                
            col_data = df[col].dropna()
            if len(col_data) > 0:
                # 检查无穷大值
                inf_count = np.isinf(col_data).sum()
                if inf_count > 0:
                    result['issues'].append(f"列'{col}'包含{inf_count}个无穷大值")
                
                # 检查异常大的值
                q99 = col_data.quantile(0.99)
                q01 = col_data.quantile(0.01)
                extreme_high = (col_data > q99 * 100).sum()
                extreme_low = (col_data < q01 / 100).sum()
                
                if extreme_high > 0:
                    result['warnings'].append(f"列'{col}'可能包含{extreme_high}个异常高值")
                if extreme_low > 0:
                    result['warnings'].append(f"列'{col}'可能包含{extreme_low}个异常低值")
        
        # 生成建议
        if result['issues']:
            result['recommendations'].append("需要立即修复数据质量问题")
        if result['warnings']:
            result['recommendations'].append("建议检查数据异常值")
        if not time_columns:
            result['recommendations'].append("建议添加时间戳列以便追踪数据更新")
        
        return result
        
    except Exception as e:
        return {
            'file_name': file_name,
            'error': str(e),
            'issues': ['文件读取失败'],
            'recommendations': ['检查文件格式和编码']
        }

def generate_comprehensive_report():
    """
    生成综合数据质量报告
    
    Returns:
        dict: 综合报告
    """
    data_dir = 'data'
    if not os.path.exists(data_dir):
        return {'error': 'data目录不存在'}
    
    import glob
    csv_files = glob.glob(os.path.join(data_dir, '*.csv'))
    
    if not csv_files:
        return {'error': 'data目录下没有找到CSV文件'}
    
    results = []
    summary = {
        'total_files': len(csv_files),
        'files_with_issues': 0,
        'files_with_warnings': 0,
        'total_issues': 0,
        'total_warnings': 0,
        'critical_files': [],
        'problematic_files': [],
        'healthy_files': []
    }
    
    for file_path in sorted(csv_files):
        result = analyze_data_quality(file_path)
        results.append(result)
        
        # 更新汇总统计
        if result.get('issues'):
            summary['files_with_issues'] += 1
            summary['total_issues'] += len(result['issues'])
            
            if len(result['issues']) >= 3:  # 3个或以上问题视为严重
                summary['critical_files'].append(result['file_name'])
            else:
                summary['problematic_files'].append(result['file_name'])
        else:
            summary['healthy_files'].append(result['file_name'])
        
        if result.get('warnings'):
            summary['files_with_warnings'] += 1
            summary['total_warnings'] += len(result['warnings'])
    
    return {
        'summary': summary,
        'detailed_results': results,
        'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

def print_issues_report(report):
    """
    打印问题报告
    
    Args:
        report (dict): 分析报告
    """
    if 'error' in report:
        print(f"错误: {report['error']}")
        return
    
    summary = report['summary']
    results = report['detailed_results']
    
    print("\n" + "="*80)
    print("数据质量问题深度分析报告")
    print("="*80)
    print(f"分析时间: {report['analysis_time']}")
    print(f"总文件数: {summary['total_files']}")
    print(f"有问题的文件: {summary['files_with_issues']}")
    print(f"有警告的文件: {summary['files_with_warnings']}")
    print(f"健康文件: {len(summary['healthy_files'])}")
    print(f"总问题数: {summary['total_issues']}")
    print(f"总警告数: {summary['total_warnings']}")
    
    if summary['critical_files']:
        print(f"\n🚨 严重问题文件 ({len(summary['critical_files'])}个):")
        for file_name in summary['critical_files']:
            print(f"  - {file_name}")
    
    if summary['problematic_files']:
        print(f"\n⚠️  问题文件 ({len(summary['problematic_files'])}个):")
        for file_name in summary['problematic_files']:
            print(f"  - {file_name}")
    
    print(f"\n✅ 健康文件 ({len(summary['healthy_files'])}个):")
    for file_name in summary['healthy_files'][:5]:  # 只显示前5个
        print(f"  - {file_name}")
    if len(summary['healthy_files']) > 5:
        print(f"  ... 还有{len(summary['healthy_files']) - 5}个")
    
    # 详细问题列表
    print("\n" + "-"*80)
    print("详细问题分析:")
    print("-"*80)
    
    for result in results:
        if result.get('issues') or result.get('warnings'):
            print(f"\n📁 {result['file_name']}")
            print(f"   行数: {result.get('row_count', 'N/A'):,}")
            print(f"   列数: {result.get('col_count', 'N/A')}")
            print(f"   大小: {result.get('file_size_mb', 'N/A')} MB")
            
            if result.get('issues'):
                print("   🚨 问题:")
                for issue in result['issues']:
                    print(f"      - {issue}")
            
            if result.get('warnings'):
                print("   ⚠️  警告:")
                for warning in result['warnings']:
                    print(f"      - {warning}")
            
            if result.get('recommendations'):
                print("   💡 建议:")
                for rec in result['recommendations']:
                    print(f"      - {rec}")
            
            # 显示时间分析结果
            if result.get('time_analysis') and result['time_analysis'].get('abnormal_gaps'):
                print("   📅 时间间隔异常:")
                for gap in result['time_analysis']['abnormal_gaps'][:3]:  # 只显示前3个
                    print(f"      - {gap['date']}: 间隔{gap['gap_days']}天 (预期{gap['expected_days']}天)")
    
    print("\n" + "="*80)

if __name__ == '__main__':
    # 执行深度分析
    report = generate_comprehensive_report()
    print_issues_report(report)
    
    # 保存详细报告
    with open('data_issues_report.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print("\n详细问题报告已保存到 data_issues_report.json")