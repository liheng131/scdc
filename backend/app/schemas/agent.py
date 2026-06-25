"""
Agent 流水线 Schema 模块

定义 AI Agent 流水线各阶段（采集→清洗→分析→报告→编排）的输入/输出数据结构。

Schema 层级关系：
  OrchestratorInput → CollectorInput → CollectedItem → CleanerInput → CleanedItem
     → AnalyzerInput → Insight → AnalyzerOutput → ReporterInput → ReportSection → ReporterOutput
     → OrchestratorOutput

为什么每个阶段都有独立的 Input/Output Schema：
- 每个 Agent 可独立测试，只需提供正确的 Input 即可验证 Output
- 阶段间数据格式变化被 Pydantic 强制校验，避免类型错误在串联时传播
"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
import uuid
from datetime import datetime

# ============================================================
# Constants
# ============================================================

# DimensionGenerator 失败时的回退维度集合（与旧版硬编码的 4 个默认维度一致）
DEFAULT_DIMENSIONS: List[str] = [
    "宏观经济环境",
    "行业形势与趋势",
    "细分板块分析",
    "竞争格局与对手",
]

# ============================================================
# Collector（采集）阶段
# ============================================================

class CollectorInput(BaseModel):
    task_id: str
    topic: str
    max_items: int = Field(default=20, ge=1, le=50)
    search_categories: Optional[List[str]] = None
    attachment_ids: List[str] = Field(default_factory=list)  # 用户上传的附件 ID 列表

class CollectedItem(BaseModel):
    source_type: str  # search / crawler / document / datasource
    source_uri: str
    title: str
    content: str
    metadata: Dict[str, Any] = {}

class CollectorOutput(BaseModel):
    task_id: str
    success: bool
    items: List[CollectedItem] = []
    error: Optional[str] = None
    warning: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)  # 阶段元数据(如 user_attachment_count)
    expanded_keywords: List[str] = Field(default_factory=list)  # 数据采集阶段 LLM 扩展的关键词

# ============================================================
# Cleaner（清洗）阶段
# ============================================================

class CleanerInput(BaseModel):
    task_id: str
    raw_items: List[CollectedItem]

class CleanedItem(BaseModel):
    item_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_type: str
    source_uri: str
    title: str
    summary: str
    content_chunks: List[str] = []
    relevance_score: float = 1.0
    metadata: Dict[str, Any] = {}

class CleanerOutput(BaseModel):
    task_id: str
    success: bool
    cleaned_items: List[CleanedItem] = []
    total_removed: int = 0
    error: Optional[str] = None
    cleaning_operations: Dict[str, int] = Field(
        default_factory=lambda: {
            "duplicates_removed": 0,
            "low_quality_filtered": 0,
            "format_standardized": 0,
        },
        description="清洗操作统计：重复移除数、低质量过滤数、格式标准化数",
    )

# ============================================================
# Analyzer（分析）阶段
# ============================================================

class Insight(BaseModel):
    conclusion: str
    analysis: str = ""
    evidence: List[str] = []
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    dimension: str = Field(default="")


class NarrativeAngle(BaseModel):
    """叙述角度：每个分析维度下的多个叙述角度"""
    dimension: str = Field(default="", description="所属维度名称")
    angle_title: str = Field(default="", description="角度标题（如'市场规模与增速'、'技术路线演进'）")
    focus: str = Field(default="", description="聚焦点描述（引导 LLM 生成内容）")
    suggested_chart_types: List[str] = Field(
        default_factory=list,
        description="建议图表类型列表（如 ['bar', 'line']）"
    )

class AnalyzerInput(BaseModel):
    task_id: str
    topic: str
    cleaned_items: List[CleanedItem]
    dimensions: List[str] = Field(default_factory=list)  # 由 Orchestrator 动态注入
    expanded_keywords: List[str] = Field(default_factory=list)  # 由 Collector 阶段透传的扩展关键词,供 RAG 多关键词检索

class AnalyzerOutput(BaseModel):
    task_id: str
    success: bool
    summary: str
    insights: List[Insight] = []
    error: Optional[str] = None
    degraded: bool = False
    rag_results_count: int = 0  # RAG 检索结果数量
    rag_results: List[Dict[str, Any]] = []  # RAG 结果摘要列表，每项包含 title, content_snippet, relevance_score
    chart_plan: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="图表规划：每个分析维度的图表类型、数据点、位置"
    )
    structured_metrics: List["StructuredMetric"] = Field(
        default_factory=list,
        description="结构化指标：可绘制统计图的时序数据，如逐年/季度/月度趋势、同比/环比、市场份额等"
    )


# ============================================================
# 结构化指标数据模型（用于统计图绘制）
# ============================================================

class MetricDataPoint(BaseModel):
    """单个数据点：一个 label + 一个 value"""
    label: str = Field(..., description="数据点标签，如 '2020', 'Q1', '华为'")
    value: float = Field(..., description="数据点数值")


class StructuredMetric(BaseModel):
    """结构化指标：可绘制统计图的完整时序/对比数据"""
    metric_name: str = Field(..., description="指标名称，如 '全球AI芯片市场规模'")
    metric_type: str = Field(
        default="other",
        description="指标类型: yearly_trend, quarterly_trend, monthly_trend, "
                    "yoy_growth, qoq_growth, market_share, other"
    )
    unit: str = Field(default="", description="单位，如 '亿美元', '%', '家'")
    dimension: str = Field(default="", description="所属分析维度，如 '宏观经济环境'")
    data_points: List[MetricDataPoint] = Field(
        default_factory=list,
        description="数据点列表"
    )
    period_granularity: str = Field(
        default="",
        description="时间粒度: year, quarter, month, week（为空表示非时序数据）"
    )
    yoy_data: Optional[List[MetricDataPoint]] = Field(
        default=None,
        description="同比（Year-over-Year）对比数据"
    )
    qoq_data: Optional[List[MetricDataPoint]] = Field(
        default=None,
        description="环比（Quarter-over-Quarter）对比数据"
    )
    source: str = Field(default="", description="数据来源说明")
    chart_type_hint: str = Field(
        default="bar",
        description="建议图表类型: bar, line, pie"
    )

# ============================================================
# Reporter（报告）阶段
# ============================================================

class ConversationMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class ReporterInput(BaseModel):
    task_id: str
    topic: str
    analyzer_output: AnalyzerOutput
    include_charts: bool = True
    source_contents: List[Dict[str, Any]] = []
    dimensions: List[str] = Field(default_factory=list)
    conversation_history: List[ConversationMessage] = Field(default_factory=list)

class ReportSection(BaseModel):
    title: str
    content: str

class ReporterOutput(BaseModel):
    task_id: str
    success: bool
    markdown_report: str
    sections: List[ReportSection] = []
    chart_configs: List[Dict[str, Any]] = []
    chart_images: List[Dict[str, str]] = []
    dimension_illustrations: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="维度配图数据列表，格式: [{'section': str, 'title': str, 'base64': str, 'position': int}]"
    )
    # ---- html-ppt 结构化输出（Phase 1 新增）----
    # 完整结构化页面描述；存储为 JSON 序列化的 List[Dict]
    # 字段由 ReporterAgent prompt 引导 LLM 直接产出，包含 layout/animations/notes/kpi_metrics 等 html-ppt 语义
    # 若 LLM 未能按结构化格式输出，此字段为空，运行时降级为 markdown 解析路径
    pages: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="html-ppt 结构化 PageModel 列表（每项为 PageModel dict）",
    )
    theme: str = Field(
        default="minimal-white",
        description="html-ppt 主题名，36 套之一",
    )
    notes_summary: str = Field(
        default="",
        description="整份报告的 150 字以内执行摘要（演讲者模式开篇用）",
    )
    html_content: str = Field(
        default="",
        description="完整的 HTML 演示文稿内容（基于 html-ppt 设计系统生成）",
    )
    # ---- 兼容字段 ----
    error: Optional[str] = None
    degraded: bool = False
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="额外元数据，如质量校验结果等",
    )

# ============================================================
# Orchestrator（编排）阶段
# ============================================================

class OrchestratorInput(BaseModel):
    task_id: str
    topic: str
    max_items: int = Field(default=10, ge=1, le=20)
    min_content_length: int = 10
    include_charts: bool = True
    dimensions: List[str] = Field(default_factory=list)
    start_stage: Optional[str] = None
    reentry_context: Optional[str] = None
    previous_output: Optional[Dict[str, Any]] = None

class OrchestratorOutput(BaseModel):
    task_id: str
    topic: str
    status: str  # created / queued / collecting / cleaning / analyzing / reporting / completed / failed
    started_at: datetime
    ended_at: Optional[datetime] = None
    collected_count: int = 0
    cleaned_count: int = 0
    analyzer_output: Optional[AnalyzerOutput] = None
    reporter_output: Optional[ReporterOutput] = None
    error_message: Optional[str] = None
    partial_results: Optional[Dict[str, Any]] = None

# ============================================================
# Intent Classification（意图分类）阶段
# ============================================================

IntentType = Literal["market_insight", "general_question", "workflow_reentry"]


class IntentResult(BaseModel):
    intent_type: IntentType
    target_stage: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning: str = ""
    user_feedback: str = ""


class ReentryRequest(BaseModel):
    workflow_id: str
    target_stage: str
    user_feedback: str = ""
