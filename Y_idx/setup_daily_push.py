#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业微信推送配置和环境设置脚本
"""

import os
import sys
import json
from pathlib import Path

def create_config_template():
    """创建配置文件模板"""
    config = {
        "wechat_webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE",
        "push_schedule": {
            "enabled": True,
            "times": ["08:00", "09:30", "15:00", "21:00"],
            "timezone": "Asia/Shanghai"
        },
        "data_sources": {
            "y_index_file": "y_data/y_idx.csv",
            "sentiment_file": "y_data/market_sentiment.csv",
            "breadth_file": "y_data/market_breadth.csv",
            "chain_file": "y_data/chain_metrics.csv",
            "volatility_file": "y_data/volatility_data.csv"
        },
        "content_settings": {
            "include_charts": True,
            "include_summary": True,
            "emoji_enabled": True,
            "language": "zh_CN"
        },
        "logging": {
            "level": "INFO",
            "file": "daily_wechat_push.log",
            "max_size_mb": 100,
            "backup_count": 5
        }
    }
    
    return config

def setup_environment():
    """设置环境"""
    print("🚀 设置企业微信每日推送系统环境")
    print("=" * 50)
    
    # 获取用户输入
    webhook_url = input("请输入企业微信机器人Webhook地址: ").strip()
    if not webhook_url:
        print("❌ Webhook地址不能为空")
        return False
    
    # 创建配置文件
    config = create_config_template()
    config["wechat_webhook_url"] = webhook_url
    
    config_file = "daily_wechat_push_config.json"
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 配置文件已创建: {config_file}")
    
    # 创建启动脚本
    create_startup_scripts()
    
    # 创建数据目录
    data_dir = Path("y_data")
    data_dir.mkdir(exist_ok=True)
    print(f"✅ 数据目录已创建: {data_dir}")
    
    # 设置环境变量建议
    print("\n📋 环境变量设置建议:")
    print(f"export WECHAT_WEBHOOK_URL=\"{webhook_url}\"")
    print("或者添加到系统环境变量中")
    
    print("\n🎯 下一步操作:")
    print("1. 确保数据文件存在于 y_data/ 目录中")
    print("2. 运行测试: python daily_wechat_push.py")
    print("3. 设置定时任务或使用启动脚本")
    
    return True

def create_startup_scripts():
    """创建启动脚本"""
    
    # Windows批处理脚本
    windows_script = """@echo off
echo 启动企业微信每日推送系统...

REM 设置Python路径（根据需要修改）
set PYTHON_PATH=python

REM 设置环境变量
if exist daily_wechat_push_config.json (
    for /f "tokens=2 delims=\"" %%a in ('findstr "wechat_webhook_url" daily_wechat_push_config.json') do (
        set WECHAT_WEBHOOK_URL=%%a
    )
)

REM 启动程序
%PYTHON_PATH% daily_wechat_push.py

pause
"""
    
    # Linux/macOS shell脚本
    unix_script = """#!/bin/bash

echo "启动企业微信每日推送系统..."

# 设置Python路径（根据需要修改）
PYTHON_PATH=${PYTHON_PATH:-python3}

# 设置环境变量
if [ -f "daily_wechat_push_config.json" ]; then
    export WECHAT_WEBHOOK_URL=$(grep -o '"wechat_webhook_url": *"[^"]*"' daily_wechat_push_config.json | cut -d'"' -f4)
fi

# 启动程序
$PYTHON_PATH daily_wechat_push.py
"""
    
    # 写入脚本文件
    with open("start_push.bat", 'w', encoding='utf-8') as f:
        f.write(windows_script)
    
    with open("start_push.sh", 'w', encoding='utf-8') as f:
        f.write(unix_script)
    
    # 设置Unix脚本可执行权限
    try:
        os.chmod("start_push.sh", 0o755)
    except:
        pass
    
    print("✅ 启动脚本已创建: start_push.bat, start_push.sh")

def create_systemd_service():
    """创建systemd服务文件（Linux）"""
    service_content = """[Unit]
Description=Y指数企业微信每日推送服务
After=network.target

[Service]
Type=simple
User=yidx
WorkingDirectory=/opt/y_idx
Environment=WECHAT_WEBHOOK_URL=
ExecStart=/usr/bin/python3 /opt/y_idx/daily_wechat_push.py
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
"""
    
    with open("yidx-daily-push.service", 'w', encoding='utf-8') as f:
        f.write(service_content)
    
    print("✅ systemd服务文件已创建: yidx-daily-push.service")
    print("安装命令: sudo cp yidx-daily-push.service /etc/systemd/system/")
    print("启动命令: sudo systemctl start yidx-daily-push")

def create_task_scheduler_xml():
    """创建Windows任务计划程序XML"""
    xml_content = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Date>2024-01-01T00:00:00</Date>
    <Author>Y指数系统</Author>
    <Description>企业微信每日市场数据推送</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2024-01-01T08:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <UserId></UserId>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>true</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT1H</ExecutionTimeLimit>
    <Priority>6</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>python</Command>
      <Arguments>daily_wechat_push.py</Arguments>
      <WorkingDirectory></WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""
    
    with open("daily_push_task.xml", 'w', encoding='utf-8') as f:
        f.write(xml_content)
    
    print("✅ Windows任务计划XML已创建: daily_push_task.xml")
    print("导入命令: schtasks /create /xml daily_push_task.xml /tn \"Y指数每日推送\"")

def main():
    """主函数"""
    if len(sys.argv) > 1:
        if sys.argv[1] == "--systemd":
            create_systemd_service()
            return
        elif sys.argv[1] == "--windows-task":
            create_task_scheduler_xml()
            return
    
    # 默认设置环境
    if setup_environment():
        print("\n🎉 环境设置完成！")
        print("现在可以运行: python daily_wechat_push.py")
    else:
        print("\n❌ 环境设置失败")
        sys.exit(1)

if __name__ == "__main__":
    main()