-- ============================================================
-- 37_meal_plan_is_executed_v1.2r3.sql
-- 补齐 app.meal_plan.is_executed（历史回顾「是否执行过」标记）。
--
-- 背景：ORM backend/app/models/meal_plan.py 已定义该列
--   （Boolean, nullable=False, default=False, server_default=false），
--   backend/app/routers/{mealplan,nutrition}.py 均读写它；
--   但 v1.2r2 基线（01 dump / 02 结构）与全部迁移脚本均未落库，
--   导致空库重建后首次生成方案落库报 400：
--   column "is_executed" of relation "meal_plan" does not exist。
--   本文件由 docker/initdb/58_executed.sh 应用（/delivery/37_*.sql）。
--
-- 幂等：ADD COLUMN IF NOT EXISTS，重复执行无副作用。
-- ============================================================

ALTER TABLE app.meal_plan
    ADD COLUMN IF NOT EXISTS is_executed boolean NOT NULL DEFAULT false;
