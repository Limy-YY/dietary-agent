# -*- coding: utf-8 -*-
"""窗口⑤测试的导入地基：把 `agent/` 与 `backend/` 挂到 `sys.path`。

- `import agent` 需要 `agent/` 在 sys.path（Agent 是平铺模块，无包 `__init__.py`，
  内部用 `import backend_client` / `import blocks` 这类平铺相对导入）；
- `from app.services.rule_engine import ...` 需要 `backend/` 在 sys.path。

两个目录都只是**只读依赖**（纯计算 + 确定性路由），不碰 DB / LLM / 网络，
因此意图回归与硬约束画像回归均可离线跑、可进 CI。
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

for _p in (_ROOT / "agent", _ROOT / "backend"):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)
