\set ON_ERROR_STOP on

-- 基于同一核心食材扩展10道普通家常做法；不新增或改写食材营养事实。
BEGIN;
SELECT pg_advisory_xact_lock(hashtextextended('diet-agent:v21-home-variants-10:2026-11-19', 0));

DO $$
BEGIN
  IF current_database() <> 'diet_agent' THEN
    RAISE EXCEPTION '目标数据库错误：当前为 %，要求 diet_agent', current_database();
  END IF;
END $$;

CREATE TEMP TABLE _v21_before ON COMMIT DROP AS
SELECT 'dish'::text entity, md5(COALESCE(string_agg(to_jsonb(d)::text,'|' ORDER BY d.dish_id),'')) fingerprint
FROM core.dish d WHERE d.dish_id BETWEEN 'DISH-001' AND 'DISH-100'
UNION ALL
SELECT 'dish_ingredient', md5(COALESCE(string_agg(to_jsonb(di)::text,'|' ORDER BY di.dish_ingredient_id),''))
FROM core.dish_ingredient di WHERE di.dish_id BETWEEN 'DISH-001' AND 'DISH-100';

INSERT INTO audit.import_batch (
  dataset_name,dataset_version,original_file_name,original_sha256,imported_by,status,notes
)
SELECT 'V2.1同核心食材家常变体','2026-11-19','v21_home_variants_10.sql',
       '16e896f9fbecdfabd840857999eb18ec4fd31d1a1cb49eedfbba51a08c80b604',
       current_user,'promoted',
       '语义清单哈希；新增10道家常变体，只复用已有食材事实和已使用过的份量/调味口径，不改DISH-001..DISH-100。'
WHERE NOT EXISTS (
  SELECT 1 FROM audit.import_batch
  WHERE dataset_name='V2.1同核心食材家常变体' AND dataset_version='2026-11-19'
);

CREATE TEMP TABLE _v21_batch ON COMMIT DROP AS
SELECT import_batch_id FROM audit.import_batch
WHERE dataset_name='V2.1同核心食材家常变体' AND dataset_version='2026-11-19'
ORDER BY import_batch_id LIMIT 1;

CREATE TEMP TABLE _v21_variant (
  dish_id text PRIMARY KEY,name text NOT NULL,category text NOT NULL,tags text[] NOT NULL,
  method_text text NOT NULL,cooking_rule_id text NOT NULL,default_oil_g numeric NOT NULL,
  default_salt_g numeric NOT NULL,cook_time_min integer,standardization_note text NOT NULL
) ON COMMIT DROP;

