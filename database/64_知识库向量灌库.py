#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""64_知识库向量灌库.py —— 配置向导 + 一键灌库（包装 15_RAG灌库脚本.py）

解决什么：
  15 脚本要靠一堆环境变量（PGDSN / EMBEDDING_BASE_URL / EMBEDDING_API_KEY ...），
  换个人、换台机器就要重新 set 一遍。本脚本把「配一次、存下来、以后直接跑」做成一条路径。

用法：
  python 64_知识库向量灌库.py            向导：检查配置 → 缺什么问什么 → 存 .env → 问要不要现在灌
  python 64_知识库向量灌库.py --check    只体检：配置 + 连库 + 调一次 embedding 验证 key 有效
  python 64_知识库向量灌库.py --run      用已存配置直接灌，不再交互
  python 64_知识库向量灌库.py --dry-run  只统计待灌数量与预估调用量，不调模型不写库（不花钱）
  python 64_知识库向量灌库.py --set-key  只更新 API Key（打码输入），不灌库

配置存哪：
  backend/.env（该文件在 .gitignore，不会提交）。已有其它行原样保留，只改下面 5 个键。
  Windows 下可直接双击同目录的 灌库.bat。

前置：
  1. 库已建好，且 14_RAG向量化 的 knowledge_doc.embedding / v_embedding_backlog 存在；
  2. 本机 python 已装 psycopg（pip install "psycopg[binary]>=3.1"）。

退出码：0 成功；1 灌库有失败批次；2 配置/前置不满足；3 用户中断。
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

DB_DIR = Path(__file__).resolve().parent
ROOT = DB_DIR.parent
ENV_PATH = ROOT / "backend" / ".env"
ENV_EXAMPLE = ROOT / "backend" / ".env.example"

# 本脚本负责的键：(说明, 默认值, 是否敏感)
MANAGED = {
    "DATABASE_URL": ("数据库连接串", "postgresql+psycopg://postgres@127.0.0.1:5432/diet_agent", False),
    "EMBEDDING_BASE_URL": ("嵌入服务地址（OpenAI 兼容 /v1 前缀）", "https://api.siliconflow.cn/v1", False),
    "EMBEDDING_MODEL": ("嵌入模型", "BAAI/bge-m3", False),
    "EMBEDDING_DIM": ("向量维度（必须与 embedding 列一致）", "1024", False),
    "EMBEDDING_API_KEY": ("嵌入服务 API Key", "", True),
}


# --------------------------------------------------------------------------
# .env 读写（保留其它行，只替换受管键）
# --------------------------------------------------------------------------
def parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip("'\"")
    return out


def write_env(updates: dict[str, str]) -> Path:
    """把 updates 写回 backend/.env：命中键就地替换，未命中追加；写前备份。"""
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not ENV_PATH.exists() and ENV_EXAMPLE.exists():
        shutil.copyfile(ENV_EXAMPLE, ENV_PATH)
        print(f"[信息] 未找到 backend/.env，已从 .env.example 复制一份")

    lines = ENV_PATH.read_text(encoding="utf-8", errors="ignore").splitlines() if ENV_PATH.exists() else []
    bak = ENV_PATH.with_suffix(ENV_PATH.suffix + time.strftime(".bak-%Y%m%d%H%M%S"))
    if ENV_PATH.exists():
        shutil.copyfile(ENV_PATH, bak)

    remaining = dict(updates)
    new_lines: list[str] = []
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k in remaining:
                new_lines.append(f"{k}={remaining.pop(k)}")
                continue
        new_lines.append(line)

    if remaining:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append("# --- 知识库向量灌库（64_知识库向量灌库.py 自动写入） ---")
        for k, v in remaining.items():
            new_lines.append(f"{k}={v}")

    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    try:  # 尽量收权限，Windows 上无效果
        os.chmod(ENV_PATH, 0o600)
    except Exception:
        pass
    return bak


def mask(value: str) -> str:
    if not value:
        return "（未设置）"
    if len(value) <= 8:
        return value[:2] + "***"
    return f"{value[:6]}***（{len(value)} 字符）"


# --------------------------------------------------------------------------
# 探测
# --------------------------------------------------------------------------
def dsn_for_psycopg(url: str) -> str:
    """postgresql+psycopg:// -> postgresql://，psycopg 只认后者。"""
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url.strip())


def probe_db(url: str) -> tuple[bool, str]:
    try:
        import psycopg
    except ImportError:
        return False, "未安装 psycopg：pip install \"psycopg[binary]>=3.1\""
    try:
        with psycopg.connect(dsn_for_psycopg(url), connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute("select count(*) from knowledge.knowledge_doc")
                docs = cur.fetchone()[0]
                cur.execute("select count(*) from knowledge.knowledge_doc where embedding is not null")
                with_emb = cur.fetchone()[0]
                cur.execute("select count(*) from knowledge.v_embedding_backlog")
                backlog = cur.fetchone()[0]
        return True, f"文档 {docs} 篇 / 已有向量 {with_emb} 篇 / 待灌 {backlog} 篇"
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).strip().splitlines()[0]
        return False, f"连不上或缺少对象：{msg}"


