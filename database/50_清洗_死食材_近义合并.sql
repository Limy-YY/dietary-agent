-- ============================================================================
-- 50 · 数据清洗：清死食材 + 近义合并（窗口③ step4，2026-11-23）
-- 幂等可重跑。
--
-- 口径：
--   1. 「清死食材」用软删除（is_deleted=true），不删行 → 可逆、不破坏 FK / check_catalog_sync / 04 断言。
--      对象 = 库内存在但零菜式引用的食材（评审报告 §一.2 32 种，经 49 号复活核桃/杏仁/芝麻后剩 29 种）。
--   2. 「近义合并」：把冗余近义词并入规范词 aliases，再软删除冗余行：
--        红苋菜 → 苋菜(598) 的别名；全脂牛奶 → 牛奶(607) 的别名。
--      另：米饭(熟,619) 与 大米(生,531) 口径统一——菜谱一律用生米（大米/糙米），米饭(熟) 冗余软删。
--   3. 「43 少盐变体」定调为**存表 + 生成池外**（47 号已落地：39 道 is_generation_enabled=false、保留 4 道），
--     未来参数化由后端在引擎侧做，数据侧不动。本脚本无少盐相关数据改动，仅登记口径。
-- ============================================================================

BEGIN;

-- 1. 近义合并：别名并归（幂等：不存在才加）
UPDATE core.ingredient SET aliases = (
  SELECT array_agg(DISTINCT x ORDER BY x)
  FROM unnest(COALESCE(aliases, ARRAY[]::text[]) || ARRAY['红苋菜','红苋']) AS x
) WHERE ingredient_id = 598 AND NOT (COALESCE(aliases, ARRAY[]::text[]) @> ARRAY['红苋菜']::text[]);

UPDATE core.ingredient SET aliases = (
  SELECT array_agg(DISTINCT x ORDER BY x)
  FROM unnest(COALESCE(aliases, ARRAY[]::text[]) || ARRAY['全脂牛奶']::text[]) AS x
) WHERE ingredient_id = 607 AND NOT (COALESCE(aliases, ARRAY[]::text[]) @> ARRAY['全脂牛奶']::text[]);

-- 2. 软删除 29 种死食材（零菜式引用）
UPDATE core.ingredient SET is_deleted = true, updated_at = now()
WHERE NOT is_deleted
  AND NOT EXISTS (SELECT 1 FROM core.dish_ingredient di WHERE di.ingredient_id = core.ingredient.ingredient_id)
  AND ingredient_id IN (
    516,519,520,530,536,538,543,545,559,562,563,566,569,570,577,587,588,
    600,601,610,613,616,619,620,627,634,635,636,637
  );

-- 3. 自检
DO $$
DECLARE dead int; dead_used int; fiber_null int; total_ing int;
BEGIN
  SELECT count(*) INTO dead FROM core.ingredient
   WHERE NOT is_deleted AND NOT EXISTS (SELECT 1 FROM core.dish_ingredient di WHERE di.ingredient_id = core.ingredient.ingredient_id);
  SELECT count(*) INTO dead_used FROM core.ingredient
   WHERE NOT is_deleted AND NOT EXISTS (SELECT 1 FROM core.dish_ingredient di WHERE di.ingredient_id = core.ingredient.ingredient_id)
     AND EXISTS (SELECT 1 FROM core.dish_ingredient di JOIN core.dish d ON d.dish_id=di.dish_id WHERE di.ingredient_id = core.ingredient.ingredient_id AND NOT d.is_deleted);
  SELECT count(*) INTO fiber_null FROM core.ingredient WHERE NOT is_deleted AND fiber_g IS NULL;
  SELECT count(*) INTO total_ing FROM core.ingredient WHERE NOT is_deleted;
  IF dead <> 0 THEN RAISE EXCEPTION '仍有 % 种死食材（库在但零菜式引用）', dead; END IF;
  IF fiber_null <> 0 THEN RAISE EXCEPTION '仍有 % 种食材 fiber_g IS NULL', fiber_null; END IF;
  RAISE NOTICE '死食材归零；菜式引用且缺纤维=%；活食材=%；活菜式=%',
    dead_used, total_ing, (SELECT count(*) FROM core.dish WHERE NOT is_deleted);
END $$;

COMMIT;
