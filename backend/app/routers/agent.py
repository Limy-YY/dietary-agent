"""知识检索接口（T9/T10 / API-15/16）。

API-15：优先走 `knowledge.search_documents` 的 RRF 混合检索（向量路 + 关键词路，
权重 1:1、`k=60`、`top_k=5`、每路池 20）；未配置 `EMBEDDING_API_KEY` 或函数不可用时，
自动退化为纯关键词 RRF；再不行回落进程内关键词兜底，并在 `method` 字段如实标注。
T10 反向营养：symptom_nutrient_map 表待数据岗补（D3），先走知识库关键词兜底。
"""
import logging
import re

try:  # B4：中文分词。缺包时退 n-gram，不让检索接口因为一个新依赖起不来
    import jieba

    jieba.setLogLevel(60)  # 关掉首次加载词典的日志，避免污染 stderr
except Exception:  # noqa: BLE001
    jieba = None

from fastapi import APIRouter, Depends
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.response import ApiResponse, api_success
from app.db import get_db
from app.schemas.agent import RagItem, RagQueryRequest, RagResult, ReverseNutritionRequest, ReverseNutritionResult
from app.services.embedding import embed_text, to_pgvector_literal

router = APIRouter(prefix="/agent", tags=["agent"])

logger = logging.getLogger(__name__)

#: 向量路最低余弦相似度默认值（B5：改由 settings.RAG_MIN_SIMILARITY 提供，此处仅作兜底说明）
_MIN_SIMILARITY = 0.5

#: 查询切片段：空白与中英文标点
_QUERY_SPLIT = re.compile(r"[\s,，。、；;：:？?！!（）()\[\]【】\"'“”‘’·/]+")
_CJK = re.compile(r"[\u4e00-\u9fff]")
#: 中文停用词：问句骨架，只参与召回、不参与打分（避免「每天/多少」把无关文档顶上来）
_CJK_STOP_WORDS = {
    "请问", "怎么", "怎样", "如何", "多少", "什么", "哪些", "哪个", "为什么", "是否",
    "能不能", "可以", "应该", "需要", "推荐", "合适", "一天", "每天", "每日", "一次",
    "我", "你", "他", "她", "的", "了", "吗", "呢", "啊", "和", "与", "及", "或",
    "在", "是", "有", "要", "吃", "这", "那", "一些", "比较", "告诉", "建议", "请",
    "告诉我", "问题", "情况", "时候", "一般", "大概", "左右",
}


def _tokenize(query: str) -> list[str]:
    """把查询切成检索词（B4）。

    英文/数字按标点切；中文优先 jieba 精确分词，缺包时退 2 字 n-gram。
    某中文片段滤完停用词后若只剩单字（如「钙每天补多少」→ 钙 / 每天 / 补 / 多少），
    保留全部切词：宁可多召回也不丢实词，停用词在打分阶段不计分，不会抬高噪声。
    """
    terms: list[str] = []
    for part in _QUERY_SPLIT.split(query or ""):
        if not part:
            continue
        if not _CJK.search(part):
            terms.append(part)
            continue
        if jieba is not None:
            words = [w for w in jieba.cut_for_search(part) if w.strip()]
        else:
            words = [part[i:i + 2] for i in range(max(len(part) - 1, 1))]
        strong = [w for w in words if len(w) >= 2 and w not in _CJK_STOP_WORDS]
        if strong:
            terms.extend(strong)
            # 单字实词也带上：中文营养素名（钙/铁/锌）和英文代号（维生素D 的 D）都是单字
            terms.extend(
                w for w in words
                if len(w) == 1 and w not in _CJK_STOP_WORDS and w.isalnum()
                and w.lower() not in ("a", "i")
            )
        else:
            terms.extend(words)

    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        t = t.strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out[:12]


def _score_terms(terms: list[str], title: str, content: str, category: str) -> float:
    """命中度打分：title 0.9 / category 0.5 / content 0.7，取实词均值。

    停用词只召回不计分；实词全不命中返回 0（该文档直接不进结果）。
    """
    title = (title or "").lower()
    content = (content or "").lower()
    category = (category or "").lower()
    weights: list[float] = []
    for t in terms:
        if t in _CJK_STOP_WORDS:
            continue
        t = t.lower()
        if t in title:
            weights.append(0.9)
        elif t in category:
            weights.append(0.5)
        elif t in content:
            weights.append(0.7)
        else:
            weights.append(0.0)
    return round(sum(weights) / len(weights), 6) if weights else 0.0


