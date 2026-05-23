"""
AI Agent API 路由

提供单阶段 Agent 执行和全流程编排（orchestrate）端点。

五个端点分别对应 Agent 流水线的五个阶段：
  /collect    → CollectorAgent（数据采集）
  /clean      → CleanerAgent（数据清洗）
  /analyze    → AnalyzerAgent（AI 分析）
  /report     → ReporterAgent（报告生成）
  /orchestrate → OrchestratorAgent（全流程自动编排，串联以上四阶段）

各 Agent 实例在模块加载时创建，复用避免每次请求重复初始化。
"""

from typing import Any
from fastapi import APIRouter, Depends
from app.api.responses import success_response, ResponseModel
from app.schemas.agent import CollectorInput, CollectorOutput, CleanerInput, CleanerOutput, AnalyzerInput, AnalyzerOutput, ReporterInput, ReporterOutput, OrchestratorInput, OrchestratorOutput
from app.agents.collector import CollectorAgent
from app.agents.cleaner import CleanerAgent
from app.agents.analyzer import AnalyzerAgent
from app.agents.reporter import ReporterAgent
from app.agents.orchestrator import OrchestratorAgent
from app.api.deps import get_current_active_user
from app.models.user import User

router = APIRouter()
# 各阶段 Agent 单例，模块加载时初始化
collector_agent = CollectorAgent()
cleaner_agent = CleanerAgent()
analyzer_agent = AnalyzerAgent()
reporter_agent = ReporterAgent()
orchestrator_agent = OrchestratorAgent()

@router.post("/collect", response_model=ResponseModel[CollectorOutput])
async def trigger_collection(
    request: CollectorInput,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """触发数据采集阶段（搜索聚合、爬虫抓取）"""
    result = await collector_agent.execute(request)
    return success_response(data=result)

@router.post("/clean", response_model=ResponseModel[CleanerOutput])
async def trigger_cleaning(
    request: CleanerInput,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """触发数据清洗阶段（去重、过滤低质内容）"""
    result = await cleaner_agent.execute(request)
    return success_response(data=result)

@router.post("/analyze", response_model=ResponseModel[AnalyzerOutput])
async def trigger_analyzing(
    request: AnalyzerInput,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """触发 AI 分析阶段（LLM 深度分析清洗后的内容）"""
    result = await analyzer_agent.execute(request)
    return success_response(data=result)

@router.post("/report", response_model=ResponseModel[ReporterOutput])
async def trigger_reporting(
    request: ReporterInput,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """触发报告生成阶段（根据分析结果生成结构化报告）"""
    result = await reporter_agent.execute(request)
    return success_response(data=result)

@router.post("/orchestrate", response_model=ResponseModel[OrchestratorOutput])
async def trigger_orchestrating(
    request: OrchestratorInput,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    触发全流程自动化编排

    OrchestratorAgent 将依次执行：
    collecting → cleaning → analyzing → reporting
    任一阶段失败将中止后续阶段并返回失败状态。
    """
    result = await orchestrator_agent.execute(request)
    return success_response(data=result)
