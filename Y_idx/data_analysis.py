#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据完整性分析脚本
用于检查项目中所有指标数据文件的完整性和状态
"""

import os
import pandas as pd
from datetime import datetime, timedelta
import glob
import json

def analyze_csv_file(file_path):
    """
    分析单个CSV文件的基本信息
    
    Args:
        file_path (str): CSV文件路径
        
    Returns:
        dict: 文件分析结果
    """
    try:
        # 获取文件基本信息
        file_stat = os.stat(file_path)
        file_size = file_stat.st_size
        modify_time = datetime.fromtimestamp(file_stat.st_mtime)
        
        # 读取CSV文件
        df = pd.read_csv(file_path)
        
        # 基本统计信息
        row_count = len(df)
        col_count = len(df.columns)
        columns = list(df.columns)
        
        # 检查时间列
        time_columns = [col for col in columns if any(keyword in col.lower() 
                      for keyword in ['time', 'date', 'timestamp'])]
        
        # 分析时间范围
        time_range = None
        if time_columns:
            time_col = time_columns[0]
            try:
                df[time_col] = pd.to_datetime(df[time_col])
                time_range = {
                    'start': df[time_col].min().strftime('%Y-%m-%d'),
                    'end': df[time_col].max().strftime('%Y-%m-%d'),
                    'days': (df[time_col].max() - df[time_col].min()).days
                }
            except:
                time_range = "时间列解析失败"
        
        # 检查空值情况
        null_counts = df.isnull().sum().to_dict()
        total_nulls = sum(null_counts.values())
        
        return {
            'file_name': os.path.basename(file_path),
            'file_size_kb': round(file_size / 1024, 2),
            'modify_time': modify_time.strftime('%Y-%m-%d %H:%M:%S'),
            'row_count': row_count,
            'col_count': col_count,
            'columns': columns,
            'time_columns': time_columns,
            'time_range': time_range,
            'total_nulls': total_nulls,
            'null_percentage': round(total_nulls / (row_count * col_count) * 100, 2) if row_count > 0 else 0,
            'status': 'OK' if row_count > 0 else 'EMPTY'
        }
        
    except Exception as e:
        return {
            'file_name': os.path.basename(file_path),
            'error': str(e),
            'status': 'ERROR'
        }

def analyze_all_data_files():
    """
    分析data目录下所有CSV文件
    
    Returns:
        dict: 完整的分析报告
    """
    data_dir = 'data'
    if not os.path.exists(data_dir):
        return {'error': 'data目录不存在'}
    
    # 获取所有CSV文件
    csv_files = glob.glob(os.path.join(data_dir, '*.csv'))
    
    if not csv_files:
        return {'error': 'data目录下没有找到CSV文件'}
    
    results = []
    summary = {
        'total_files': len(csv_files),
        'ok_files': 0,
        'empty_files': 0,
        'error_files': 0,
        'total_rows': 0,
        'oldest_data': None,
        'newest_data': None,
        'last_updated': None
    }
    
    for file_path in sorted(csv_files):
        result = analyze_csv_file(file_path)
        results.append(result)
        
        # 更新汇总统计
        if result['status'] == 'OK':
            summary['ok_files'] += 1
            summary['total_rows'] += result['row_count']
            
            # 更新时间范围
            if result.get('time_range') and isinstance(result['time_range'], dict):
                start_date = result['time_range']['start']
                end_date = result['time_range']['end']
                
                if not summary['oldest_data'] or start_date < summary['oldest_data']:
                    summary['oldest_data'] = start_date
                if not summary['newest_data'] or end_date > summary['newest_data']:
                    summary['newest_data'] = end_date
            
            # 更新最后修改时间
            modify_time = result['modify_time']
            if not summary['last_updated'] or modify_time > summary['last_updated']:
                summary['last_updated'] = modify_time
                
        elif result['status'] == 'EMPTY':
            summary['empty_files'] += 1
        else:
            summary['error_files'] += 1
    
    return {
        'summary': summary,
        'files': results,
        'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

def print_analysis_report(analysis_result):
    """
    打印分析报告
    
    Args:
        analysis_result (dict): 分析结果
    """
    if 'error' in analysis_result:
        print(f"错误: {analysis_result['error']}")
        return
    
    summary = analysis_result['summary']
    files = analysis_result['files']
    
    print("\n" + "="*80)
    print("数据文件完整性分析报告")
    print("="*80)
    print(f"分析时间: {analysis_result['analysis_time']}")
    print(f"总文件数: {summary['total_files']}")
    print(f"正常文件: {summary['ok_files']}")
    print(f"空文件: {summary['empty_files']}")
    print(f"错误文件: {summary['error_files']}")
    print(f"总数据行数: {summary['total_rows']:,}")
    print(f"数据时间范围: {summary['oldest_data']} 至 {summary['newest_data']}")
    print(f"最后更新时间: {summary['last_updated']}")
    
    print("\n" + "-"*80)
    print("详细文件信息:")
    print("-"*80)
    
    for file_info in files:
        print(f"\n文件: {file_info['file_name']}")
        if file_info['status'] == 'OK':
            print(f"  状态: ✓ 正常")
            print(f"  大小: {file_info['file_size_kb']} KB")
            print(f"  行数: {file_info['row_count']:,}")
            print(f"  列数: {file_info['col_count']}")
            print(f"  修改时间: {file_info['modify_time']}")
            if file_info.get('time_range') and isinstance(file_info['time_range'], dict):
                tr = file_info['time_range']
                print(f"  时间范围: {tr['start']} 至 {tr['end']} ({tr['days']}天)")
            if file_info['total_nulls'] > 0:
                print(f"  空值: {file_info['total_nulls']} ({file_info['null_percentage']}%)")
        elif file_info['status'] == 'EMPTY':
            print(f"  状态: ⚠ 空文件")
        else:
            print(f"  状态: ✗ 错误")
            print(f"  错误信息: {file_info.get('error', '未知错误')}")
    
    # 问题汇总
    print("\n" + "-"*80)
    print("问题汇总:")
    print("-"*80)
    
    issues = []
    if summary['empty_files'] > 0:
        issues.append(f"发现 {summary['empty_files']} 个空文件")
    if summary['error_files'] > 0:
        issues.append(f"发现 {summary['error_files']} 个错误文件")
    
    # 检查数据更新时效性
    if summary['last_updated']:
        last_update = datetime.strptime(summary['last_updated'], '%Y-%m-%d %H:%M:%S')
        days_since_update = (datetime.now() - last_update).days
        if days_since_update > 1:
            issues.append(f"数据已 {days_since_update} 天未更新")
    
    # 检查数据量异常
    for file_info in files:
        if file_info['status'] == 'OK' and file_info['row_count'] < 10:
            issues.append(f"{file_info['file_name']} 数据量过少 ({file_info['row_count']} 行)")
    
    if issues:
        for issue in issues:
            print(f"  ⚠ {issue}")
    else:
        print("  ✓ 未发现明显问题")
    
    print("\n" + "="*80)

if __name__ == '__main__':
    # 执行分析
    result = analyze_all_data_files()
    print_analysis_report(result)
    
    # 保存详细报告到JSON文件
    with open('data_analysis_report.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("\n详细报告已保存到 data_analysis_report.json")