def _search_knowledge(query: str, top_k: int, db: Session) -> list[RagItem]:
    """关键词检索（B4 重写）：knowledge_doc 为主，nutrient_knowledge 补位。

    旧实现按空格分词 + 整串 `ILIKE '%整句%'` + AND 语义，中文无空格查询必然 0 命中。
    现在：jieba 分词 → `ILIKE` OR 召回 → Python 侧按命中度排序，命中实词为 0 的被丢弃。
    """
    terms = _tokenize(query)
    if not terms:
        return []
    n = len(terms)

    # 中文问句没有空格，不能把整句当成一个 AND 关键词：先按分词结果 OR 召回，
    # 再给「别名 / 标题整串出现在问句里」的文档加权（沿用主线的别名匹配思路）。
    where = " OR ".join(
        f"(title ILIKE :w{i} OR content ILIKE :w{i} OR category ILIKE :w{i})"
        for i in range(len(terms))
    )
    alias_match = (
        "EXISTS (SELECT 1 FROM jsonb_array_elements_text("
        "COALESCE(meta_data -> 'aliases', '[]'::jsonb)) AS a(value) "
        "WHERE length(a.value) >= 2 AND :query ILIKE '%' || a.value || '%')"
    )
    title_in_query = "(length(title) >= 2 AND :query ILIKE '%' || title || '%')"
    rows = db.execute(
        text(
            f"SELECT knowledge_doc_id, title, content, category, source, source_id, "
            f"       NULLIF(meta_data ->> 'source_url', '') AS source_url, "
            f"       (CASE WHEN {alias_match} THEN 1.0 "
            f"        WHEN {title_in_query} THEN 0.95 ELSE 1.0 END) AS boost "
            f"FROM knowledge.knowledge_doc "
            f"WHERE NOT is_deleted AND ({where} OR {alias_match} OR {title_in_query}) "
            f"LIMIT 300"
        ),
        {"query": query, **{f"w{i}": f"%{t}%" for i, t in enumerate(terms)}},
    ).mappings().all()

    scored = [
        (_score_terms(terms, r["title"], r["content"], r["category"]) * float(r["boost"] or 1.0), r)
        for r in rows
    ]
    scored = [s for s in scored if s[0] > 0]
    scored.sort(key=lambda x: (-x[0], x[1]["knowledge_doc_id"]))
    items = [
        RagItem(
            doc_id=str(r["knowledge_doc_id"]),
            title=r["title"],
            content=r["content"],
            source=r["source"],
            source_id=r["source_id"],
            source_url=r["source_url"],
            category=r["category"],
            score=s,
            kind="doc",
        )
        for s, r in scored[:top_k]
    ]

    if len(items) < top_k:
        nwhere = " OR ".join(
            f"(payload::text ILIKE :w{i} OR nutrient_id ILIKE :w{i})" for i in range(len(terms))
        )
        nrows = db.execute(
            text(
                f"SELECT nutrient_id, payload::text AS content, "
                f"COALESCE(payload ->> 'name', nutrient_id) AS name_zh "
                f"FROM knowledge.nutrient_knowledge "
                f"WHERE {nwhere} LIMIT 100"
            ),
            {f"w{i}": f"%{t}%" for i, t in enumerate(terms)},
        ).mappings().all()
        nscored = [
            (_score_terms(terms, r["name_zh"], r["content"], ""), r) for r in nrows
        ]
        nscored = [s for s in nscored if s[0] > 0]
        nscored.sort(key=lambda x: (-x[0], x[1]["nutrient_id"]))
        items.extend(
            RagItem(
                title=f"营养素知识：{r['name_zh']}",
                content=r["content"],
                score=s,
                kind="nutrient",
            )
            for s, r in nscored[: top_k - len(items)]
        )
    return items


