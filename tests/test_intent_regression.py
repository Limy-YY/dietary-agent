# -*- coding: utf-8 -*-
"""意图回归表（窗口⑤）：锁 `_regex_intent` 的 canonical / gray 边界。

收敛原则（P0）：正则只当「高精度」分类器——canonical 话术命中，语义灰区一律 None 交 LLM。
灰区是回归锚点：「推荐补钙食物」「贫血吃什么」这类营养问答曾因正则高召回被误判成配餐。

覆盖四组：
  1) canonical 话术（换/选/确认/固定/取消 + 明确范围词）必须命中；
  2) 语义灰区必须返回 None（交 LLM 走 rag_qa / plan_custom / 澄清）；
  3) QA 灰区在无 LLM 兜底路径下也绝不落成 plan_*；
  4) 确定性偏好抽取（「不要X」→硬排除、「清淡/少油」→软偏好）。

运行：`pytest tests/test_intent_regression.py -q`（离线，无 DB/LLM 依赖）。
"""
from __future__ import annotations

import pytest

import agent


# ---------------------------------------------------------------- 1. canonical 话术必须命中


@pytest.mark.parametrize(
    "msg,expected",
    [
        # 换 / 选（卡片按钮话术，必须带明确餐次）
        ("换一换午餐", {"intent": "swap_candidate", "meal_type": "午餐"}),
        ("换一换早餐", {"intent": "swap_candidate", "meal_type": "早餐"}),
        ("换个候选晚餐", {"intent": "swap_candidate", "meal_type": "晚餐"}),
        ("选这个午餐", {"intent": "choose_candidate", "meal_type": "午餐", "name": "选这个午餐"}),
        ("选用晚餐", {"intent": "choose_candidate", "meal_type": "晚餐", "name": "选用晚餐"}),
        # 确认 / 固定（含「替换」类确定性动作）
        ("确认", {"intent": "confirm", "replace": False}),
        ("固定", {"intent": "confirm", "replace": False}),
        ("就这个方案", {"intent": "confirm", "replace": False}),
        ("替换", {"intent": "confirm", "replace": True}),
        ("覆盖", {"intent": "confirm", "replace": True}),
        # 取消
        ("取消", {"intent": "cancel"}),
        ("算了", {"intent": "cancel"}),
        ("不用了", {"intent": "cancel"}),
        # 明确范围词 → 配餐粒度
        ("生成一周食谱", {"intent": "plan_week"}),
        ("一周", {"intent": "plan_week"}),
        ("七天", {"intent": "plan_week"}),
        ("推荐一餐", {"intent": "plan_meal", "meal_type": "午餐"}),
        ("推荐午餐", {"intent": "plan_meal", "meal_type": "午餐"}),
        ("来一餐", {"intent": "plan_meal", "meal_type": "午餐"}),
        ("三餐", {"intent": "plan_day"}),
        ("一日三餐", {"intent": "plan_day"}),
        ("今天吃什么", {"intent": "plan_day"}),
        ("生成菜单", {"intent": "plan_day"}),
        # 报告 / 结构化卡片动作
        ("生成周膳食报告", {"intent": "report", "scope": "week"}),
        ("生成月膳食报告", {"intent": "report", "scope": "month"}),
        ("完整食谱", {"intent": "recipe_detail"}),
        ("食材清单", {"intent": "shopping_list"}),
        ("为什么这样搭", {"intent": "explain"}),
    ],
)
def test_canonical_intents(msg, expected):
    assert agent._regex_intent(msg) == expected


# ---------------------------------------------------------------- 2. 语义灰区必须返回 None


@pytest.mark.parametrize(
    "msg",
    [
        # 营养问答（最易被高召回正则误判成配餐）
        "推荐补钙食物",
        "贫血吃什么",
        "高血压食谱",
        "吃什么补铁",
        # 软偏好 / 模糊餐次提问 / 自定义范围（交 LLM 抽日期餐次）
        "这周清淡点",
        "午餐吃什么",
        "换一换",           # 缺餐次 → 不抢先
        "出差三天",
        "三天",
        "下周一到周三",
        "只排午餐",
    ],
)
def test_gray_areas_deferred(msg):
    assert agent._regex_intent(msg) is None


# ---------------------------------------------------------------- 3. 灰区绝不误入配餐（确定性路径）


def test_qa_gray_not_plan_without_llm(monkeypatch):
    """QA 灰区在无 LLM 兜底路径下也绝不落成 plan_*（防正则/症状短路误判成配餐）。

    这里 mock 掉 `_llm`，使 `classify` 走确定性兜底，保证回归可离线、可进 CI。
    「这周清淡点」这类软偏好规划请求不在此列——它交给 LLM 出规划意图，本就允许规划。
    """
    monkeypatch.setattr(agent, "_llm", lambda: None)
    for msg in ("推荐补钙食物", "贫血吃什么", "高血压食谱", "吃什么补铁"):
        assert agent.classify(msg)["intent"] == "chat"


def test_symptom_short_circuit_is_deterministic(monkeypatch):
    """症状词在正则之后、LLM 之前短路到 reverse_nutrition，不依赖 LLM。"""
    monkeypatch.setattr(agent, "_llm", lambda: None)
    assert agent.classify("乏力")["intent"] == "reverse_nutrition"


# ---------------------------------------------------------------- 4. 确定性偏好抽取（意图 → 引擎参数）


def test_extract_exclude_and_soft_avoid():
    """「不要X」→ 硬排除；「清淡/少油」→ 软偏好关键词（供引擎降权，不硬排除）。"""
    pref = agent._extract_preferences("不要牛肉，清淡点")
    assert "牛肉" in pref["exclude"]
    assert "炒" in pref["soft_avoid"] and "油炸" in pref["soft_avoid"]


def test_extract_exclude_only():
    pref = agent._extract_preferences("别吃香菜")
    assert pref["exclude"] == ["香菜"]
    assert pref["soft_avoid"] == []


def test_extract_empty():
    assert agent._extract_preferences("") == {"exclude": [], "soft_avoid": []}
