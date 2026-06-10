"""
MasterAgent（主控 Agent）

职责：
- 统一管理"用户消息 → 意图分类 → 路由到具体执行单元"的全流程
- 组合 IntentClassifier（分类）+ DirectResponseService（直答）+ OrchestratorAgent（工作流调度）
- 暴露 process_message() 统一入口，供上层调用方使用
- 提供 MasterDecision 数据结构描述路由决策

设计原则：
- 组合而非继承：MasterAgent 持有 IntentClassifier / DirectResponseService 引用，但**不**继承它们
- 向后兼容：WorkflowService 可继续使用 IntentClassifier / DirectResponseService，MasterAgent 仅作为新的统一入口
- 单一职责：MasterAgent 本身**不执行** LLM 调用，不写 DB，不做嵌入；只做"分类 → 决策 → 分发"

主控 Agent 动作 vs 实际执行：

| 场景                  | 主控 Agent 动作                                        | 实际执行                |
|-----------------------|--------------------------------------------------------|-------------------------|
| 常规问题（直答）      | classify → general_question                            | DirectResponseService   |
| 复杂问题（工作流）    | classify → market_insight → create WorkflowState       | OrchestratorAgent       |
| 追问/回退             | classify → workflow_reentry (target_stage, feedback)   | OrchestratorAgent       |
| 跨会话召回            | （暂未实现）vectorstore.search_cross_session()         | N/A                     |

历史 spec 依赖：
- intent-routing-and-workflow-reentry —— 提供三类意图分类的语义基础
- fix-intent-classification-and-routing —— 提供超时/重试/容错的实现
- conversation-followup-and-memory —— 提供 conversation_history 传递机制
- reports-vector-upload —— 提供向量库检索基础
- enhance-intent-routing-and-rag-coverage —— 引入 use_rag 开关 + MasterAgent 概念

使用示例：

    master = MasterAgent()
    decision = await master.process_message(
        message="2025年AI芯片市场趋势",
        conversation_history=[],
        use_rag=True,
    )
    if decision.action == "orchestrate":
        # 调用方（WorkflowService / API 路由）启动 OrchestratorAgent
        ...
    elif decision.action == "direct":
        # 调用方启动 DirectResponseService 流式输出
        ...
    elif decision.action == "reentry":
        # 调用方启动工作流回退
        ...
"""

import logging
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.services.intent_classifier import IntentClassifier
from app.services.direct_response import DirectResponseService

logger = logging.getLogger(__name__)

# Reentry guard 关键词：消息中包含任一关键词 → 视为用户明确要求重入某个阶段
# 不包含这些词 + 短文本（< 20 字）→ 视为分类器误判，改判为 direct
REENTRY_KEYWORDS = [
    "重新",
    "不够",
    "改进",
    "格式",
    "维度",
    "深度",
    "完善",
    "优化",
    "调整",
    "重做",
    "再",
]

# Chitchat guard 关键词：消息中包含任一关键词 → 视为闲聊/能力询问，
# 强改判为 direct，避免误启动工作流（不限制消息长度）
CHITCHAT_KEYWORDS = [
    "你好", "hi", "嗨", "在吗", "再见", "谢谢",   # 问候
    "你能", "你会", "你是", "有什么功能", "能做啥",  # AI 能力询问
    "什么是", "怎么用", "如何", "为什么", "在哪",    # 概念询问
    "是什么", "干嘛",                                # 模糊询问
]


