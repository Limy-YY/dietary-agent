# -*- coding: utf-8 -*-
"""RAG 向量召回评测：量化 recall@k，验证 p_min_similarity。

背景：`16_RAG对齐与灌库说明.md` 遗留风险「向量质量无评测集」。
本脚本做一个小评测集（真实问句 → 期望命中的 stable_key），跑 `knowledge.search_documents`，
输出每条命中情况 + recall@k + 不同阈值下的召回对比，用于把 p_min_similarity 定死（默认 0.5）。

用法（在后端 venv 里，配好 EMBEDDING_* 与 DATABASE_URL）：
    python eval_recall.py

依赖：openai（或任意 OpenAI 兼容嵌入）+ sqlalchemy + psycopg。
"""
from __future__ import annotations

import os
from collections import defaultdict

from openai import OpenAI
from sqlalchemy import create_engine, text

EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://diet_app:diet_app_dev@localhost:5432/diet_agent"
)
TOP_K = 5

# 评测集：真实问句 → 期望命中的 stable_key 列表
# topic:* 为 19 号脚本新增的 17 篇；nutrient:*:overview 为 26 篇营养素条目。
# 营养素 slug 以库内为准：SELECT stable_key FROM knowledge.knowledge_doc WHERE stable_key LIKE 'nutrient:%';
QUERIES: dict[str, list[str]] = {
    "高血压病人饮食要注意什么": ["topic:hypertension_diet"],
    "糖尿病患者怎么控制血糖": ["topic:diabetes_diet"],
    "高血脂饮食建议": ["topic:hyperlipidemia_diet"],
    "痛风尿酸高不能吃什么": ["topic:hyperuricemia_diet"],
    "脂肪肝怎么吃": ["topic:fatty_liver_diet"],
    "慢性肾病饮食注意": ["topic:ckd_diet"],
    "孕妇孕期营养补充": ["topic:pregnancy_nutrition"],
    "哺乳期妈妈吃什么好": ["topic:lactation_nutrition"],
    "老年人营养注意什么": ["topic:elderly_nutrition"],
    "儿童营养怎么搭配": ["topic:child_nutrition"],
    "减脂怎么吃": ["topic:weight_loss_diet"],
    "平衡膳食餐盘怎么搭": ["topic:balance_plate"],
    "钠和钾怎么平衡": ["topic:sodium_potassium_balance"],
    "全谷杂粮怎么当主食": ["topic:whole_grain_staple"],
    "过敏食材怎么替代": ["topic:allergen_substitution"],
    "剩菜剩饭怎么处理安全": ["topic:food_safety_leftover"],
    "生吃食物有风险吗": ["topic:raw_food_risk"],
    "钙每天要补多少": ["nutrient:calcium:overview"],
    "缺铁吃什么补铁": ["nutrient:iron:overview"],
    "锌的作用和食物来源": ["nutrient:zinc:overview"],
    "维生素C每天摄入多少": ["nutrient:vitamin_c:overview"],
    "维生素A缺乏会怎样": ["nutrient:vitamin_a:overview"],
    "膳食纤维每天吃多少": ["nutrient:fiber:overview"],
    "钠每天摄入多少合适": ["nutrient:sodium:overview"],
}


def _vec_str(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"


def _embed(client: OpenAI, text: str) -> list[float] | None:
    try:
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
        return resp.data[0].embedding
    except Exception:
        return None


def _search(conn, query: str, vec: list[float] | None, p_min: float) -> list[dict]:
    v = _vec_str(vec) if vec is not None else None
    return conn.execute(text(
        "SELECT d.stable_key, d.title, s.vector_similarity "
        "FROM knowledge.search_documents("
        "  CAST(:q AS text), CAST(:emb AS vector), :limit, :pmin, 60) s "
        "JOIN knowledge.knowledge_doc d ON d.knowledge_doc_id = s.knowledge_doc_id "
        "ORDER BY s.score DESC"
    ), {"q": query, "emb": v, "limit": TOP_K, "pmin": p_min}).mappings().all()


def main() -> int:
    if not EMBEDDING_API_KEY:
        print("缺少 EMBEDDING_API_KEY")
        return 1
    client = OpenAI(api_key=EMBEDDING_API_KEY, base_url=EMBEDDING_BASE_URL)
    engine = create_engine(DATABASE_URL)

    # 先打印库内真实 stable_key，供核对营养素 slug 是否写对
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT stable_key FROM knowledge.knowledge_doc "
            "WHERE NOT is_deleted ORDER BY stable_key"
        )).scalars().all()
        print(f"库内知识条目共 {len(rows)} 条：")
        print("  " + " ".join(rows[:43]) if rows else "  (空)")

    recalls: dict[float, float] = {}

    for p_min in (0.3, 0.4, 0.5, 0.6):  # 多阈值跑一遍，看召回曲线定 p_min_similarity
        print(f"\n===== p_min_similarity = {p_min}（top_k={TOP_K}）=====")
        total_relevant = 0
        total_hit = 0
        missed = []
        with engine.connect() as conn:
            for q, truth in QUERIES.items():
                vec = _embed(client, q)
                if vec is None:
                    print(f"  [embed fail] {q}")
                    continue
                rows = _search(conn, q, vec, p_min)
                keys = [r["stable_key"] for r in rows]
                hit = len(set(truth) & set(keys))
                total_relevant += len(truth)
                total_hit += hit
                mark = "✓" if hit else "✗"
                if not hit:
                    missed.append((q, keys))
                sims = [f"{r['title']}({float(r['vector_similarity']):.2f})" for r in rows[:TOP_K]]
                print(f"  {mark} {q} -> {sims}")
        if total_relevant:
            recall = total_hit / total_relevant
            recalls[p_min] = recall
            print(f"\n  recall@{TOP_K} = {total_hit}/{total_relevant} = {recall:.2%}")
        else:
            print("  无标注")
        if missed:
            print("  未命中：")
            for q, keys in missed:
                print(f"    - {q} 实际返回 {keys}")

    min_recall = float(os.getenv("MIN_RECALL", "0"))
    if recalls and min_recall > 0:
        worst = min(recalls.values())
        print(f"\n各阈值 recall：{', '.join(f'{p:.0f}={r:.2%}' for p, r in sorted(recalls.items()))}")
        if worst < min_recall:
            print(f"[FAIL] 最差 recall {worst:.2%} 低于门禁 {min_recall:.0%}")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
