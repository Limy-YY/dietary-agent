--
-- 46_博淇v21少盐变体_v1.2r4.sql
-- 用途：为 43 道已复核基础菜生成 -LS 少盐变体（dish_id = 基础 id || '-LS'，菜名 = 原名 || '（少盐）'），
--       仅把可识别的精盐减半，食用油、酱油、腌渍/防腐调味不变；基础菜谱与食材事实不改。
-- 前置：既有迁移链跑完，43 道基础菜（DISH-001..120 段）在 core.dish 且配料事实与契约一致；
--       建议排在 45、44 之后执行，以继承已落定的过敏原快照。core.dish / dish_ingredient / ingredient 表已存在。执行账号：postgres。
-- 幂等：可重复执行；同变体已属本迁移时 ON CONFLICT DO UPDATE 描述性字段，ID 占用或事实漂移直接抛错。
-- 口径：source_id = v21-low-salt-round1，generated_from = v21_low_salt_round1；
--       营养快照只从活的食材事实派生，缺失值保持 NULL，不按 0 计算；口味为配方试验，待实测复核。
--

\set ON_ERROR_STOP on
\pset pager off

DO $$
DECLARE v_has_table boolean; v_can_write boolean; v_base_count integer;
BEGIN
  v_has_table := to_regclass('core.dish') IS NOT NULL AND to_regclass('core.dish_ingredient') IS NOT NULL
                 AND to_regclass('core.ingredient') IS NOT NULL;
  IF NOT v_has_table THEN
    RAISE EXCEPTION 'core.dish / dish_ingredient / ingredient 未建：先还原 01 备份并跑完既有迁移链，再跑本脚本';
  END IF;
  v_can_write := has_table_privilege(current_user,'core.dish','INSERT')
                 AND has_table_privilege(current_user,'core.dish_ingredient','INSERT');
  IF NOT v_can_write THEN
    RAISE EXCEPTION '当前用户 % 对 core 无 INSERT 权限，请换 postgres 执行', current_user;
  END IF;
  SELECT count(*) INTO v_base_count FROM core.dish WHERE dish_id NOT LIKE '%-LS' AND NOT is_deleted;
  IF v_base_count < 120 THEN
    RAISE EXCEPTION '前置不满足：普通菜基线应为 120 道，当前普通菜 % 道，先跑前置扩充脚本', v_base_count;
  END IF;
END $$;

-- 0. 登记迁移日志（幂等）
INSERT INTO audit.schema_migration (migration_id, description, applied_by)
VALUES ('2026-11-20-v21-lowsalt-round1',
        '博淇 v21 少盐变体 round1：43 条 -LS 变体，基础菜精盐减半、其余配料不变；幂等可重跑。',
        'chentiantian-bot')
ON CONFLICT (migration_id) DO NOTHING;

BEGIN;

\set ON_ERROR_STOP on
-- Recipe variants with real IDs, not a change to existing dishes or nutrient facts.
-- Less-salt seasoning is a culinary proposal; verify taste with project staff.
SELECT pg_advisory_xact_lock(hashtextextended('diet-agent:v21-lowsalt-round1',0));
CREATE TEMP TABLE _ls_base ON COMMIT DROP AS
SELECT d.* FROM core.dish d WHERE NOT d.is_deleted AND d.servings=1 AND d.dish_id IN (
 'DISH-001','DISH-002','DISH-003','DISH-005','DISH-006','DISH-008','DISH-012','DISH-014',
 'DISH-015','DISH-016','DISH-017','DISH-019','DISH-020','DISH-021','DISH-022','DISH-023',
 'DISH-025','DISH-031','DISH-034','DISH-035','DISH-036','DISH-041','DISH-042','DISH-043',
 'DISH-044','DISH-081','DISH-085','DISH-088','DISH-089','DISH-090','DISH-093','DISH-094',
 'DISH-095','DISH-096','DISH-097','DISH-098','DISH-101','DISH-102','DISH-103','DISH-104',
 'DISH-106','DISH-107','DISH-108');
