--
-- 45_博淇v21基础菜合入_v1.2r4.sql
-- 用途：把博淇 v21 基础家常菜单合入菜式库：DISH-121..160（40 道基础菜）+ DISH-161..170（10 道同食材变体），
--       共 50 道普通菜；含 4 条有权威来源的新增食材（鸡腿 CN-882 / 豆浆 CN-338 / 白菜薹 CN-453 / 生菜 CN-483）。
-- 前置：01 备份还原且既有迁移链已跑完，DISH-001..120 共 120 道普通菜已入库（38 号扩充批次在位）；
--       core.dish / core.dish_ingredient / core.ingredient 表已存在。执行账号：postgres（diet_app 无 core 写权限）。
-- 幂等：可重复执行；同 dish_id 冲突时 ON CONFLICT DO UPDATE 描述性字段；脚本带原 DISH-001..100 指纹漂移校验，原段被改动即抛错。
-- 口径：source_id 沿用原稿 home-basics-v2.1-20261119 / home-variants-v2.1-20261119；
--       营养快照由 app.v_dish_live_nutrition 按 core.ingredient × amount_g 汇总，缺失值保持 NULL，不按 0 计算。
-- 备注：清蒸带鱼、洋葱炒蛋与库内同名菜以「（家常版）」后缀区分；43 条 -LS 少盐变体见 46 号脚本。
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
  SELECT count(*) INTO v_base_count FROM core.dish
   WHERE dish_id NOT LIKE '%-LS' AND NOT is_deleted;
  IF v_base_count < 120 THEN
    RAISE EXCEPTION '前置不满足：普通菜基线应为 120（原 60 + 38 号 061..120），当前普通菜 % 道，先跑 38 号扩充脚本', v_base_count;
  END IF;
END $$;

-- 0. 登记迁移日志（幂等）
INSERT INTO audit.schema_migration (migration_id, description, applied_by)
VALUES ('2026-11-20-v21-basics-merge',
        '博淇 v21 基础菜单合入：DISH-121..170 共 50 道普通菜（40 基础 + 10 同食材变体），新增 4 条权威来源食材；重排自 v21 原稿，幂等可重跑。',
        'chentiantian-bot')
ON CONFLICT (migration_id) DO NOTHING;

BEGIN;

\set ON_ERROR_STOP on

-- V2.1 增量：40 道简单家常基础菜 + 4 条有权威来源的缺失食材。
-- 设计原则：
-- 1. 只新增，不修改 DISH-001..DISH-060 及其配料关系；
-- 2. 食材营养来自中国食物成分查询平台，缺失字段保持 NULL；
-- 3. 配料克数优先采用国家卫生健康委食谱，或复用现有同类菜的项目标准化量；
-- 4. 新食材的过敏原未被来源明确核实时保留“未核查”，不声称安全；
-- 5. 整个脚本在单一事务中执行，可重复运行，冲突时整体回滚。

SELECT pg_advisory_xact_lock(hashtextextended('diet-agent:v21-home-basics-40:2026-11-19', 0));


CREATE TEMP TABLE _v21_base_fingerprint ON COMMIT DROP AS
SELECT 'dish'::text AS entity,
       md5(COALESCE(string_agg(to_jsonb(d)::text, '|' ORDER BY d.dish_id), '')) AS fingerprint
FROM core.dish d WHERE d.dish_id BETWEEN 'DISH-001' AND 'DISH-060'
UNION ALL
SELECT 'dish_ingredient',
       md5(COALESCE(string_agg(to_jsonb(di)::text, '|' ORDER BY di.dish_ingredient_id), ''))
FROM core.dish_ingredient di
WHERE di.dish_id BETWEEN 'DISH-001' AND 'DISH-060';

INSERT INTO audit.import_batch (
  dataset_name, dataset_version, original_file_name, original_sha256,
  imported_by, status, notes
)
SELECT
  'V2.1普通家常基础菜增量', '2026-11-19', 'v21_home_basics_40.sql',
  '496a643224fccc3ec68b67ed361ae13ee7631d8b6e5c24045a99afcda4f41823',
  current_user, 'promoted',
  '语义清单哈希；新增40道基础菜和4条有权威来源的食材。营养按core.ingredient×amount_g重算，缺失值不按0处理；不改原60道菜。'
WHERE NOT EXISTS (
  SELECT 1 FROM audit.import_batch
  WHERE dataset_name = 'V2.1普通家常基础菜增量' AND dataset_version = '2026-11-19'
);

CREATE TEMP TABLE _v21_batch ON COMMIT DROP AS
SELECT import_batch_id
FROM audit.import_batch
WHERE dataset_name = 'V2.1普通家常基础菜增量' AND dataset_version = '2026-11-19'
ORDER BY import_batch_id
LIMIT 1;

CREATE TEMP TABLE _v21_source (
  source_name text PRIMARY KEY,
  source_url text NOT NULL,
  publisher text NOT NULL
) ON COMMIT DROP;

INSERT INTO _v21_source VALUES
  ('中国食物成分查询平台：鸡腿', 'https://nlc.chinanutri.cn/fq/foodinfo/882.html', '中国疾病预防控制中心营养与健康所、中国营养学会'),
  ('中国食物成分查询平台：豆浆', 'https://nlc.chinanutri.cn/fq/foodinfo/338.html', '中国疾病预防控制中心营养与健康所、中国营养学会'),
  ('中国食物成分查询平台：白菜薹（菜心）', 'https://nlc.chinanutri.cn/fq/foodinfo/453.html', '中国疾病预防控制中心营养与健康所、中国营养学会'),
  ('中国食物成分查询平台：生菜（叶用莴苣）', 'https://nlc.chinanutri.cn/fq/foodinfo/483.html', '中国疾病预防控制中心营养与健康所、中国营养学会');

INSERT INTO core.data_source (source_name, source_url, publisher, version, accessed_on, notes)
SELECT source_name, source_url, publisher, '中国食物成分表在线查询', DATE '2026-11-19',
       '用于本次本机家常基础菜增量；网页数据口径为每100克可食部。'
FROM _v21_source
ON CONFLICT (source_name, source_url, version) DO NOTHING;

CREATE TEMP TABLE _v21_ingredient (
  food_id text PRIMARY KEY,
  name text NOT NULL,
  aliases text[] NOT NULL,
  category text NOT NULL,
  state text NOT NULL,
  edible_portion_pct numeric NOT NULL,
  energy_kj numeric,
  energy_kcal numeric NOT NULL,
  protein_g numeric,
  fat_g numeric,
  carbohydrate_g numeric,
  fiber_g numeric,
  sodium_mg numeric,
  potassium_mg numeric,
  calcium_mg numeric,
  magnesium_mg numeric,
  cholesterol_mg numeric,
  micro_nutrients jsonb NOT NULL,
  allergens text[] NOT NULL,
  allergen_status text NOT NULL,
  source_name text NOT NULL,
  source_url text NOT NULL,
  source_note text NOT NULL
) ON COMMIT DROP;

