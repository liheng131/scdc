import json
import logging
import os
from copy import deepcopy
from threading import Lock
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "runtime_config.json")

_DEFAULTS = {
    "llm_provider": settings.llm_provider,
    "llm_api_key": settings.llm_api_key,
    "llm_base_url": settings.ollama_base_url,
    "default_model": settings.default_model,
    "temperature": 0.5,
    "max_tokens": 4096,
}


class RuntimeConfig:
    def __init__(self):
        self._config: dict = {}
        self._lock = Lock()
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            self.load()

    def load(self):
        with self._lock:
            self._config = deepcopy(_DEFAULTS)
            try:
                if os.path.exists(_CONFIG_FILE):
                    with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                        file_data = json.load(f)
                    if isinstance(file_data, dict):
                        for key in _DEFAULTS:
                            if key in file_data:
                                self._config[key] = file_data[key]
                    logger.info("Runtime config loaded from %s", _CONFIG_FILE)
                else:
                    logger.info("No runtime config file found, using defaults")
            except Exception:
                logger.exception("Failed to load runtime config, using defaults")
                self._config = deepcopy(_DEFAULTS)
            self._loaded = True

    def save(self):
        with self._lock:
            try:
                os.makedirs(os.path.dirname(_CONFIG_FILE), exist_ok=True)
                with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(self._config, f, ensure_ascii=False, indent=2)
                logger.info("Runtime config saved to %s", _CONFIG_FILE)
            except Exception:
                logger.exception("Failed to save runtime config")

    def get_all(self) -> dict:
        self._ensure_loaded()
        with self._lock:
            return deepcopy(self._config)

    def get(self, key: str, default=None):
        self._ensure_loaded()
        with self._lock:
            return self._config.get(key, default)

    def update(self, data: dict):
        valid_keys = set(_DEFAULTS.keys())
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        if "temperature" in filtered:
            try:
                t = float(filtered["temperature"])
                if t < 0.0 or t > 1.0:
                    raise ValueError("temperature must be between 0.0 and 1.0")
                filtered["temperature"] = t
            except (TypeError, ValueError):
                raise ValueError("temperature must be a float between 0.0 and 1.0")
        if "max_tokens" in filtered:
            try:
                mt = int(filtered["max_tokens"])
                if mt <= 0:
                    raise ValueError("max_tokens must be positive")
                filtered["max_tokens"] = mt
            except (TypeError, ValueError):
                raise ValueError("max_tokens must be a positive integer")
        with self._lock:
            self._config.update(filtered)
        self.save()
        return self.get_all()

    async def get_default_model_config(self, model_type: str) -> Optional[dict]:
        from app.models.ai_model_config import AiModelConfig
        from app.core.db import async_session_factory
        from app.core.security import decrypt_api_key

        try:
            async with async_session_factory() as session:
                from sqlalchemy import select
                result = await session.execute(
                    select(AiModelConfig).where(
                        AiModelConfig.model_type == model_type,
                        AiModelConfig.is_default == True
                    ).limit(1)
                )
                config = result.scalar_one_or_none()
                if config is None:
                    logger.debug("No default %s model config found in database", model_type)
                    return None
                logger.info("Loaded default %s model config from database: provider=%s, model=%s",
                            model_type, config.provider, config.model_name)
                return {
                    "provider": config.provider,
                    "model_name": config.model_name,
                    "model_type": config.model_type,
                    "base_url": config.base_url,
                    "api_key": decrypt_api_key(config.api_key),
                }
        except Exception:
            logger.warning("Failed to load default %s model config from database, falling back to settings", model_type)
            return None


rumtime_config = RuntimeConfig()


def get_default_model_config_sync(model_type: str) -> Optional[dict]:
    return None