INSERT INTO _v21_variant VALUES
 ('DISH-101','洋葱炒蛋','蛋豆类',ARRAY['基础家常菜','常见','简单','鸡蛋','蔬菜'],'快炒','CR009',5,1,8,'鸡蛋100g、油5g、盐1g复用番茄炒蛋；洋葱50g复用现有牛肉菜'),
 ('DISH-102','肉末蒸蛋','蛋豆类',ARRAY['基础家常菜','常见','简单','鸡蛋','猪肉'],'清蒸','CR002',0,0.6,15,'鸡蛋50g采用卫健委早餐份量；猪里脊25g复用菜花炒里脊；盐0.6g采用清蒸口径'),
 ('DISH-103','香菇蒸鸡','畜禽肉类',ARRAY['基础家常菜','常见','简单','鸡肉','香菇'],'清蒸','CR002',0,0.8,20,'鸡胸肉40g、香菇25g、姜5g、盐0.8g复用香菇炖鸡胸肉，改为无油清蒸'),
 ('DISH-104','土豆炖鸡','畜禽肉类',ARRAY['基础家常菜','常见','简单','鸡肉','土豆'],'清炖','CR006',2,0.8,35,'土豆75g复用土豆茄子炖牛肉；鸡胸肉50g复用黄瓜甜椒炒鸡丁；油盐复用现有清炖菜'),
 ('DISH-105','清炖鸡汤','汤羹',ARRAY['基础家常菜','常见','简单','鸡肉','汤羹'],'汤煮','CR005',0,0.8,40,'鸡胸肉40g、姜5g、盐0.8g复用现有指南标准化菜；未称量饮用水不计营养'),
 ('DISH-106','肉末豆腐','蛋豆类',ARRAY['基础家常菜','常见','简单','猪肉','豆腐'],'快炒','CR009',4,0.8,12,'猪里脊25g复用菜花炒里脊；豆腐100g为可食部标准份；油4g盐0.8g复用清炒口径'),
 ('DISH-107','小葱拌豆腐','蛋豆类',ARRAY['基础家常菜','常见','简单','豆腐','凉拌'],'凉拌','CR007',0,0.6,5,'豆腐100g为可食部标准份；大葱5g、盐0.6g复用现有菜库称量口径；不额外加油'),
 ('DISH-108','香煎豆腐','蛋豆类',ARRAY['基础家常菜','常见','简单','豆腐','煎'],'煎','CR011',4,0.8,12,'豆腐100g为可食部标准份；油4g盐0.8g复用项目少油家常菜口径'),
 ('DISH-109','蒸土豆','主食',ARRAY['基础家常菜','常见','简单','主食','土豆'],'清蒸','CR002',0,0,20,'土豆100g复用醋溜土豆丝主料量；不额外加油盐'),
 ('DISH-110','白粥','主食',ARRAY['基础家常菜','常见','简单','主食','早餐'],'煮粥','CR005',0,0,35,'大米50g复用卫健委米饭示例；未称量饮用水不计营养，不额外加油盐');

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM core.dish d JOIN _v21_variant n USING(dish_id)
    WHERE d.name IS DISTINCT FROM n.name OR d.source_id IS DISTINCT FROM 'home-variants-v2.1-20261119'
  ) THEN RAISE EXCEPTION '目标dish_id已存在但不属于本迁移'; END IF;
  IF EXISTS (
    SELECT 1 FROM core.dish d JOIN _v21_variant n ON d.name=n.name WHERE d.dish_id<>n.dish_id
  ) THEN RAISE EXCEPTION '新增菜名已被其他dish_id使用'; END IF;
END $$;

INSERT INTO core.dish (
 dish_id,name,aliases,category,tags,method_text,cooking_rule_id,servings,
 default_oil_g,default_salt_g,cook_time_min,nutrition_snapshot,avoid_snapshot,
 source_row,import_batch_id,source,source_id
)
SELECT n.dish_id,n.name,ARRAY[]::text[],n.category,n.tags,n.method_text,n.cooking_rule_id,1,
 n.default_oil_g,n.default_salt_g,n.cook_time_min,'{}'::jsonb,'{}'::jsonb,
 jsonb_build_object(
  'dish_id',n.dish_id,'dish_name',n.name,'category',n.category,'method',n.method_text,
  'servings',1,'oil_g',n.default_oil_g,'salt_g',n.default_salt_g,
  'cooking_rule_id',n.cooking_rule_id,'standardization_note',n.standardization_note,
  'nutrition_basis','core.ingredient × amount_g；缺失值保持NULL，不按0计算；未按烹饪损耗修正',
  'standardized_at','2026-11-19','data_quality','existing_verified_ingredient_facts_reused'
 ),b.import_batch_id,'基础家常变体库（复用现有食材）','home-variants-v2.1-20261119'
FROM _v21_variant n CROSS JOIN _v21_batch b
WHERE NOT EXISTS (SELECT 1 FROM core.dish d WHERE d.dish_id=n.dish_id);

CREATE TEMP TABLE _v21_relation (
 dish_id text,food_id text,amount_g numeric,role text,
 generated_from text DEFAULT 'v21_home_variants_20261119',
 PRIMARY KEY(dish_id,food_id,role,generated_from)
) ON COMMIT DROP;

