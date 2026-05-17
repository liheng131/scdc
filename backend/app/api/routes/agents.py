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
    result = await collector_agent.execute(request)
    return success_response(data=result)

@router.post("/clean", response_model=ResponseModel[CleanerOutput])
async def trigger_cleaning(
    request: CleanerInput,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    result = await cleaner_agent.execute(request)
    return success_response(data=result)

@router.post("/analyze", response_model=ResponseModel[AnalyzerOutput])
async def trigger_analyzing(
    request: AnalyzerInput,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    result = await analyzer_agent.execute(request)
    return success_response(data=result)

@router.post("/report", response_model=ResponseModel[ReporterOutput])
async def trigger_reporting(
    request: ReporterInput,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    result = await reporter_agent.execute(request)
    return success_response(data=result)

@router.post("/orchestrate", response_model=ResponseModel[OrchestratorOutput])
async def trigger_orchestrating(
    request: OrchestratorInput,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    result = await orchestrator_agent.execute(request)
    return success_response(data=result)
