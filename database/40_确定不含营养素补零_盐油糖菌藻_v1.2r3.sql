-- ============================================================
-- 40_确定不含营养素补零_盐油糖菌藻_v1.2r3.sql
-- 延续 38 号迁移：把「营养学上确定≈0」的微量补成 0（而非 null）。
-- 这批针对盐/油/糖/菌藻干货——它们是「部分餐次缺数据」的元凶：
--   盐出现在 53/60 道菜、橄榄油 40/60 道菜，缺微量会把整道菜/整餐拖成 NULL。
-- 语义同 38：null=真未知（保留），0=确定不含（参与聚合）。
-- ============================================================

-- 1. 盐（精制盐≈纯氯化钠：维A/B1/B2≈0）
UPDATE core.ingredient
SET micro_nutrients = micro_nutrients || '{"vitamin_a_ug":0,"vitamin_b1_mg":0,"vitamin_b2_mg":0}'::jsonb
WHERE ingredient_id = 639;  -- 盐

-- 2. 油脂（≈纯脂肪：锌/B1/B2≈0，椰子油另含铁≈0）
UPDATE core.ingredient
SET micro_nutrients = micro_nutrients || '{"zinc_mg":0,"vitamin_b1_mg":0,"vitamin_b2_mg":0}'::jsonb
WHERE ingredient_id IN (580, 559, 586);  -- 橄榄油 / 花生油 / 香油

UPDATE core.ingredient
SET micro_nutrients = micro_nutrients || '{"iron_mg":0,"zinc_mg":0,"vitamin_b1_mg":0,"vitamin_b2_mg":0}'::jsonb
WHERE ingredient_id = 634;  -- 椰子油

-- 3. 糖（≈纯蔗糖/糖浆：维A/B1/B2≈0）
UPDATE core.ingredient
SET micro_nutrients = micro_nutrients || '{"vitamin_a_ug":0,"vitamin_b1_mg":0,"vitamin_b2_mg":0}'::jsonb
WHERE ingredient_id = 530;  -- 白糖

UPDATE core.ingredient
SET micro_nutrients = micro_nutrients || '{"vitamin_a_ug":0}'::jsonb
WHERE ingredient_id IN (613, 588);  -- 冰糖 / 蜂蜜

-- 4. 菌藻干货（维C≈0）
UPDATE core.ingredient
SET micro_nutrients = micro_nutrients || '{"vitamin_c_mg":0}'::jsonb
WHERE ingredient_id IN (564, 516, 581);  -- 海带 / 银耳 / 木耳
