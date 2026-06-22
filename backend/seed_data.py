"""
数据库种子脚本 - 初始化基础配置数据

用途：新环境部署后运行此脚本，自动填充：
1. 管理员账号
2. AI 模型配置（LLM + Embedding）
3. 通知规则（邮件推送）

运行方式：
    cd backend
    python seed_data.py
"""

import asyncio
import sys
import os

# 确保可以导入 app 模块
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.user import User, UserRole
from app.models.ai_model_config import AiModelConfig
from app.models.notification import NotificationRule

try:
    from app.core.security import get_password_hash
except ImportError:
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    def get_password_hash(password: str) -> str:
        return pwd_context.hash(password)


async def seed():
    engine = create_async_engine(settings.async_postgres_dsn)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 1. 管理员账号
        existing_admin = await session.execute(
            select(User).where(User.username == "admin")
        )
        if not existing_admin.scalar_one_or_none():
            admin = User(
                username="admin",
                email="admin@scdc.local",
                password_hash=get_password_hash("password"),
                role=UserRole.admin,
                status="active",
            )
            session.add(admin)
            print("[OK] 创建管理员账号: admin / password")
        else:
            print("[--] 管理员账号已存在，跳过")

        # 2. AI 模型配置
        # LLM 模型 (gpustack)
        existing_llm = await session.execute(
            select(AiModelConfig).where(AiModelConfig.model_type == "llm", AiModelConfig.is_default == True)
        )
        if not existing_llm.scalar_one_or_none():
            llm_config = AiModelConfig(
                provider="gpustack",
                model_name="qwen3-vl-32b-instruct-gguf",
                model_type="llm",
                base_url="http://120.79.96.231:6003",
                api_key="",
                is_default=True,
            )
            session.add(llm_config)
            print("[OK] 创建默认 LLM 模型配置: gpustack / qwen3-vl-32b-instruct-gguf")
        else:
            print("[--] 默认 LLM 模型配置已存在，跳过")

        # Embedding 模型
        existing_emb = await session.execute(
            select(AiModelConfig).where(AiModelConfig.model_type == "embedding", AiModelConfig.is_default == True)
        )
        if not existing_emb.scalar_one_or_none():
            emb_config = AiModelConfig(
                provider="ollama",
                model_name="nomic-embed-text",
                model_type="embedding",
                base_url="http://ollama:11434",
                api_key="",
                is_default=True,
            )
            session.add(emb_config)
            print("[OK] 创建默认 Embedding 模型配置: ollama / nomic-embed-text")
        else:
            print("[--] 默认 Embedding 模型配置已存在，跳过")

        # Rerank 模型 (gpustack)
        existing_rerank = await session.execute(
            select(AiModelConfig).where(AiModelConfig.model_type == "rerank", AiModelConfig.is_default == True)
        )
        if not existing_rerank.scalar_one_or_none():
            rerank_config = AiModelConfig(
                provider="gpustack",
                model_name="lb-reranker-0.5b-v1.0-gguf",
                model_type="rerank",
                base_url="http://120.79.96.231:6003",
                api_key="",
                is_default=True,
            )
            session.add(rerank_config)
            print("[OK] 创建默认 Rerank 模型配置: gpustack / lb-reranker-0.5b-v1.0-gguf")
        else:
            print("[--] 默认 Rerank 模型配置已存在，跳过")

        # 3. 通知规则（邮件推送）
        existing_rules = await session.execute(
            select(NotificationRule).where(NotificationRule.channel == "email")
        )
        rules = existing_rules.scalars().all()
        if not rules:
            rule = NotificationRule(
                name="高管报告邮件推送",
                channel="email",
                trigger="report_ready",
                target="u0015856@unilumin.com",
                enabled=True,
            )
            session.add(rule)
            print("[OK] 创建通知规则: 高管报告邮件推送 -> u0015856@unilumin.com")
        else:
            print(f"[--] 已有 {len(rules)} 条邮件通知规则，跳过")

        await session.commit()
        print("\n[完成] 种子数据初始化完成！")

    await engine.dispose()


if __name__ == "__main__":
    print("=" * 50)
    print("数据库种子数据初始化")
    print("=" * 50)
    print(f"数据库: {settings.async_postgres_dsn}")
    print()
    asyncio.run(seed())