-- Only reduce identifiable plain table salt, not oil, soy sauce, pickling or preservation.
DO $$ BEGIN
 IF (SELECT count(*) FROM _ls_base)<>43 THEN RAISE EXCEPTION 'Expected 43 reviewed base recipes'; END IF;
 IF EXISTS (SELECT 1 FROM _ls_base d WHERE d.default_salt_g IS NULL OR d.default_salt_g<=0
 OR NOT EXISTS (SELECT 1 FROM core.dish_ingredient di JOIN core.ingredient i USING(ingredient_id)
    WHERE di.dish_id=d.dish_id AND di.role='食盐' AND i.food_id='CN-1565' AND NOT i.is_deleted)
 OR d.default_salt_g IS DISTINCT FROM (SELECT sum(di.amount_g) FROM core.dish_ingredient di
   JOIN core.ingredient i USING(ingredient_id) WHERE di.dish_id=d.dish_id AND di.role='食盐' AND i.food_id='CN-1565')
 OR EXISTS (SELECT 1 FROM core.dish_ingredient di JOIN core.ingredient i USING(ingredient_id)
    WHERE di.dish_id=d.dish_id AND (i.is_deleted OR di.amount_g IS NULL OR di.amount_g<=0)))
 THEN RAISE EXCEPTION 'Recipe salt or ingredient facts do not match the reviewed contract'; END IF;
 IF EXISTS (SELECT 1 FROM _ls_base b JOIN core.dish d ON d.dish_id=b.dish_id||'-LS'
 WHERE d.source_id IS DISTINCT FROM 'v21-low-salt-round1' OR d.name IS DISTINCT FROM b.name||'（少盐）'
 OR d.default_salt_g IS DISTINCT FROM b.default_salt_g/2 OR d.is_deleted)
 THEN RAISE EXCEPTION 'Variant ID collision or changed variant'; END IF;
END $$;
INSERT INTO audit.import_batch(dataset_name,dataset_version,original_file_name,original_sha256,imported_by,status,notes)
SELECT 'V2.1少盐配方','round1','v21_low_salt_variants.sql','f95de434231faf77bfe38913f33a1ce1a6b574e609ee188ca316487302f19774',current_user,'promoted','仅调整配方中已有精盐至一半，基础菜谱不改；口味待实测。'
WHERE NOT EXISTS (SELECT 1 FROM audit.import_batch WHERE dataset_name='V2.1少盐配方' AND dataset_version='round1');
CREATE TEMP TABLE _ls_new ON COMMIT DROP AS SELECT b.* FROM _ls_base b WHERE NOT EXISTS(SELECT 1 FROM core.dish d WHERE d.dish_id=b.dish_id||'-LS');
INSERT INTO core.dish(dish_id,name,aliases,category,tags,method_text,cooking_rule_id,servings,default_oil_g,default_salt_g,cook_time_min,nutrition_snapshot,avoid_snapshot,source_row,import_batch_id,source,source_id)
SELECT b.dish_id||'-LS',b.name||'（少盐）',ARRAY[]::text[],b.category,
 ARRAY(SELECT DISTINCT unnest(coalesce(b.tags,ARRAY[]::text[])||ARRAY['少盐配方'])),b.method_text,b.cooking_rule_id,b.servings,b.default_oil_g,b.default_salt_g/2,b.cook_time_min,
 '{}'::jsonb,b.avoid_snapshot,(coalesce(b.source_row,'{}'::jsonb)-'nutrition_estimate'-'dish_kcal'-'dish_protein_g'-'dish_sodium_mg'-'nutrition_snapshot'-'ingredients')||jsonb_build_object('dish_id',b.dish_id||'-LS','dish_name',b.name||'（少盐）','base_dish_id',b.dish_id,'salt_g',b.default_salt_g/2,
 'standardization_note','少盐配方试验：主要食材及做法不变，本标准份精盐总量以 salt_g 为准，原步骤涉及食盐用量以此覆盖；不得额外补盐。未调整其他调味料。'),
 (SELECT min(import_batch_id) FROM audit.import_batch WHERE dataset_name='V2.1少盐配方' AND dataset_version='round1'),
 '原菜谱少盐试验变体（保留食材来源）','v21-low-salt-round1' FROM _ls_base b
ON CONFLICT (dish_id) DO UPDATE SET
  name=EXCLUDED.name, tags=EXCLUDED.tags, method_text=EXCLUDED.method_text,
  cooking_rule_id=EXCLUDED.cooking_rule_id, default_oil_g=EXCLUDED.default_oil_g,
  default_salt_g=EXCLUDED.default_salt_g, cook_time_min=EXCLUDED.cook_time_min,
  avoid_snapshot=EXCLUDED.avoid_snapshot, source_row=EXCLUDED.source_row,
  source=EXCLUDED.source, source_id=EXCLUDED.source_id, updated_at=now();
