"""
PPT 母版模板列表 API

提供 GET /api/v1/templates/ppt 接口供前端拉取可选模板。
"""

from typing import List

from fastapi import APIRouter, Depends

from app.models.user import User
from app.api.deps import get_current_active_user_sse
from app.services.ppt_template import PPTTemplateService

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("/ppt")
async def list_ppt_templates(
    current_user: User = Depends(get_current_active_user_sse),
) -> dict:
    """返回所有可用 PPT 母版模板的元数据列表。

    前端导出对话框调用此接口填充"PPT 主题"二级菜单。
    """
    svc = PPTTemplateService()
    items = svc.list_templates()
    return {
        "items": [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "file": t.file,
                "layouts_count": t.layouts_count,
            }
            for t in items
        ],
        "total": len(items),
    }
