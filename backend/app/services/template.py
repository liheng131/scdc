"""
报告模板服务

提供 Jinja2 模板的 CRUD 和渲染能力，支持报告内容的动态生成。

使用场景：
- ReporterAgent 生成报告后，通过模板将结构化数据渲染为最终 Markdown 文本
- 用户可自定义模板内容，调整报告的格式、段落结构、数据展示方式
- 支持按 scope 分类（如 "report"、"email"、"summary"），按 status 管理生命周期

为什么选择 Jinja2：
- Python 生态中最成熟的模板引擎，语法简洁
- 支持条件判断、循环、过滤器等编程能力
- 沙箱执行（基础 Template 类不含 eval 等危险操作）
"""

from typing import List, Optional, Dict, Any
import jinja2
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.template import Template
from app.schemas.template import TemplateCreate, TemplateUpdate

class TemplateService:
    async def create_template(self, session: AsyncSession, tmpl_in: TemplateCreate) -> Template:
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
        """
        使用 Jinja2 渲染模板字符串

        为什么 try/except 捕获 TemplateError：
        - 用户自定义模板可能存在语法错误（如未闭合的 {{ }}）
        - 返回明确错误信息比 Jinja2 原始异常栈更友好
        """
        try:
            tmpl = jinja2.Template(content)
            return tmpl.render(**variables)
        except jinja2.TemplateError as e:
            raise ValueError(f"Template rendering syntax error: {e}")

    async def render_template(self, session: AsyncSession, tmpl_id: int, variables: Dict[str, Any]) -> str:
        """根据模板 ID 查找模板并渲染，供 ReporterAgent 调用"""
        t = await self.get_template(session, tmpl_id)
        if not t:
            raise ValueError("Template not found")
        return self.render_content(t.content, variables)
