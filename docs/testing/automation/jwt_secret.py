"""测试脚本共用的 JWT 密钥来源。

B6 已把后端 JWT_SECRET 轮换成随机串，脚本不再硬编码 `change-me-in-production`：
1) 优先 `LIVE_JWT_SECRET` 环境变量；
2) 其次从仓库 `backend/.env` 的 `JWT_SECRET=` 行读取；
3) 都取不到时直接退出并提示，避免签发无效 token 后误判为接口故障。

明文密钥只在进程内使用，不打印、不落报告。
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[3] / "backend" / ".env"


def jwt_secret() -> str:
    value = os.getenv("LIVE_JWT_SECRET", "").strip()
    if value:
        return value
    try:
        for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("JWT_SECRET="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    except OSError:
        value = ""
    if not value:
        raise SystemExit(
            "未取到 JWT_SECRET：请设置环境变量 LIVE_JWT_SECRET，"
            f"或确认 {ENV_FILE} 中存在 JWT_SECRET=... 行"
        )
    return value
