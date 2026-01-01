"""推送内容优化模块
增强市场数据推送格式，包含更详细的指标信息、图表分析、自定义模板和优先级管理
"""

import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import logging
from pathlib import Path
import pandas as pd
import numpy as np

# 配置日志
logger = logging.getLogger(__name__)

class MessagePriority(Enum):
    """消息优先级枚举"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"
    CRITICAL = "critical"

class MessageType(Enum):
    """消息类型枚举"""
    MARKET_SUMMARY = "market_summary"
    INDICATOR_ALERT = "indicator_alert"
    CHART_ANALYSIS = "chart_analysis"
    SYSTEM_STATUS = "system_status"
    ERROR_REPORT = "error_report"
    DAILY_REPORT = "daily_report"
    CUSTOM = "custom"

@dataclass
class MessageTemplate:
    """消息模板数据类"""
    name: str
    type: MessageType
    priority: MessagePriority
    title_template: str
    content_template: str
    variables: List[str]
    description: str
    created_time: str
    last_used: Optional[str] = None
    use_count: int = 0

@dataclass
class MarketIndicator:
    """市场指标数据类"""
    name: str
    current_value: float
    previous_value: Optional[float]
    change_percent: Optional[float]
    status: str  # "正常", "警告", "危险"
    description: str
    trend: str  # "上升", "下降", "平稳"
    signal_strength: float  # 0-1之间
    timestamp: str

@dataclass
class ChartAnalysis:
    """图表分析数据类"""
    chart_name: str
    chart_path: str
    key_points: List[str]
    trend_analysis: str
    support_resistance: Dict[str, float]
    recommendations: List[str]
    risk_level: str
    confidence_score: float
    analysis_time: str

class PushContentOptimizer:
    """推送内容优化器"""
    
    def __init__(self, config: Dict = None):
        """
        初始化推送内容优化器
        
        Args:
            config: 配置字典
        """
        self.config = config or {}
        self.templates_dir = self.config.get('templates_dir', 'templates')
        self.max_content_length = self.config.get('max_content_length', 4000)
        self.enable_emoji = self.config.get('enable_emoji', True)
        
        # 确保模板目录存在
        Path(self.templates_dir).mkdir(parents=True, exist_ok=True)
        
        # 加载默认模板
        self.templates: Dict[str, MessageTemplate] = {}
        self._load_default_templates()
        
        # 优先级权重配置
        self.priority_weights = {
            MessagePriority.LOW: 1,
            MessagePriority.NORMAL: 2,
            MessagePriority.HIGH: 3,
            MessagePriority.URGENT: 4,
            MessagePriority.CRITICAL: 5
        }
    
    def _load_default_templates(self):
        """加载默认消息模板"""
        default_templates = [
            MessageTemplate(
                name="market_summary",
                type=MessageType.MARKET_SUMMARY,
                priority=MessagePriority.NORMAL,
                title_template="📊 市场数据汇总 - {date}",
                content_template="""## 📈 市场概况

**📅 日期**: {date}
**⏰ 更新时间**: {update_time}

### 🔍 核心指标
{indicators_summary}

### 📊 技术分析
{technical_analysis}

### ⚠️ 风险提示
{risk_alerts}

---
*数据来源: Y量化系统*""",
                variables=["date", "update_time", "indicators_summary", "technical_analysis", "risk_alerts"],
                description="市场数据汇总模板",
                created_time=datetime.now().isoformat()
            ),
            
            MessageTemplate(
                name="indicator_alert",
                type=MessageType.INDICATOR_ALERT,
                priority=MessagePriority.HIGH,
                title_template="🚨 {indicator_name} 指标预警",
                content_template="""## 🚨 指标预警通知

**📊 指标名称**: {indicator_name}
**📈 当前值**: {current_value}
**📉 前值**: {previous_value}
**📊 变化**: {change_percent}%
**⚠️ 状态**: {status}
**📈 趋势**: {trend}
**💪 信号强度**: {signal_strength}/10

