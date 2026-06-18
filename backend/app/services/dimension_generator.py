"""
DimensionGenerator 服务

职责：
- 根据用户主题动态生成 4-6 个分析维度
- 在 prompt 中注入 4 个参考框架（PEST / 供需缺口模型 / 竞品对标画布 / SWOT），
  引导 LLM 选择最合适的 1-2 个框架或自由组合
- 数量边界约束：少于 min_dim 时补全通用维度；多于 max_dim 时截断；单个维度
  长度不在 [2, 15] 区间内则过滤
- LLM 失败 / 解析失败 / 维度全被过滤时降级为固定的 4 个默认维度

为什么单独拆服务：
- 让 Orchestrator 在 collect 阶段之后、analyze 阶段之前注入主题相关的维度，
  避免所有主题共用同一套硬编码维度导致报告同质化
- 与 AnalyzerAgent 解耦，方便后续替换生成策略（如基于历史报告聚类）
"""

import json
import logging
import re
from typing import List

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import settings
from app.core.runtime_config import rumtime_config

logger = logging.getLogger(__name__)


_FALLBACK_DIMENSIONS: List[str] = [
    "宏观经济环境",
    "行业形势与趋势",
    "细分板块分析",
    "竞争格局与对手",
]

_PADDING_DIMENSIONS: List[str] = [
    "市场前景展望",
    "关键驱动因素",
    "潜在风险与挑战",
    "未来发展机遇",
]


