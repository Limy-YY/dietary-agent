-- =====================================================================
-- 57 · 统一维生素A 口径：vitamin_a_ug 归一为 RAE（视黄醇活性当量）
-- =====================================================================
-- 背景（IMP-042）：食材表 vitamin_a_ug 口径混乱——
--   · 动物性食材：存「视黄醇」（retinol，μg），如猪肝 4972、鸡蛋 234、牛肉 6；
--   · 大多数植物性食材：存 0（胡萝卜素未折算）；
--   · 四季豆/西葫芦/鲜蘑菇 3 个植物性食材：存了 carotene/6 的 RE 值（35/5/2，口径漂移）。
--   而 core.nutrient_reference 参考值/UL 是 RAE 口径（成人 RNI 660/770 μg RAE，UL 3000）。
--   口径不统一 → 植物来源维生素A 被严重低估（忽略胡萝卜素），少数食材又被高估 2 倍（RE vs RAE）。
-- 统一口径（DRIs 2023 RAE）：
--   RAE(μg) = 视黄醇(μg) + β-胡萝卜素(μg) / 12
--   植物性食材视黄醇 = 0（胡萝卜素另存 carotene_ug）。
-- 做法：先把「真·视黄醇」存到 retinol_ug（供溯源），再用 retinol_ug + carotene_ug/12 覆盖 vitamin_a_ug。
-- 幂等：retinol_ug 只保存一次（guard）；vitamin_a_ug 每次由 retinol_ug + carotene_ug 重算，结果不变。
-- =====================================================================

-- 1) 保存真·视黄醇（植物性=0，动物性=原 vitamin_a_ug）；已保存过则跳过
UPDATE core.ingredient
SET micro_nutrients = micro_nutrients || jsonb_build_object(
    'retinol_ug',
    CASE WHEN COALESCE((micro_nutrients->>'carotene_ug')::numeric, 0) > 0
         THEN 0
         ELSE COALESCE((micro_nutrients->>'vitamin_a_ug')::numeric, 0)
    END
)
WHERE NOT is_deleted
  AND (micro_nutrients->>'retinol_ug') IS NULL;

-- 2) 归一 vitamin_a_ug = RAE = retinol_ug + carotene_ug / 12（round 1 位）
UPDATE core.ingredient
SET micro_nutrients = micro_nutrients || jsonb_build_object(
    'vitamin_a_ug',
    round(COALESCE((micro_nutrients->>'retinol_ug')::numeric, 0)
          + COALESCE((micro_nutrients->>'carotene_ug')::numeric, 0) / 12.0, 1)
)
WHERE NOT is_deleted;

-- 验证：抽查典型食材 + 全库 null 数
SELECT food_id, name,
       micro_nutrients->>'retinol_ug' AS retinol,
       micro_nutrients->>'carotene_ug' AS carotene,
       micro_nutrients->>'vitamin_a_ug' AS vit_a_rae
FROM core.ingredient
WHERE food_id IN ('CN-797','CN-978','CN-465','CN-392','CN-431','CN-280')
ORDER BY food_id;

SELECT count(*) FILTER (WHERE micro_nutrients->>'vitamin_a_ug' IS NULL) AS va_null
FROM core.ingredient WHERE NOT is_deleted;
