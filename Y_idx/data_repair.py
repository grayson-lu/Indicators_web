#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据修复脚本
修复数据文件中发现的关键问题
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime
import shutil
import glob

def backup_file(file_path):
    """
    备份原始文件
    
    Args:
        file_path (str): 文件路径
        
    Returns:
        str: 备份文件路径
    """
    backup_path = file_path + '.backup_' + datetime.now().strftime('%Y%m%d_%H%M%S')
    shutil.copy2(file_path, backup_path)
    return backup_path

def fix_infinite_values(df, file_name):
    """
    修复无穷大值
    
    Args:
        df (DataFrame): 数据框
        file_name (str): 文件名
        
    Returns:
        tuple: (修复后的数据框, 修复日志)
    """
    fixes = []
    
    # 查找数值列
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    
    for col in numeric_cols:
        # 检查无穷大值
        inf_mask = np.isinf(df[col])
        if inf_mask.any():
            inf_count = inf_mask.sum()
            
            # 用NaN替换无穷大值
            df.loc[inf_mask, col] = np.nan
            
            # 尝试用前后值的平均值填充
            df[col] = df[col].interpolate(method='linear')
            
            fixes.append(f"修复列'{col}': {inf_count}个无穷大值")
    
    return df, fixes

def fix_early_dates(df, time_col, file_name):
    """
    修复异常早期日期（如1970年）
    
    Args:
        df (DataFrame): 数据框
        time_col (str): 时间列名
        file_name (str): 文件名
        
    Returns:
        tuple: (修复后的数据框, 修复日志)
    """
    fixes = []
    
    try:
        df[time_col] = pd.to_datetime(df[time_col])
        
        # 查找异常早期日期（2020年之前）
        early_mask = df[time_col] < datetime(2020, 1, 1)
        
        if early_mask.any():
            early_count = early_mask.sum()
            
            # 删除异常早期日期的行
            df = df[~early_mask].copy()
            
            fixes.append(f"删除{early_count}行异常早期日期数据")
    
    except Exception as e:
        fixes.append(f"时间列修复失败: {str(e)}")
    
    return df, fixes

def fix_duplicate_dates(df, time_col, file_name):
    """
    修复重复日期
    
    Args:
        df (DataFrame): 数据框
        time_col (str): 时间列名
        file_name (str): 文件名
        
    Returns:
        tuple: (修复后的数据框, 修复日志)
    """
    fixes = []
    
    try:
        df[time_col] = pd.to_datetime(df[time_col])
        
        # 查找重复日期
        duplicate_mask = df[time_col].duplicated()
        
        if duplicate_mask.any():
            duplicate_count = duplicate_mask.sum()
            
            # 保留第一个，删除重复的
            df = df[~duplicate_mask].copy()
            
            fixes.append(f"删除{duplicate_count}行重复日期数据")
    
    except Exception as e:
        fixes.append(f"重复日期修复失败: {str(e)}")
    
    return df, fixes

def repair_file(file_path):
    """
    修复单个文件
    
    Args:
        file_path (str): 文件路径
        
    Returns:
        dict: 修复结果
    """
    file_name = os.path.basename(file_path)
    
    try:
        # 备份原文件
        backup_path = backup_file(file_path)
        
        # 读取数据
        df = pd.read_csv(file_path)
        original_rows = len(df)
        
        all_fixes = []
        
        # 修复无穷大值
        df, inf_fixes = fix_infinite_values(df, file_name)
        all_fixes.extend(inf_fixes)
        
        # 查找时间列
        time_columns = [col for col in df.columns if any(keyword in col.lower() 
                      for keyword in ['time', 'date', 'timestamp'])]
        
        if time_columns:
            time_col = time_columns[0]
            
            # 修复异常早期日期
            df, date_fixes = fix_early_dates(df, time_col, file_name)
            all_fixes.extend(date_fixes)
            
            # 修复重复日期
            df, dup_fixes = fix_duplicate_dates(df, time_col, file_name)
            all_fixes.extend(dup_fixes)
        
        # 保存修复后的文件
        if all_fixes:  # 只有在有修复的情况下才保存
            df.to_csv(file_path, index=False)
        
        return {
            'file_name': file_name,
            'status': 'success',
            'original_rows': original_rows,
            'final_rows': len(df),
            'rows_removed': original_rows - len(df),
            'fixes': all_fixes,
            'backup_path': backup_path if all_fixes else None
        }
        
    except Exception as e:
        return {
            'file_name': file_name,
            'status': 'error',
            'error': str(e)
        }

def repair_critical_files():
    """
    修复关键问题文件
    
    Returns:
        dict: 修复报告
    """
    # 根据之前的分析，这些文件有严重问题需要修复
    critical_files = [
        'data/altcoin_season_index.csv',  # 有1970年日期
        'data/up_down_ratio.csv',  # 有无穷大值
        'data/fear_greed_index.csv'  # 有1970年日期
    ]
    
    results = []
    summary = {
        'total_files_processed': 0,
        'successful_repairs': 0,
        'failed_repairs': 0,
        'total_fixes_applied': 0,
        'total_rows_removed': 0
    }
    
    for file_path in critical_files:
        if os.path.exists(file_path):
            result = repair_file(file_path)
            results.append(result)
            
            summary['total_files_processed'] += 1
            
            if result['status'] == 'success':
                summary['successful_repairs'] += 1
                summary['total_fixes_applied'] += len(result.get('fixes', []))
                summary['total_rows_removed'] += result.get('rows_removed', 0)
            else:
                summary['failed_repairs'] += 1
    
    return {
        'summary': summary,
        'detailed_results': results,
        'repair_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

def print_repair_report(report):
    """
    打印修复报告
    
    Args:
        report (dict): 修复报告
    """
    summary = report['summary']
    results = report['detailed_results']
    
    print("\n" + "="*80)
    print("数据修复报告")
    print("="*80)
    print(f"修复时间: {report['repair_time']}")
    print(f"处理文件数: {summary['total_files_processed']}")
    print(f"成功修复: {summary['successful_repairs']}")
    print(f"修复失败: {summary['failed_repairs']}")
    print(f"总修复项目: {summary['total_fixes_applied']}")
    print(f"总删除行数: {summary['total_rows_removed']}")
    
    print("\n" + "-"*80)
    print("详细修复结果:")
    print("-"*80)
    
    for result in results:
        print(f"\n📁 {result['file_name']}")
        
        if result['status'] == 'success':
            print(f"   ✅ 修复成功")
            print(f"   原始行数: {result['original_rows']:,}")
            print(f"   最终行数: {result['final_rows']:,}")
            
            if result.get('rows_removed', 0) > 0:
                print(f"   删除行数: {result['rows_removed']:,}")
            
            if result.get('fixes'):
                print("   🔧 修复项目:")
                for fix in result['fixes']:
                    print(f"      - {fix}")
            
            if result.get('backup_path'):
                print(f"   💾 备份文件: {os.path.basename(result['backup_path'])}")
        
        else:
            print(f"   ❌ 修复失败")
            print(f"   错误: {result.get('error', '未知错误')}")
    
    print("\n" + "="*80)

if __name__ == '__main__':
    # 执行修复
    print("开始修复关键数据文件...")
    report = repair_critical_files()
    print_repair_report(report)
    
    # 保存修复报告
    import json
    with open('data_repair_report.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print("\n修复报告已保存到 data_repair_report.json")