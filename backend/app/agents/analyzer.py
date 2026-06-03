"""
AnalyzerAgent（AI 分析 Agent）

职责：
- 接收 CleanerAgent 清洗后的数据，调用 Ollama LLM 进行分析
- 将清洗后的内容拼接为结构化 Prompt，要求 LLM 返回 JSON 格式的分析结果
- LLM 不可用时自动降级为基于规则的分析（rule-based degradation）

为什么使用 Ollama：
- 完全本地部署，数据不出内网，满足企业安全合规要求
- 无需 API 费用，适合持续集成和批量分析

为什么设计降级策略：
- LLM 服务可能因 GPU 资源不足、网络故障等原因不可用
- 降级到规则分析确保系统在 LLM 故障时仍能产出可用结果，不中断流水线
"""

import json
import logging
import re
import traceback
import httpx
from typing import List, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.schemas.agent import AnalyzerInput, AnalyzerOutput, Insight, CleanedItem
from app.core.config import settings
from app.core.runtime_config import rumtime_config
from app.services.embedding import EmbeddingService
from app.services.vectorstore import VectorStoreService
from app.services.rerank import RerankService

logger = logging.getLogger(__name__)


def _sanitize_text(text: str, max_len: int = 300) -> str:
    text = re.sub(r'[^\x20-\x7E\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\n\r\t]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_len]


class AnalyzerAgent:
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

    def _build_prompt(self, topic: str, items: List[CleanedItem], dimensions: List[str], context_snippets: List[str] = None) -> str:
        context_parts = []
        for i, item in enumerate(items):
            full_text = "\n".join(item.content_chunks) if item.content_chunks else item.summary
            if len(full_text) > 1500:
                full_text = full_text[:1500] + "..."
            context_parts.append(
                f"--- Source #{i+1} ---\n"
                f"URI: {item.source_uri}\n"
                f"Title: {item.title}\n"
                f"Content:\n{full_text}\n"
            )

        context_str = "\n".join(context_parts)

        dim_labels = "\n".join(f"  - {d}" for d in dimensions)
        dim_slots = ", ".join(f'"{d}"' for d in dimensions)

        historical_section = ""
        if context_snippets:
            snippets_str = "\n".join(f"{i+1}. {s}" for i, s in enumerate(context_snippets))
            historical_section = f"""## 历史相关报告背景
以下是之前相关报告中的关键背景信息片段，可用于了解历史上下文和趋势：
{snippets_str}

"""

        prompt = f"""You are a senior market intelligence analyst with decades of experience at a top-tier consulting firm.

Your task: produce a deep, insightful analysis of the topic "{topic}" based on the source materials below.

The analysis MUST be structured into the following dimensions (do NOT use any other dimension labels):
{dim_labels}

{historical_section}REQUIREMENTS:
1. Write a substantive executive summary (200-400 words) that synthesizes findings into a coherent narrative, covering ALL the dimensions above. Include key numbers, specific company names, and directional trends where available.
2. For EACH dimension above, extract 1-3 insights. Total 5-8 insights across all dimensions. For EACH insight:
   - "conclusion": a one-sentence headline
   - "analysis": 2-4 sentence deep dive explaining the evidence, implications, and why it matters (80-150 words)
   - "evidence": URIs from the sources that support this insight
   - "confidence": your certainty level (0.0-1.0)
   - "dimension": MUST be exactly one of [{dim_slots}]
3. Cross-reference sources where possible - if two sources reinforce the same finding, mention that in the analysis.
4. Be specific and data-driven. Avoid vague generalities like "the market is growing."
5. Every dimension listed above MUST have at least one insight. Do not leave any dimension uncovered.

Output strictly as JSON, no markdown:
{{
  "summary": "detailed executive summary covering all dimensions above (200-400 words)",
  "insights": [
    {{
      "conclusion": "one-sentence headline",
      "analysis": "2-4 sentence deep-dive with evidence, implications, significance (80-150 words)",
      "evidence": ["uri1", "uri2"],
      "confidence": 0.92,
      "dimension": "{dimensions[0] if dimensions else ''}"
    }}
  ]
}}

SOURCE MATERIALS:
{context_str}"""
        return prompt

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, json.JSONDecodeError)),
        reraise=True
    )
    async def _call_llm(self, prompt: str, timeout: int = 120) -> Dict[str, Any]:
        if self.llm_provider == "gpustack":
            payload = {
                "model": self.default_model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": rumtime_config.get("temperature"),
                "max_tokens": rumtime_config.get("max_tokens"),
            }
        else:
            payload = {
                "model": self.default_model,
                "prompt": prompt,
                "format": "json",
                "stream": False,
                "options": {"temperature": rumtime_config.get("temperature")}
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

    def _clean_json_response(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def _rule_based_degradation(self, input_data: AnalyzerInput) -> AnalyzerOutput:
        logger.warning(f"LLM unreachable or failed for task '{input_data.task_id}'. Degrading to rule-based analysis.")
        insights = []
        summary_parts = []
        fallback_dim = input_data.dimensions[0] if input_data.dimensions else ""
        dims = input_data.dimensions if input_data.dimensions else ["综合分析"]

        for idx, item in enumerate(input_data.cleaned_items):
            summary_parts.append(item.title)
            full_text = "\n".join(item.content_chunks) if item.content_chunks else item.summary
            safe_summary = _sanitize_text(item.summary, 200)
            safe_content = _sanitize_text(full_text, 300)
            dim = dims[idx % len(dims)]
            analysis = safe_content if safe_content else f"Source '{item.title}' provides relevant information."
            insights.append(Insight(
                conclusion=safe_summary[:80] if safe_summary else f"Key finding from {item.title}",
                analysis=analysis,
                evidence=[item.source_uri],
                confidence=0.8,
                dimension=dim
            ))

        combined_summary = f"Analysis Summary for '{input_data.topic}': Found {len(input_data.cleaned_items)} relevant sources including {', '.join(summary_parts[:3])}. {len(input_data.cleaned_items)} key observations were extracted for further review."
        return AnalyzerOutput(
            task_id=input_data.task_id,
            success=True,
            summary=combined_summary,
            insights=insights,
            degraded=True
        )

    async def execute(self, input_data: AnalyzerInput) -> AnalyzerOutput:
        await self._ensure_db_config()
        logger.info(f"AnalyzerAgent started for task_id: {input_data.task_id}, topic: '{input_data.topic}'")

        if not input_data.cleaned_items:
            logger.warning("No cleaned items provided for analysis.")
            return AnalyzerOutput(
                task_id=input_data.task_id,
                success=True,
                summary=f"No data available to analyze for topic '{input_data.topic}'.",
                insights=[],
                degraded=False
            )

        context_snippets = []
        try:
            vectorstore = VectorStoreService()
            if vectorstore.collection_exists():
                embedding_service = EmbeddingService()
                embeddings = await embedding_service.embed_texts_or_empty([input_data.topic])
                if embeddings and embeddings[0]:
                    hits = vectorstore.search(embeddings[0], top_k=20)
                    if hits:
                        documents = [hit.get("text", "") for hit in hits]
                        rerank_service = RerankService()
                        reranked = await rerank_service.rerank(input_data.topic, documents)
                        top_indices = [r["index"] for r in reranked[:3]]
                        context_snippets = [documents[i] for i in top_indices]
                        logger.info(f"Retrieved {len(hits)} vector hits, reranked to {len(context_snippets)} context snippets for topic '{input_data.topic}'")
                    else:
                        logger.info(f"No vector hits found for topic '{input_data.topic}'")
        except Exception as e:
            logger.warning(f"Failed to retrieve vector context for topic '{input_data.topic}': {e}")

        prompt = self._build_prompt(input_data.topic, input_data.cleaned_items, input_data.dimensions, context_snippets if context_snippets else None)
        try:
            llm_result = await self._call_llm(prompt)
            summary = llm_result.get("summary", f"Analysis summary for {input_data.topic}")
            raw_insights = llm_result.get("insights", [])

            validated_insights = []
            valid_uris = {item.source_uri for item in input_data.cleaned_items}
            valid_dims = set(input_data.dimensions)

            for ri in raw_insights:
                conclusion = ri.get("conclusion", "")
                analysis = ri.get("analysis", "")
                evidence = ri.get("evidence", [])
                confidence = float(ri.get("confidence", 0.8))
                dimension = ri.get("dimension", ri.get("category", ""))

                if dimension and dimension not in valid_dims and valid_dims:
                    dim_lower = dimension.strip().lower()
                    for vd in valid_dims:
                        if vd.lower() == dim_lower or vd.lower().startswith(dim_lower[:4]) or dim_lower.startswith(vd.lower()[:4]):
                            dimension = vd
                            break
                    else:
                        dimension = list(valid_dims)[0]

                clean_evidence = [e for e in evidence if e in valid_uris]
                if not clean_evidence and valid_uris:
                    clean_evidence = [list(valid_uris)[0]]

                validated_insights.append(Insight(
                    conclusion=conclusion,
                    analysis=analysis,
                    evidence=clean_evidence,
                    confidence=max(0.0, min(1.0, confidence)),
                    dimension=dimension
                ))

            return AnalyzerOutput(
                task_id=input_data.task_id,
                success=True,
                summary=summary,
                insights=validated_insights
            )
        except Exception as e:
            logger.error(f"AnalyzerAgent LLM execution failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")
            return self._rule_based_degradation(input_data)
