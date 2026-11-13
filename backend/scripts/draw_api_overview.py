# -*- coding: utf-8 -*-
"""绘制《系统设计说明书》4.4.1 接口总览图（分层接口关系，v3 布局）。

输出：接口总览图.png（白色背景，可直接插入飞书文档）
运行：backend/.venv/Scripts/python.exe scripts/draw_api_overview.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib import font_manager

FONT = Path("C:/Windows/Fonts/msyh.ttc")
if FONT.exists():
    font_manager.fontManager.addfont(str(FONT))
    plt.rcParams["font.family"] = "Microsoft YaHei"
plt.rcParams["axes.unicode_minus"] = False

fig, ax = plt.subplots(figsize=(10, 7.8), dpi=200)
ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
ax.axis("off")

C_DARK = "#1f2937"
C_LINE = "#4b5563"
C_FILL = "#f3f4f6"
C_BLUE = "#e8f0fe"
C_GREEN = "#e9f7ef"
C_ORANGE = "#fef3e2"
C_PURPLE = "#f0eafc"


def box(x0, y0, x1, y1, text="", fc=C_FILL, fs=10.5, bold=False, ec=C_LINE, lw=1.2):
    ax.add_patch(FancyBboxPatch(
        (x0, y0), x1 - x0, y1 - y0,
        boxstyle="round,pad=0.4,rounding_size=1.4",
        linewidth=lw, edgecolor=ec, facecolor=fc,
    ))
    if text:
        ax.text((x0 + x1) / 2, (y0 + y1) / 2, text, ha="center", va="center",
                fontsize=fs, color=C_DARK, fontweight="bold" if bold else "normal",
                linespacing=1.55)


def biarrow(x, y_bottom, y_top, label="", ls="-", color=C_LINE):
    """垂直双向箭头（若 y_bottom > y_top 自动交换），标签放箭头右侧。"""
    y0, y1 = min(y_bottom, y_top), max(y_bottom, y_top)
    for a, b in (((x, y0), (x, y1)), ((x, y1), (x, y0))):
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", linestyle=ls,
                                     mutation_scale=12, linewidth=1.25, color=color))
    if label:
        ax.text(x + 2.2, (y0 + y1) / 2, label, fontsize=8, color="#111827",
                ha="left", va="center",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.98))


def arrow_to(x0, y0, x1, y1, label="", lx=None, ly=None, color="#b45309"):
    for a, b in (((x0, y0), (x1, y1)), ((x1, y1), (x0, y0))):
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", linestyle="--",
                                     mutation_scale=12, linewidth=1.25, color=color))
    if label:
        ax.text(lx if lx is not None else (x0 + x1) / 2,
                ly if ly is not None else (y0 + y1) / 2 + 2.2,
                label, fontsize=8, color="#7c2d12", ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.98))


# 标题
ax.text(50, 96.8, "图 4-1  膳食搭配智能体系统接口总览（IF-UI / IF-EXT / IF-INT）",
        fontsize=13, fontweight="bold", ha="center", va="center", color=C_DARK)

X = 34                                 # 主链路箭头横坐标
LX0, LX1 = 3.5, 68                     # 主链路左/右边界

# 1 用户
box(28, 88.5, 45, 93.6, "用户（浏览器）", fc=C_BLUE, fs=10.5, bold=True)

# 2 前端三模块  83.2 - 72.5
box(LX0, 72.5, LX1, 83.2, fc="#fafafa")
ax.text(35.75, 81.4, "前端三模块（接口 IF-UI-01 ～ 03）", fontsize=9,
        ha="center", va="center", color=C_LINE)
box(5.5, 73.4, 23.5, 79.8, "FE_Profile｜档案管理", fs=9)
box(25.8, 73.4, 44.8, 79.8, "FE_MealPlan｜食谱规划", fs=9)
box(47, 73.4, 66, 79.8, "FE_Chat｜营养对话", fs=9)

# 3 接口层  57.5 - 68.2
box(LX0, 57.5, LX1, 68.2, fc=C_BLUE)
ax.text(35.75, 65.9, "接口层  FastAPI（BE_*）", fontsize=11, fontweight="bold",
        ha="center", va="center", color=C_DARK)
ax.text(35.75, 62.9, "REST 15 个（IF-EXT-01 ～ 15）｜SSE 流式（IF-EXT-16）｜JWT 鉴权｜{code, message, data}",
        fontsize=8, ha="center", va="center", color=C_LINE)
ax.text(35.75, 60.1, "例外：BE_mealplan 内部直接调度规则引擎（跨层旁路，仅此一处）",
        fontsize=8, ha="center", va="center", color="#6b7280", style="italic")

# 4 Agent 层  42 - 53.2
box(LX0, 42, LX1, 53.2, fc="#fafafa")
ax.text(35.75, 51.4, "Agent 层（Agno + DeepSeek）｜工具接口 IF-INT-T01 ～ T12",
        fontsize=9, ha="center", va="center", color=C_LINE)
box(5.5, 43.2, 35, 49.6, "Agent A｜营养对话\n只读工具：解释 / 咨询", fc=C_ORANGE, fs=8.8)
box(37, 43.2, 66, 49.6, "Agent B｜配餐决策\n生成 / 计算 / 规则 / 落库", fc=C_ORANGE, fs=8.8)

# 5 规则引擎  29 - 38.5
box(LX0, 29, LX1, 38.5,
    "规则引擎层（确定性计算，非 LLM）\n"
    "五步：算目标 → 构造候选 → 差异化 → 整周微量校验 → 输出",
    fc=C_GREEN, fs=9.3)

# 6 数据层  12.5 - 26.5
box(LX0, 12.5, LX1, 26.5, fc=C_PURPLE)
ax.text(35.75, 24.2, "数据层  PostgreSQL 18 · 单库 diet_agent · 四 Schema（IF-INT-DB-01 ～ 04）",
        fontsize=9, ha="center", va="center", color=C_DARK, fontweight="bold")
box(5.5, 14, 19, 20.8, "core｜权威\n（只读）", fs=8.6)
box(21, 14, 35, 20.8, "knowledge｜知识\n（只读）", fs=8.6)
box(37, 14, 51, 20.8, "app｜业务\n（读写）", fs=8.6)
box(53, 14, 66, 20.8, "audit｜审计\n（追加）", fs=8.6)

# 右侧外部服务
box(74, 44, 96.5, 52.2, "DeepSeek 大模型\nFunction Calling + JSON 输出", fc="#fff7ed", fs=8.8)
box(74, 14, 96.5, 22.6, "pgvector 向量检索\n向量 + 关键词 RRF 混合", fc="#fff7ed", fs=8.8)

# 层间箭头
biarrow(X, 88.4, 83.4, "IF-UI-01 ～ 03")
biarrow(X, 72.4, 68.4, "IF-EXT-01 ～ 16")
biarrow(X, 57.4, 53.4, "IF-INT-T01 ～ T12")
biarrow(X, 28.9, 26.7)   # 标识已写入数据层标题，避免标签压框线

# 外部服务箭头
arrow_to(68.2, 47.4, 73.8, 47.9, "IF-EXT-17", lx=78, ly=42.4)
arrow_to(68.2, 17.6, 73.8, 18.4, "IF-EXT-18", lx=78, ly=10.9)

# 底部说明
ax.text(40, 7.6,
        "调用约束：只允许相邻层调用（前端 → 接口层 → Agent 层 / 规则引擎 → 数据层）；Agent 不直连数据库，一律经后端取数。",
        fontsize=8.4, ha="center", va="center", color="#374151")
ax.text(40, 4.2,
        "补注：当前最小闭环为单 Agent 承载 12 工具（CLI 入口），Agent A/B 拆分与 SSE 接入属后续里程碑；初始化层位于底层，评测层贯穿五层。",
        fontsize=8.4, ha="center", va="center", color="#374151", style="italic")

out = Path(__file__).resolve().parent.parent.parent / "接口总览图.png"
fig.savefig(out, bbox_inches="tight", facecolor="white", pad_inches=0.35)
print(str(out))
