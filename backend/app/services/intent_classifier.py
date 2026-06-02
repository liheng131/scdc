import json
import logging
import traceback
import httpx
from typing import Dict, Any, Optional

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import settings
from app.core.runtime_config import rumtime_config

logger = logging.getLogger(__name__)


class IntentClassifier:
    def __init__(self):
        self.llm_provider = rumtime_config.get("llm_provider")
        self.default_model = rumtime_config.get("default_model")
        self.llm_base_url = rumtime_config.get("llm_base_url")
        self.llm_api_key = settings.llm_api_key
        self._db_config_loaded = False

        self._build_llm_config()

    def _build_llm_config(self):
        if self.llm_provider == "gpustack":
            self.llm_url = f"{self.llm_base_url.rstrip('/')}/v1/chat/completions"
            self.headers = {
                "Authorization": f"Bearer {self.llm_api_key}",
                "Content-Type": "application/json",
            }
        else:
            self.llm_url = f"{self.llm_base_url.rstrip('/')}/api/generate"
            self.headers = {}

    async def _ensure_db_config(self):
        if self._db_config_loaded:
            return
        self._db_config_loaded = True
        try:
            db_config = await rumtime_config.get_default_model_config("llm")
            if db_config:
                self.llm_provider = db_config["provider"].lower() if db_config["provider"] else self.llm_provider
                self.default_model = db_config["model_name"] or self.default_model
                if db_config["base_url"]:
                    self.llm_base_url = db_config["base_url"]
                if db_config["api_key"]:
                    self.llm_api_key = db_config["api_key"]
                self._build_llm_config()
        except Exception:
            pass

    def _clean_json_response(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def _build_classification_prompt(
        self,
        message: str,
        conversation_history: list = None,
        has_existing_report: bool = False,
    ) -> str:
        history_text = ""
        if conversation_history:
            recent = conversation_history[-6:]
            history_parts = []
            for msg in recent:
                role = "\u7528\u6237" if msg.get("role") == "user" else "\u52a9\u624b"
                history_parts.append(f"{role}: {msg.get('content', '')}")
            history_text = "\n".join(history_parts)

        report_context = "\u7528\u6237\u5f53\u524d\u6709\u5df2\u751f\u6210\u7684\u62a5\u544a\u3002" if has_existing_report else "\u7528\u6237\u5f53\u524d\u8fd8\u6ca1\u6709\u751f\u6210\u62a5\u544a\u3002"

        template = """\u4f60\u662f\u4e00\u4e2a\u610f\u56fe\u5206\u7c7b\u5668\u3002\u8bf7\u5c06\u4ee5\u4e0b\u7528\u6237\u6d88\u606f\u5206\u7c7b\u4e3a\u4e09\u79cd\u610f\u56fe\u4e4b\u4e00\u3002

\u5bf9\u8bdd\u5386\u53f2\uff1a
{history_text}

{report_context}

\u7528\u6237\u6700\u65b0\u6d88\u606f\uff1a
"{message}"

\u610f\u56fe\u7c7b\u578b\u5b9a\u4e49\uff1a
1. **market_insight**\uff08\u5e02\u573a\u6d1e\u5bdf\uff09\uff1a\u7528\u6237\u60f3\u8981\u8fdb\u884c\u5e02\u573a/\u884c\u4e1a\u5206\u6790\u3001\u8d8b\u52bf\u7814\u7a76\u3001\u7ade\u4e89\u683c\u5c40\u7814\u7a76\u3001\u5546\u4e1a\u60c5\u62a5\u6536\u96c6\u3002\u4f8b\u5982\uff1a\u201c\u5e2e\u6211\u5206\u6790\u65b0\u80fd\u6e90\u6c7d\u8f66\u5e02\u573a\u201d\u3001\u201c\u667a\u80fd\u624b\u673a\u884c\u4e1a\u8d8b\u52bf\u5982\u4f55\u201d\u3001\u201cAI\u82af\u7247\u7ade\u4e89\u683c\u5c40\u201d
2. **general_question**\uff08\u4e00\u822c\u95ee\u9898\uff09\uff1a\u95f2\u804a\u3001\u975e\u5206\u6790\u7c7b\u95ee\u9898\uff0c\u5982\u201c\u4f60\u80fd\u505a\u4ec0\u4e48\uff1f\u201d\u3001\u201c\u4eca\u5929\u5929\u6c14\u600e\u4e48\u6837\u201d\u3001\u6570\u5b66\u8ba1\u7b97\u3001\u201c\u4f60\u597d\u201d\u3001\u6253\u62db\u547c\u7b49\u3002\u8fd9\u4e9b\u4e0e\u5e02\u573a\u5206\u6790\u65e0\u5173\u7684\u95ee\u9898\u3002
3. **workflow_reentry**\uff08\u5de5\u4f5c\u6d41\u91cd\u5165\uff09\uff1a\u7528\u6237\u60f3\u8981\u91cd\u505a/\u6539\u8fdb\u5df2\u5b8c\u6210\u62a5\u544a\u7684\u67d0\u4e2a\u7279\u5b9a\u9636\u6bb5\u3002\u9700\u8981\u8bc6\u522btarget_stage\uff1a
   - \u63d0\u5230\u201c\u62a5\u544a\u4e0d\u591f\u8be6\u7ec6\u201d\u201c\u91cd\u65b0\u751f\u6210\u62a5\u544a\u201d\u201c\u62a5\u544a\u683c\u5f0f\u4e0d\u597d\u201d\u201c\u6539\u8fdb\u62a5\u544a\u201d \u2192 target_stage = "reporting"
   - \u63d0\u5230\u201c\u5206\u6790\u4e0d\u591f\u201d\u201c\u91cd\u65b0\u5206\u6790\u201d\u201c\u7ef4\u5ea6\u4e0d\u591f\u201d\u201c\u5206\u6790\u6df1\u5ea6\u4e0d\u591f\u201d \u2192 target_stage = "analyzing"
   - \u63d0\u5230\u201c\u6570\u636e\u4e0d\u51c6\u201d\u201c\u6570\u636e\u865a\u5047\u201d\u201c\u91cd\u65b0\u641c\u7d22\u201d\u201c\u91cd\u65b0\u91c7\u96c6\u201d\u201c\u6570\u636e\u6765\u6e90\u4e0d\u591f\u201d \u2192 target_stage = "collecting"

\u5bf9\u4e8eworkflow_reentry\uff0c\u8fd8\u9700\u8981\u63d0\u53d6user_feedback\uff08\u7528\u6237\u5e0c\u671b\u6dfb\u52a0\u7684\u989d\u5916\u7ea6\u675f\u6761\u4ef6\uff09\u3002

\u8bf7\u4e25\u683c\u6309\u4ee5\u4e0bJSON\u683c\u5f0f\u8f93\u51fa\uff0c\u4e0d\u8981\u5305\u542b\u4efb\u4f55\u5176\u4ed6\u5185\u5bb9\uff1a
{{
  "intent_type": "market_insight|general_question|workflow_reentry",
  "target_stage": "reporting|analyzing|collecting|null",
  "confidence": 0.0-1.0,
  "reasoning": "\u7b80\u77ed\u5206\u7c7b\u7406\u7531\uff08\u4e00\u53e5\u8bdd\uff09",
  "user_feedback": "\u7528\u6237\u7684\u5177\u4f53\u53cd\u9988\u63cf\u8ff0\uff08\u4ec5workflow_reentry\u65f6\u9700\u8981\uff0c\u5426\u5219\u4e3anull\uff09"
}}"""
        prompt = template.format(
            history_text=history_text if history_text else "（无历史记录）",
            report_context=report_context,
            message=message,
        )
        return prompt

    @retry(
        stop=stop_after_attempt(1),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, json.JSONDecodeError)),
        reraise=True
    )
    async def _call_llm(self, prompt: str, timeout: int = 30) -> Dict[str, Any]:
        if self.llm_provider == "gpustack":
            payload = {
                "model": self.default_model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 512,
            }
        else:
            payload = {
                "model": self.default_model,
                "prompt": prompt,
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.1}
            }

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(self.llm_url, json=payload, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()

            if self.llm_provider == "gpustack":
                response_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                response_text = data.get("response", "")

            response_text = self._clean_json_response(response_text)
            if not response_text:
                raise json.JSONDecodeError("Empty response after cleaning", "", 0)
            return json.loads(response_text)

    async def classify(
        self,
        message: str,
        conversation_history: list = None,
        has_existing_report: bool = False,
    ) -> dict:
        await self._ensure_db_config()
        logger.info(f"IntentClassifier classifying message: '{message[:100]}...'")

        try:
            prompt = self._build_classification_prompt(message, conversation_history, has_existing_report)
            result = await self._call_llm(prompt, timeout=30)

            intent_type = result.get("intent_type", "market_insight")
            if intent_type not in ("market_insight", "general_question", "workflow_reentry"):
                logger.warning(f"Unknown intent_type '{intent_type}', defaulting to 'market_insight'")
                intent_type = "market_insight"

            target_stage = result.get("target_stage")
            if intent_type == "workflow_reentry":
                if target_stage not in ("reporting", "analyzing", "collecting"):
                    logger.warning(f"Invalid target_stage '{target_stage}' for workflow_reentry, defaulting to 'reporting'")
                    target_stage = "reporting"
            else:
                target_stage = None

            confidence = result.get("confidence", 0.5)
            try:
                confidence = float(confidence)
                confidence = max(0.0, min(1.0, confidence))
            except (TypeError, ValueError):
                confidence = 0.5

            reasoning = result.get("reasoning", "")
            user_feedback = result.get("user_feedback") if intent_type == "workflow_reentry" else None

            classification = {
                "intent_type": intent_type,
                "target_stage": target_stage,
                "confidence": confidence,
                "reasoning": reasoning,
                "user_feedback": user_feedback,
            }

            logger.info(f"Intent classification result: {intent_type}, confidence={confidence:.2f}")
            return classification

        except Exception as e:
            logger.error(f"Intent classification failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")
            logger.warning("Falling back to default intent: market_insight")
            return {
                "intent_type": "market_insight",
                "target_stage": None,
                "confidence": 0.3,
                "reasoning": f"Classification failed ({type(e).__name__}), defaulting to market_insight",
                "user_feedback": None,
            }