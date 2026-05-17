from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import uuid
from datetime import datetime

# --- Step 9: Collector Schemas ---
class CollectorInput(BaseModel):
    task_id: str
    topic: str
    max_items: int = Field(default=5, ge=1, le=20)
    search_categories: Optional[List[str]] = None

class CollectedItem(BaseModel):
    source_type: str # 'search', 'crawler', 'document', 'datasource'
    source_uri: str
    title: str
    content: str
    metadata: Dict[str, Any] = {}

class CollectorOutput(BaseModel):
    task_id: str
    success: bool
    items: List[CollectedItem] = []
    error: Optional[str] = None

# --- Step 10: Cleaner Schemas ---
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

# --- Step 11: Analyzer Schemas ---
class Insight(BaseModel):
    conclusion: str
    evidence: List[str] # List of source_uris or specific reference tags
    confidence: float = Field(..., ge=0.0, le=1.0)
    category: str = Field(default="general") # 'trend', 'competitor', 'risk', 'opportunity', 'general'

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

# --- Step 12: Reporter Schemas ---
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

# --- Step 13: Orchestrator Schemas ---
class OrchestratorInput(BaseModel):
    task_id: str
    topic: str
    max_items: int = Field(default=5, ge=1, le=20)
    min_content_length: int = 20
    include_charts: bool = True

class OrchestratorOutput(BaseModel):
    task_id: str
    topic: str
    status: str # 'created', 'queued', 'collecting', 'cleaning', 'analyzing', 'reporting', 'completed', 'failed'
    started_at: datetime
    ended_at: Optional[datetime] = None
    collected_count: int = 0
    cleaned_count: int = 0
    analyzer_output: Optional[AnalyzerOutput] = None
    reporter_output: Optional[ReporterOutput] = None
    error_message: Optional[str] = None
