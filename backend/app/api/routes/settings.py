from typing import Any, Optional
import json
import os

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


# ===== Dispatch Config (cron, email, webhook) =====

_DISPATCH_CONFIG = {
    "cron_schedule": "0 8 * * *",
    "notification_email": "",
    "webhook_url": "",
}

_dispatch_config_file = os.path.join(os.path.dirname(__file__), "..", "..", "..", "dispatch_config.json")


def _load_dispatch_config() -> dict:
    try:
        if os.path.exists(_dispatch_config_file):
            with open(_dispatch_config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                _DISPATCH_CONFIG.update(data)
    except Exception:
        pass
    return dict(_DISPATCH_CONFIG)


def _save_dispatch_config(data: dict):
    try:
        os.makedirs(os.path.dirname(_dispatch_config_file), exist_ok=True)
        with open(_dispatch_config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class DispatchConfigUpdate(BaseModel):
    cron_schedule: str = ""
    notification_email: str = ""
    webhook_url: str = ""


@router.get("/dispatch-config", response_model=ResponseModel)
async def get_dispatch_config(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    return success_response(data=_load_dispatch_config())


@router.put("/dispatch-config", response_model=ResponseModel)
async def update_dispatch_config(
    body: DispatchConfigUpdate,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    data = body.model_dump()
    _DISPATCH_CONFIG.update(data)
    _save_dispatch_config(_DISPATCH_CONFIG)
    return success_response(data=_DISPATCH_CONFIG)


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
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{base_url}/v1/chat/completions",
                    json={
                        "model": config.model_name,
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 1,
                    },
                    headers=headers | {"Content-Type": "application/json"},
                )

                if resp.status_code == 401 or resp.status_code == 403:
                    raise HTTPException(
                        status_code=401,
                        detail=f"认证失败：API Key 无效或已过期（HTTP {resp.status_code}）",
                    )
                if resp.status_code == 404:
                    raise HTTPException(
                        status_code=404,
                        detail=f"模型 '{config.model_name}' 不存在，请检查模型名",
                    )
                if resp.status_code == 429:
                    raise HTTPException(
                        status_code=429,
                        detail="请求频率过高，请稍后重试",
                    )
                if resp.status_code >= 400:
                    try:
                        error_body = resp.json()
                        error_msg = error_body.get("error", {}).get("message", str(error_body))
                    except Exception:
                        error_msg = resp.text[:200]
                    raise HTTPException(
                        status_code=resp.status_code,
                        detail=f"模型服务返回错误 ({resp.status_code}): {error_msg}",
                    )

                data = resp.json()
                if not data.get("choices"):
                    raise HTTPException(
                        status_code=502,
                        detail=f"模型 '{config.model_name}' 未返回任何推理结果，可能该模型不可用或不存在",
                    )
                first_choice = data["choices"][0]
                if not first_choice.get("message"):
                    raise HTTPException(
                        status_code=502,
                        detail="推理响应格式异常：缺少 message 字段",
                    )

            return success_response(data={"status": "ok", "message": data["choices"][0]["message"].get("content", "")[:50]})

        elif config.model_type == "embedding":
            provider = (config.provider or "ollama").lower()
            async with httpx.AsyncClient(timeout=30) as client:
                if provider == "ollama":
                    # Ollama 原生端点：POST /api/embeddings，payload {"model":..., "prompt":...}
                    # （Ollama 0.1.32+ 才有 /v1/embeddings，但 /api/embeddings 一直存在）
                    resp = await client.post(
                        f"{base_url}/api/embeddings",
                        json={"model": config.model_name, "prompt": "test"},
                        headers=headers | {"Content-Type": "application/json"},
                    )
                else:
                    # OpenAI 兼容端点（GPUStack、Ollama 0.1.32+、vLLM、OpenAI 等）
                    resp = await client.post(
                        f"{base_url}/v1/embeddings",
                        json={"input": ["test"], "model": config.model_name},
                        headers=headers | {"Content-Type": "application/json"},
                    )

                if resp.status_code == 401 or resp.status_code == 403:
                    raise HTTPException(
                        status_code=401,
                        detail=f"认证失败：API Key 无效或已过期（HTTP {resp.status_code}）",
                    )
                if resp.status_code == 404:
                    model_hint = ""
                    # 尝试列出可用模型供用户参考
                    try:
                        list_path = "/api/tags" if provider == "ollama" else "/v1/models"
                        list_resp = await client.get(f"{base_url}{list_path}", headers=headers)
                        if list_resp.status_code == 200:
                            list_data = list_resp.json()
                            if provider == "ollama":
                                names = [m.get("name", "") for m in list_data.get("models", [])]
                            else:
                                names = [m.get("id", "") for m in list_data.get("data", [])]
                            if names:
                                model_hint = f"；该服务可用模型：{', '.join(names[:10])}"
                    except Exception:
                        pass
                    raise HTTPException(
                        status_code=404,
                        detail=f"模型 '{config.model_name}' 不存在，请检查模型名{model_hint}",
                    )
                if resp.status_code >= 400:
                    try:
                        error_body = resp.json()
                        error_msg = error_body.get("error", {}).get("message", str(error_body))
                    except Exception:
                        error_msg = resp.text[:200]
                    raise HTTPException(
                        status_code=resp.status_code,
                        detail=f"模型服务返回错误 ({resp.status_code}): {error_msg}",
                    )

                data = resp.json()
                if provider == "ollama":
                    # Ollama 原生返回：{"embedding": [...]}  （有时带 "model" 字段，无 data 包装）
                    embedding = data.get("embedding", [])
                else:
                    # OpenAI 兼容返回：{"data": [{"embedding": [...], "index": 0}]}
                    if not data.get("data"):
                        raise HTTPException(
                            status_code=502,
                            detail=f"模型 '{config.model_name}' 未返回 embedding 结果",
                        )
                    embedding = data["data"][0].get("embedding", [])

                if not embedding or len(embedding) == 0:
                    raise HTTPException(
                        status_code=502,
                        detail="Embedding 响应格式异常：向量数据为空",
                    )

            return success_response(data={"status": "ok", "dimension": len(embedding)})

        elif config.model_type == "rerank":
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{base_url}/v1/rerank",
                    json={
                        "model": config.model_name,
                        "query": "test query",
                        "documents": ["test document"],
                    },
                    headers=headers | {"Content-Type": "application/json"},
                )

                if resp.status_code == 401 or resp.status_code == 403:
                    raise HTTPException(
                        status_code=401,
                        detail=f"认证失败：API Key 无效或已过期（HTTP {resp.status_code}）",
                    )
                if resp.status_code == 404:
                    raise HTTPException(
                        status_code=404,
                        detail=f"模型 '{config.model_name}' 不存在，请检查模型名",
                    )
                if resp.status_code >= 400:
                    try:
                        error_body = resp.json()
                        error_msg = error_body.get("error", {}).get("message", str(error_body))
                    except Exception:
                        error_msg = resp.text[:200]
                    raise HTTPException(
                        status_code=resp.status_code,
                        detail=f"模型服务返回错误 ({resp.status_code}): {error_msg}",
                    )

                data = resp.json()
                results = data.get("results", data.get("data", []))
                if not results:
                    raise HTTPException(
                        status_code=502,
                        detail=f"模型 '{config.model_name}' 未返回 rerank 结果",
                    )

            return success_response(data={"status": "ok", "result_count": len(results)})

        else:
            raise HTTPException(status_code=400, detail=f"Unknown model type: {config.model_type}")

    except HTTPException:
        raise
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail=f"无法连接到服务 '{base_url}'，请检查服务地址和网络",
        )
    except httpx.ConnectTimeout:
        raise HTTPException(
            status_code=504,
            detail=f"连接超时：服务 '{base_url}' 未在 30 秒内响应",
        )
    except httpx.ReadTimeout:
        raise HTTPException(
            status_code=504,
            detail=f"读取超时：服务 '{base_url}' 响应过慢",
        )
    except (httpx.RemoteProtocolError, httpx.RequestError) as e:
        # 典型场景：base_url 填成了 Docker 网络名（如 http://ollama:11434），
        # 但后端是 host 上跑的 uvicorn，DNS 解析失败 / TCP 直接被拒
        # → httpx 抛 RemoteProtocolError 或 ServerDisconnected
        raise HTTPException(
            status_code=502,
            detail=(
                f"无法与服务 '{base_url}' 建立有效连接：{str(e)[:120]}。"
                f"请检查：① 服务地址是否可访问（host uvicorn 模式填 http://localhost:11434，"
                f"Docker backend 容器模式填 Docker 网络名如 http://ollama:11434）；"
                f"② 端口是否被防火墙拦截。"
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"测试连接时发生未知错误: {str(e)[:300]}",
        )