class DimensionGenerator:
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
                self.llm_provider = (
                    db_config["provider"].lower()
                    if db_config["provider"]
                    else self.llm_provider
                )
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
        # 1) 去 markdown 围栏
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        # 2) 如果已经是合法 JSON 开头,直接返回
        if text.startswith("[") or text.startswith("{"):
            return text
        # 3) 从散文中提取最外层 JSON 数组 [...]
        #    用栈匹配方括号,找到第一个完整的数组区间
        start = text.find("[")
        if start != -1:
            depth = 0
            in_string = False
            escape_next = False
            for i in range(start, len(text)):
                ch = text[i]
                if escape_next:
                    escape_next = False
                    continue
                if ch == "\\":
                    escape_next = True
                    continue
                if ch == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        return text[start:i + 1].strip()
        # 4) 退而求其次:找第一个 [ 到最后一个 ] 之间的内容
        if start != -1:
            end = text.rfind("]")
            if end > start:
                return text[start:end + 1].strip()
        # 5) 无方括号,返回原文让 json.loads 去报错
        return text

    def _build_prompt(self, topic: str, min_dim: int, max_dim: int) -> str:
        return f"""你是一位资深市场情报分析师，曾在顶级咨询公司任职多年。
请根据用户的主题"{topic}"，动态生成 {min_dim}-{max_dim} 个**中文**分析维度。

## 可选参考框架（请根据主题选择最合适的 1-2 个，或自由组合）

1. **PEST**（政治 Political / 经济 Economic / 社会 Social / 技术 Technological）
   - 适合：宏观/政策类主题（如行业政策、监管环境、宏观经济）

2. **供需缺口模型**（供给端 / 需求端 / 价格弹性 / 缺口测算）
   - 适合：行业市场类主题（如市场规模、产能、消费者需求）

3. **竞品对标画布**（产品 / 价格 / 渠道 / 营销 / 服务 / 核心壁垒 六维）
   - 适合：竞争分析类主题（如对标特定公司、产品横评）

4. **SWOT**（优势 Strengths / 劣势 Weaknesses / 机会 Opportunities / 威胁 Threats）
   - 适合：企业战略类主题（如单家公司评估、战略转型）

5. **自由组合**：如果上述框架都不完全契合，请自创适合该主题的维度。

## 严格要求

- 输出必须是**严格的 JSON 数组**格式：`["维度1", "维度2", ...]`
- 维度数量：{min_dim} 到 {max_dim} 个
- 每个维度名：2-10 个中文字符
- 维度之间相关性低、覆盖角度不同（不要出现近义或高度重叠的维度）
- 维度名要具体、有信息量，避免泛泛而谈（如不要写"分析"、"总结"这类空泛词）
- **只返回 JSON 数组，不要包含任何其他文字、解释或 markdown 标记**

示例（仅作格式参考，不要照搬）：
主题："2025年AI芯片市场趋势"
输出：["市场规模与增速", "技术路线演进", "政策与地缘风险", "竞争格局", "下游应用场景"]

主题："{topic}"
请输出："""

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(
            (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, json.JSONDecodeError, ValueError)
        ),
        reraise=True,
    )
    async def _call_llm(self, prompt: str, timeout: int = 30) -> List[str]:
        if self.llm_provider == "gpustack":
            payload = {
                "model": self.default_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": rumtime_config.get("temperature"),
                "max_tokens": rumtime_config.get("max_tokens"),
            }
        else:
            payload = {
                "model": self.default_model,
                "prompt": prompt,
                "format": "json",
                "stream": False,
                "options": {"temperature": rumtime_config.get("temperature")},
            }

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(self.llm_url, json=payload, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()

            if self.llm_provider == "gpustack":
                response_text = (
                    data.get("choices", [{}])[0].get("message", {}).get("content", "")
                )
            else:
                response_text = data.get("response", "")

            response_text = self._clean_json_response(response_text)
            if not response_text:
                raise json.JSONDecodeError("Empty response after cleaning", "", 0)

            parsed = json.loads(response_text)

            if not isinstance(parsed, list):
                # 容错：有些模型会把数组包在 dict 里
                if isinstance(parsed, dict):
                    for key in ("dimensions", "items", "data", "result"):
                        if key in parsed and isinstance(parsed[key], list):
                            parsed = parsed[key]
                            break
                    else:
                        raise ValueError(
                            f"Expected JSON array, got object: {list(parsed.keys())}"
                        )
                else:
                    raise ValueError(
                        f"Expected JSON array, got {type(parsed).__name__}"
                    )

            dimensions = [str(d).strip() for d in parsed if d]
            return dimensions

    def _enforce_constraints(
        self, dimensions: List[str], min_dim: int, max_dim: int
    ) -> List[str]:
        # 1) 过滤长度不合法的维度（< 2 字 或 > 15 字）
        filtered: List[str] = []
        seen = set()
        for d in dimensions:
            d = d.strip()
            if len(d) < 2 or len(d) > 15:
                continue
            if d in seen:
                continue
            seen.add(d)
            filtered.append(d)

        # 2) 截断到 max_dim
        if len(filtered) > max_dim:
            filtered = filtered[:max_dim]

        # 3) 不足 min_dim 时用通用维度补足
        if len(filtered) < min_dim:
            for pad in _PADDING_DIMENSIONS:
                if len(filtered) >= min_dim:
                    break
                if pad not in filtered:
                    filtered.append(pad)

        return filtered

    async def generate(
        self, topic: str, min_dim: int = 4, max_dim: int = 6
    ) -> List[str]:
        """根据主题动态生成 4-6 个分析维度。

        Args:
            topic: 用户主题
            min_dim: 最少维度数，默认 4
            max_dim: 最多维度数，默认 6

        Returns:
            中文维度名列表。任何失败场景下都会回退到固定的 4 个默认维度。
        """
        await self._ensure_db_config()
        logger.info(
            f"DimensionGenerator generating dimensions for topic: '{topic[:80]}' "
            f"(min={min_dim}, max={max_dim})"
        )

        try:
            prompt = self._build_prompt(topic, min_dim, max_dim)
            raw_dimensions = await self._call_llm(prompt, timeout=30)

            constrained = self._enforce_constraints(raw_dimensions, min_dim, max_dim)

            if not constrained:
                # 极端情况：LLM 返回的所有维度都被过滤掉
                logger.warning(
                    "DimensionGenerator all candidates filtered, degrading to defaults for topic: %s",
                    topic,
                )
                return list(_FALLBACK_DIMENSIONS)

            logger.info(
                f"DimensionGenerator generated {len(constrained)} dimensions: {constrained}"
            )
            return constrained

        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            logger.warning(
                f"DimensionGenerator LLM connection/timeout error ({type(e).__name__}): {e}"
            )
            logger.warning(
                "DimensionGenerator degraded to defaults for topic: %s", topic
            )
            return list(_FALLBACK_DIMENSIONS)

        except json.JSONDecodeError as e:
            logger.warning(f"DimensionGenerator JSON parse error: {e}")
            logger.warning(
                "DimensionGenerator degraded to defaults for topic: %s", topic
            )
            return list(_FALLBACK_DIMENSIONS)

        except Exception as e:
            logger.warning(
                f"DimensionGenerator unexpected error ({type(e).__name__}): {e}"
            )
            logger.warning(
                "DimensionGenerator degraded to defaults for topic: %s", topic
            )
            return list(_FALLBACK_DIMENSIONS)


# 模块级单例实例
dimension_generator = DimensionGenerator()
