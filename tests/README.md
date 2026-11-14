# tests/ 自动化测试

测试岗 · 马英慧 ｜ 口径以《Agent 输出契约 v1.2》为唯一字段源。

## 契约断言（联调前自动门禁）

```bash
python tests/test_contract_v12.py -v
```

- `contract_v12.py`：SSE 事件解析 / REST `{code,message,data}` 解包 / clarify 追问校验 / 错误码表（与 `backend/app/core/errors.py` 一致）；
- `test_contract_v12.py`：9 条断言，覆盖三组——SSE 三类事件、统一包裹解包、字段命名（`plan_id` / `is_staple` / `kcal_per_100g`）；
- 退出码 0 = 通过，可直接挂 CI。**当前 `backend/app/routers/chat.py` 为占位实现（仅 session/message/done），artifact 与 clarify 接线后重跑本脚本即可判定契约回归。**

## 与其他测试资产的关系

| 资产 | 位置 | 说明 |
| --- | --- | --- |
| 116 条用例 + 需求追溯 + 13 缺陷清单 | `docs/testing/膳食搭配智能体MVP_测试用例与缺陷清单.xlsx` | 已按 v1.2 契约改版（含 TC-CT-01~05 契约用例） |
| 测试计划 / 测试报告 | `docs/testing/` | L1~L5 分层策略与首轮结论 |
| 52+9 项离线断言与用例生成器 | `docs/testing/automation/` | 桩测，不依赖环境，退出码可挂 CI |
| 数据库验收环境 | `../deploy/` | compose 一键起库 + 27 项验收说明 |