@dataclass
class MasterDecision:
    """主控 Agent 的路由决策

    action 字段：
    - "orchestrate"   → 调用方应启动 OrchestratorAgent 完整四阶段（collecting→cleaning→analyzing→reporting）
    - "direct"        → 调用方应启动 DirectResponseService 流式直答
    - "reentry"       → 调用方应启动 OrchestratorAgent 从 target_stage 阶段重入
    """
    action: str
    intent_type: str
    confidence: float
    reasoning: str = ""
    target_stage: Optional[str] = None
    user_feedback: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class MasterAgent:
    """主控 Agent（统一入口）

    组合 IntentClassifier 进行意图分类；DirectResponseService / OrchestratorAgent 由调用方持有并按决策执行。
    """

    def __init__(
        self,
        intent_classifier: Optional[IntentClassifier] = None,
        direct_response: Optional[DirectResponseService] = None,
    ):
        self.intent_classifier = intent_classifier or IntentClassifier()
        self.direct_response = direct_response or DirectResponseService()
        # OrchestratorAgent 不在 MasterAgent 实例化时构造（每个工作流一个实例），
        # 路由到 orchestrate/reentry 时由调用方按需构造
        logger.info("MasterAgent initialized")

    async def classify(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        has_existing_report: bool = False,
    ) -> Dict[str, Any]:
        """意图分类（薄封装，便于调用方复用）

        实际行为委托 IntentClassifier.classify()，享受上下文偏置修复。
        """
        return await self.intent_classifier.classify(
            message,
            conversation_history=conversation_history,
            has_existing_report=has_existing_report,
        )

    async def process_message(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        use_rag: bool = False,
        has_existing_report: bool = False,
    ) -> MasterDecision:
        """主控 Agent 统一入口：分类 + 决策

        Args:
            message: 用户消息
            conversation_history: 对话历史（可选）
            use_rag: 是否在直答路径启用 RAG（MasterDecision.extra["use_rag"] 中透传给调用方）
            has_existing_report: 当前是否有已生成报告（影响意图分类的"workflow_reentry"识别）

        Returns:
            MasterDecision: 路由决策

        调用方根据 decision.action 分发：
        - "orchestrate" → 启动 OrchestratorAgent.execute(OrchestratorInput(...))
        - "direct"      → 启动 DirectResponseService.generate_response_stream(..., use_rag=use_rag)
        - "reentry"     → 启动 OrchestratorAgent.execute(OrchestratorInput(..., start_stage=decision.target_stage, reentry_context=decision.user_feedback))
        """
        logger.info(
            "MasterAgent processing message (len=%d, history_len=%d, use_rag=%s)",
            len(message) if message else 0,
            len(conversation_history) if conversation_history else 0,
            use_rag,
        )

        try:
            classification = await self.classify(
                message,
                conversation_history=conversation_history,
                has_existing_report=has_existing_report,
            )
        except Exception as e:
            # 分类器异常（极少见，通常已被 IntentClassifier 内部 fallback 处理）
            logger.warning("MasterAgent classify failed: %s, fallback to direct", e)
            classification = {
                "intent_type": "general_question",
                "confidence": 0.3,
                "reasoning": f"Classifier exception: {e}",
                "target_stage": None,
                "user_feedback": None,
            }

        intent_type = classification.get("intent_type", "general_question")
        confidence = classification.get("confidence", 0.5)
        reasoning = classification.get("reasoning", "")
        target_stage = classification.get("target_stage")
        user_feedback = classification.get("user_feedback")

        if intent_type == "market_insight":
            action = "orchestrate"
        elif intent_type == "workflow_reentry":
            action = "reentry"
        else:
            action = "direct"

        decision = MasterDecision(
            action=action,
            intent_type=intent_type,
            confidence=confidence,
            reasoning=reasoning,
            target_stage=target_stage,
            user_feedback=user_feedback,
            extra={"use_rag": use_rag},
        )

        # Reentry guard：短文本（< 20 字）且不含重入关键词 → 视为误判的 workflow_reentry，
        # 改判为 direct，避免误启动工作流
        safe_message = message or ""

        # Guard 1: 短文本+无重入关键词 → reentry 误判
        if (
            decision.action == "reentry"
            and len(safe_message) < 20
            and not any(kw in safe_message for kw in REENTRY_KEYWORDS)
        ):
            logger.warning(
                'reentry-guard: short msg "%s" without reentry keywords, falling back to direct',
                safe_message,
            )
            decision.action = "direct"
            decision.reasoning = (decision.reasoning or "") + " [reentry-guard: 短文本+无重入关键词]"

        # Guard 2: 闲聊关键词 → orchestrate/reentry 误判
        elif (
            decision.action in ("reentry", "orchestrate")
            and any(kw in safe_message for kw in CHITCHAT_KEYWORDS)
        ):
            logger.warning(
                'chitchat-guard: msg "%s" contains chitchat keywords, falling back to direct',
                safe_message,
            )
            decision.action = "direct"
            decision.reasoning = (decision.reasoning or "") + " [chitchat-guard: 含闲聊关键词]"

        logger.info(
            "MasterAgent decision: action=%s, intent=%s, confidence=%.2f",
            decision.action, decision.intent_type, decision.confidence,
        )
        return decision


# 全局单例（避免每次新建 IntentClassifier 时重复连接 LLM）
master_agent = MasterAgent()
