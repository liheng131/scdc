import asyncio
from app.models.base import Base
from app.core.db import engine
from app.models.user import User
from app.models.task import Task, TaskRun
from app.models.report import Report
from app.models.data_source import DataSource
from app.models.template import Template
from app.models.event_rule import EventRule
from app.models.notification import NotificationRule
from app.models.collected_record import CollectedRecord


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("All tables created successfully.")


asyncio.run(main())