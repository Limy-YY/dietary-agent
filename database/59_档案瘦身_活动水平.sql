-- 59_档案瘦身_活动水平.sql
-- 2026-11-24 · 档案字段精简（删 cooking_equipment / religious_ethical）+ activity_level 转主字段
--
-- 1. 删除 cooking_equipment：烹饪设备过滤已被移除（规则引擎不再按厨具排除候选）。
-- 2. 删除 religious_ethical：宗教伦理限制被移除（「不吃猪肉/牛肉」原为引擎空操作，
--    且「清真」与「不吃猪肉」语义重复，方案 a：直接删）。
-- 3. activity_level：由 v1.1「只读兼容」转为 v1.3 可写主字段（列已存在，仅更新口径）。

BEGIN;

-- 1) v_profile_effective 视图引用了要删的两列，先删视图再删列
DROP VIEW IF EXISTS app.v_profile_effective;

-- 2) 删两列
ALTER TABLE app.profile
    DROP COLUMN IF EXISTS cooking_equipment,
    DROP COLUMN IF EXISTS religious_ethical;

-- 3) 重建视图（去掉 cooking_equipment / religious_ethical，保留 activity_level）
CREATE VIEW app.v_profile_effective AS
 SELECT profile_id,
    user_id,
    name,
    avatar,
    COALESCE(gender, sex) AS gender,
    COALESCE(goal_code, goal) AS goal_code,
    birth_date,
    age,
    app.age_in_months(birth_date, CURRENT_DATE) AS age_months,
    height_cm,
    weight_kg,
    activity_level,
    target_calories,
    allergies,
    taboos,
    conditions,
    extras,
    profile_version,
    created_at,
    updated_at,
    (gender IS NULL AND sex IS NOT NULL) AS gender_from_legacy,
    (goal_code IS NULL AND goal IS NOT NULL) AS goal_code_from_legacy
   FROM app.profile p;

COMMENT ON VIEW app.v_profile_effective IS '用户档案唯一读取入口：新字段优先、v1.1 旧字段兜底，并用 *_from_legacy 标记兜底来源；写入仍只写主字段。';

-- 4) activity_level 口径更新（列结构不变，仅注释）
COMMENT ON COLUMN app.profile.activity_level IS '活动水平（久坐少动/轻度活动/中度活动/重度活动），用于能量目标 = BMR × PAL；v1.3 起为可写主字段。';

COMMIT;
