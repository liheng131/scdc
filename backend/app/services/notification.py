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
        stmt = select(NotificationRule).where(NotificationRule.enabled == True).where(NotificationRule.trigger == trigger)
        res = await session.execute(stmt)
        rules = res.scalars().all()

        results = {}
        for r in rules:
            adapter = self.adapters.get(r.channel)
            if not adapter:
                continue
            
            success = False
            # 3 retries with exponential backoff
            for attempt in range(1, 4):
                if await adapter.send(r.target, title, content):
                    success = True
                    break
                logger.warning(f"Notification send failed for rule {r.id}, retrying attempt {attempt+1}")
                await asyncio.sleep(2 ** attempt)
            
            results[r.id] = success
        
        return results
