"""JWT 鉴权（骨架）：签发与校验 token。"""
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header

from app.config import get_settings
from app.core.errors import BizCode, BizError


def create_access_token(user_id: str, expires_minutes: int | None = None) -> str:
    """签发 JWT，payload 携带 user_id。"""
    settings = get_settings()
    expire = expires_minutes or settings.TOKEN_EXPIRE_MINUTES
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=expire),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> str:
    """解析并校验 JWT，返回 user_id；失败抛业务异常。"""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise BizError(BizCode.UNAUTHORIZED, "登录已过期", http_status=401) from None
    except jwt.InvalidTokenError:
        raise BizError(BizCode.UNAUTHORIZED, "无效的访问令牌", http_status=401) from None
    user_id = payload.get("sub")
    if not user_id:
        raise BizError(BizCode.UNAUTHORIZED, "令牌缺少用户标识", http_status=401)
    return user_id


def get_current_user(authorization: str | None = Header(default=None)) -> str:
    """FastAPI 依赖：从 Authorization: Bearer <token> 提取当前 user_id。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise BizError(BizCode.UNAUTHORIZED, "缺少 Authorization 头", http_status=401)
    return decode_token(authorization[len("Bearer "):].strip())


# 供路由依赖注入的别名
CurrentUser = Depends(get_current_user)