def _search_hybrid(query: str, top_k: int, db: Session) -> tuple[list[RagItem], str]:
    """RRF 混合检索（`knowledge.search_documents`），不可用时回落关键词兜底。

    返回 `(items, method)`：`hybrid_rrf` 表示向量+关键词双路融合，
    `rrf_text_only` 表示仅有查询向量缺失时的关键词路 RRF，
    `keyword_fallback` 表示检索函数不存在（未跑 14 脚本）或查询为空。
    """
    settings = get_settings()
    embedding = embed_text(query)
    sql = text(
        "SELECT s.knowledge_doc_id, s.title, s.category, s.content, s.score, "
        "       s.vector_rank, s.text_rank, d.source, d.source_id, "
        "       NULLIF(d.meta_data ->> 'source_url', '') AS source_url "
        "FROM knowledge.search_documents("
        "CAST(:q AS text), CAST(:emb AS vector), "
        "CAST(:limit AS integer), CAST(:min_sim AS numeric), CAST(:rrf_k AS integer)) s "
        "JOIN knowledge.knowledge_doc d ON d.knowledge_doc_id = s.knowledge_doc_id "
        "ORDER BY s.score DESC, s.knowledge_doc_id"
    )
    try:
        rows = db.execute(
            sql,
            {
                "q": query,
                "emb": to_pgvector_literal(embedding),
                "limit": top_k,
                "min_sim": settings.RAG_MIN_SIMILARITY,
                "rrf_k": settings.RAG_RRF_K,
            },
        ).mappings().all()
    except Exception as exc:  # noqa: BLE001 —— 退化路径不能把检索接口打挂
        # 函数未部署 / 权限不足 / 维度不符：回到进程内关键词兜底，不影响出参结构
        logger.warning("search_documents 不可用，回落关键词兜底：%s", exc)
        db.rollback()
        return _search_knowledge(query, top_k, db), "keyword_fallback"

    if not rows:
        return _search_knowledge(query, top_k, db), "keyword_fallback"

    # BUG-027：knowledge.search_documents 的 RETURNS TABLE 不含 source/source_id，
    # 这里按 knowledge_doc_id 回查一次补齐，保证 hybrid 与 keyword_fallback 两路溯源行为一致。
    doc_ids = [r["knowledge_doc_id"] for r in rows]
    sources: dict[int, tuple[str | None, str | None]] = {}
    try:
        src_rows = db.execute(
            text(
                "SELECT knowledge_doc_id, source, source_id FROM knowledge.knowledge_doc "
                "WHERE knowledge_doc_id IN :ids"
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": doc_ids},
        ).mappings().all()
        sources = {r["knowledge_doc_id"]: (r["source"], r["source_id"]) for r in src_rows}
    except Exception as exc:  # noqa: BLE001 —— 溯源补查失败不应把检索接口打挂
        logger.warning("溯源回查失败，source 置空：%s", exc)
        db.rollback()

    items = [
        RagItem(
            doc_id=str(r["knowledge_doc_id"]),
            title=r["title"] or "",
            content=r["content"] or "",
            source=(sources.get(r["knowledge_doc_id"]) or (None, None))[0],
            source_id=(sources.get(r["knowledge_doc_id"]) or (None, None))[1],
            category=r["category"],
            score=float(r["score"]) if r["score"] is not None else None,
            kind="doc",
        )
        for r in rows
    ]
    return items, ("hybrid_rrf" if embedding is not None else "rrf_text_only")


#: B7 营养参考值召回：默认取成人 18-29 岁层（rag-query 无 user_id，不做个性化）
_REFERENCE_DEFAULT_AGE_GROUP = "18-29"
_REFERENCE_SOURCE_NAME = "中国营养学会《中国居民膳食营养素参考摄入量（2023版）》"
_REFERENCE_SOURCE_ID = "DRIs 2023"


def _match_nutrients(query: str, db: Session) -> list[dict]:
    """从查询文本识别营养素（确定性匹配，不做模糊）。

    命中规则：`core.nutrient.name_zh` 括号外主名（如「维生素B1（硫胺素）」→「维生素B1」）
    出现在查询里；否则用 `knowledge.nutrient_knowledge.payload.aliases` 兜底，
    别名限定 ≥2 字符，避免「Ca」「B1」这类短串误命中无关文本。
    """
    rows = db.execute(
        text(
            "SELECT n.nutrient_id, n.name_zh, n.unit, "
            "       COALESCE(k.payload -> 'aliases', '[]'::jsonb) AS aliases "
            "FROM core.nutrient n "
            "LEFT JOIN knowledge.nutrient_knowledge k ON k.nutrient_id = n.nutrient_id"
        )
    ).mappings().all()

    hits: list[dict] = []
    for r in rows:
        name_zh = (r["name_zh"] or "").strip()
        base = name_zh.split("（")[0].strip()
        matched = bool(base) and base in query
        if not matched:
            for alias in (r["aliases"] or []):
                alias = str(alias).strip()
                if len(alias) >= 2 and alias in query:
                    matched = True
                    break
        if matched:
            hits.append({"nutrient_id": r["nutrient_id"], "name_zh": name_zh, "unit": r["unit"]})
    return hits


def _fmt_num(v) -> str:
    """数值格式化：800.0 → 800，0.75 → 0.75。"""
    if v is None:
        return ""
    f = float(v)
    return str(int(f)) if f == int(f) else f"{f:g}"


def _search_nutrient_reference(query: str, db: Session) -> list[RagItem]:
    """B7：营养参考值召回路。命中营养素时查 `core.nutrient_reference`。

    取成人 18-29 岁层；男/女数值一致时合并为一条「成人」，不一致时按性别各出一条。
    数值全部取自库，不在此处推算或补默认值。
    """
    items: list[RagItem] = []
    for n in _match_nutrients(query, db):
        rows = db.execute(
            text(
                "SELECT sex, age_group, reference_type, value, ul_value "
                "FROM core.nutrient_reference "
                "WHERE nutrient_id = :nid "
                "ORDER BY age_min_months, sex, age_group"
            ),
            {"nid": n["nutrient_id"]},
        ).mappings().all()
        if not rows:
            # 库内无该营养素的 RNI/AI 行（当前 8 种：叶酸/ω-3/B12/B5/B6/B7/D/K）。
            # 给一条显式「暂无数据」提示且不返回任何数值，避免 Agent 编造，
            # 也避免把 nutrient_knowledge 的科普文案当成参考量引用。
            items.append(
                RagItem(
                    doc_id=f"notice:no-reference:{n['nutrient_id']}",
                    title=f"{n['name_zh']}：库内暂无参考值",
                    content=(
                        f"{n['name_zh']} 的 RNI/AI 参考摄入量尚未入库，本节不给数值。"
                        "需要按参考量安排摄入时，请以《中国居民膳食营养素参考摄入量（2023）》原文为准。"
                    ),
                    source=_REFERENCE_SOURCE_NAME,
                    source_id=_REFERENCE_SOURCE_ID,
                    category="营养参考值",
                    kind="notice",
                )
            )
            continue

        # 代表层取成人 18-29（rag-query 无 user_id，不做个性化）；无该层时退到全量首层
        adult = [r for r in rows if r["age_group"] == _REFERENCE_DEFAULT_AGE_GROUP] or rows

        # 年龄分层全量随 reference.layers 一并返回，供 Agent 按用户年龄/孕哺期取用
        layers = [
            {
                "age_group": r["age_group"],
                "sex": r["sex"],
                "reference_type": r["reference_type"],
                "value": float(r["value"]),
                "ul": float(r["ul_value"]) if r["ul_value"] is not None else None,
            }
            for r in rows
        ]

        unit = n["unit"] if n["unit"] and n["unit"] != "未提供" else ""
        by_value: dict[tuple, list] = {}
        for r in adult:
            key = (r["reference_type"], _fmt_num(r["value"]), _fmt_num(r["ul_value"]))
            by_value.setdefault(key, []).append(r)

        groups: list[tuple[str, list]] = []
        if len(by_value) == 1:
            groups.append(("成人", next(iter(by_value.values()))))
        else:
            for _key, rs in by_value.items():
                label = {"male": "男", "female": "女"}.get(rs[0]["sex"], rs[0]["sex"])
                groups.append((label, rs))

        for idx, (label, rs) in enumerate(groups):
            r = rs[0]
            rt = r["reference_type"]
            value = _fmt_num(r["value"])
            ul = _fmt_num(r["ul_value"])
            age = r["age_group"]
            who = "成人" if label == "成人" else f"{label}性"
            headline = f"{who}（{age}岁）每天 {value} {unit}".strip()
            content = f"{rt} {value} {unit}/天".strip()
            if ul:
                content += f"；UL（可耐受最高摄入量）{ul} {unit}/天"
            ref = {
                "nutrient_id": n["nutrient_id"],
                "name_zh": n["name_zh"],
                "unit": unit,
                "age_group": age,
                "sex": "both" if label == "成人" else r["sex"],
                "reference_type": rt,
                "value": float(r["value"]),
                "ul": float(r["ul_value"]) if r["ul_value"] is not None else None,
                "headline": headline,
            }
            # 分层只挂第一条，避免同营养素多条 item 各自重复一份全量
            if idx == 0:
                ref["layers"] = layers
            items.append(
                RagItem(
                    title=f"营养参考值：{n['name_zh']}（{label}）",
                    content=content,
                    source=_REFERENCE_SOURCE_NAME,
                    source_id=_REFERENCE_SOURCE_ID,
                    category="营养参考值",
                    kind="reference",
                    reference=ref,
                )
            )
    return items


@router.post("/rag-query")
def rag_query(req: RagQueryRequest, db: Session = Depends(get_db)) -> ApiResponse[RagResult]:
    """RAG 知识库检索（RRF 混合检索，兼容关键词退化；每条带 doc_id 溯源）。

    B7：命中营养素时先去 `core.nutrient_reference` 取定量参考值（kind=reference），
    再按原检索顺序补齐文档，总量仍受 `top_k` 约束。
    """
    items, method = _search_hybrid(req.query, req.top_k, db)
    refs = _search_nutrient_reference(req.query, db)
    if refs:
        items = (refs + items)[: req.top_k]
    return api_success(RagResult(items=items, method=method))


def _search_symptom_map(symptoms: str, db: Session) -> list[RagItem]:
    """确定性反向营养映射（症状 → 营养素）：查 core.symptom_nutrient_map。

    按 symptom 与 aliases 子串命中输入症状文本；仅取 is_active 记录（数据岗审核后置 active）。
    命中条目映射成 RagItem：title=「症状→营养素」、content=advice（措辞已含「可能…建议就医」）、
    source 取 core.data_source，供 Agent「可溯源」标注。
    """
    symptoms = (symptoms or "").strip()
    if not symptoms:
        return []
    rows = db.execute(
        text(
            "SELECT m.symptom_nutrient_map_id, m.symptom, m.aliases, m.nutrient_id, "
            "       m.advice, m.evidence_level, m.source_id, ds.source_name, ds.source_url "
            "FROM core.symptom_nutrient_map m "
            "LEFT JOIN core.data_source ds ON ds.source_id = m.source_id "
            "WHERE m.is_active"
        )
    ).mappings().all()
    items: list[RagItem] = []
    for r in rows:
        terms = [r["symptom"]] + list(r["aliases"] or [])
        if not any(t and t in symptoms for t in terms):
            continue
        items.append(
            RagItem(
                doc_id=str(r["symptom_nutrient_map_id"]),
                title=f"{r['symptom']} → {r['nutrient_id']}",
                content=r["advice"],
                source=r["source_name"],
                source_id=str(r["source_id"]) if r["source_id"] is not None else None,
                source_url=r["source_url"],
                category="symptom_nutrient_map",
                kind="symptom",
            )
        )
    return items


@router.post("/reverse-nutrition")
def reverse_nutrition(
    req: ReverseNutritionRequest, db: Session = Depends(get_db)
) -> ApiResponse[ReverseNutritionResult]:
    """反向营养推理（症状 → 营养素）：优先查 core.symptom_nutrient_map（确定性映射），
    未命中时回落知识库关键词兜底；结果仅作线索，不得直接作为诊断依据。"""
    items = _search_symptom_map(req.symptoms, db)
    if items:
        return api_success(
            ReverseNutritionResult(
                items=items,
                method="symptom_map",
                note="命中反向营养映射（symptom_nutrient_map）；结果仅作参考线索，不构成医学诊断。",
            )
        )
    items = _search_knowledge(req.symptoms, req.top_k, db)
    return api_success(
        ReverseNutritionResult(
            items=items,
            method="keyword_fallback",
            note="未命中反向营养映射，回落知识库关键词兜底；结果仅作参考线索，不构成医学诊断。",
        )
    )
