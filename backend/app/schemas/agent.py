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

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import uuid
from datetime import datetime

# ============================================================
# Collector（采集）阶段
# ============================================================

class CollectorInput(BaseModel):
    task_id: str
    topic: str
    max_items: int = Field(default=5, ge=1, le=20)
    search_categories: Optional[List[str]] = None

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

# ============================================================
# Analyzer（分析）阶段
# ============================================================

class Insight(BaseModel):
    conclusion: str
    evidence: List[str]  # 证据来源 URI 列表
    confidence: float = Field(..., ge=0.0, le=1.0)
    category: str = Field(default="general")  # trend / competitor / risk / opportunity / general

class AnalyzerInput(BaseModel):
    task_id: str
    topic: str
    cleaned_items: List[CleanedItem]

class AnalyzerOutput(BaseModel):
    task_id: str
    success: bool
    summary: str
    insights: List[Insight] = []
    error: Optional[str] = None

# ============================================================
# Reporter（报告）阶段
# ============================================================

class ReporterInput(BaseModel):
    task_id: str
    topic: str
    analyzer_output: AnalyzerOutput
    include_charts: bool = True

class ReportSection(BaseModel):
    title: str
    content: str

class ReporterOutput(BaseModel):
    task_id: str
    success: bool
    markdown_report: str
    sections: List[ReportSection] = []
    chart_configs: List[Dict[str, Any]] = []
    error: Optional[str] = None

# ============================================================
# Orchestrator（编排）阶段
# ============================================================

class OrchestratorInput(BaseModel):
    task_id: str
    topic: str
    max_items: int = Field(default=5, ge=1, le=20)
    min_content_length: int = 20
    include_charts: bool = True

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
