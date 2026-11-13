"""规则引擎的领域异常。

业务码与《后端接口契约 v1.2》一致：
- 2005 方案状态非法（由 API 层判定，引擎不抛）
- 2006 硬约束不可满足（引擎抛，交由 API 层转成 2006）
"""

from __future__ import annotations


class RuleEngineError(Exception):
    """规则引擎的可预期失败（不满足硬约束、数据不足等）。"""

    def __init__(self, code: str, message: str, detail: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}


class HardConstraintUnsatisfiable(RuleEngineError):
    """每餐连兜底候选都无法满足硬约束（过敏原/宗教/忌口/厨具）。"""

    def __init__(self, message: str, detail: dict | None = None) -> None:
        super().__init__(code="2006", message=message, detail=detail)


class InsufficientData(RuleEngineError):
    """菜式或参考值不足，无法产出有意义结果。"""

    def __init__(self, message: str, detail: dict | None = None) -> None:
        super().__init__(code="2006", message=message, detail=detail)
