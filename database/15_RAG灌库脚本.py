#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
15_RAG灌库脚本.py  ——  knowledge.knowledge_doc 的嵌入灌库/重灌工具（v1.2r1）

配套文件：
  14_RAG向量化_v1.2r1.sql   建 vector 扩展、embedding 列、HNSW 索引、检索函数
  16_RAG对齐与灌库说明.md   模型/维度对齐记录、灌库 SOP、验收口径

工作方式：
  1) 从 knowledge.v_embedding_backlog 取待灌/待重灌文档（从未灌过，或内容 md5 变过）；
  2) 分批调用嵌入后端（OpenAI 兼容 /embeddings 接口，或本地命令行模型）；
  3) 校验维度后调用 knowledge.apply_document_embedding() 写回，并记录 model / dim / content hash；
  4) 重复执行是幂等的：hash 未变的文档不会再调用模型。

三种运行模式：
  默认            调模型并写库
  --dry-run       只统计待灌数量与预估调用量，不调模型不写库
  --emit FILE     调模型但不写库，把 (id, md5, vector) 落到 JSONL，便于离线核查或换机灌库

用法示例：
  set PGHOST=127.0.0.1 & set PGPORT=5432 & set PGDATABASE=diet_agent
  set EMBEDDING_BASE_URL=https://api.example.com/v1
  set EMBEDDING_API_KEY=sk-xxx
  python 15_RAG灌库脚本.py --dry-run
  python 15_RAG灌库脚本.py --batch-size 32
  python 15_RAG灌库脚本.py --emit vectors.jsonl --limit 100

退出码：0 成功（含无事可做）；1 有失败批次；2 配置或前置条件不满足。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Iterable, Iterator


def env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        fail(f"缺少环境变量 {name}")
    return value or ""


def fail(message: str, code: int = 2) -> "NoReturn":  # type: ignore[name-defined]
    print(f"[配置错误] {message}", file=sys.stderr)
    raise SystemExit(code)


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
class Config:
    def __init__(self, args: argparse.Namespace) -> None:
        self.dsn = env("PGDSN") or " ".join(
            filter(
                None,
                [
                    f"host={env('PGHOST', '127.0.0.1')}",
                    f"port={env('PGPORT', '5432')}",
                    f"dbname={env('PGDATABASE', 'diet_agent')}",
                    f"user={env('PGUSER', 'postgres')}",
                    f"password={env('PGPASSWORD')}" if env("PGPASSWORD") else "",
                ],
            )
        )
        self.model = args.model or env("EMBEDDING_MODEL", "bge-m3")
        self.dim = int(args.dim or env("EMBEDDING_DIM", "1024"))
        self.mode = args.embed_mode or env("EMBEDDING_MODE", "api")
        self.base_url = env("EMBEDDING_BASE_URL", "http://127.0.0.1:9997/v1").rstrip("/")
        self.api_key = env("EMBEDDING_API_KEY")
        self.command = args.command or env("EMBEDDING_COMMAND")
        self.batch_size = args.batch_size
        self.limit = args.limit
        self.dry_run = args.dry_run
        self.emit = args.emit
        self.timeout = args.timeout
        self.retry = args.retry

        if self.mode not in ("api", "command"):
            fail("EMBEDDING_MODE 只能是 api 或 command")
        if self.mode == "command" and not self.command:
            fail("command 模式需要 --command 或 EMBEDDING_COMMAND（从 stdin 读 JSONL、向 stdout 写 JSONL）")
        if self.dim != 1024:
            fail(
                f"EMBEDDING_DIM={self.dim} 与 14 脚本中的列维度 1024 不一致；"
            "请先把 14_RAG向量化_v1.2r1.sql 中的 1024 统一改成新维度并重建列与索引"
            )

    def banner(self) -> str:
        masked = "（未设置）" if not self.api_key else self.api_key[:6] + "***"
        return (
            f"模型={self.model} 维度={self.dim} 后端={self.mode} "
            f"base_url={self.base_url if self.mode == 'api' else '-'} key={masked} "
            f"批大小={self.batch_size} 上限={self.limit or '不限'}"
        )


# ---------------------------------------------------------------------------
# 数据库
# ---------------------------------------------------------------------------
def connect(dsn: str):
    try:
        import psycopg
    except ImportError:
        fail("未安装 psycopg：pip install 'psycopg[binary]>=3.1'")
    try:
        return psycopg.connect(dsn, autocommit=False)
    except Exception as exc:  # noqa: BLE001
        fail(f"连不上数据库：{exc}")