### 📝 分析说明
{description}

### 🎯 操作建议
{recommendations}

**⏰ 预警时间**: {timestamp}

---
*Y量化系统自动监控*""",
                variables=["indicator_name", "current_value", "previous_value", "change_percent", 
                          "status", "trend", "signal_strength", "description", "recommendations", "timestamp"],
                description="指标预警模板",
                created_time=datetime.now().isoformat()
            ),
            
            MessageTemplate(
                name="chart_analysis",
                type=MessageType.CHART_ANALYSIS,
                priority=MessagePriority.NORMAL,
                title_template="📈 {chart_name} 图表分析",
                content_template="""## 📈 图表技术分析

**📊 图表**: {chart_name}
**⏰ 分析时间**: {analysis_time}
**🎯 置信度**: {confidence_score}%

### 🔍 关键要点
{key_points}

### 📈 趋势分析
{trend_analysis}

### 🎯 支撑阻力位
{support_resistance}

### 💡 操作建议
{recommendations}

### ⚠️ 风险等级
{risk_level}

---
*图表路径: {chart_path}*""",
                variables=["chart_name", "analysis_time", "confidence_score", "key_points", 
                          "trend_analysis", "support_resistance", "recommendations", "risk_level", "chart_path"],
                description="图表分析模板",
                created_time=datetime.now().isoformat()
            ),
            
            MessageTemplate(
                name="daily_report",
                type=MessageType.DAILY_REPORT,
                priority=MessagePriority.NORMAL,
                title_template="📋 每日交易报告 - {date}",
                content_template="""## 📋 每日交易报告

**📅 报告日期**: {date}
**📊 数据统计**: {stats_summary}

### 🏆 今日亮点
{highlights}

### 📈 市场表现
{market_performance}

### 🔍 指标监控
{indicators_status}

### 📊 图表汇总
{charts_summary}

### 📝 总结与展望
{summary_outlook}

### ⚠️ 风险提醒
{risk_reminders}

---
**📈 系统状态**: 正常运行
**⏰ 报告生成时间**: {report_time}""",
                variables=["date", "stats_summary", "highlights", "market_performance", 
                          "indicators_status", "charts_summary", "summary_outlook", "risk_reminders", "report_time"],
                description="每日报告模板",
                created_time=datetime.now().isoformat()
            )
        ]
        
        for template in default_templates:
            self.templates[template.name] = template
    
    def add_custom_template(self, template: MessageTemplate) -> bool:
        """
        添加自定义模板
        
        Args:
            template: 消息模板
            
        Returns:
            bool: 添加是否成功
        """
        try:
            self.templates[template.name] = template
            self._save_template(template)
            logger.info(f"自定义模板添加成功: {template.name}")
            return True
        except Exception as e:
            logger.error(f"添加自定义模板失败: {str(e)}")
            return False
    
    def _save_template(self, template: MessageTemplate):
        """保存模板到文件"""
        template_path = Path(self.templates_dir) / f"{template.name}.json"
        with open(template_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(template), f, ensure_ascii=False, indent=2)
    
    def format_market_indicators(self, indicators: List[MarketIndicator]) -> str:
        """
        格式化市场指标信息
        
        Args:
            indicators: 市场指标列表
            
        Returns:
            str: 格式化后的指标信息
        """
        if not indicators:
            return "暂无指标数据"
        
        formatted_text = ""
        
        for indicator in indicators:
            # 状态图标
            status_icon = {
                "正常": "✅",
                "警告": "⚠️",
                "危险": "🚨"
            }.get(indicator.status, "ℹ️")
            
            # 趋势图标
            trend_icon = {
                "上升": "📈",
                "下降": "📉",
                "平稳": "➡️"
            }.get(indicator.trend, "➡️")
            
            # 计算变化
            change_text = ""
            if indicator.previous_value is not None and indicator.change_percent is not None:
                change_sign = "+" if indicator.change_percent > 0 else ""
                change_text = f" ({change_sign}{indicator.change_percent:.2f}%)"
            
            # 信号强度条
            strength_bars = int(indicator.signal_strength * 10)
            strength_display = "█" * strength_bars + "░" * (10 - strength_bars)
            
            formatted_text += f"""
