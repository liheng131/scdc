import json
import logging
import httpx
from typing import Dict, Any, Optional

from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from app.core.config import settings
from app.core.runtime_config import rumtime_config

logger = logging.getLogger(__name__)


class IntentClassifier:
    def __init__(self):
        self.llm_provider = rumtime_config.get("llm_provider") or "ollama"
        self.default_model = rumtime_config.get("default_model") or settings.default_model
        self.llm_base_url = rumtime_config.get("llm_base_url") or settings.ollama_base_url
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
        include_history: bool = True,
    ) -> str:
        history_text = ""
        if include_history and conversation_history:
            recent = conversation_history[-6:]
            history_parts = []
            for msg in recent:
                role = "\u7528\u6237" if msg.get("role") == "user" else "\u52a9\u624b"
                history_parts.append(f"{role}: {msg.get('content', '')}")
            history_text = "\n".join(history_parts)

        report_context = "\u7528\u6237\u5f53\u524d\u6709\u5df2\u751f\u6210\u7684\u62a5\u544a\u3002" if has_existing_report else "\u7528\u6237\u5f53\u524d\u8fd8\u6ca1\u6709\u751f\u6210\u62a5\u544a\u3002"

        template = """\u3010\u91cd\u8981\u539f\u5219\u3011\u4f60\u5fc5\u987b**\u53ea\u6839\u636e\u7528\u6237\u6700\u65b0\u4e00\u6761\u6d88\u606f**\u5224\u65ad\u610f\u56fe\u7c7b\u578b\u3002
\u5bf9\u8bdd\u5386\u53f2**\u4ec5\u4f5c\u4e3a\u8f85\u52a9\u53c2\u8003**\uff1b\u5982\u679c\u5386\u53f2\u8bdd\u9898\u4e0e\u6700\u65b0\u6d88\u606f\u65e0\u5173\uff0c**\u4e0d\u8981\u88ab\u5386\u53f2\u8bdd\u9898\u5f71\u54cd**\u3002
\u4f8b\u5982\uff1a\u7528\u6237\u4e0a\u4e00\u8f6e\u95ee\u4e86"AI\u82af\u7247\u5e02\u573a\u5206\u6790"\uff08\u5df2\u751f\u6210\u62a5\u544a\uff09\uff0c\u8fd9\u4e00\u8f6e\u95ee\u4e0e\u5206\u6790\u65e0\u5173\u7684\u95ee\u9898\u2014\u2014\u8fd9\u5c5e\u4e8e **general_question**\uff0c**\u4e0d\u662f** workflow_reentry\u3002

\u3010\u95f2\u804a\u7279\u5f81\u8bc6\u522b\u3011\u4ee5\u4e0b\u60c5\u51b5\u4e00\u5f8b\u5224\u4e3a general_question\uff08\u65e0\u8bba\u5386\u53f2/\u62a5\u544a\u4e0a\u4e0b\u6587\uff09\uff1a
1. \u95ee\u5019\u5bd2\u6684\uff1a"\u4f60\u597d" "hi" "\u55e8" "\u5728\u5417" "\u518d\u89c1" "\u8c22\u8c22"
2. \u54a8\u8be2 AI \u80fd\u529b/\u8eab\u4efd\uff1a"\u4f60\u80fd\u505a\u4ec0\u4e48" "\u4f60\u662f\u4ec0\u4e48" "\u4f60\u662f\u8c01" "\u4f60\u4f1a\u4ec0\u4e48" "\u4f60\u80fd\u5e2e\u6211\u505a\u5565" "\u4f60\u6709\u4ec0\u4e48\u529f\u80fd"
3. \u957f\u5ea6 < 5 \u5b57\u4e14\u65e0\u540d\u8bcd\u6027\u4e3b\u9898\uff08"\u4ec0\u4e48\u662fX"\u662f\u54a8\u8be2\u6982\u5ff5\uff0cX \u662f\u540d\u8bcd\uff1b"\u4f60\u597d"\u662f\u5bd2\u6684\uff09

\u5bf9\u8bdd\u5386\u53f2\uff1a
{history_text}

{report_context}

\u7528\u6237\u6700\u65b0\u6d88\u606f\uff1a
"{message}"

\u610f\u56fe\u7c7b\u578b\u5b9a\u4e49\uff1a
1. **market_insight**\uff08\u5e02\u573a\u6d1e\u5bdf\uff09\uff1a\u7528\u6237\u60f3\u8981\u8fdb\u884c\u5e02\u573a/\u884c\u4e1a\u5206\u6790\u3001\u8d8b\u52bf\u7814\u7a76\u3001\u7ade\u4e89\u683c\u5c40\u7814\u7a76\u3001\u5546\u4e1a\u60c5\u62a5\u6536\u96c6\u3002\u4f8b\u5982\uff1a\u201c\u5e2e\u6211\u5206\u6790\u65b0\u80fd\u6e90\u6c7d\u8f66\u5e02\u573a\u201d\u3001\u201c\u667a\u80fd\u624b\u673a\u884c\u4e1a\u8d8b\u52bf\u5982\u4f55\u201d\u3001\u201cAI\u82af\u7247\u7ade\u4e89\u683c\u5c40\u201d\u3002
   \u53cd\u4f8b\uff1a\u7528\u6237\u4e0a\u4e00\u8f6e\u95ee\u4e86"AI\u82af\u7247\u5e02\u573a\u5206\u6790"\uff0c\u8fd9\u4e00\u8f6e\u95ee"\u4f60\u80fd\u505a\u4ec0\u4e48"\u2014\u2014\u8fd9\u5c5e\u4e8e general_question\uff0c\u4e0d\u662f market_insight\u3002
2. **general_question**\uff08\u4e00\u822c\u95ee\u9898\uff09\uff1a\u3010\u91cd\u70b9\u53cd\u4f8b\u3011\u95ee\u9898\u4e2d**\u4e0d\u5305\u542b\u4e0b\u9762\u8fd9\u4e9b\u91cd\u5165\u52a8\u8bcd\u77ed\u8bed**\u65f6\uff0c\u4e00\u5f8b\u5224\u4e3a general_question\uff1a"\u4f60\u80fd\u505a\u4ec0\u4e48\uff1f\u201d\u3001"\u4f60\u662f\u8c01\uff1f\u201d\u3001"\u4f60\u597d\u201d\u3001"\u4eca\u5929\u5929\u6c14\u600e\u4e48\u6837\u201d\u3001"\u6e29\u5ea6\u591a\u5c11\u5ea6\u201d\u3001"\u591a\u5c11\u4eba\u5728\u7528\u201d\u7b49\u95f2\u804a\u3001\u6253\u62db\u547c\u3001\u80fd\u529b\u54a8\u8be2\u3002\u8fd9\u4e9b\u4e0e\u5e02\u573a\u5206\u6790\u65e0\u5173\u7684\u95ee\u9898\u3002\u201c\u4f60\u80fd\u505a\u4ec0\u4e48\u201d\u3001\u201c\u4f60\u4f1a\u505a\u4ec0\u4e48\u201d\u3001\u201c\u4f60\u80fd\u5bf9\u8fd9\u4efd\u62a5\u544a\u505a\u4ec0\u4e48\u201d\u8fd9\u7c7b\u95ee\u9898\u4e0d\u8981\u5224\u4e3a workflow_reentry\u3002"\u4f60\u80fd\u505a\u4ec0\u4e48" "\u4f60\u662f\u4ec0\u4e48" "\u4f60\u662f\u8c01" "\u4f60\u4f1a\u4ec0\u4e48" "\u4f60\u80fd\u5e2e\u6211\u505a\u5565" \u2014\u2014 \u8fd9\u4e9b\u90fd\u5224\u4e3a general_question\u3002
3. **workflow_reentry**\uff08\u5de5\u4f5c\u6d41\u91cd\u5165\uff09\uff1a**\u5f3a\u7ea6\u675f**\uff1a\u4ec5\u5f53\u7528\u6237\u6d88\u606f\u663e\u5f0f\u5305\u542b\u4ee5\u4e0b **1 \u4e2a\u6216\u591a\u4e2a**\u52a8\u8bcd\u77ed\u8bed\u65f6\u624d\u5141\u8bb8\u5224\u4e3a workflow_reentry\uff1a
   - \u91cd\u65b0\u751f\u6210 / \u91cd\u65b0\u505a / \u91cd\u505a / \u91cd\u65b0\u5206\u6790 / \u91cd\u65b0\u641c\u7d22 / \u91cd\u65b0\u91c7\u96c6 / \u91cd\u65b0\u8dd1
   - \u4e0d\u591f\u8be6\u7ec6 / \u4e0d\u591f\u6df1 / \u4e0d\u591f\u5168 / \u6df1\u5ea6\u4e0d\u591f / \u7ef4\u5ea6\u4e0d\u591f / \u683c\u5f0f\u4e0d\u597d / \u62a5\u544a\u4e0d\u597d
   - \u6539\u8fdb / \u5b8c\u5584 / \u4f18\u5316 / \u8c03\u6574 / \u6539\u4e00\u4e0b / \u6539\u6539
   - \u518d\u5206\u6790 / \u518d\u641c\u7d22 / \u518d\u505a
   \u5426\u5219\u5373\u4f7f has_existing_report=True\uff0c\u4e5f\u4e0d\u5e94\u5224\u4e3a workflow_reentry\u3002\u9700\u8981\u8bc6\u522b target_stage\uff1a
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
        if not include_history:
            history_text = "（无需参考历史）"
        elif not history_text:
            history_text = "（无历史记录）"
        prompt = template.format(
            history_text=history_text,
            report_context=report_context,
            message=message,
        )
        return prompt

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(2),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, json.JSONDecodeError)),
        reraise=True
    )
    async def _call_llm(self, prompt: str, timeout: int = 10) -> Dict[str, Any]:
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

    async def _classify_internal(
        self,
        message: str,
        conversation_history: list = None,
        has_existing_report: bool = False,
        include_history: bool = True,
    ) -> dict:
        """Internal helper: build prompt and call LLM, returns the raw classification dict.
        Does NOT perform arbitration. This is the building block used by classify() and
        the arbitration re-classification path."""
        await self._ensure_db_config()
        prompt = self._build_classification_prompt(
            message, conversation_history, has_existing_report, include_history=include_history
        )
        return await self._call_llm(prompt, timeout=10)

    async def classify(
        self,
        message: str,
        conversation_history: list = None,
        has_existing_report: bool = False,
        _skip_arbitration: bool = False,
    ) -> dict:
        await self._ensure_db_config()
        logger.info(f"IntentClassifier classifying message: '{message[:100]}...'")

        try:
            result = await self._classify_internal(
                message, conversation_history, has_existing_report, include_history=True
            )

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

            # Arbitration: if the with-history result has low confidence, re-classify without
            # history and adopt that result if it disagrees and has higher confidence. This
            # mitigates context-bias where the LLM overweights prior conversation topics.
            # Additionally, force arbitration when has_existing_report=True and the with-history
            # result is workflow_reentry (high-bias scenario where LLM tends to over-route).
            if not _skip_arbitration and (
                confidence < 0.6
                or (has_existing_report and intent_type in ("workflow_reentry", "market_insight"))
            ):
                try:
                    no_hist_result = await self.classify(
                        message, None, False, _skip_arbitration=True
                    )
                    no_hist_intent = no_hist_result.get("intent_type")
                    no_hist_conf = no_hist_result.get("confidence", 0.0)
                    # 仲裁采纳：no-history 结果为 general_question 且 confidence > 0.5
                    # → 改判 general_question（防止 has_existing_report 上下文偏置）
                    if no_hist_intent == "general_question" and no_hist_conf > 0.5:
                        logger.info(
                            "Intent arbitration: with_history=%s(%.2f) vs without_history=%s(%.2f), adopting without_history",
                            intent_type, confidence,
                            no_hist_intent, no_hist_conf,
                        )
                        intent_type = no_hist_intent
                        target_stage = no_hist_result.get("target_stage")
                        confidence = no_hist_conf
                        reasoning = (no_hist_result.get("reasoning", "") + " (经无历史仲裁)").strip()
                        user_feedback = no_hist_result.get("user_feedback")
                        classification = {
                            "intent_type": intent_type,
                            "target_stage": target_stage,
                            "confidence": confidence,
                            "reasoning": reasoning,
                            "user_feedback": user_feedback,
                        }
                except Exception as arb_err:
                    logger.warning("Intent arbitration failed (%s), keeping original result", type(arb_err).__name__)

            logger.info(f"Intent classification result: {intent_type}, confidence={confidence:.2f}")
            return classification

        except httpx.ReadTimeout:
            logger.warning("Intent classification timeout, falling back to market_insight")
            return {
                "intent_type": "market_insight",
                "target_stage": None,
                "confidence": 0.3,
                "reasoning": "Classification timeout, defaulting to market_insight",
                "user_feedback": None,
            }

        except httpx.ConnectError:
            logger.warning("Intent classification connection error, falling back to market_insight")
            return {
                "intent_type": "market_insight",
                "target_stage": None,
                "confidence": 0.3,
                "reasoning": "Classification connection error, defaulting to market_insight",
                "user_feedback": None,
            }

        except Exception as e:
            logger.warning("Intent classification failed (%s), falling back to market_insight", type(e).__name__)
            return {
                "intent_type": "market_insight",
                "target_stage": None,
                "confidence": 0.3,
                "reasoning": f"Classification failed ({type(e).__name__}), defaulting to market_insight",
                "user_feedback": None,
            }