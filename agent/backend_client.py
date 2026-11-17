# -*- coding: utf-8 -*-
"""后端 REST 封装：统一解包 {code, message, data}。

Agent 的「非生成」工具（档案 / 食材 / 菜式 / 核算 / RAG / 反向营养 / 疾病规则 / 周报）
都走后端 HTTP；「生成方案」走 rule_engine（见 rule_engine_bridge.py，进程内直调）。
"""
import contextvars

import requests

import config

BASE = config.BACKEND_BASE_URL.rstrip("/")
_TIMEOUT = 30

# 本机回连后端（127.0.0.1）不走系统代理：requests 默认 trust_env 会读系统代理，
# 在开了 Clash/V2Ray 等代理的机器上会把 localhost 也路由到代理导致 502。
_session = requests.Session()
_session.trust_env = False

# 后端业务接口都要 JWT（403/401 否则），Agent 由后端 /agent/chat 代调时必须复用调用方身份。
# 后端在请求体里带上 token，main.py 收到后调 set_token()。
# 用 ContextVar 而非模块级全局变量：SSE 是流式的，并发请求各有独立 ASGI task context，
# 每个请求的 token 只在本 task 内可见，避免 A 的 token 被 B 覆盖导致身份串号/越权。
_token_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "agent_backend_token", default=None
)


def set_token(token: str | None) -> None:
    """设置当前请求上下文使用的 Bearer token（由后端 /agent/chat 透传）。"""
    _token_ctx.set(token or None)


def _auth_headers() -> dict:
    token = _token_ctx.get()
    return {"Authorization": f"Bearer {token}"} if token else {}


class BackendError(RuntimeError):
    """后端业务错误（code != 0）或网络异常；code 保留后端业务码供按码分支。"""

    def __init__(self, message: str, code: int | None = None, data=None):
        super().__init__(message)
        self.code = code
        self.data = data


def _parse(resp: requests.Response):
    try:
        body = resp.json()
    except ValueError:
        raise BackendError(f"后端返回非 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")
    if isinstance(body, dict) and body.get("code") != 0:
        raise BackendError(
            str(body.get("message") or ""),
            code=body.get("code"),
            data=body.get("data"),
        )
    return body.get("data") if isinstance(body, dict) else body


def _get(path: str, params: dict | None = None):
    try:
        resp = _session.get(f"{BASE}{path}", params=params, headers=_auth_headers(), timeout=_TIMEOUT)
    except requests.RequestException as e:
        raise BackendError(f"请求后端失败：{e}")
    return _parse(resp)


def _post(path: str, payload: dict | None = None):
    try:
        resp = _session.post(f"{BASE}{path}", json=payload, headers=_auth_headers(), timeout=_TIMEOUT)
    except requests.RequestException as e:
        raise BackendError(f"请求后端失败：{e}")
    return _parse(resp)


def _put(path: str, payload: dict | None = None):
    try:
        resp = _session.put(f"{BASE}{path}", json=payload, headers=_auth_headers(), timeout=_TIMEOUT)
    except requests.RequestException as e:
        raise BackendError(f"请求后端失败：{e}")
    return _parse(resp)


# ---------------------------------------------------------------- 档案
def get_profile(user_id: str):
    """读取用户完整档案（API-20 / T12）。"""
    # 契约已改为 /api/profile，不拼 URL。
    return _get("/api/profile")

def upsert_profile(user_id: str, **fields):
    """创建 / 更新用户档案（API-01）。"""
    payload = {"user_id": user_id, **fields}
    return _put("/api/profile", payload) # 切回标准的 PUT


# ---------------------------------------------------------------- 食材 / 菜式
def search_ingredients(q: str, limit: int = 20):
    return _get("/api/ingredients/search", {"q": q, "limit": limit})


def search_dishes(q: str | None = None, exclude_allergies: list[str] | None = None,
                  page: int = 1, page_size: int = 20):
    params: dict = {"page": page, "page_size": page_size}
    if q:
        params["q"] = q
    if exclude_allergies:
        params["exclude_allergies"] = ",".join(exclude_allergies)
    return _get("/api/dishes/search", params)


