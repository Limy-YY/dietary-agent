-- ============================================================
-- 37_历史方案执行状态_v1.2r3.sql
-- 用途：历史方案「已执行 / 未执行」标记（配合前端历史方案面板改造）
--
-- 说明：
--   * 只加一列布尔标记，不改动方案状态机（draft/candidates/fixed）。
--   * 故意不加进 app.guard_meal_plan_update 的 fixed 只读列清单，
--     因此 fixed 方案仍可单独翻转 is_executed（这正是「回顾打卡」需要的）。
--   * IF NOT EXISTS 保证幂等，可重复执行。
-- 应用方式（正在运行的本地库）：
--   docker exec diet-agent-db psql -U postgres -d diet_agent \
--     -c "ALTER TABLE app.meal_plan ADD COLUMN IF NOT EXISTS is_executed boolean DEFAULT false NOT NULL;"
-- ============================================================

ALTER TABLE app.meal_plan
    ADD COLUMN IF NOT EXISTS is_executed boolean DEFAULT false NOT NULL;

COMMENT ON COLUMN app.meal_plan.is_executed IS
    '历史回顾用：用户是否实际照这份方案执行过（不影响方案状态机）';
