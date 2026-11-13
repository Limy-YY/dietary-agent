"""健康检查：验证服务与数据库连通性。"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health(db: Session = Depends(get_db)) -> dict:
    """GET /api/health：服务与数据库状态。"""
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "unavailable"
    return {
        "service": "diet-agent-backend",
        "status": "ok" if db_status == "ok" else "degraded",
        "database": db_status,
    }
