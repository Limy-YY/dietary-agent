-- ============================================================================
-- 48 · 补膳食纤维：71 种食材 fiber_g（窗口③ step2，2026-11-23）
-- 幂等可重跑（WHERE fiber_g IS NULL 保护，不覆盖已填值）。
--
-- 口径（对应「缺失=0 还是 null 跳过」的定调）：
--   1. 采用「真值补齐」，不把未知当 0：
--      - 动物性食材（肉/禽/水产/蛋奶）与纯糖/油脂**确定不含**膳食纤维 → 补 0（真 0，非缺失）；
--      - 果蔬/谷物/豆类/坚果/菌藻 → 补「模型估算近似值」。
--   2. 这满足「纤维缺失归零」验收，又不违反「null≠0」铁律（0 只给真不含者）。
--   3. **诚实口径（重要）**：本脚本 71 条纤维值为模型估算，**未逐条对照权威库查证**；
--      纤维子项的 data_quality 标 'check'（待核查），source 如实写「模型估算，待数据岗核查」，
--      **不写具体食物成分表出处冒充已溯源**。食材级 data_quality 三态不动（不因补一项纤维整体降级）。
--      待数据岗（陈媛/陈博淇）用「中国食物成分查询平台 / USDA」按 CN 食物码逐条回填真实值 + source_url。
--   4. 菌藻（木耳/银耳/竹笋）按库内 amount_g 的「生重/干重」口径取干重值（同样待核查）。
-- ============================================================================

BEGIN;

UPDATE core.ingredient AS i
SET fiber_g = v.fiber,
    source_row = COALESCE(source_row, '{}'::jsonb) || jsonb_build_object(
      'supplemental_nutrients',
      COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object(
        'fiber_g', jsonb_build_object(
          'value', v.fiber,
          'unit', 'g/100g',
          'source', CASE WHEN v.fiber = 0
                        THEN '动物性/精炼油脂/纯糖确定不含膳食纤维（常识，未逐条溯源）'
                        ELSE '模型估算，待数据岗对照中国食物成分表/USDA 逐条核查' END,
          'data_quality', 'check'))
    )
FROM (VALUES
  (513,  0.0), (514,  1.4), (516, 30.4), (518,  1.2), (519,  5.9),
  (520,  1.4), (524,  2.5), (525,  1.0), (527,  0.0), (530,  0.0),
  (532,  0.0), (538,  0.7), (541,  0.6), (542,  0.0), (543,  1.1),
  (545,  1.2), (546,  9.8), (548,  9.9), (550,  0.8), (552,  0.8),
  (554,  0.6), (555,  1.3), (556,  1.5), (558,  1.0), (559,  0.0),
  (563,  0.0), (566,  1.4), (567,  0.2), (569,  0.8), (570,  0.5),
  (574,  1.2), (577,  1.8), (579,  0.4), (581, 29.9), (583,  0.6),
  (584,  0.6), (587,  1.0), (588,  0.0), (589,  0.0), (591,  0.0),
  (594,  9.5), (598,  1.8), (599,  1.2), (600,  0.4), (601,  0.0),
  (603,  0.0), (605,  1.5), (607,  0.0), (610,  6.1), (611,  0.0),
  (612,  2.6), (613,  0.0), (614,  0.0), (616,  0.0), (618,  2.2),
  (619,  0.3), (620,  1.0), (622,  0.0), (624,  2.6), (626,  0.0),
  (627,  0.0), (628,  0.0), (631,  0.0), (634,  0.0), (635, 41.7),
  (637,  3.1), (640,  0.8), (660,  0.0), (661,  0.2), (662,  1.0),
  (663,  0.6)
) AS v(ingredient_id, fiber)
WHERE i.ingredient_id = v.ingredient_id AND i.fiber_g IS NULL;

-- 自检：fiber 缺失应归零（非删除食材）
DO $$
DECLARE null_fiber int; used_null int;
BEGIN
  SELECT count(*) INTO null_fiber FROM core.ingredient WHERE NOT is_deleted AND fiber_g IS NULL;
  SELECT count(*) INTO used_null
    FROM core.ingredient i
   WHERE NOT i.is_deleted AND i.fiber_g IS NULL
     AND EXISTS (SELECT 1 FROM core.dish_ingredient di JOIN core.dish d ON d.dish_id=di.dish_id
                  WHERE di.ingredient_id=i.ingredient_id AND NOT d.is_deleted);
  IF null_fiber <> 0 THEN RAISE EXCEPTION '仍有 % 种食材 fiber_g IS NULL', null_fiber; END IF;
  RAISE NOTICE '纤维缺失归零；其中被菜式引用且仍缺失 = %', used_null;
END $$;

COMMIT;