def fetch_backlog(conn, limit: int | None) -> list[tuple[int, str, str, str]]:
    sql = """
        SELECT knowledge_doc_id, stable_key, title, content
        FROM knowledge.v_embedding_backlog
        ORDER BY knowledge_doc_id
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    with conn.cursor() as cur:
        cur.execute(sql)
        return [(r[0], r[1], r[2], r[3]) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# 嵌入后端
# ---------------------------------------------------------------------------
def embed_api(texts: list[str], cfg: Config) -> list[list[float]]:
    payload = json.dumps({"model": cfg.model, "input": texts}, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"

    last_error = None
    for attempt in range(cfg.retry + 1):
        try:
            req = urllib.request.Request(cfg.base_url + "/embeddings", data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            items = body.get("data") or []
            if len(items) != len(texts):
                raise RuntimeError(f"返回条数 {len(items)} 与请求条数 {len(texts)} 不一致")
            items.sort(key=lambda d: d.get("index", 0))
            return [[float(x) for x in item["embedding"]] for item in items]
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}: {exc.read()[:200].decode('utf-8', 'ignore')}"
            if exc.code in (429, 500, 502, 503, 504):
                time.sleep(min(2 ** attempt, 30))
                continue
            raise RuntimeError(last_error) from exc
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            time.sleep(min(2 ** attempt, 30))
    raise RuntimeError(f"重试 {cfg.retry} 次仍失败：{last_error}")


def embed_command(texts: list[str], cfg: Config) -> list[list[float]]:
    payload = "\n".join(json.dumps({"text": t}, ensure_ascii=False) for t in texts) + "\n"
    proc = subprocess.run(
        cfg.command,
        shell=True,
        input=payload.encode("utf-8"),
        capture_output=True,
        timeout=cfg.timeout * 3,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"命令后端退出码 {proc.returncode}：{proc.stderr[:300].decode('utf-8', 'ignore')}")
    rows = [json.loads(ln) for ln in proc.stdout.decode("utf-8").splitlines() if ln.strip()]
    if len(rows) != len(texts):
        raise RuntimeError(f"命令后端返回 {len(rows)} 条，请求 {len(texts)} 条")
    return [[float(x) for x in r["embedding"]] for r in rows]


def embed_batch(texts: list[str], cfg: Config) -> list[list[float]]:
    vectors = embed_api(texts, cfg) if cfg.mode == "api" else embed_command(texts, cfg)
    for idx, vec in enumerate(vectors):
        if len(vec) != cfg.dim:
            raise RuntimeError(f"第 {idx} 条向量维度 {len(vec)} 与配置 {cfg.dim} 不一致")
    return vectors


# ---------------------------------------------------------------------------
# 写回
# ---------------------------------------------------------------------------
def write_back(conn, doc_id: int, vector: list[float], cfg: Config, content_hash: str) -> None:
    literal = "[" + ",".join(f"{v:.7f}" for v in vector) + "]"
    with conn.cursor() as cur:
        cur.execute(
            "SELECT updated_id FROM knowledge.apply_document_embedding(%s, %s::vector, %s, %s)",
            (doc_id, literal, cfg.model, content_hash),
        )
        cur.fetchone()


def batches(rows: list, size: int) -> Iterator[list]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def main() -> int:
    parser = argparse.ArgumentParser(description="knowledge_doc 嵌入灌库（v1.2r1）")
    parser.add_argument("--batch-size", type=int, default=32, help="每批调用条数，默认 32")
    parser.add_argument("--limit", type=int, default=0, help="本次最多处理多少条，0 表示全部")
    parser.add_argument("--model", help="覆盖 EMBEDDING_MODEL")
    parser.add_argument("--dim", help="覆盖 EMBEDDING_DIM，必须与 embedding 列维度一致")
    parser.add_argument("--embed-mode", choices=["api", "command"], help="覆盖 EMBEDDING_MODE")
    parser.add_argument("--command", help="command 模式下的外部命令")
    parser.add_argument("--timeout", type=int, default=60, help="单次调用超时（秒）")
    parser.add_argument("--retry", type=int, default=3, help="失败重试次数")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不调模型不写库")
    parser.add_argument("--emit", help="把向量写到 JSONL 文件而不写库")
    args = parser.parse_args()

    cfg = Config(args)
    print(f"[信息] {cfg.banner()}")

    conn = connect(cfg.dsn)
    try:
        rows = fetch_backlog(conn, cfg.limit)
        print(f"[信息] 待灌/待重灌 {len(rows)} 条")

        if cfg.dry_run:
            chars = sum(len(r[3]) for r in rows)
            calls = (len(rows) + cfg.batch_size - 1) // cfg.batch_size
            print(f"[信息] 预计 {calls} 次后端调用，约 {chars} 字符；不改动数据库")
            return 0

        if not rows:
            print("[信息] 无事可做（内容 hash 与向量记录一致）")
            return 0

        ok = failed = 0
        emit_fh = open(cfg.emit, "w", encoding="utf-8") if cfg.emit else None
        try:
            for batch in batches(rows, cfg.batch_size):
                texts = [r[3] for r in batch]
                try:
                    vectors = embed_batch(texts, cfg)
                except Exception as exc:  # noqa: BLE001
                    failed += len(batch)
                    print(f"[失败] 批次 {batch[0][0]}..{batch[-1][0]}：{exc}", file=sys.stderr)
                    continue

                for (doc_id, stable_key, title, content), vec in zip(batch, vectors):
                    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
                    if emit_fh:
                        emit_fh.write(
                            json.dumps(
                                {"knowledge_doc_id": doc_id, "stable_key": stable_key, "content_md5": content_hash,
                                 "model": cfg.model, "dim": len(vec), "embedding": vec},
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                        ok += 1
                    else:
                        try:
                            write_back(conn, doc_id, vec, cfg, content_hash)
                            conn.commit()
                            ok += 1
                        except Exception as exc:  # noqa: BLE001
                            conn.rollback()
                            failed += 1
                            print(f"[失败] 写回 {doc_id}（{title}）：{exc}", file=sys.stderr)
                print(f"[进度] 已完成 {ok}，失败 {failed}")
        finally:
            if emit_fh:
                emit_fh.close()

        if cfg.emit:
            print(f"[信息] 向量已写入 {cfg.emit}（未改数据库，可用 COPY/脚本导入）")
        else:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM knowledge.v_embedding_backlog")
                left = cur.fetchone()[0]
            print(f"[信息] 本次成功 {ok}，失败 {failed}，剩余待灌 {left}")
        return 0 if failed == 0 else 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