INSERT INTO _v21_relation(dish_id,food_id,amount_g,role) VALUES
 ('DISH-101','CN-978',100,'主料'),('DISH-101','CN-444',50,'配菜'),('DISH-101','CN-1510',5,'烹调油'),('DISH-101','CN-1565',1,'食盐'),
 ('DISH-102','CN-978',50,'主料'),('DISH-102','CN-784',25,'主料'),('DISH-102','CN-1565',0.6,'食盐'),
 ('DISH-103','CN-880',40,'主料'),('DISH-103','CN-584',25,'配菜'),('DISH-103','CN-528',5,'调味辅料'),('DISH-103','CN-1565',0.8,'食盐'),
 ('DISH-104','CN-880',50,'主料'),('DISH-104','CN-313',75,'主料'),('DISH-104','CN-528',5,'调味辅料'),('DISH-104','CN-1510',2,'烹调油'),('DISH-104','CN-1565',0.8,'食盐'),
 ('DISH-105','CN-880',40,'主料'),('DISH-105','CN-528',5,'调味辅料'),('DISH-105','CN-1565',0.8,'食盐'),
 ('DISH-106','CN-784',25,'主料'),('DISH-106','CN-333',100,'主料'),('DISH-106','CN-1510',4,'烹调油'),('DISH-106','CN-1565',0.8,'食盐'),
 ('DISH-107','CN-333',100,'主料'),('DISH-107','CN-441',5,'调味辅料'),('DISH-107','CN-1565',0.6,'食盐'),
 ('DISH-108','CN-333',100,'主料'),('DISH-108','CN-1510',4,'烹调油'),('DISH-108','CN-1565',0.8,'食盐'),
 ('DISH-109','CN-313',100,'主料'),
 ('DISH-110','CN-280',50,'主料');

DO $$
BEGIN
 IF EXISTS (
   SELECT 1 FROM _v21_relation r LEFT JOIN core.ingredient i ON i.food_id=r.food_id AND NOT i.is_deleted
   WHERE i.ingredient_id IS NULL
 ) THEN RAISE EXCEPTION '变体引用了不存在的food_id'; END IF;
 IF EXISTS (
   SELECT 1 FROM core.dish_ingredient di JOIN core.ingredient i USING(ingredient_id)
   JOIN _v21_relation r ON r.dish_id=di.dish_id AND r.food_id=i.food_id AND r.generated_from=di.generated_from
   WHERE di.amount_g IS DISTINCT FROM r.amount_g OR di.role IS DISTINCT FROM r.role
 ) THEN RAISE EXCEPTION '既有变体配料关系与迁移不一致'; END IF;
END $$;

INSERT INTO core.dish_ingredient(
 dish_id,ingredient_id,amount_g,cooked_amount_g,role,is_optional,generated_from,source_snapshot
)
SELECT r.dish_id,i.ingredient_id,r.amount_g,NULL,r.role,false,r.generated_from,
 jsonb_build_object(
  'food_id',r.food_id,'amount_g',r.amount_g,'role',r.role,
  'amount_basis',v.standardization_note,
  'nutrition_basis','core.ingredient每100g数据按amount_g线性计算；未按烹饪损耗修正'
 )
FROM _v21_relation r JOIN core.ingredient i ON i.food_id=r.food_id AND NOT i.is_deleted
JOIN _v21_variant v USING(dish_id)
WHERE NOT EXISTS (
 SELECT 1 FROM core.dish_ingredient di
 WHERE di.dish_id=r.dish_id AND di.ingredient_id=i.ingredient_id
 AND di.role=r.role AND di.generated_from=r.generated_from
);

