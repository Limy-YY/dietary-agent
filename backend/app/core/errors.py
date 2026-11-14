"""业务错误码：与《后端接口契约 v1.2》§2.5 一致。"""
from enum import IntEnum


class BizCode(IntEnum):
    OK = 0
    PARAM_ERROR = 1001
    UNAUTHORIZED = 1002
    FORBIDDEN = 1003
    NOT_FOUND = 1004
    CALC_FAILED = 2001
    AGENT_CALL_FAILED = 2002
    STRUCTURED_OUTPUT_INVALID = 2003
    DATA_SOURCE_UNAVAILABLE = 2004
    PLAN_STATE_CONFLICT = 2005
    PLAN_GENERATION_FAILED = 2006
    CONTENT_SAFETY_BLOCKED = 3001


class BizError(Exception):
    """业务异常：携带业务码与提示信息。"""

    def __init__(self, code: BizCode, message: str, http_status: int = 400):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)
