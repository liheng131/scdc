import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import async_session_factory, engine
from app.models.base import Base
from app.core.security import get_password_hash
from app.models.user import User, UserRole


async def seed_admin_user():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.username == "admin"))
        existing_admin = result.scalars().first()

        if existing_admin:
            print("Admin user already exists, skipping seed.")
            return

        admin_user = User(
            username="admin",
            email="admin@scdc.local",
            password_hash=get_password_hash("password"),
            role=UserRole.admin,
            status="active",
        )
        session.add(admin_user)
        await session.commit()
        print("Admin user created successfully!")
        print("Username: admin")
        print("Password: password")


if __name__ == "__main__":
    asyncio.run(seed_admin_user())
