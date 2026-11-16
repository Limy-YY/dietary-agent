-- ============================================================
-- 38_确定不含营养素补零_v1.2r3.sql
-- 目的：把「营养学上确定≈0」的微量补成 0（而非 null），
--       避免严格 NULL 传播（任一食材缺值→整道菜 NULL）把菜式级微量数据全部坍塌。
-- 语义（对应 null≠0 铁律的细化）：
--   - null = 真未知（数据未采集，保留 null，报告显示「—/数据不足」）
--   - 0    = 确定不含（营养学上含量可忽略，补 0 参与聚合）
-- data_quality 说明：core.ingredient.data_quality 是「食材级」而非「营养素级」，
--   本次补 0 不改动该字段（大多为 check，本就表示待核查/非官方实测）。
-- ============================================================

-- 维生素C：动物性食材 / 油脂 / 调味料 / 谷物 / 豆类 / 糖 / 烘焙 等几乎不含维生素C，
-- 补 0；蔬菜、水果是维生素C 的主要来源，保持原值（缺值的仍为 null=真未知）。
UPDATE core.ingredient
SET micro_nutrients = micro_nutrients || '{"vitamin_c_mg": 0}'::jsonb
WHERE NOT is_deleted
  AND category NOT IN ('蔬菜', '水果与果汁')
  AND (micro_nutrients->>'vitamin_c_mg') IS NULL;

-- 复核：补 0 后，非蔬菜水果类食材的维生素C 应有值（0 或原值），蔬菜/水果缺值保持 null。