def probe_embedding(base_url: str, model: str, key: str, dim: int, timeout: int = 30) -> tuple[bool, str]:
    """真发一次最小请求，验证 key / 模型 / 维度三者是否对得上。"""
    payload = json.dumps({"model": model, "input": ["连通性测试"]}, ensure_ascii=False).encode()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(base_url.rstrip("/") + "/embeddings", data=payload, headers=headers, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        items = body.get("data") or []
        if not items:
            return False, f"返回里没有 data（{json.dumps(body, ensure_ascii=False)[:200]}）"
        vec = items[0].get("embedding") or []
        cost = round(time.time() - t0, 2)
        if len(vec) != dim:
            return False, f"返回维度 {len(vec)} 与配置 {dim} 不一致，先对齐再灌"
        return True, f"模型可用，维度 {len(vec)} 一致（{cost}s）"
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:300].decode("utf-8", "ignore")
        return False, f"HTTP {exc.code}：{detail}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}：{exc}"


# --------------------------------------------------------------------------
# 交互
# --------------------------------------------------------------------------
def ask(prompt: str, default: str = "", secret: bool = False, allow_empty: bool = False) -> str:
    hint = f"（默认 {default}）" if default and not secret else ""
    tty = sys.stdin.isatty()
    while True:
        try:
            if secret and tty:
                val = getpass.getpass(f"{prompt}{hint}: ")
            else:
                # 非终端（管道 / 重定向）下 getpass 会去抢 /dev/tty 导致卡死，退回普通输入
                val = input(f"{prompt}{hint}: ")
        except (EOFError, KeyboardInterrupt):
            print("\n[中断] 已退出，未做任何修改。")
            raise SystemExit(3)
        val = val.strip()
        if val:
            return val
        if default:
            return default
        if allow_empty:
            return ""
        print("  这一项不能为空，请重新输入。")


def configure(cfg: dict[str, str], interactive: bool, set_key_only: bool) -> dict[str, str]:
    """找出缺失项，逐项补全；返回需要写回的键值。"""
    updates: dict[str, str] = {}

    if set_key_only:
        print("\n只更新 API Key（输入时不回显）。留空回车则放弃。")
        val = ask("新的 EMBEDDING_API_KEY", secret=True, allow_empty=True)
        if not val:
            print("[取消] 没有输入，退出。")
            raise SystemExit(0)
        updates["EMBEDDING_API_KEY"] = val
        return updates

    # 环境变量兜底：CI / 服务器上 export 即可，不必写 .env
    for key in MANAGED:
        if not cfg.get(key) and os.environ.get(key):
            cfg[key] = os.environ[key]

    missing = [k for k, (_, default, _) in MANAGED.items() if not cfg.get(k) or cfg.get(k, "").startswith("<")]
    if not missing:
        if interactive and not set_key_only:
            ans = input("\n配置已齐全，要替换哪些？直接回车=不替换，输入 K 只换 Key: ").strip().lower()
            if ans == "k":
                val = ask("新的 EMBEDDING_API_KEY", secret=True, allow_empty=True)
                if val:
                    updates["EMBEDDING_API_KEY"] = val
        return updates

    if not interactive:
        print(f"\n[错误] 缺配置：{', '.join(missing)}", file=sys.stderr)
        print("  非交互环境，无法逐项询问。二选一：", file=sys.stderr)
        print("   1) 先跑一次交互模式（或双击 灌库.bat）把配置存进 backend/.env；", file=sys.stderr)
        print("   2) 用环境变量提供，例如 set EMBEDDING_API_KEY=sk-xxx。", file=sys.stderr)
        raise SystemExit(2)

    print(f"\n[配置] 缺 {len(missing)} 项，逐项补一下（直接回车用默认值）：")
    for key in missing:
        desc, default, secret = MANAGED[key]
        updates[key] = ask(f"  {desc} [{key}]", default=default, secret=secret)
    return updates


# --------------------------------------------------------------------------
# 调 15 脚本
# --------------------------------------------------------------------------
def find_engine() -> Path:
    cands = sorted(DB_DIR.glob("15_*.py"))
    if not cands:
        print("[错误] 同目录找不到 15_RAG灌库脚本.py", file=sys.stderr)
        raise SystemExit(2)
    return cands[0]


def run_engine(cfg: dict[str, str], extra: list[str]) -> int:
    engine = find_engine()
    env = os.environ.copy()
    env["PGDSN"] = dsn_for_psycopg(cfg["DATABASE_URL"])
    env["EMBEDDING_BASE_URL"] = cfg["EMBEDDING_BASE_URL"]
    env["EMBEDDING_MODEL"] = cfg["EMBEDDING_MODEL"]
    env["EMBEDDING_DIM"] = cfg.get("EMBEDDING_DIM", "1024")
    env["EMBEDDING_MODE"] = "api"
    env["EMBEDDING_API_KEY"] = cfg.get("EMBEDDING_API_KEY", "")
    env.setdefault("PGCLIENTENCODING", "UTF8")

    cmd = [sys.executable, str(engine), *extra]
    print(f"\n[执行] {engine.name} {' '.join(extra)}")
    print("-" * 62)
    proc = subprocess.run(cmd, env=env, cwd=str(DB_DIR))
    print("-" * 62)
    return proc.returncode