INSERT INTO _v21_ingredient VALUES
  ('CN-882', '鸡腿', ARRAY['鸡全腿'], '禽肉', '生', 69, 753, 180.0, 16.0, 13.0, 0.0, NULL, 64.4, 242, 6, 34, 162,
   '{"iron_mg":1.5,"zinc_mg":1.12,"selenium_ug":12.4,"copper_mg":0.09,"manganese_mg":0.03,"phosphorus_mg":172,"vitamin_a_ug":44,"vitamin_b1_mg":0.02,"vitamin_b2_mg":0.14,"vitamin_b3_mg":6.0}'::jsonb,
   ARRAY[]::text[], '未核查', '中国食物成分查询平台：鸡腿', 'https://nlc.chinanutri.cn/fq/foodinfo/882.html',
   '官方每100克可食部；碳水为Tr按0记录；来源未给出过敏原核查，保留未核查。'),
  ('CN-338', '豆浆', ARRAY['无糖豆浆'], '豆类与豆制品', '液态即饮', 100, 65, 15.5, 1.8, 0.7, 1.1, NULL, 3.0, 48, 10, 9, NULL,
   '{"iron_mg":0.5,"zinc_mg":0.24,"selenium_ug":0.1,"copper_mg":0.07,"manganese_mg":0.09,"phosphorus_mg":30,"carotene_ug":90,"vitamin_b1_mg":0.02,"vitamin_b2_mg":0.02,"vitamin_b3_mg":0.1}'::jsonb,
   ARRAY['大豆'], '已确认含', '中国食物成分查询平台：豆浆', 'https://nlc.chinanutri.cn/fq/foodinfo/338.html',
   '官方每100克可食部；食物类别为大豆制品，按项目既有豆制品口径记录大豆过敏原。'),
  ('CN-453', '白菜薹', ARRAY['菜薹','菜心'], '蔬菜', '生', 84, 119, 28.4, 2.8, 0.5, 4.0, NULL, 26.0, 236, 96, 19, NULL,
   '{"iron_mg":2.8,"zinc_mg":0.87,"selenium_ug":6.7,"copper_mg":0.18,"manganese_mg":0.41,"phosphorus_mg":54,"carotene_ug":960,"vitamin_c_mg":44,"vitamin_b1_mg":0.05,"vitamin_b2_mg":0.08,"vitamin_b3_mg":1.2}'::jsonb,
   ARRAY[]::text[], '未核查', '中国食物成分查询平台：白菜薹（菜心）', 'https://nlc.chinanutri.cn/fq/foodinfo/453.html',
   '官方每100克可食部；来源未给出过敏原核查，保留未核查。'),
  ('CN-483', '生菜', ARRAY['叶用莴苣'], '蔬菜', '生', 94, 61, 14.6, 1.3, 0.3, 2.0, NULL, 32.8, 170, 34, 18, NULL,
   '{"iron_mg":0.9,"zinc_mg":0.27,"selenium_ug":1.2,"copper_mg":0.03,"manganese_mg":0.13,"phosphorus_mg":27,"carotene_ug":1790,"vitamin_c_mg":13,"vitamin_b1_mg":0.03,"vitamin_b2_mg":0.06,"vitamin_b3_mg":0.4}'::jsonb,
   ARRAY[]::text[], '未核查', '中国食物成分查询平台：生菜（叶用莴苣）', 'https://nlc.chinanutri.cn/fq/foodinfo/483.html',
   '官方每100克可食部；来源未给出过敏原核查，保留未核查。');

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM core.ingredient i JOIN _v21_ingredient n USING (food_id)
    WHERE i.name IS DISTINCT FROM n.name
       OR i.energy_kcal IS DISTINCT FROM n.energy_kcal
       OR i.protein_g IS DISTINCT FROM n.protein_g
       OR i.fat_g IS DISTINCT FROM n.fat_g
       OR i.carbohydrate_g IS DISTINCT FROM n.carbohydrate_g
       OR i.source_url IS DISTINCT FROM n.source_url
  ) THEN
    RAISE EXCEPTION '目标 food_id 已存在但事实不同，停止迁移';
  END IF;
END $$;

INSERT INTO core.ingredient (
  food_id, name, aliases, category, state, edible_portion_pct,
  energy_kj, energy_kcal, protein_g, fat_g, carbohydrate_g, fiber_g,
  sodium_mg, potassium_mg, calcium_mg, magnesium_mg, cholesterol_mg,
  micro_nutrients, fatty_acids, tags, allergens, allergen_status,
  purine_level, cooked_factor, oil_absorption_g_per_100g,
  source_url, source_id, source_row, import_batch_id, version, data_quality
)
SELECT
  n.food_id, n.name, n.aliases, n.category, n.state, n.edible_portion_pct,
  n.energy_kj, n.energy_kcal, n.protein_g, n.fat_g, n.carbohydrate_g, n.fiber_g,
  n.sodium_mg, n.potassium_mg, n.calcium_mg, n.magnesium_mg, n.cholesterol_mg,
  n.micro_nutrients, '{}'::jsonb, ARRAY['V2.1基础家常菜增量'], n.allergens, n.allergen_status,
  NULL, NULL, NULL,
  n.source_url, ds.source_id,
  jsonb_build_object(
    'food_id', n.food_id, 'name', n.name, 'aliases', n.aliases,
    'category', n.category, 'state', n.state, 'edible_pct', n.edible_portion_pct,
    'energy_kj', n.energy_kj, 'energy_kcal', n.energy_kcal,
    'protein_g', n.protein_g, 'fat_g', n.fat_g, 'carbohydrate_g', n.carbohydrate_g,
    'fiber_g', n.fiber_g, 'sodium_mg', n.sodium_mg, 'potassium_mg', n.potassium_mg,
    'calcium_mg', n.calcium_mg, 'magnesium_mg', n.magnesium_mg,
    'cholesterol_mg', n.cholesterol_mg, 'allergens', n.allergens,
    'allergen_status', n.allergen_status, 'source_url', n.source_url,
    'source_note', n.source_note, 'data_quality', 'official',
    'micro_nutrients', n.micro_nutrients,
    'missing_value_policy', '来源空白字段保持NULL，不视为0',
    'accessed_on', '2026-11-19'
  ),
  b.import_batch_id, '2026-11-19', 'official'
FROM _v21_ingredient n
JOIN core.data_source ds
  ON ds.source_name = n.source_name AND ds.source_url = n.source_url
 AND ds.version = '中国食物成分表在线查询'
