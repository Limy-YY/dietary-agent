# -*- coding: utf-8 -*-
"""后端 REST 封装：统一解包 {code, message, data}。

Agent 的「非生成」工具（档案 / 食材 / 菜式 / 核算 / RAG / 反向营养 / 疾病规则 / 周报）
都走后端 HTTP；「生成方案」走 rule_engine（见 rule_engine_bridge.py，进程内直调）。
"""
import requests

import config

BASE = config.BACKEND_BASE_URL.rstrip("/")
_TIMEOUT = 30


class BackendError(RuntimeError):
    """后端业务错误（code != 0）或网络异常。"""


def _parse(resp: requests.Response):
    try:
        body = resp.json()
    except ValueError:
        raise BackendError(f"后端返回非 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")
    if isinstance(body, dict) and body.get("code") != 0:
        raise BackendError(f"后端错误 code={body.get('code')}：{body.get('message')}")
    return body.get("data") if isinstance(body, dict) else body


def _get(path: str, params: dict | None = None):
    try:
        resp = requests.get(f"{BASE}{path}", params=params, timeout=_TIMEOUT)
    except requests.RequestException as e:
        raise BackendError(f"请求后端失败：{e}")
    return _parse(resp)


def _post(path: str, payload: dict | None = None):
    try:
        resp = requests.post(f"{BASE}{path}", json=payload, timeout=_TIMEOUT)
    except requests.RequestException as e:
        raise BackendError(f"请求后端失败：{e}")
    return _parse(resp)


# ---------------------------------------------------------------- 档案
def get_profile(user_id: str):
    """读取用户完整档案（API-20 / T12）。"""
    return _get(f"/api/users/{user_id}/profile")


def upsert_profile(user_id: str, **fields):
    """创建 / 更新用户档案（API-01）。"""
    payload = {"user_id": user_id, **fields}
    return _post("/api/profile", payload)


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


# ---------------------------------------------------------------- 周度报告
def weekly_report(user_id: str, week_start: str):
    return _get("/api/nutrition/weekly-report", {"user_id": user_id, "week_start": week_start})


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
