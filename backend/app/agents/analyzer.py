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
        self.ollama_url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"
        self.default_model = settings.default_model

    def _build_prompt(self, topic: str, items: List[CleanedItem]) -> str:
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
        payload = {
            "model": self.default_model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.2}
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(self.ollama_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            response_text = data.get("response", "{}")
            return json.loads(response_text)

    def _rule_based_degradation(self, input_data: AnalyzerInput) -> AnalyzerOutput:
        logger.warning(f"Ollama LLM unreachable or failed for task '{input_data.task_id}'. Degrading to rule-based analysis.")
        insights = []
        summary_parts = []

        for item in input_data.cleaned_items:
            summary_parts.append(item.title)
            # Create a simple insight from each cleaned item
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

                # Filter valid evidence URIs
                clean_evidence = [e for e in evidence if e in valid_uris]
                if not clean_evidence and valid_uris: # Fallback to first valid URI if matching failed
                    clean_evidence = [list(valid_uris)[0]]

                validated_insights.append(Insight(
                    conclusion=conclusion,
                    evidence=clean_evidence,
                    confidence=max(0.0, min(1.0, confidence)),
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
