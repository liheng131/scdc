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
import httpx
from typing import List, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.schemas.agent import AnalyzerInput, AnalyzerOutput, Insight, CleanedItem
from app.core.config import settings

logger = logging.getLogger(__name__)

class AnalyzerAgent:
    def __init__(self):
        self.llm_provider = settings.llm_provider
        self.default_model = settings.default_model
        
        if self.llm_provider == "gpustack":
            self.llm_url = f"{settings.ollama_base_url.rstrip('/')}/v1/chat/completions"
            self.headers = {
                "Authorization": f"Bearer {settings.llm_api_key}",
                "Content-Type": "application/json",
            }
        else:
            self.llm_url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"
            self.headers = {}

    def _build_prompt(self, topic: str, items: List[CleanedItem]) -> str:
        """
        构建发送给 LLM 的分析 Prompt

        为什么要求输出 JSON 格式：
        - 便于程序化解析和校验（按 schema 验证必填字段）
        - JSON 结构化输出比纯文本更易于后续 Reporter 阶段组装报告
        """
        context_parts = []
        for i, item in enumerate(items):
            context_parts.append(f"[Source #{i+1} | URI: {item.source_uri} | Title: {item.title}]\nSummary: {item.summary}")

        context_str = "\n\n".join(context_parts)
        prompt = f"""You are an expert market analyst. Based on the provided context sources, analyze the topic: '{topic}'.
Extract deep insights and format your response strictly as a JSON object matching this schema:
{{
  "summary": "High level executive summary of the findings (approx 100-200 words)",
  "insights": [
    {{
      "conclusion": "Clear, standalone analytical takeaway",
      "evidence": ["http://uri-of-source-1", "http://uri-of-source-2"],
      "confidence": 0.95,
      "category": "trend" // choose from 'trend', 'competitor', 'risk', 'opportunity', 'general'
    }}
  ]
}}

Context Sources:
{context_str}

IMPORTANT: Ensure valid JSON output only without markdown formatting or extra commentary. Every evidence entry must match one of the provided Source URIs."""
        return prompt

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException, json.JSONDecodeError)),
        reraise=True
    )
    async def _call_llm(self, prompt: str, timeout: int = 30) -> Dict[str, Any]:
        """
        调用 LLM API 发送 Prompt 并解析 JSON 响应

        为什么使用指数退避重试：
        - LLM 服务可能在 GPU 占用高峰期暂时无法响应
        - 指数退避给服务留出恢复时间，避免雪崩效应
        """
        if self.llm_provider == "gpustack":
            payload = {
                "model": self.default_model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            }
        else:
            payload = {
                "model": self.default_model,
                "prompt": prompt,
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.2}
            }

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(self.llm_url, json=payload, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()
            
            if self.llm_provider == "gpustack":
                response_text = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            else:
                response_text = data.get("response", "{}")
            
            return json.loads(response_text)

    def _rule_based_degradation(self, input_data: AnalyzerInput) -> AnalyzerOutput:
        """
        LLM 不可用时的降级分析逻辑

        为什么这样降级：
        - 将每条清洗后的数据直接转换为一条 insight，确保不丢失信息
        - 虽然缺少 LLM 的深度分析能力，但仍能产出结构化的报告供人工审阅
        """
        logger.warning(f"Ollama LLM unreachable or failed for task '{input_data.task_id}'. Degrading to rule-based analysis.")
        insights = []
        summary_parts = []

        for item in input_data.cleaned_items:
            summary_parts.append(item.title)
            conclusion = f"Key observation from {item.title}: {item.summary[:100]}..."
            insights.append(Insight(
                conclusion=conclusion,
                evidence=[item.source_uri],
                confidence=0.8,
                category="general"
            ))

        combined_summary = f"Degraded Analysis Summary for '{input_data.topic}': Found {len(input_data.cleaned_items)} relevant sources including " + ", ".join(summary_parts[:3]) + "."
        return AnalyzerOutput(
            task_id=input_data.task_id,
            success=True,
            summary=combined_summary,
            insights=insights
        )

    async def execute(self, input_data: AnalyzerInput) -> AnalyzerOutput:
        """
        执行分析流程：
        1. 构建 Prompt 并调用 LLM
        2. 从 LLM 响应中提取 summary 和 insights
        3. 校验 evidence URI 的有效性（只保留已采集到的来源）
        4. LLM 调用失败时自动降级为规则分析
        """
        logger.info(f"AnalyzerAgent started for task_id: {input_data.task_id}, topic: '{input_data.topic}'")

        if not input_data.cleaned_items:
            logger.warning("No cleaned items provided for analysis.")
            return AnalyzerOutput(
                task_id=input_data.task_id,
                success=True,
                summary=f"No data available to analyze for topic '{input_data.topic}'.",
                insights=[]
            )

        prompt = self._build_prompt(input_data.topic, input_data.cleaned_items)
        try:
            llm_result = await self._call_llm(prompt)
            summary = llm_result.get("summary", f"Analysis summary for {input_data.topic}")
            raw_insights = llm_result.get("insights", [])

            validated_insights = []
            valid_uris = {item.source_uri for item in input_data.cleaned_items}

            for ri in raw_insights:
                conclusion = ri.get("conclusion", "")
                evidence = ri.get("evidence", [])
                confidence = float(ri.get("confidence", 0.8))
                category = ri.get("category", "general")

                # 过滤合法的 evidence URI，只保留已采集的来源
                clean_evidence = [e for e in evidence if e in valid_uris]
                if not clean_evidence and valid_uris:  # 匹配失败时回退到第一个有效 URI
                    clean_evidence = [list(valid_uris)[0]]

                validated_insights.append(Insight(
                    conclusion=conclusion,
                    evidence=clean_evidence,
                    confidence=max(0.0, min(1.0, confidence)),  # 将置信度钳制在 [0, 1]
                    category=category
                ))

            return AnalyzerOutput(
                task_id=input_data.task_id,
                success=True,
                summary=summary,
                insights=validated_insights
            )
        except Exception as e:
            logger.error(f"AnalyzerAgent LLM execution failed: {str(e)}")
            return self._rule_based_degradation(input_data)