CROSS JOIN _v21_batch b
WHERE NOT EXISTS (SELECT 1 FROM core.ingredient i WHERE i.food_id = n.food_id);

CREATE TEMP TABLE _v21_dish (
  dish_id text PRIMARY KEY,
  name text NOT NULL,
  category text NOT NULL,
  tags text[] NOT NULL,
  method_text text NOT NULL,
  cooking_rule_id text NOT NULL,
  default_oil_g numeric NOT NULL,
  default_salt_g numeric NOT NULL,
  cook_time_min integer,
  reference_url text NOT NULL,
  standardization_note text NOT NULL
) ON COMMIT DROP;

INSERT INTO _v21_dish VALUES
  ('DISH-121','白米饭','主食',ARRAY['基础家常菜','常见','简单','主食'],'蒸煮','CR004',0,0,30,'https://www.nhc.gov.cn/cms-search/downFiles/cbd48e38de3d4b8bb3e2093c9fbd43a5.pdf','卫健委示例食谱：大米50g；不额外加油盐'),
  ('DISH-122','白馒头','主食',ARRAY['基础家常菜','常见','简单','主食','早餐'],'直接食用','CR001',0,0,NULL,'https://nlc.chinanutri.cn/fq/foodinfo/272.html','按食物成分来源的100g可食部设为可缩放标准份'),
  ('DISH-123','原味切片面包','主食',ARRAY['基础家常菜','常见','简单','主食','早餐'],'直接食用','CR001',0,0,NULL,'https://www.nhc.gov.cn/cms-search/downFiles/cbd48e38de3d4b8bb3e2093c9fbd43a5.pdf','卫健委示例食谱：切片面包35g'),
  ('DISH-124','蒸玉米','主食',ARRAY['基础家常菜','常见','简单','主食','早餐'],'清蒸','CR002',0,0,20,'https://www.nhc.gov.cn/cms-search/downFiles/63f752a17cfd4b4781f744477561866f.pdf','卫健委示例食谱：玉米100g；不额外加油盐'),
  ('DISH-125','清汤面','主食',ARRAY['基础家常菜','常见','简单','主食'],'水煮','CR004',0,0,12,'https://www.nhc.gov.cn/cms-search/downFiles/4fcbecd2c18e46baaf291bf46c2b79cd.pdf','卫健委示例食谱：面条75g；本条仅记录面条，不加入未称量汤料'),
  ('DISH-126','原味米粉','主食',ARRAY['基础家常菜','常见','简单','主食'],'水煮','CR004',0,0,12,'https://www.nhc.gov.cn/sps/c100087/202604/a69d2fce21e040dc96cbc40b923a06d3/files/%E9%99%84%E4%BB%B65.%E6%88%90%E4%BA%BA%E8%82%8C%E5%B0%91%E7%97%87%E9%A3%9F%E5%85%BB%E6%8C%87%E5%8D%97%EF%BC%882026%E5%B9%B4%E7%89%88%EF%BC%89.pdf','卫健委示例食谱：干米粉50g；不加入未称量汤料'),
  ('DISH-127','水煮鸡蛋','蛋豆类',ARRAY['基础家常菜','常见','简单','早餐','蛋白质来源'],'水煮','CR004',0,0,10,'https://www.nhc.gov.cn/cms-search/downFiles/cbd48e38de3d4b8bb3e2093c9fbd43a5.pdf','卫健委示例食谱：鸡蛋50g'),
  ('DISH-128','无糖豆浆','饮品',ARRAY['基础家常菜','常见','简单','早餐','豆类饮品'],'煮透后饮用','CR001',0,0,NULL,'https://www.nhc.gov.cn/sps/c100087/202404/90c64c79708740a1bca0ee31e524caf7.shtml','卫健委等量交换：豆浆约300g；不额外加糖'),
  ('DISH-129','纯牛奶','饮品',ARRAY['基础家常菜','常见','简单','早餐','奶类'],'直接饮用','CR001',0,0,NULL,'https://www.nhc.gov.cn/wjw/c100175/202005/7757e4f72e13402a97b42f785d7a335a.shtml','卫健委建议：液体奶300g；不按含乳饮料处理'),
  ('DISH-130','原味酸奶','饮品',ARRAY['基础家常菜','常见','简单','早餐','奶类'],'直接食用','CR001',0,0,NULL,'https://www.nhc.gov.cn/sps/c100087/202604/a69d2fce21e040dc96cbc40b923a06d3/files/%E9%99%84%E4%BB%B65.%E6%88%90%E4%BA%BA%E8%82%8C%E5%B0%91%E7%97%87%E9%A3%9F%E5%85%BB%E6%8C%87%E5%8D%97%EF%BC%882026%E5%B9%B4%E7%89%88%EF%BC%89.pdf','卫健委示例食谱：酸奶100g'),
  ('DISH-131','苹果','水果',ARRAY['基础家常菜','常见','简单','水果','即食'],'洗净直接食用','CR001',0,0,NULL,'https://www.nhc.gov.cn/wjw/c100378/202301/7faed9993c9b45aea158c5335346f282/files/1732844468018_41219.pdf','卫健委示例食谱：苹果200g'),
  ('DISH-132','香蕉','水果',ARRAY['基础家常菜','常见','简单','水果','即食'],'去皮直接食用','CR001',0,0,NULL,'https://www.nhc.gov.cn/cms-search/downFiles/63f752a17cfd4b4781f744477561866f.pdf','卫健委示例食谱：香蕉200g'),
  ('DISH-133','橙子','水果',ARRAY['基础家常菜','常见','简单','水果','即食'],'去皮直接食用','CR001',0,0,NULL,'https://www.nhc.gov.cn/sps/c100087/202604/a69d2fce21e040dc96cbc40b923a06d3/files/%E9%99%84%E4%BB%B65.%E6%88%90%E4%BA%BA%E8%82%8C%E5%B0%91%E7%97%87%E9%A3%9F%E5%85%BB%E6%8C%87%E5%8D%97%EF%BC%882026%E5%B9%B4%E7%89%88%EF%BC%89.pdf','卫健委示例食谱：橙子200g'),
  ('DISH-134','梨','水果',ARRAY['基础家常菜','常见','简单','水果','即食'],'洗净直接食用','CR001',0,0,NULL,'https://www.nhc.gov.cn/sps/c100087/202604/a69d2fce21e040dc96cbc40b923a06d3/files/%E9%99%84%E4%BB%B65.%E6%88%90%E4%BA%BA%E8%82%8C%E5%B0%91%E7%97%87%E9%A3%9F%E5%85%BB%E6%8C%87%E5%8D%97%EF%BC%882026%E5%B9%B4%E7%89%88%EF%BC%89.pdf','卫健委示例食谱：梨200g'),
  ('DISH-135','葡萄','水果',ARRAY['基础家常菜','常见','简单','水果','即食'],'洗净直接食用','CR001',0,0,NULL,'https://www.nhc.gov.cn/cms-search/downFiles/63f752a17cfd4b4781f744477561866f.pdf','卫健委示例食谱：葡萄200g'),
  ('DISH-136','西瓜','水果',ARRAY['基础家常菜','常见','简单','水果','即食'],'切块直接食用','CR001',0,0,NULL,'https://www.nhc.gov.cn/xcs/cbcl/201706/d7d8ff3889be445b8bfb86a5efea952f.shtml','按每日水果200至350g建议取200g可食部'),
  ('DISH-137','桃','水果',ARRAY['基础家常菜','常见','简单','水果','即食'],'洗净直接食用','CR001',0,0,NULL,'https://www.nhc.gov.cn/xcs/cbcl/201706/d7d8ff3889be445b8bfb86a5efea952f.shtml','按每日水果200至350g建议取200g可食部'),
  ('DISH-138','猕猴桃','水果',ARRAY['基础家常菜','常见','简单','水果','即食'],'去皮直接食用','CR001',0,0,NULL,'https://www.nhc.gov.cn/cms-search/downFiles/4fcbecd2c18e46baaf291bf46c2b79cd.pdf','卫健委示例食谱：猕猴桃100g'),
  ('DISH-139','卤鸡腿','畜禽肉类',ARRAY['基础家常菜','常见','简单','蛋白质来源','酱卤'],'少盐酱卤','CR016',0,0,35,'https://nlc.chinanutri.cn/fq/foodinfo/882.html','鸡腿按100g可食部标准份；姜和酱油各5g复用现有菜库称量口径；不额外加油盐糖'),
  ('DISH-140','白切鸡腿','畜禽肉类',ARRAY['基础家常菜','常见','简单','蛋白质来源'],'水煮','CR004',0,0,25,'https://nlc.chinanutri.cn/fq/foodinfo/882.html','鸡腿按100g可食部标准份；姜5g复用现有菜库称量口径；不额外加盐'),
  ('DISH-141','清蒸豆腐','蛋豆类',ARRAY['基础家常菜','常见','简单','蛋白质来源'],'清蒸','CR002',0,0.6,12,'https://nlc.chinanutri.cn/fq/foodinfo/333.html','豆腐按100g可食部标准份；盐0.6g复用现有清蒸菜口径'),
  ('DISH-142','白灼虾仁','水产类',ARRAY['基础家常菜','常见','简单','蛋白质来源'],'白灼','CR003',0,0.6,8,'https://nlc.chinanutri.cn/fq/foodinfo/1091.html','海虾100g可食部；盐0.6g复用现有白灼规则口径'),
  ('DISH-143','清蒸带鱼（家常版）','水产类',ARRAY['基础家常菜','常见','简单','蛋白质来源'],'清蒸','CR002',0,0.6,15,'https://www.nhc.gov.cn/sps/c100088/202301/f01895a06c5349ef999f25da833c166d/files/1732844468278_20318.pdf','卫健委示例食谱：带鱼100g；姜5g、盐0.6g复用现有清蒸鱼口径'),
  ('DISH-144','清炖鲤鱼','水产类',ARRAY['基础家常菜','常见','简单','蛋白质来源'],'清炖','CR006',0,0.8,30,'https://www.nhc.gov.cn/cms-search/downFiles/63f752a17cfd4b4781f744477561866f.pdf','卫健委示例食谱：鲤鱼100g；姜5g、盐0.8g复用现有清炖菜口径'),
  ('DISH-145','清蒸鸡蛋羹','蛋豆类',ARRAY['基础家常菜','常见','简单','早餐','蛋白质来源'],'清蒸','CR002',0,0.6,12,'https://www.nhc.gov.cn/cms-search/downFiles/cbd48e38de3d4b8bb3e2093c9fbd43a5.pdf','鸡蛋50g采用卫健委早餐份量；盐0.6g复用现有清蒸规则口径'),
  ('DISH-146','盐水菜心','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'白灼','CR003',0,0.6,8,'https://nlc.chinanutri.cn/fq/foodinfo/453.html','菜心按100g可食部标准份；盐0.6g采用白灼规则默认口径'),
  ('DISH-147','白灼生菜','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'白灼','CR003',0,0.6,5,'https://www.nhc.gov.cn/cms-search/downFiles/4fcbecd2c18e46baaf291bf46c2b79cd.pdf','卫健委示例食谱：白灼生菜100g；盐0.6g采用白灼规则默认口径'),
  ('DISH-148','清炒生菜','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'快炒','CR009',4,0.8,6,'https://www.nhc.gov.cn/wjw/c100378/202301/7faed9993c9b45aea158c5335346f282/files/1732844468018_41219.pdf','卫健委炒时蔬：生菜200g；油4g盐0.8g复用现有清炒蔬菜口径'),
  ('DISH-149','蒜炒空心菜','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'快炒','CR009',4,0.8,7,'https://www.nhc.gov.cn/cms-search/downFiles/4fcbecd2c18e46baaf291bf46c2b79cd.pdf','卫健委示例食谱：空心菜100g；蒜5g、油4g盐0.8g复用现有清炒蔬菜口径'),
  ('DISH-150','清炒丝瓜','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'快炒','CR009',4,0.8,7,'https://www.nhc.gov.cn/cms-search/downFiles/4fcbecd2c18e46baaf291bf46c2b79cd.pdf','卫健委示例食谱：丝瓜150g；油4g盐0.8g复用现有清炒蔬菜口径'),
  ('DISH-151','白灼西兰花','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'白灼','CR003',0,0.6,7,'https://www.nhc.gov.cn/cms-search/downFiles/63f752a17cfd4b4781f744477561866f.pdf','卫健委示例食谱含西兰花100g；盐0.6g采用白灼规则默认口径'),
  ('DISH-152','盐水小白菜','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'白灼','CR003',0,0.6,6,'https://www.nhc.gov.cn/cms-search/downFiles/cbd48e38de3d4b8bb3e2093c9fbd43a5.pdf','卫健委水煮叶菜示例100g；盐0.6g采用白灼规则默认口径'),
  ('DISH-153','清炒大白菜','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'快炒','CR009',4,0.8,7,'https://www.nhc.gov.cn/cms-search/downFiles/cbd48e38de3d4b8bb3e2093c9fbd43a5.pdf','卫健委示例食谱：炒圆白菜80g；油4g盐0.8g复用现有清炒蔬菜口径'),
  ('DISH-154','清炒油菜','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'快炒','CR009',4,0.8,7,'https://www.nhc.gov.cn/sps/c100087/202604/a69d2fce21e040dc96cbc40b923a06d3/files/%E9%99%84%E4%BB%B65.%E6%88%90%E4%BA%BA%E8%82%8C%E5%B0%91%E7%97%87%E9%A3%9F%E5%85%BB%E6%8C%87%E5%8D%97%EF%BC%882026%E5%B9%B4%E7%89%88%EF%BC%89.pdf','卫健委示例食谱：油菜150g；油4g盐0.8g复用现有清炒蔬菜口径'),
  ('DISH-155','清炒菜心','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'快炒','CR009',4,0.8,7,'https://www.nhc.gov.cn/sps/c100087/202604/a69d2fce21e040dc96cbc40b923a06d3/files/%E9%99%84%E4%BB%B65.%E6%88%90%E4%BA%BA%E8%82%8C%E5%B0%91%E7%97%87%E9%A3%9F%E5%85%BB%E6%8C%87%E5%8D%97%EF%BC%882026%E5%B9%B4%E7%89%88%EF%BC%89.pdf','卫健委示例食谱：清炒菜薹150g；油4g盐0.8g复用现有清炒蔬菜口径'),
  ('DISH-156','清炒茼蒿','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'快炒','CR009',4,0.8,7,'https://www.nhc.gov.cn/sps/c100088/202301/f01895a06c5349ef999f25da833c166d/files/1732844468278_20318.pdf','卫健委示例食谱：炒茼蒿150g；油4g盐0.8g复用现有清炒蔬菜口径'),
  ('DISH-157','清炒苋菜','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'快炒','CR009',4,0.8,7,'https://www.nhc.gov.cn/sps/c100087/202604/a69d2fce21e040dc96cbc40b923a06d3/files/%E9%99%84%E4%BB%B65.%E6%88%90%E4%BA%BA%E8%82%8C%E5%B0%91%E7%97%87%E9%A3%9F%E5%85%BB%E6%8C%87%E5%8D%97%EF%BC%882026%E5%B9%B4%E7%89%88%EF%BC%89.pdf','卫健委示例食谱：米苋菜150g；油4g盐0.8g复用现有清炒蔬菜口径'),
  ('DISH-158','清炒西葫芦','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'快炒','CR009',4,0.8,7,'https://www.nhc.gov.cn/wjw/c100378/202301/7faed9993c9b45aea158c5335346f282/files/1732844468018_41219.pdf','卫健委炒时蔬：西葫芦200g；油4g盐0.8g复用现有清炒蔬菜口径'),
  ('DISH-159','蒸茄子','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'清蒸','CR002',0,0.6,12,'https://www.nhc.gov.cn/cms-search/downFiles/63f752a17cfd4b4781f744477561866f.pdf','卫健委示例食谱：茄子100g；盐0.6g采用清蒸规则默认口径'),
  ('DISH-160','白灼菜花','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'白灼','CR003',0,0.6,7,'https://nlc.chinanutri.cn/fq/foodinfo/464.html','菜花按100g可食部标准份；盐0.6g采用白灼规则默认口径');

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM core.dish d JOIN _v21_dish n USING (dish_id)
    WHERE d.name IS DISTINCT FROM n.name OR d.source_id IS DISTINCT FROM 'home-basics-v2.1-20261119'
  ) THEN
    RAISE EXCEPTION '目标 dish_id 已存在但不属于本迁移，停止迁移';
  END IF;
  IF EXISTS (
    SELECT 1 FROM core.dish d JOIN _v21_dish n ON d.name = n.name
    WHERE d.dish_id <> n.dish_id
  ) THEN
    RAISE EXCEPTION '新增菜名已被其他 dish_id 使用，停止迁移';
  END IF;
END $$;

INSERT INTO core.dish (
  dish_id, name, aliases, category, tags, method_text, cooking_rule_id,
  servings, default_oil_g, default_salt_g, cook_time_min,
  nutrition_snapshot, avoid_snapshot, source_row, import_batch_id,
  source, source_id
)
SELECT
  n.dish_id, n.name, ARRAY[]::text[], n.category, n.tags, n.method_text, n.cooking_rule_id,
  1, n.default_oil_g, n.default_salt_g, n.cook_time_min,
  '{}'::jsonb, '{}'::jsonb,
  jsonb_build_object(
    'dish_id', n.dish_id, 'dish_name', n.name, 'category', n.category,
    'method', n.method_text, 'servings', 1, 'oil_g', n.default_oil_g,
    'salt_g', n.default_salt_g, 'cooking_rule_id', n.cooking_rule_id,
    'data_quality', 'verified_ingredient_facts_with_project_recipe_standardization',
    'nutrition_basis', 'core.ingredient × amount_g；缺失值保持NULL，不按0计算；未按烹饪损耗修正',
    'reference_source_url', n.reference_url,
    'standardization_note', n.standardization_note,
    'standardized_at', '2026-11-19'
  ),
  b.import_batch_id, '基础家常菜库（可核验食材）', 'home-basics-v2.1-20261119'
FROM _v21_dish n CROSS JOIN _v21_batch b
ON CONFLICT (dish_id) DO UPDATE SET
  name=EXCLUDED.name, category=EXCLUDED.category, tags=EXCLUDED.tags,
  method_text=EXCLUDED.method_text, cooking_rule_id=EXCLUDED.cooking_rule_id,
  default_oil_g=EXCLUDED.default_oil_g, default_salt_g=EXCLUDED.default_salt_g,
  cook_time_min=EXCLUDED.cook_time_min, source_row=EXCLUDED.source_row,
  source=EXCLUDED.source, source_id=EXCLUDED.source_id, updated_at=now();

CREATE TEMP TABLE _v21_dish_ingredient (
  dish_id text NOT NULL,
  food_id text NOT NULL,
  amount_g numeric NOT NULL,
  role text NOT NULL,
  generated_from text NOT NULL DEFAULT 'v21_home_basics_20261119',
  PRIMARY KEY (dish_id, food_id, role, generated_from)
) ON COMMIT DROP;

INSERT INTO _v21_dish_ingredient (dish_id, food_id, amount_g, role) VALUES
  ('DISH-121','CN-280',50,'主料'),
  ('DISH-122','CN-272',100,'主料'),
  ('DISH-123','CN-1316',35,'主料'),
  ('DISH-124','CN-292',100,'主料'),
  ('DISH-125','CN-264',75,'主料'),
  ('DISH-126','CN-289',50,'主料'),
  ('DISH-127','CN-978',50,'主料'),
  ('DISH-128','CN-338',300,'主料'),
  ('DISH-129','CN-916',300,'主料'),
  ('DISH-130','CN-958',100,'主料'),
  ('DISH-131','CN-613',200,'主料'),
  ('DISH-132','CN-726',200,'主料'),
  ('DISH-133','CN-704',200,'主料'),
  ('DISH-134','CN-630',200,'主料'),
  ('DISH-135','CN-684',200,'主料'),
  ('DISH-136','CN-739',200,'主料'),
  ('DISH-137','CN-660',200,'主料'),
  ('DISH-138','CN-700',100,'主料'),
  ('DISH-139','CN-882',100,'主料'),('DISH-139','CN-528',5,'调味辅料'),('DISH-139','CN-1518',5,'调味料'),
  ('DISH-140','CN-882',100,'主料'),('DISH-140','CN-528',5,'调味辅料'),
  ('DISH-141','CN-333',100,'主料'),('DISH-141','CN-1565',0.6,'食盐'),
  ('DISH-142','CN-1091',100,'主料'),('DISH-142','CN-1565',0.6,'食盐'),
  ('DISH-143','CN-1030',100,'主料'),('DISH-143','CN-528',5,'调味辅料'),('DISH-143','CN-1565',0.6,'食盐'),
  ('DISH-144','CN-1012',100,'主料'),('DISH-144','CN-528',5,'调味辅料'),('DISH-144','CN-1565',0.8,'食盐'),
  ('DISH-145','CN-978',50,'主料'),('DISH-145','CN-1565',0.6,'食盐'),
  ('DISH-146','CN-453',100,'主料'),('DISH-146','CN-1565',0.6,'食盐'),
  ('DISH-147','CN-483',100,'主料'),('DISH-147','CN-1565',0.6,'食盐'),
  ('DISH-148','CN-483',200,'主料'),('DISH-148','CN-1510',4,'烹调油'),('DISH-148','CN-1565',0.8,'食盐'),
  ('DISH-149','CN-493',100,'主料'),('DISH-149','CN-436',5,'调味辅料'),('DISH-149','CN-1510',4,'烹调油'),('DISH-149','CN-1565',0.8,'食盐'),
  ('DISH-150','CN-429',150,'主料'),('DISH-150','CN-1510',4,'烹调油'),('DISH-150','CN-1565',0.8,'食盐'),
  ('DISH-151','CN-465',100,'主料'),('DISH-151','CN-1565',0.6,'食盐'),
  ('DISH-152','CN-452',100,'主料'),('DISH-152','CN-1565',0.6,'食盐'),
  ('DISH-153','CN-450',80,'主料'),('DISH-153','CN-1510',4,'烹调油'),('DISH-153','CN-1565',0.8,'食盐'),
  ('DISH-154','CN-457',150,'主料'),('DISH-154','CN-1510',4,'烹调油'),('DISH-154','CN-1565',0.8,'食盐'),
  ('DISH-155','CN-453',150,'主料'),('DISH-155','CN-1510',4,'烹调油'),('DISH-155','CN-1565',0.8,'食盐'),
  ('DISH-156','CN-488',150,'主料'),('DISH-156','CN-1510',4,'烹调油'),('DISH-156','CN-1565',0.8,'食盐'),
  ('DISH-157','CN-486',150,'主料'),('DISH-157','CN-1510',4,'烹调油'),('DISH-157','CN-1565',0.8,'食盐'),
  ('DISH-158','CN-431',200,'主料'),('DISH-158','CN-1510',4,'烹调油'),('DISH-158','CN-1565',0.8,'食盐'),
  ('DISH-159','CN-402',100,'主料'),('DISH-159','CN-1565',0.6,'食盐'),
  ('DISH-160','CN-464',100,'主料'),('DISH-160','CN-1565',0.6,'食盐');

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM _v21_dish_ingredient x
    LEFT JOIN core.ingredient i ON i.food_id = x.food_id AND NOT i.is_deleted
    WHERE i.ingredient_id IS NULL
  ) THEN
    RAISE EXCEPTION '配料清单引用了不存在或已删除的 food_id';
  END IF;
  IF EXISTS (
    SELECT 1 FROM core.dish_ingredient di
    JOIN core.ingredient i USING (ingredient_id)
    JOIN _v21_dish_ingredient x ON x.dish_id = di.dish_id AND x.food_id = i.food_id
    WHERE di.generated_from = x.generated_from
      AND (
            di.role IS DISTINCT FROM x.role
         OR (di.amount_g IS DISTINCT FROM x.amount_g
             -- 修订（2026-11-25，issue #23）：58 号把白米饭大米由 50g 对齐到 65g，
             -- 之后重跑本迁移属于预期差异，不视为事实冲突。
             AND NOT (x.food_id = 'CN-280' AND x.dish_id = 'DISH-121'
                      AND x.amount_g = 50 AND di.amount_g = 65))
          )
  ) THEN
    RAISE EXCEPTION '本迁移的配料关系已存在但克数或角色不同，停止迁移';
  END IF;
END $$;

INSERT INTO core.dish_ingredient (
  dish_id, ingredient_id, amount_g, cooked_amount_g, role,
  is_optional, generated_from, source_snapshot
)
SELECT
  x.dish_id, i.ingredient_id, x.amount_g, NULL, x.role,
  false, x.generated_from,
  jsonb_build_object(
    'food_id', x.food_id, 'amount_g', x.amount_g, 'role', x.role,
    'amount_basis', d.standardization_note,
    'reference_source_url', d.reference_url,
    'nutrition_basis', 'core.ingredient每100g数据按amount_g线性计算；未按烹饪损耗修正'
  )
FROM _v21_dish_ingredient x
JOIN core.ingredient i ON i.food_id = x.food_id AND NOT i.is_deleted
JOIN _v21_dish d USING (dish_id)
ON CONFLICT (dish_id, ingredient_id, role, generated_from) DO UPDATE SET
  amount_g=EXCLUDED.amount_g, role=EXCLUDED.role, source_snapshot=EXCLUDED.source_snapshot;

WITH base AS (
  SELECT d.dish_id, di.amount_g, di.role, i.*
  FROM core.dish d
  JOIN core.dish_ingredient di USING (dish_id)
  JOIN core.ingredient i USING (ingredient_id)
  WHERE d.source_id = 'home-basics-v2.1-20261119'
), nutrition AS (
  SELECT dish_id, count(*) AS ingredient_count,
    CASE WHEN bool_or(energy_kcal IS NULL) THEN NULL ELSE round(sum(amount_g*energy_kcal/100.0),1) END AS energy_kcal,
    CASE WHEN bool_or(protein_g IS NULL) THEN NULL ELSE round(sum(amount_g*protein_g/100.0),1) END AS protein_g,
    CASE WHEN bool_or(fat_g IS NULL) THEN NULL ELSE round(sum(amount_g*fat_g/100.0),1) END AS fat_g,
    CASE WHEN bool_or(carbohydrate_g IS NULL) THEN NULL ELSE round(sum(amount_g*carbohydrate_g/100.0),1) END AS carbohydrate_g,
    CASE WHEN bool_or(fiber_g IS NULL) THEN NULL ELSE round(sum(amount_g*fiber_g/100.0),1) END AS fiber_g,
    CASE WHEN bool_or(sodium_mg IS NULL) THEN NULL ELSE round(sum(amount_g*sodium_mg/100.0),1) END AS sodium_mg,
    CASE WHEN bool_or(calcium_mg IS NULL) THEN NULL ELSE round(sum(amount_g*calcium_mg/100.0),1) END AS calcium_mg,
    CASE WHEN bool_or((micro_nutrients->>'iron_mg') IS NULL) THEN NULL ELSE round(sum(amount_g*(micro_nutrients->>'iron_mg')::numeric/100.0),2) END AS iron_mg,
    CASE WHEN bool_or((micro_nutrients->>'zinc_mg') IS NULL) THEN NULL ELSE round(sum(amount_g*(micro_nutrients->>'zinc_mg')::numeric/100.0),2) END AS zinc_mg
  FROM base GROUP BY dish_id
), ingredient_json AS (
  SELECT dish_id,
    jsonb_agg(jsonb_build_object(
      'food_id',food_id,'food_name',name,'amount_g',amount_g,'role',role,
      'source_url',source_url,'data_quality',data_quality,
      'allergens',allergens,'allergen_status',allergen_status
    ) ORDER BY ingredient_id) AS ingredients
  FROM base GROUP BY dish_id
), allergy AS (
  SELECT b.dish_id,
    COALESCE(array_agg(DISTINCT a.allergen) FILTER (
      WHERE b.allergen_status='已确认含' AND a.allergen IS NOT NULL
    ), ARRAY[]::text[]) AS strict_allergens,
    COALESCE(array_agg(DISTINCT b.food_id) FILTER (
      WHERE b.allergen_status='未核查'
    ), ARRAY[]::text[]) AS unverified_food_ids
  FROM base b
  LEFT JOIN LATERAL unnest(b.allergens) AS a(allergen) ON true
  GROUP BY b.dish_id
), facts AS (
  SELECT n.*, j.ingredients, a.strict_allergens, a.unverified_food_ids,
    jsonb_build_object(
      'energy_kcal',n.energy_kcal,'protein_g',n.protein_g,'fat_g',n.fat_g,
      'carbohydrate_g',n.carbohydrate_g,'fiber_g',n.fiber_g,
      'sodium_mg',n.sodium_mg,'calcium_mg',n.calcium_mg,
      'iron_mg',n.iron_mg,'zinc_mg',n.zinc_mg,
      'ingredient_count',n.ingredient_count,'snapshot_date','2026-11-19',
      'calculation_basis','core.ingredient × amount_g / 100',
      'missing_value_policy','任一配料对应字段缺失时，该菜该字段为NULL，不将缺失值视为0',
      'cooking_loss_adjusted',false
    ) AS nutrition_snapshot,
    jsonb_build_object(
      'strict_allergens',a.strict_allergens,
      'unverified_food_ids',a.unverified_food_ids,
      'note','过敏原按食材记录汇总；未核查不等于确认不含。'
    ) AS avoid_snapshot
  FROM nutrition n JOIN ingredient_json j USING (dish_id) JOIN allergy a USING (dish_id)
)
UPDATE core.dish d
SET nutrition_snapshot = f.nutrition_snapshot,
    avoid_snapshot = f.avoid_snapshot,
    source_row = d.source_row || jsonb_build_object(
      'ingredients',f.ingredients,
      'nutrition_snapshot',f.nutrition_snapshot,
      'avoid_snapshot',f.avoid_snapshot
    ),
    updated_at = now()
FROM facts f
WHERE d.dish_id = f.dish_id AND d.source_id = 'home-basics-v2.1-20261119';

DO $$
DECLARE
  dish_count integer;
  ingredient_count integer;
  relation_count integer;
BEGIN
  SELECT count(*) INTO dish_count FROM core.dish WHERE source_id='home-basics-v2.1-20261119' AND NOT is_deleted;
  SELECT count(*) INTO ingredient_count FROM core.ingredient WHERE food_id IN (SELECT food_id FROM _v21_ingredient) AND NOT is_deleted;
  SELECT count(*) INTO relation_count
  FROM core.dish_ingredient WHERE generated_from='v21_home_basics_20261119';

  IF dish_count <> 40 OR ingredient_count <> 4 OR relation_count <> (SELECT count(*) FROM _v21_dish_ingredient) THEN
    RAISE EXCEPTION '迁移计数异常：dish %, ingredient %, relation %', dish_count, ingredient_count, relation_count;
  END IF;
  IF EXISTS (
    SELECT 1 FROM _v21_base_fingerprint before
    JOIN (
      SELECT 'dish'::text entity, md5(COALESCE(string_agg(to_jsonb(d)::text,'|' ORDER BY d.dish_id),'')) fingerprint
      FROM core.dish d WHERE d.dish_id BETWEEN 'DISH-001' AND 'DISH-060'
      UNION ALL
      SELECT 'dish_ingredient', md5(COALESCE(string_agg(to_jsonb(di)::text,'|' ORDER BY di.dish_ingredient_id),''))
      FROM core.dish_ingredient di WHERE di.dish_id BETWEEN 'DISH-001' AND 'DISH-060'
    ) after USING (entity)
    WHERE before.fingerprint <> after.fingerprint
  ) THEN
    RAISE EXCEPTION '原60道菜或配料关系发生变化，停止迁移';
  END IF;
  IF EXISTS (
    SELECT 1 FROM core.dish d
    WHERE d.source_id='home-basics-v2.1-20261119'
      AND (d.nutrition_snapshot='{}'::jsonb OR d.avoid_snapshot='{}'::jsonb)
  ) THEN
    RAISE EXCEPTION '新增菜营养或过敏原快照未生成';
  END IF;
END $$;

-- ============ 第二段：同核心食材家常变体 10 道（DISH-161..170） ============

\set ON_ERROR_STOP on

-- 基于同一核心食材扩展10道普通家常做法；不新增或改写食材营养事实。
SELECT pg_advisory_xact_lock(hashtextextended('diet-agent:v21-home-variants-10:2026-11-19', 0));


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

CREATE TEMP TABLE _v21_batch_v ON COMMIT DROP AS
SELECT import_batch_id FROM audit.import_batch
WHERE dataset_name='V2.1同核心食材家常变体' AND dataset_version='2026-11-19'
ORDER BY import_batch_id LIMIT 1;

CREATE TEMP TABLE _v21_variant (
  dish_id text PRIMARY KEY,name text NOT NULL,category text NOT NULL,tags text[] NOT NULL,
  method_text text NOT NULL,cooking_rule_id text NOT NULL,default_oil_g numeric NOT NULL,
  default_salt_g numeric NOT NULL,cook_time_min integer,standardization_note text NOT NULL
) ON COMMIT DROP;

INSERT INTO _v21_variant VALUES
 ('DISH-161','洋葱炒蛋（家常版）','蛋豆类',ARRAY['基础家常菜','常见','简单','鸡蛋','蔬菜'],'快炒','CR009',5,1,8,'鸡蛋100g、油5g、盐1g复用番茄炒蛋；洋葱50g复用现有牛肉菜'),
 ('DISH-162','肉末蒸蛋','蛋豆类',ARRAY['基础家常菜','常见','简单','鸡蛋','猪肉'],'清蒸','CR002',0,0.6,15,'鸡蛋50g采用卫健委早餐份量；猪里脊25g复用菜花炒里脊；盐0.6g采用清蒸口径'),
 ('DISH-163','香菇蒸鸡','畜禽肉类',ARRAY['基础家常菜','常见','简单','鸡肉','香菇'],'清蒸','CR002',0,0.8,20,'鸡胸肉40g、香菇25g、姜5g、盐0.8g复用香菇炖鸡胸肉，改为无油清蒸'),
 ('DISH-164','土豆炖鸡','畜禽肉类',ARRAY['基础家常菜','常见','简单','鸡肉','土豆'],'清炖','CR006',2,0.8,35,'土豆75g复用土豆茄子炖牛肉；鸡胸肉50g复用黄瓜甜椒炒鸡丁；油盐复用现有清炖菜'),
 ('DISH-165','清炖鸡汤','汤羹',ARRAY['基础家常菜','常见','简单','鸡肉','汤羹'],'汤煮','CR005',0,0.8,40,'鸡胸肉40g、姜5g、盐0.8g复用现有指南标准化菜；未称量饮用水不计营养'),
 ('DISH-166','肉末豆腐','蛋豆类',ARRAY['基础家常菜','常见','简单','猪肉','豆腐'],'快炒','CR009',4,0.8,12,'猪里脊25g复用菜花炒里脊；豆腐100g为可食部标准份；油4g盐0.8g复用清炒口径'),
 ('DISH-167','小葱拌豆腐','蛋豆类',ARRAY['基础家常菜','常见','简单','豆腐','凉拌'],'凉拌','CR007',0,0.6,5,'豆腐100g为可食部标准份；大葱5g、盐0.6g复用现有菜库称量口径；不额外加油'),
 ('DISH-168','香煎豆腐','蛋豆类',ARRAY['基础家常菜','常见','简单','豆腐','煎'],'煎','CR011',4,0.8,12,'豆腐100g为可食部标准份；油4g盐0.8g复用项目少油家常菜口径'),
 ('DISH-169','蒸土豆','主食',ARRAY['基础家常菜','常见','简单','主食','土豆'],'清蒸','CR002',0,0,20,'土豆100g复用醋溜土豆丝主料量；不额外加油盐'),
 ('DISH-170','白粥','主食',ARRAY['基础家常菜','常见','简单','主食','早餐'],'煮粥','CR005',0,0,35,'大米50g复用卫健委米饭示例；未称量饮用水不计营养，不额外加油盐');

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
FROM _v21_variant n CROSS JOIN _v21_batch_v b
ON CONFLICT (dish_id) DO UPDATE SET
  name=EXCLUDED.name, category=EXCLUDED.category, tags=EXCLUDED.tags,
  method_text=EXCLUDED.method_text, cooking_rule_id=EXCLUDED.cooking_rule_id,
  default_oil_g=EXCLUDED.default_oil_g, default_salt_g=EXCLUDED.default_salt_g,
  cook_time_min=EXCLUDED.cook_time_min, source_row=EXCLUDED.source_row,
  source=EXCLUDED.source, source_id=EXCLUDED.source_id, updated_at=now();

CREATE TEMP TABLE _v21_relation (
 dish_id text,food_id text,amount_g numeric,role text,
 generated_from text DEFAULT 'v21_home_variants_20261119',
 PRIMARY KEY(dish_id,food_id,role,generated_from)
) ON COMMIT DROP;

INSERT INTO _v21_relation(dish_id,food_id,amount_g,role) VALUES
 ('DISH-161','CN-978',100,'主料'),('DISH-161','CN-444',50,'配菜'),('DISH-161','CN-1510',5,'烹调油'),('DISH-161','CN-1565',1,'食盐'),
 ('DISH-162','CN-978',50,'主料'),('DISH-162','CN-784',25,'主料'),('DISH-162','CN-1565',0.6,'食盐'),
 ('DISH-163','CN-880',40,'主料'),('DISH-163','CN-584',25,'配菜'),('DISH-163','CN-528',5,'调味辅料'),('DISH-163','CN-1565',0.8,'食盐'),
 ('DISH-164','CN-880',50,'主料'),('DISH-164','CN-313',75,'主料'),('DISH-164','CN-528',5,'调味辅料'),('DISH-164','CN-1510',2,'烹调油'),('DISH-164','CN-1565',0.8,'食盐'),
 ('DISH-165','CN-880',40,'主料'),('DISH-165','CN-528',5,'调味辅料'),('DISH-165','CN-1565',0.8,'食盐'),
 ('DISH-166','CN-784',25,'主料'),('DISH-166','CN-333',100,'主料'),('DISH-166','CN-1510',4,'烹调油'),('DISH-166','CN-1565',0.8,'食盐'),
 ('DISH-167','CN-333',100,'主料'),('DISH-167','CN-441',5,'调味辅料'),('DISH-167','CN-1565',0.6,'食盐'),
 ('DISH-168','CN-333',100,'主料'),('DISH-168','CN-1510',4,'烹调油'),('DISH-168','CN-1565',0.8,'食盐'),
 ('DISH-169','CN-313',100,'主料'),
 ('DISH-170','CN-280',50,'主料');

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
ON CONFLICT (dish_id, ingredient_id, role, generated_from) DO UPDATE SET
  amount_g=EXCLUDED.amount_g, role=EXCLUDED.role, source_snapshot=EXCLUDED.source_snapshot;

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

SELECT '45_v21_basics_merge' AS migration,
       count(*) FILTER (WHERE source_id IN ('home-basics-v2.1-20261119','home-variants-v2.1-20261119')) AS added_basics,
       count(*) FILTER (WHERE dish_id NOT LIKE '%-LS') AS total_nls
FROM core.dish WHERE NOT is_deleted;
