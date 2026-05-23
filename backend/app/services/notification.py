"""
通知服务

提供多渠道通知能力（邮件 + Webhook）和通知规则的 CRUD 管理。

架构说明：
- NotificationAdapter 是抽象基类，定义 send() 接口
- EmailAdapter: 通过 SMTP 发送 HTML 格式邮件，SMTP 操作在线程池中执行避免阻塞事件循环
- WebhookAdapter: 向目标 URL 发送 POST 请求（钉钉/飞书等兼容格式）

为什么使用适配器模式：
- 新增通知渠道（如企业微信、Slack）只需实现新的 Adapter 子类
- NotificationService 通过 self.adapters dict 动态路由，无需修改已有代码
"""

import asyncio
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.notification import NotificationRule
from app.schemas.notification import NotificationRuleCreate, NotificationRuleUpdate

logger = logging.getLogger(__name__)

class NotificationAdapter:
    async def send(self, target: str, title: str, content: str) -> bool:
        raise NotImplementedError

class EmailAdapter(NotificationAdapter):
    async def send(self, target: str, title: str, content: str) -> bool:
        """通过 SMTP 发送邮件通知，异步委托到线程池执行"""
        if not settings.smtp_host:
            logger.warning("SMTP host not configured. Skipping email send.")
            return False

        def _send_sync():
            msg = MIMEMultipart()
            msg['From'] = settings.smtp_from_email
            msg['To'] = target
            msg['Subject'] = title
            msg.attach(MIMEText(content, 'html', 'utf-8'))

            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                if settings.smtp_user and settings.smtp_password:
                    server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)

        try:
            await asyncio.to_thread(_send_sync)
            logger.info(f"Email sent successfully to {target}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {target}: {e}", exc_info=True)
            return False

class WebhookAdapter(NotificationAdapter):
    async def send(self, target: str, title: str, content: str) -> bool:
        """向 Webhook URL 发送 Markdown 格式消息（兼容钉钉机器人格式）"""
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": f"# {title}\n\n{content}"
            }
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(target, json=payload)
                res.raise_for_status()
            logger.info(f"Webhook notification sent successfully to {target}")
            return True
        except Exception as e:
            logger.error(f"Failed to send webhook to {target}: {e}", exc_info=True)
            return False

class NotificationService:
    def __init__(self):
        self.adapters = {
            "email": EmailAdapter(),
            "webhook": WebhookAdapter()
        }

    async def create_rule(self, session: AsyncSession, rule_in: NotificationRuleCreate) -> NotificationRule:
        rule = NotificationRule(
            name=rule_in.name,
            channel=rule_in.channel,
            trigger=rule_in.trigger,
            target=rule_in.target,
            enabled=rule_in.enabled
        )
        session.add(rule)
        await session.commit()
        await session.refresh(rule)
        return rule

    async def list_rules(self, session: AsyncSession, enabled_only: bool = False) -> List[NotificationRule]:
        stmt = select(NotificationRule).order_by(NotificationRule.id.desc())
        if enabled_only:
            stmt = stmt.where(NotificationRule.enabled == True)
        res = await session.execute(stmt)
        return res.scalars().all()

    async def update_rule(self, session: AsyncSession, rule_id: int, up: NotificationRuleUpdate) -> Optional[NotificationRule]:
        stmt = select(NotificationRule).where(NotificationRule.id == rule_id)
        res = await session.execute(stmt)
        rule = res.scalar_one_or_none()
        if not rule:
            return None

        data = up.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(rule, k, v)
        await session.commit()
        await session.refresh(rule)
        return rule

    async def delete_rule(self, session: AsyncSession, rule_id: int) -> bool:
        stmt = select(NotificationRule).where(NotificationRule.id == rule_id)
        res = await session.execute(stmt)
        rule = res.scalar_one_or_none()
        if not rule:
            return False
        await session.delete(rule)
        await session.commit()
        return True

    async def notify(self, session: AsyncSession, trigger: str, title: str, content: str) -> dict:
        """
        根据触发事件类型查找启用的通知规则，调用对应适配器发送通知

        为什么内置 3 次重试 + 指数退避：
        - 邮件服务器/Webhook 接收端可能有瞬时不可用
        - 2^1=2s / 2^2=4s / 2^3=8s 的退避间隔给服务恢复时间
        """
        stmt = select(NotificationRule).where(NotificationRule.enabled == True).where(NotificationRule.trigger == trigger)
        res = await session.execute(stmt)
        rules = res.scalars().all()

        results = {}
        for r in rules:
            adapter = self.adapters.get(r.channel)
            if not adapter:
                continue

            success = False
            for attempt in range(1, 4):
                if await adapter.send(r.target, title, content):
                    success = True
                    break
                logger.warning(f"Notification send failed for rule {r.id}, retrying attempt {attempt+1}")
                await asyncio.sleep(2 ** attempt)

            results[r.id] = success

        return results