**{status_icon} {indicator.name}**
• 当前值: {indicator.current_value:.4f}{change_text}
• 趋势: {trend_icon} {indicator.trend}
• 信号强度: {strength_display} ({indicator.signal_strength:.1f})
• 说明: {indicator.description}

"""
        
        return formatted_text.strip()
    
    def format_chart_analysis(self, analysis: ChartAnalysis) -> str:
        """
        格式化图表分析信息
        
        Args:
            analysis: 图表分析对象
            
        Returns:
            str: 格式化后的分析信息
        """
        # 格式化关键要点
        key_points_text = "\n".join([f"• {point}" for point in analysis.key_points])
        
        # 格式化支撑阻力位
        sr_text = ""
        for level_type, value in analysis.support_resistance.items():
            sr_text += f"• {level_type}: {value:.4f}\n"
        
        # 格式化建议
        recommendations_text = "\n".join([f"• {rec}" for rec in analysis.recommendations])
        
        # 风险等级图标
        risk_icons = {
            "低": "🟢",
            "中": "🟡",
            "高": "🔴"
        }
        risk_icon = risk_icons.get(analysis.risk_level, "⚪")
        
        # 置信度条
        confidence_bars = int(analysis.confidence_score * 10)
        confidence_display = "█" * confidence_bars + "░" * (10 - confidence_bars)
        
        formatted_text = f"""
### 🔍 关键要点
{key_points_text}

### 📈 趋势分析
{analysis.trend_analysis}

### 🎯 支撑阻力位
{sr_text.strip()}

### 💡 操作建议
{recommendations_text}

### ⚠️ 风险等级
{risk_icon} {analysis.risk_level}风险

