from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.api.responses import success_response, ResponseModel
from app.core.runtime_config import rumtime_config
from app.core.security import encrypt_api_key, decrypt_api_key
from app.models.ai_model_config import AiModelConfig
from app.models.user import User

router = APIRouter()


class RuntimeConfigUpdate(BaseModel):
    llm_provider: str | None = None
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    default_model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class AiModelCreate(BaseModel):
    provider: str = Field(..., min_length=1, max_length=100)
    model_name: str = Field(..., min_length=1, max_length=255)
    model_type: str = Field(..., pattern=r"^(llm|embedding|rerank)$")
    base_url: str = Field(..., min_length=1, max_length=500)
    api_key: str = ""


class AiModelUpdate(BaseModel):
    provider: str | None = Field(None, max_length=100)
    model_name: str | None = Field(None, max_length=255)
    model_type: str | None = Field(None, pattern=r"^(llm|embedding|rerank)$")
    base_url: str | None = Field(None, max_length=500)
    api_key: str | None = None


VALID_MODEL_TYPES = {"llm", "embedding", "rerank"}


def _config_to_dict(config: AiModelConfig) -> dict:
    return {
        "id": config.id,
        "provider": config.provider,
        "model_name": config.model_name,
        "model_type": config.model_type,
        "base_url": config.base_url,
        "api_key": decrypt_api_key(config.api_key),
        "is_default": config.is_default,
        "created_at": config.created_at.isoformat() if config.created_at else None,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }


@router.get("/", response_model=ResponseModel)
async def get_runtime_settings() -> Any:
    config = rumtime_config.get_all()
    return success_response(data=config)


@router.put("/", response_model=ResponseModel)
async def update_runtime_settings(request: RuntimeConfigUpdate) -> Any:
    update_data = request.model_dump(exclude_none=True)
    updated = rumtime_config.update(update_data)
    return success_response(data=updated)


@router.get("/llm-health", response_model=ResponseModel)
async def check_llm_health() -> Any:
    provider = rumtime_config.get("llm_provider", "ollama")
    base_url = rumtime_config.get("llm_base_url", "").rstrip("/")
    api_key = rumtime_config.get("llm_api_key", "")

    try:
        if provider == "gpustack":
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{base_url}/v1/models", headers=headers)
                resp.raise_for_status()
                data = resp.json()
                all_models = data.get("data", [])
                models = [m.get("id", "") for m in all_models]
        else:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{base_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]

        return success_response(data={
            "status": "ok",
            "provider": provider,
            "base_url": base_url,
            "models": models,
        })
    except Exception as e:
        return success_response(data={
            "status": "unavailable",
            "provider": provider,
            "base_url": base_url,
            "error": str(e)[:500],
        })