INSERT INTO core.dish_ingredient(dish_id,ingredient_id,amount_g,cooked_amount_g,role,is_optional,generated_from,source_snapshot)
SELECT b.dish_id||'-LS',di.ingredient_id,
 CASE WHEN di.role='食盐' AND i.food_id='CN-1565' THEN di.amount_g/2 ELSE di.amount_g END,
 CASE WHEN di.role='食盐' AND i.food_id='CN-1565' THEN NULL ELSE di.cooked_amount_g END,
 di.role,di.is_optional,'v21_low_salt_round1',coalesce(di.source_snapshot,'{}'::jsonb)||jsonb_build_object('base_dish_id',b.dish_id,'amount_g',CASE WHEN di.role='食盐' AND i.food_id='CN-1565' THEN di.amount_g/2 ELSE di.amount_g END)
FROM _ls_base b JOIN core.dish_ingredient di USING(dish_id) JOIN core.ingredient i USING(ingredient_id)
ON CONFLICT (dish_id, ingredient_id, role, generated_from) DO UPDATE SET
  amount_g=EXCLUDED.amount_g, cooked_amount_g=EXCLUDED.cooked_amount_g,
  role=EXCLUDED.role, source_snapshot=EXCLUDED.source_snapshot;
-- Derive snapshots exclusively from live ingredient facts, preserving NULL propagation.
WITH raw AS (
 SELECT d.dish_id,di.amount_g,di.role,i.* FROM core.dish d JOIN core.dish_ingredient di USING(dish_id) JOIN core.ingredient i USING(ingredient_id)
 WHERE d.dish_id IN (SELECT dish_id||'-LS' FROM _ls_new)
), facts AS (
 SELECT dish_id,jsonb_build_object(
 'energy_kcal',CASE WHEN bool_or(energy_kcal IS NULL) THEN NULL ELSE round(sum(amount_g*energy_kcal/100.0),1) END,
 'protein_g',CASE WHEN bool_or(protein_g IS NULL) THEN NULL ELSE round(sum(amount_g*protein_g/100.0),1) END,
 'fat_g',CASE WHEN bool_or(fat_g IS NULL) THEN NULL ELSE round(sum(amount_g*fat_g/100.0),1) END,
 'carbohydrate_g',CASE WHEN bool_or(carbohydrate_g IS NULL) THEN NULL ELSE round(sum(amount_g*carbohydrate_g/100.0),1) END,
 'fiber_g',CASE WHEN bool_or(fiber_g IS NULL) THEN NULL ELSE round(sum(amount_g*fiber_g/100.0),1) END,
 'sodium_mg',CASE WHEN bool_or(sodium_mg IS NULL) THEN NULL ELSE round(sum(amount_g*sodium_mg/100.0),1) END,
 'calcium_mg',CASE WHEN bool_or(calcium_mg IS NULL) THEN NULL ELSE round(sum(amount_g*calcium_mg/100.0),2) END,
 'ingredient_count',count(*),'calculation_basis','core.ingredient × amount_g / 100','cooking_loss_adjusted',false) snapshot,
 jsonb_agg(jsonb_build_object('food_id',food_id,'food_name',name,'amount_g',amount_g,'role',role,'source_url',source_url,'data_quality',data_quality,'allergens',allergens,'allergen_status',allergen_status) ORDER BY ingredient_id) ingredients
 FROM raw GROUP BY dish_id
)
UPDATE core.dish d SET nutrition_snapshot=f.snapshot,source_row=d.source_row||jsonb_build_object('ingredients',f.ingredients,'nutrition_snapshot',f.snapshot) FROM facts f WHERE f.dish_id=d.dish_id;
-- Re-running must not change existing data; reject any ingredient-row drift.
DO $$ BEGIN
 IF EXISTS (
  WITH expected AS (SELECT b.dish_id||'-LS' dish_id,di.ingredient_id,di.role,CASE WHEN di.role='食盐' AND i.food_id='CN-1565' THEN di.amount_g/2 ELSE di.amount_g END amount_g FROM _ls_base b JOIN core.dish_ingredient di USING(dish_id) JOIN core.ingredient i USING(ingredient_id)),
 actual AS (SELECT di.dish_id,di.ingredient_id,di.role,di.amount_g FROM core.dish_ingredient di JOIN _ls_base b ON di.dish_id=b.dish_id||'-LS')
 (SELECT * FROM expected EXCEPT ALL SELECT * FROM actual) UNION ALL (SELECT * FROM actual EXCEPT ALL SELECT * FROM expected)
 ) THEN RAISE EXCEPTION 'Variant ingredient mismatch'; END IF;
END $$;

COMMIT;

SELECT '46_v21_lowsalt_round1' AS migration,
       count(*) AS low_salt_variants,
       count(*) FILTER (WHERE dish_id NOT LIKE '%-LS') AS total_nls
FROM core.dish WHERE NOT is_deleted;
