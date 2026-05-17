from typing import List, Optional, Dict, Any
import jinja2
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.template import Template
from app.schemas.template import TemplateCreate, TemplateUpdate

class TemplateService:
    async def create_template(self, session: AsyncSession, tmpl_in: TemplateCreate) -> Template:
        # Check duplicate name
        existing = await self.get_template_by_name(session, tmpl_in.name)
        if existing:
            raise ValueError(f"Template with name '{tmpl_in.name}' already exists")

        t = Template(
            name=tmpl_in.name,
            scope=tmpl_in.scope,
            version=tmpl_in.version,
            content=tmpl_in.content,
            status=tmpl_in.status
        )
        session.add(t)
        await session.commit()
        await session.refresh(t)
        return t

    async def get_template(self, session: AsyncSession, tmpl_id: int) -> Optional[Template]:
        stmt = select(Template).where(Template.id == tmpl_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_template_by_name(self, session: AsyncSession, name: str) -> Optional[Template]:
        stmt = select(Template).where(Template.name == name)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_templates(
        self, session: AsyncSession, scope: Optional[str] = None, status: Optional[str] = None, skip: int = 0, limit: int = 50
    ) -> List[Template]:
        stmt = select(Template).order_by(Template.id.desc())
        if scope:
            stmt = stmt.where(Template.scope == scope)
        if status:
            stmt = stmt.where(Template.status == status)
        stmt = stmt.offset(skip).limit(limit)
        res = await session.execute(stmt)
        return res.scalars().all()

    async def update_template(self, session: AsyncSession, tmpl_id: int, up: TemplateUpdate) -> Optional[Template]:
        t = await self.get_template(session, tmpl_id)
        if not t:
            return None

        if up.name and up.name != t.name:
            existing = await self.get_template_by_name(session, up.name)
            if existing:
                raise ValueError(f"Template with name '{up.name}' already exists")

        data = up.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(t, k, v)
        await session.commit()
        await session.refresh(t)
        return t

    async def delete_template(self, session: AsyncSession, tmpl_id: int) -> bool:
        t = await self.get_template(session, tmpl_id)
        if not t:
            return False
        await session.delete(t)
        await session.commit()
        return True

    def render_content(self, content: str, variables: Dict[str, Any]) -> str:
        try:
            tmpl = jinja2.Template(content)
            return tmpl.render(**variables)
        except jinja2.TemplateError as e:
            raise ValueError(f"Template rendering syntax error: {e}")

    async def render_template(self, session: AsyncSession, tmpl_id: int, variables: Dict[str, Any]) -> str:
        t = await self.get_template(session, tmpl_id)
        if not t:
            raise ValueError("Template not found")
        return self.render_content(t.content, variables)