@router.get("/ai-models", response_model=ResponseModel)
async def list_ai_models(
    model_type: Optional[str] = Query(None, description="Filter by model type: llm, embedding, rerank"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
) -> Any:
    stmt = select(AiModelConfig)
    if model_type:
        stmt = stmt.where(AiModelConfig.model_type == model_type)
    stmt = stmt.order_by(AiModelConfig.id)
    result = await session.execute(stmt)
    configs = result.scalars().all()
    return success_response(data=[_config_to_dict(c) for c in configs])


@router.post("/ai-models", response_model=ResponseModel)
async def create_ai_model(
    body: AiModelCreate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
) -> Any:
    config = AiModelConfig(
        provider=body.provider,
        model_name=body.model_name,
        model_type=body.model_type,
        base_url=body.base_url.rstrip("/"),
        api_key=encrypt_api_key(body.api_key) if body.api_key else "",
        is_default=False,
    )

    existing_result = await session.execute(
        select(AiModelConfig).where(AiModelConfig.model_type == body.model_type)
    )
    if existing_result.first() is None:
        config.is_default = True

    session.add(config)
    await session.commit()
    await session.refresh(config)
    return success_response(data=_config_to_dict(config))


@router.put("/ai-models/{config_id}", response_model=ResponseModel)
async def update_ai_model(
    config_id: int,
    body: AiModelUpdate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
) -> Any:
    result = await session.execute(
        select(AiModelConfig).where(AiModelConfig.id == config_id)
    )
    config = result.scalars().first()
    if not config:
        raise HTTPException(status_code=404, detail="AI model config not found")

    update_data = body.model_dump(exclude_none=True)
    api_key_value = update_data.pop("api_key", None)

    for field, value in update_data.items():
        if field == "base_url" and value:
            value = value.rstrip("/")
        setattr(config, field, value)

    if api_key_value is not None:
        if api_key_value == "":
            pass
        else:
            config.api_key = encrypt_api_key(api_key_value)

    await session.commit()
    await session.refresh(config)
    return success_response(data=_config_to_dict(config))


@router.delete("/ai-models/{config_id}", response_model=ResponseModel)
async def delete_ai_model(
    config_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
) -> Any:
    result = await session.execute(
        select(AiModelConfig).where(AiModelConfig.id == config_id)
    )
    config = result.scalars().first()
    if not config:
        raise HTTPException(status_code=404, detail="AI model config not found")

    was_default = config.is_default
    model_type = config.model_type

    await session.delete(config)

    if was_default:
        remaining_result = await session.execute(
            select(AiModelConfig)
            .where(AiModelConfig.model_type == model_type)
            .order_by(AiModelConfig.id)
        )
        remaining = remaining_result.scalars().all()
        if remaining:
            remaining[0].is_default = True

    await session.commit()
    return success_response(msg="AI model config deleted")


@router.post("/ai-models/{config_id}/set-default", response_model=ResponseModel)
async def set_default_ai_model(
    config_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
) -> Any:
    result = await session.execute(
        select(AiModelConfig).where(AiModelConfig.id == config_id)
    )
    config = result.scalars().first()
    if not config:
        raise HTTPException(status_code=404, detail="AI model config not found")

    same_type_result = await session.execute(
        select(AiModelConfig).where(
            AiModelConfig.model_type == config.model_type,
            AiModelConfig.id != config_id,
        )
    )
    for c in same_type_result.scalars().all():
        c.is_default = False

    config.is_default = True
    await session.commit()
    await session.refresh(config)
    return success_response(data=_config_to_dict(config))


@router.get("/ai-models/default", response_model=ResponseModel)
async def get_default_ai_model(
    model_type: str = Query(..., description="Model type: llm, embedding, rerank"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
) -> Any:
    result = await session.execute(
        select(AiModelConfig).where(
            AiModelConfig.model_type == model_type,
            AiModelConfig.is_default == True,
        )
    )
    config = result.scalars().first()
    if not config:
        raise HTTPException(status_code=404, detail="No default config found for this model type")
    return success_response(data=_config_to_dict(config))


@router.post("/ai-models/{config_id}/test", response_model=ResponseModel)
async def test_ai_model(
    config_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
) -> Any:
    result = await session.execute(
        select(AiModelConfig).where(AiModelConfig.id == config_id)
    )
    config = result.scalars().first()
    if not config:
        raise HTTPException(status_code=404, detail="AI model config not found")

    base_url = config.base_url.rstrip("/")
    api_key = decrypt_api_key(config.api_key)
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    try:
        if config.model_type == "llm":
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{base_url}/v1/chat/completions",
                    json={
                        "model": config.model_name,
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 1,
                    },
                    headers=headers | {"Content-Type": "application/json"},
                )
                resp.raise_for_status()
            return success_response(data={"status": "ok"})

        elif config.model_type == "embedding":
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{base_url}/v1/embeddings",
                    json={"input": ["test"], "model": config.model_name},
                    headers=headers,
                )
                resp.raise_for_status()
            return success_response(data={"status": "ok"})

        elif config.model_type == "rerank":
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{base_url}/v1/rerank",
                    json={
                        "model": config.model_name,
                        "query": "test query",
                        "documents": ["test document"],
                    },
                    headers=headers,
                )
                resp.raise_for_status()
            return success_response(data={"status": "ok"})

        else:
            raise HTTPException(status_code=400, detail=f"Unknown model type: {config.model_type}")

    except HTTPException:
        raise
    except Exception as e:
        return success_response(data={
            "status": "unavailable",
            "error": str(e)[:500],
        })