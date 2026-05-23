"""
事件触发服务

负责事件规则的 CRUD 和 Webhook 触发处理，实现"事件驱动型 AI 分析"。

支持三种触发类型：
- keyword: 当 Webhook 传入的 text 字段包含指定关键词时触发
- metric: 当 metric_value 绝对值达到 threshold 阈值时触发
- webhook: 无条件触发（收到任何 Webhook 请求都执行分析）

限流机制：
last_triggered_cache 按 rule_id 记录最近触发时间戳，5 分钟内同一规则不重复触发。
原因：Webhook 来源可能高频推送（如 Git commit hook），限流防止大量重复任务淹没系统。
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.event_rule import EventRule
from app.schemas.event_rule import EventRuleCreate, EventRuleUpdate
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.task import TaskService
from app.agents.orchestrator import OrchestratorAgent
from app.schemas.agent import OrchestratorInput

logger = logging.getLogger(__name__)

class EventTriggerService:
    def __init__(self, async_session_factory=None):
        self.task_service = TaskService()
        self.async_session_factory = async_session_factory
        self.last_triggered_cache: Dict[int, float] = {}

    async def create_rule(self, session: AsyncSession, rule_in: EventRuleCreate, user_id: int) -> EventRule:
        rule = EventRule(
            name=rule_in.name,
            event_type=rule_in.event_type,
            keywords=rule_in.keywords,
            threshold=rule_in.threshold,
            target_topic=rule_in.target_topic,
            is_active=rule_in.is_active,
            created_by=user_id
        )
        session.add(rule)
        await session.commit()
        await session.refresh(rule)
        return rule

    async def list_rules(self, session: AsyncSession, user_id: Optional[int] = None) -> List[EventRule]:
        stmt = select(EventRule).order_by(EventRule.id.desc())
        if user_id:
            stmt = stmt.where(EventRule.created_by == user_id)
        res = await session.execute(stmt)
        return res.scalars().all()

    async def update_rule(self, session: AsyncSession, rule_id: int, up: EventRuleUpdate) -> Optional[EventRule]:
        stmt = select(EventRule).where(EventRule.id == rule_id)
        res = await session.execute(stmt)
        rule = res.scalar_one_or_none()
        if not rule:
            return None

        data = up.model_dump(exclude_unset=True)
        for field, val in data.items():
            setattr(rule, field, val)
        await session.commit()
        await session.refresh(rule)
        return rule

    async def delete_rule(self, session: AsyncSession, rule_id: int) -> bool:
        stmt = select(EventRule).where(EventRule.id == rule_id)
        res = await session.execute(stmt)
        rule = res.scalar_one_or_none()
        if not rule:
            return False
        await session.delete(rule)
        await session.commit()
        return True

    async def process_webhook(self, session: AsyncSession, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理 Webhook 事件，匹配规则并触发 AI 分析流水线

        流程：
        1. 解析 Webhook payload（text / metric_value / source）
        2. 遍历所有启用的事件规则，检查匹配条件
        3. 跳过 5 分钟内已触发过的规则（限流）
        4. 每个匹配规则创建一个 Task，后台执行 OrchestratorAgent
        """
        text = payload.get("text", "").lower()
        metric_val = payload.get("metric_value", 0.0)
        source = payload.get("source", "webhook")

        stmt = select(EventRule).where(EventRule.is_active == True)
        res = await session.execute(stmt)
        rules = res.scalars().all()

        import time
        now = time.time()
        matched_rules = []
        triggered_tasks = []

        for rule in rules:
            last_ts = self.last_triggered_cache.get(rule.id, 0)
            if now - last_ts < 300:
                continue

            matched = False
            if rule.event_type == "keyword" and rule.keywords:
                if any(kw.lower() in text for kw in rule.keywords):
                    matched = True
            elif rule.event_type == "metric" and rule.threshold is not None:
                if abs(metric_val) >= abs(rule.threshold):
                    matched = True
            elif rule.event_type == "webhook":
                matched = True

            if matched:
                matched_rules.append(rule.id)
                self.last_triggered_cache[rule.id] = now
                logger.info(f"Webhook matched EventRule {rule.id} ({rule.name})")

                tc = TaskCreate(
                    name=f"Event Flash: {rule.name} ({source[:20]})",
                    type="event",
                    trigger_mode="event",
                    input_data={"topic": rule.target_topic, "payload": payload, "max_items": 2}
                )
                task = await self.task_service.create_task(session, tc, rule.created_by)
                await self.task_service.update_task(session, task.id, TaskUpdate(status="running"))
                triggered_tasks.append(task.id)

                async def run_event_bg(tid, topic):
                    try:
                        orch = OrchestratorAgent()
                        req = OrchestratorInput(task_id=f"event-{tid}", topic=topic, max_items=2)
                        res = await orch.execute(req)
                        st = "completed" if res.status == "completed" else "failed"
                    except Exception as e:
                        logger.error(f"Event task {tid} failed: {e}", exc_info=True)
                        st = "failed"

                    if self.async_session_factory:
                        async with self.async_session_factory() as s:
                            await self.task_service.update_task(s, tid, TaskUpdate(status=st))

                asyncio.create_task(run_event_bg(task.id, rule.target_topic))

        return {
            "received": True,
            "matched_rules": matched_rules,
            "triggered_tasks": triggered_tasks
        }