WITH base AS (
 SELECT d.dish_id,di.amount_g,di.role,i.*
 FROM core.dish d JOIN core.dish_ingredient di USING(dish_id)
 JOIN core.ingredient i USING(ingredient_id)
 WHERE d.source_id='home-variants-v2.1-20261119'
), nutrition AS (
 SELECT dish_id,count(*) ingredient_count,
  CASE WHEN bool_or(energy_kcal IS NULL) THEN NULL ELSE round(sum(amount_g*energy_kcal/100.0),1) END energy_kcal,
  CASE WHEN bool_or(protein_g IS NULL) THEN NULL ELSE round(sum(amount_g*protein_g/100.0),1) END protein_g,
  CASE WHEN bool_or(fat_g IS NULL) THEN NULL ELSE round(sum(amount_g*fat_g/100.0),1) END fat_g,
  CASE WHEN bool_or(carbohydrate_g IS NULL) THEN NULL ELSE round(sum(amount_g*carbohydrate_g/100.0),1) END carbohydrate_g,
  CASE WHEN bool_or(fiber_g IS NULL) THEN NULL ELSE round(sum(amount_g*fiber_g/100.0),1) END fiber_g,
  CASE WHEN bool_or(sodium_mg IS NULL) THEN NULL ELSE round(sum(amount_g*sodium_mg/100.0),1) END sodium_mg,
  CASE WHEN bool_or(calcium_mg IS NULL) THEN NULL ELSE round(sum(amount_g*calcium_mg/100.0),1) END calcium_mg
 FROM base GROUP BY dish_id
), ingredients AS (
 SELECT dish_id,jsonb_agg(jsonb_build_object(
  'food_id',food_id,'food_name',name,'amount_g',amount_g,'role',role,
  'source_url',source_url,'data_quality',data_quality,
  'allergens',allergens,'allergen_status',allergen_status
 ) ORDER BY ingredient_id) ingredients
 FROM base GROUP BY dish_id
), allergy AS (
 SELECT b.dish_id,
  COALESCE(array_agg(DISTINCT a.allergen) FILTER(WHERE b.allergen_status='已确认含' AND a.allergen IS NOT NULL),ARRAY[]::text[]) strict_allergens,
  COALESCE(array_agg(DISTINCT b.food_id) FILTER(WHERE b.allergen_status='未核查'),ARRAY[]::text[]) unverified_food_ids
 FROM base b LEFT JOIN LATERAL unnest(b.allergens) a(allergen) ON true GROUP BY b.dish_id
), facts AS (
 SELECT n.*,i.ingredients,a.strict_allergens,a.unverified_food_ids,
  jsonb_build_object(
   'energy_kcal',n.energy_kcal,'protein_g',n.protein_g,'fat_g',n.fat_g,
   'carbohydrate_g',n.carbohydrate_g,'fiber_g',n.fiber_g,'sodium_mg',n.sodium_mg,
   'calcium_mg',n.calcium_mg,'ingredient_count',n.ingredient_count,'snapshot_date','2026-11-19',
   'calculation_basis','core.ingredient × amount_g / 100',
   'missing_value_policy','任一配料对应字段缺失时，该菜该字段为NULL，不将缺失值视为0',
   'cooking_loss_adjusted',false
  ) nutrition_snapshot,
  jsonb_build_object(
   'strict_allergens',a.strict_allergens,'unverified_food_ids',a.unverified_food_ids,
   'note','过敏原按食材记录汇总；未核查不等于确认不含。'
  ) avoid_snapshot
 FROM nutrition n JOIN ingredients i USING(dish_id) JOIN allergy a USING(dish_id)
)
UPDATE core.dish d SET
 nutrition_snapshot=f.nutrition_snapshot,avoid_snapshot=f.avoid_snapshot,
 source_row=d.source_row||jsonb_build_object('ingredients',f.ingredients,'nutrition_snapshot',f.nutrition_snapshot,'avoid_snapshot',f.avoid_snapshot),
 updated_at=now()
FROM facts f WHERE d.dish_id=f.dish_id AND d.source_id='home-variants-v2.1-20261119';

DO $$
DECLARE dc int; rc int;
BEGIN
 SELECT count(*) INTO dc FROM core.dish WHERE source_id='home-variants-v2.1-20261119' AND NOT is_deleted;
 SELECT count(*) INTO rc FROM core.dish_ingredient WHERE generated_from='v21_home_variants_20261119';
 IF dc<>10 OR rc<>(SELECT count(*) FROM _v21_relation) THEN
  RAISE EXCEPTION '变体迁移计数异常：dish %, relation %',dc,rc;
 END IF;
 IF EXISTS (
  SELECT 1 FROM _v21_before b JOIN (
   SELECT 'dish'::text entity,md5(COALESCE(string_agg(to_jsonb(d)::text,'|' ORDER BY d.dish_id),'')) fingerprint
   FROM core.dish d WHERE d.dish_id BETWEEN 'DISH-001' AND 'DISH-100'
   UNION ALL
   SELECT 'dish_ingredient',md5(COALESCE(string_agg(to_jsonb(di)::text,'|' ORDER BY di.dish_ingredient_id),''))
   FROM core.dish_ingredient di WHERE di.dish_id BETWEEN 'DISH-001' AND 'DISH-100'
  ) a USING(entity) WHERE b.fingerprint<>a.fingerprint
 ) THEN RAISE EXCEPTION '原DISH-001..DISH-100被修改'; END IF;
END $$;

COMMIT;

SELECT 'v21_home_variants_10' migration,
 count(*) FILTER(WHERE source_id='home-variants-v2.1-20261119') added_variants,
 count(*) FILTER(WHERE dish_id BETWEEN 'DISH-001' AND 'DISH-100') preserved_existing
FROM core.dish WHERE NOT is_deleted;
