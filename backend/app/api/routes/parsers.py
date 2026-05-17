from typing import Any
from fastapi import APIRouter, UploadFile, File, Depends
from app.api.responses import success_response, ResponseModel
from app.schemas.parser import ParseResult
from app.parsers.manager import ParserManager
from app.api.deps import get_current_active_user
from app.models.user import User
import io

router = APIRouter()
parser_manager = ParserManager()

@router.post("/upload", response_model=ResponseModel[ParseResult])
async def upload_and_parse_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    contents = await file.read()
    file_stream = io.BytesIO(contents)
    result = await parser_manager.parse_file(file_stream, file.filename)
    return success_response(data=result)