# --------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="知识库向量灌库：配置一次，之后直接跑")
    parser.add_argument("--check", action="store_true", help="只体检配置/连库/调一次 embedding")
    parser.add_argument("--run", action="store_true", help="用已存配置直接灌库")
    parser.add_argument("--dry-run", action="store_true", help="只统计待灌数量，不调模型")
    parser.add_argument("--set-key", action="store_true", help="只更新 API Key")
    parser.add_argument("--no-probe", action="store_true", help="跳过 embedding 连通性探测（不花额度）")
    parser.add_argument("--batch-size", type=int, default=32, help="每批条数，透传给 15 脚本")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少条，0=全部")
    parser.add_argument("--yes", "-y", action="store_true", help="不询问，直接执行")
    args = parser.parse_args()

    interactive = sys.stdin.isatty() and not args.yes
    cfg = parse_env(ENV_PATH)
    print("=" * 62)
    print(" 膳宝 · 知识库向量灌库（222 基线）")
    print("=" * 62)

    # ---------- 1 配置 ----------
    updates = configure(cfg, interactive, args.set_key)
    if updates:
        bak = write_env(updates)
        cfg.update(updates)
        print(f"[信息] 已保存到 {ENV_PATH}（备份 {bak.name}，该文件不入库）")

    print("\n[当前配置]")
    for key in MANAGED:
        val = cfg.get(key, "")
        shown = mask(val) if MANAGED[key][2] else (val or "（未设置）")
        print(f"  {key:<22} {shown}")

    if args.set_key:
        print("\n[完成] Key 已更新，下次 --run 或直接运行即可灌库。")
        return 0

    # ---------- 2 体检 ----------
    ok_cfg = all(cfg.get(k) for k in MANAGED)
    if not ok_cfg:
        lack = [k for k in MANAGED if not cfg.get(k)]
        print(f"\n[错误] 仍缺配置：{', '.join(lack)}", file=sys.stderr)
        return 2

    print("\n[体检] 数据库 ...")
    db_ok, db_msg = probe_db(cfg["DATABASE_URL"])
    print(f"  {'OK ' if db_ok else 'FAIL'} {db_msg}")
    if not db_ok:
        print("\n  排查建议：确认库已启动、DATABASE_URL 的端口/库名正确；"
              "\n  若提示 v_embedding_backlog 不存在，先执行 14_RAG向量化_v1.2r1.sql。", file=sys.stderr)
        return 2

    if args.check:
        if args.no_probe:
            print("\n[体检] 跳过 embedding 探测（--no-probe）")
        else:
            print("\n[体检] 嵌入服务 ...（会消耗一次极小额度）")
            em_ok, em_msg = probe_embedding(
                cfg["EMBEDDING_BASE_URL"], cfg["EMBEDDING_MODEL"],
                cfg.get("EMBEDDING_API_KEY", ""), int(cfg.get("EMBEDDING_DIM", "1024")),
            )
            print(f"  {'OK ' if em_ok else 'FAIL'} {em_msg}")
            if not em_ok:
                print("  排查建议：Key 是否过期、模型名是否与服务商一致、base_url 是否带 /v1。", file=sys.stderr)
                return 2
        print("\n[完成] 体检通过，可以 --run 或 --dry-run。")
        return 0

    # ---------- 3 执行 ----------
    extra: list[str] = ["--batch-size", str(args.batch_size)]
    if args.limit:
        extra += ["--limit", str(args.limit)]

    if args.dry_run:
        return run_engine(cfg, extra + ["--dry-run"])

    if not args.run and interactive:
        ans = input(f"\n现在开始灌库？待灌 {db_msg.split('待灌 ')[-1]}（y/N）: ").strip().lower()
        if ans not in ("y", "yes"):
            print("[取消] 已退出，配置已保存，下次 --run 直接跑。")
            return 0

    if not args.no_probe:
        print("\n[体检] 嵌入服务 ...")
        em_ok, em_msg = probe_embedding(
            cfg["EMBEDDING_BASE_URL"], cfg["EMBEDDING_MODEL"],
            cfg.get("EMBEDDING_API_KEY", ""), int(cfg.get("EMBEDDING_DIM", "1024")),
        )
        print(f"  {'OK ' if em_ok else 'FAIL'} {em_msg}")
        if not em_ok:
            return 2

    code = run_engine(cfg, extra)

    print("\n[复查] 灌库结果")
    _, after = probe_db(cfg["DATABASE_URL"])
    print(f"  {after}")
    return code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"\n[异常] {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)