# ---------------------------------------------------------------- 营养核算
def calc_nutrition(target_type: str, items: list[dict], include_micro: bool = True):
    return _post("/api/calc/nutrition", {
        "target_type": target_type, "items": items, "include_micro": include_micro,
    })


# ---------------------------------------------------------------- 营养分析
def nutrition_analysis(meal_plan_id: int):
    return _post("/api/nutrition/analysis", {"meal_plan_id": meal_plan_id})


def get_nutrition_report(meal_plan_id: int):
    return _get("/api/nutrition/report", {"meal_plan_id": meal_plan_id})


def period_analysis(report_type: str, window_days: int | None = None,
                    period_start: str | None = None, period_end: str | None = None):
    """周/月/自定义维度跨方案报告（API-25b）。report_type: week | month | custom。"""
    payload: dict = {"report_type": report_type}
    if window_days is not None:
        payload["window_days"] = window_days
    if period_start is not None:
        payload["period_start"] = period_start
    if period_end is not None:
        payload["period_end"] = period_end
    return _post("/api/nutrition/period-analysis", payload)


# ---------------------------------------------------------------- 疾病规则
def rule_catalog(page: int = 1, page_size: int = 50):
    return _get("/api/condition-rules/catalog", {"page": page, "page_size": page_size})


def production_rules():
    return _get("/api/condition-rules/production")


def evaluate_rule(user_id: str, intake_date: str, rule_id: str):
    return _post("/api/condition-rules/evaluate", {
        "user_id": user_id, "intake_date": intake_date, "rule_id": rule_id,
    })


# ---------------------------------------------------------------- 知识 / 反向营养
def rag_query(query: str, top_k: int = 5):
    return _post("/api/agent/rag-query", {"query": query, "top_k": top_k})


def reverse_nutrition(symptoms: str, top_k: int = 5):
    return _post("/api/agent/reverse-nutrition", {"symptoms": symptoms, "top_k": top_k})

# ---------------------------------------------------------------- 调用后端接口生成方案并落库
def generate_meal_plan(user_id: str, start_date: str, end_date: str, meal_types: list,
                       exclude_ingredients: list[str] | None = None):
    """调用后端真实接口生成方案并落库。

    后端 /meal-plan/week/generate 已是「用户自定范围」：直接透传任意 start_date/end_date/meal_types，
    去掉 scope 三档硬编码（后端 GenerateRequest 本就没有 scope 字段，此前被 pydantic 静默忽略）。
    """
    payload = {
        "user_id": user_id,
        "start_date": start_date,
        "end_date": end_date,
        "meal_types": meal_types,
    }
    if exclude_ingredients:
        payload["exclude_ingredients"] = exclude_ingredients
    return _post("/api/meal-plan/week/generate", payload)

# -----------------------------------------------------------------------------
def get_meal_plan(meal_plan_id) -> dict:
    """按 id 取方案详情（API-04），含 slots / candidates / dishes 四级结构。"""
    return _get(f"/api/meal-plan/{meal_plan_id}")


def get_shopping_list(meal_plan_id) -> dict:
    """取方案食材清单（API-27，fix 时已按食材级生成落库）。"""
    return _get("/api/shopping-list", {"meal_plan_id": meal_plan_id})


def swap_candidate(meal_plan_id: str, meal_slot_id: str, candidate_id: str = None) -> dict:
    """换一换候选，落库持久化"""
    payload = {
        "meal_plan_id": meal_plan_id,
        "meal_slot_id": meal_slot_id
    }
    if candidate_id:
        payload["candidate_id"] = candidate_id
    return _post("/api/meal-plan/candidate/swap", payload)

def fix_meal_plan(meal_plan_id: str, selections: dict = None, replace: bool = False) -> dict:
    """确认方案，落库持久化；replace=True 表示若与已有固定方案餐位重叠则取代旧方案。"""
    payload = {"meal_plan_id": meal_plan_id, "replace": replace}
    if selections:
        payload["selections"] = selections
    return _post("/api/meal-plan/week/fix", payload)