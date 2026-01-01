#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
恐慌贪婪指数数据获取测试脚本
用于测试和修复恐慌贪婪指数数据获取功能
"""

import requests
import json
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
import os

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

def get_fear_greed_index():
    """
    获取恐慌贪婪指数数据
    
    Returns:
        pd.DataFrame: 恐慌贪婪指数数据
    """
    try:
        print("正在获取恐慌贪婪指数数据...")
        url = 'https://api.alternative.me/fng/?limit=33'  # 官网提供的api接口
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            print(f"API请求失败，状态码: {response.status_code}")
            return None
            
        data = response.json()  # 直接使用json()方法
        print(f"成功获取到 {len(data['data'])} 条数据")
        
        # 获取指数数据
        data_list = []
        for item in data['data']:
            data_list.append({
                'timestamp': int(item['timestamp']),
                'date': datetime.fromtimestamp(int(item['timestamp'])).strftime('%Y-%m-%d %H:%M:%S'),
                'value': int(item['value']),
                'value_classification': item['value_classification']
            })
        
        df = pd.DataFrame(data_list)
        
        # 确保data目录存在
        os.makedirs('data', exist_ok=True)
        
        # 保存数据
        df.to_csv('data/fear_greed_index.csv', index=False)
        print(f"数据已保存到 data/fear_greed_index.csv，共 {len(df)} 行")
        
        return df
        
    except Exception as e:
        print(f"获取恐慌贪婪指数失败: {str(e)}")
        return None

def draw_fear_greed_chart(df):
    """
    绘制恐慌贪婪指数图表
    
    Args:
        df (pd.DataFrame): 恐慌贪婪指数数据
    """
    if df is None or df.empty:
        print("数据为空，无法绘制图表")
        return
        
    try:
        print("正在绘制恐慌贪婪指数图表...")
        
        # 转换日期格式
        df['date_parsed'] = pd.to_datetime(df['date'])
        
        plt.figure(figsize=(16, 8))
        plt.plot(df['date_parsed'], df['value'], marker='o', linestyle='-', linewidth=2, markersize=4)
        
        # 添加背景色区域
        plt.axhspan(0, 25, alpha=0.2, color='red', label='极度恐慌')
        plt.axhspan(25, 46, alpha=0.2, color='orange', label='恐慌')
        plt.axhspan(46, 55, alpha=0.2, color='yellow', label='中性')
        plt.axhspan(55, 75, alpha=0.2, color='lightgreen', label='贪婪')
        plt.axhspan(75, 100, alpha=0.2, color='green', label='极度贪婪')
        
        plt.title('恐慌贪婪指数', fontsize=16)
        plt.xlabel('日期')
        plt.ylabel('指数值')
        plt.ylim(0, 100)
        plt.grid(True, alpha=0.3)
        plt.legend(loc='upper left')
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        # 确保data目录存在
        os.makedirs('data', exist_ok=True)
        
        plt.savefig('data/fear_greed_index.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print("图表已保存到 data/fear_greed_index.png")
        
    except Exception as e:
        print(f"绘制图表失败: {str(e)}")

def main():
    """
    主函数：测试恐慌贪婪指数数据获取和图表生成
    """
    print("=== 恐慌贪婪指数数据获取测试 ===")
    
    # 获取数据
    df = get_fear_greed_index()
    
    if df is not None:
        print(f"\n数据概览:")
        print(f"数据行数: {len(df)}")
        print(f"最新数据: {df.iloc[0]['date']} - {df.iloc[0]['value']} ({df.iloc[0]['value_classification']})")
        print(f"最旧数据: {df.iloc[-1]['date']} - {df.iloc[-1]['value']} ({df.iloc[-1]['value_classification']})")
        
        # 绘制图表
        draw_fear_greed_chart(df)
        
        print("\n=== 测试完成 ===")
    else:
        print("\n=== 测试失败：无法获取数据 ===")

if __name__ == "__main__":
    main()