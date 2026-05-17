from fastapi import APIRouter
from app.api.responses import success_response, ResponseModel
from app.api.routes import auth, data_sources, parsers, crawlers, search, agents, tasks, triggers, schedules, events, notifications, reports, templates

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(data_sources.router, prefix="/data-sources", tags=["data-sources"])
api_router.include_router(parsers.router, prefix="/parsers", tags=["parsers"])
api_router.include_router(crawlers.router, prefix="/crawlers", tags=["crawlers"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(triggers.router, prefix="/triggers", tags=["triggers"])
api_router.include_router(schedules.router, prefix="/schedules", tags=["schedules"])
api_router.include_router(events.router, prefix="/events", tags=["events"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(templates.router, prefix="/templates", tags=["templates"])

@api_router.get("/health", response_model=ResponseModel)
async def health_check():
    from app.core.config import settings
    return success_response(data={"version": "1.0.0", "environment": settings.app_env})