### 🎯 置信度
{confidence_display} {analysis.confidence_score:.1f}%
"""
        
        return formatted_text.strip()
    
    def generate_content(self, template_name: str, variables: Dict[str, Any]) -> Tuple[str, str]:
        """
        根据模板生成内容
        
        Args:
            template_name: 模板名称
            variables: 变量字典
            
        Returns:
            Tuple[str, str]: (标题, 内容)
        """
        if template_name not in self.templates:
            raise ValueError(f"模板不存在: {template_name}")
        
        template = self.templates[template_name]
        
        try:
            # 更新模板使用统计
            template.use_count += 1
            template.last_used = datetime.now().isoformat()
            
            # 格式化标题和内容
            title = template.title_template.format(**variables)
            content = template.content_template.format(**variables)
            
            # 内容长度检查
            if len(content) > self.max_content_length:
                logger.warning(f"内容长度超限 ({len(content)} > {self.max_content_length})，进行截断")
                content = content[:self.max_content_length - 50] + "\n\n...(内容已截断)"
            
            return title, content
            
        except KeyError as e:
            raise ValueError(f"模板变量缺失: {str(e)}")
        except Exception as e:
            raise ValueError(f"生成内容失败: {str(e)}")
    
    def create_market_summary(self, indicators: List[MarketIndicator], 
                            charts: List[ChartAnalysis] = None,
                            custom_notes: str = "") -> Tuple[str, str]:
        """
        创建市场汇总消息
        
        Args:
            indicators: 市场指标列表
            charts: 图表分析列表
            custom_notes: 自定义备注
            
        Returns:
            Tuple[str, str]: (标题, 内容)
        """
        # 分析指标状态
        normal_count = sum(1 for ind in indicators if ind.status == "正常")
        warning_count = sum(1 for ind in indicators if ind.status == "警告")
        danger_count = sum(1 for ind in indicators if ind.status == "危险")
        
        # 生成技术分析汇总
        technical_summary = ""
        if charts:
            high_confidence_charts = [c for c in charts if c.confidence_score >= 0.7]
            if high_confidence_charts:
                technical_summary = f"发现 {len(high_confidence_charts)} 个高置信度技术信号"
            else:
                technical_summary = "技术信号相对较弱，建议谨慎操作"
        else:
            technical_summary = "暂无技术分析数据"
        
        # 生成风险提示
        risk_alerts = []
        if danger_count > 0:
            risk_alerts.append(f"🚨 {danger_count} 个指标处于危险状态")
        if warning_count > 0:
            risk_alerts.append(f"⚠️ {warning_count} 个指标发出警告")
        if not risk_alerts:
            risk_alerts.append("✅ 当前市场指标整体正常")
        
        variables = {
            "date": datetime.now().strftime('%Y-%m-%d'),
            "update_time": datetime.now().strftime('%H:%M:%S'),
            "indicators_summary": self.format_market_indicators(indicators),
            "technical_analysis": technical_summary,
            "risk_alerts": "\n".join([f"• {alert}" for alert in risk_alerts])
        }
        
        if custom_notes:
            variables["risk_alerts"] += f"\n\n**📝 备注**: {custom_notes}"
        
        return self.generate_content("market_summary", variables)
    
    def create_indicator_alert(self, indicator: MarketIndicator, 
                             recommendations: List[str] = None) -> Tuple[str, str]:
        """
        创建指标预警消息
        
        Args:
            indicator: 市场指标
            recommendations: 操作建议列表
            
        Returns:
            Tuple[str, str]: (标题, 内容)
        """
        recommendations = recommendations or ["请密切关注市场变化", "建议适当调整仓位"]
        
        variables = {
            "indicator_name": indicator.name,
            "current_value": f"{indicator.current_value:.4f}",
            "previous_value": f"{indicator.previous_value:.4f}" if indicator.previous_value else "N/A",
            "change_percent": f"{indicator.change_percent:+.2f}" if indicator.change_percent else "N/A",
            "status": indicator.status,
            "trend": indicator.trend,
            "signal_strength": f"{indicator.signal_strength * 10:.1f}",
            "description": indicator.description,
            "recommendations": "\n".join([f"• {rec}" for rec in recommendations]),
            "timestamp": indicator.timestamp
        }
        
        return self.generate_content("indicator_alert", variables)
    
    def create_chart_analysis_message(self, analysis: ChartAnalysis) -> Tuple[str, str]:
        """
        创建图表分析消息
        
        Args:
            analysis: 图表分析对象
            
        Returns:
            Tuple[str, str]: (标题, 内容)
        """
        variables = {
            "chart_name": analysis.chart_name,
            "analysis_time": analysis.analysis_time,
            "confidence_score": f"{analysis.confidence_score * 100:.1f}",
            "key_points": "\n".join([f"• {point}" for point in analysis.key_points]),
            "trend_analysis": analysis.trend_analysis,
            "support_resistance": "\n".join([f"• {k}: {v:.4f}" for k, v in analysis.support_resistance.items()]),
            "recommendations": "\n".join([f"• {rec}" for rec in analysis.recommendations]),
            "risk_level": analysis.risk_level,
            "chart_path": analysis.chart_path
        }
        
        return self.generate_content("chart_analysis", variables)
    
    def prioritize_messages(self, messages: List[Tuple[MessageType, MessagePriority, str, str]]) -> List[Tuple[MessageType, MessagePriority, str, str]]:
        """
        根据优先级对消息进行排序
        
        Args:
            messages: 消息列表 [(type, priority, title, content), ...]
            
        Returns:
            List: 排序后的消息列表
        """
        return sorted(messages, key=lambda x: self.priority_weights[x[1]], reverse=True)
    
    def get_template_usage_stats(self) -> Dict[str, Dict]:
        """
        获取模板使用统计
        
        Returns:
            Dict: 模板使用统计信息
        """
        stats = {}
        for name, template in self.templates.items():
            stats[name] = {
                'type': template.type.value,
                'priority': template.priority.value,
                'use_count': template.use_count,
                'last_used': template.last_used,
                'created_time': template.created_time
            }
        return stats
    
    def export_templates(self, output_path: str = None) -> str:
        """
        导出所有模板
        
        Args:
            output_path: 输出文件路径
            
        Returns:
            str: 导出文件路径
        """
        if not output_path:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = f"message_templates_{timestamp}.json"
        
        templates_data = {
            'export_time': datetime.now().isoformat(),
            'total_templates': len(self.templates),
            'templates': {name: asdict(template) for name, template in self.templates.items()}
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(templates_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"模板导出完成: {output_path}")
        return output_path
    
    def analyze_content_effectiveness(self, feedback_data: List[Dict]) -> Dict:
        """
        分析内容推送效果
        
        Args:
            feedback_data: 反馈数据列表
            
        Returns:
            Dict: 效果分析结果
        """
        if not feedback_data:
            return {'message': '暂无反馈数据'}
        
        # 分析各类型消息的效果
        type_stats = {}
        priority_stats = {}
        
        for feedback in feedback_data:
            msg_type = feedback.get('type', 'unknown')
            priority = feedback.get('priority', 'normal')
            read_rate = feedback.get('read_rate', 0)
            response_rate = feedback.get('response_rate', 0)
            
            # 按类型统计
            if msg_type not in type_stats:
                type_stats[msg_type] = {'count': 0, 'total_read_rate': 0, 'total_response_rate': 0}
            type_stats[msg_type]['count'] += 1
            type_stats[msg_type]['total_read_rate'] += read_rate
            type_stats[msg_type]['total_response_rate'] += response_rate
            
            # 按优先级统计
            if priority not in priority_stats:
                priority_stats[priority] = {'count': 0, 'total_read_rate': 0, 'total_response_rate': 0}
            priority_stats[priority]['count'] += 1
            priority_stats[priority]['total_read_rate'] += read_rate
            priority_stats[priority]['total_response_rate'] += response_rate
        
        # 计算平均值
        for stats in [type_stats, priority_stats]:
            for key, data in stats.items():
                if data['count'] > 0:
                    data['avg_read_rate'] = data['total_read_rate'] / data['count']
                    data['avg_response_rate'] = data['total_response_rate'] / data['count']
        
        return {
            'analysis_time': datetime.now().isoformat(),
            'total_messages': len(feedback_data),
            'type_effectiveness': type_stats,
            'priority_effectiveness': priority_stats,
            'recommendations': self._generate_content_recommendations(type_stats, priority_stats)
        }
    
    def _generate_content_recommendations(self, type_stats: Dict, priority_stats: Dict) -> List[str]:
        """
        生成内容优化建议
        
        Args:
            type_stats: 类型统计数据
            priority_stats: 优先级统计数据
            
        Returns:
            List[str]: 优化建议列表
        """
        recommendations = []
        
        # 分析最有效的消息类型
        if type_stats:
            best_type = max(type_stats.items(), key=lambda x: x[1].get('avg_read_rate', 0))
            recommendations.append(f"'{best_type[0]}' 类型消息阅读率最高，建议增加此类内容")
        
        # 分析优先级效果
        if priority_stats:
            for priority, stats in priority_stats.items():
                if stats.get('avg_read_rate', 0) < 0.3:  # 阅读率低于30%
                    recommendations.append(f"'{priority}' 优先级消息阅读率较低，建议优化内容质量")
        
        # 通用建议
        recommendations.extend([
            "定期更新消息模板，保持内容新鲜度",
            "根据用户反馈调整消息发送频率",
            "增加互动性元素提高用户参与度"
        ])
        
        return recommendations