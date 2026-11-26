-- 45_营养提示落库_v1.2r5.sql
-- 任务书 B2：面板营养提示「作用 / 缺乏后果 / 富含来源」，配餐/确认时生成一次并写入方案字段，面板只读展示。
-- 变更范围：仅 app.meal_plan 增列，不动既有列、不动触发器、不动 RLS/权限。
-- 执行账号：postgres（diet_backend 无 DDL 权限）。
-- 幂等：可重复执行。

BEGIN;

ALTER TABLE app.meal_plan
    ADD COLUMN IF NOT EXISTS nutrition_tips jsonb NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN app.meal_plan.nutrition_tips IS
    'B2 营养提示：配餐/确认时生成一次，元素含 nutrient_id/name_zh/unit/作用(function)/缺乏后果(deficiency)/富含来源(sources) 及覆盖率与状态；面板只读展示，不实时生成';

COMMIT;

-- 回滚（只在确认无用后执行）：
-- ALTER TABLE app.meal_plan DROP COLUMN IF EXISTS nutrition_tips;

-- 验证：
-- SELECT column_name, data_type, is_nullable, column_default
--   FROM information_schema.columns
--  WHERE table_schema = 'app' AND table_name = 'meal_plan' AND column_name = 'nutrition_tips';
-- SELECT count(*) FILTER (WHERE nutrition_tips <> '[]'::jsonb) AS plans_with_tips, count(*) AS total
--   FROM app.meal_plan;
