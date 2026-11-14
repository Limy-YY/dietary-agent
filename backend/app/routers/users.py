"""用户档案接口（T12 / API-20）。

数据库对象：app.profile。Agent 工具接口：读取当前用户完整档案。
Agent 不自行持有档案：每次读取最新档案，硬约束（过敏/忌口/疾病）以本接口返回为准。
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import BizCode, BizError
from app.core.response import ApiResponse, api_success
from app.db import get_db
from app.routers.profile import PROFILE_SQL, row_to_profile
from app.schemas.profile import UserProfile

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{user_id}/profile")
def get_user_profile(user_id: str, db: Session = Depends(get_db)) -> ApiResponse[UserProfile]:
    """读取用户完整档案（Agent 工具，T12）。"""
    row = db.execute(text(PROFILE_SQL), {"uid": user_id}).mappings().first()
    if row is None:
        raise BizError(code=BizCode.NOT_FOUND, message=f"用户档案不存在: {user_id}")
    return api_success(row_to_profile(row))
