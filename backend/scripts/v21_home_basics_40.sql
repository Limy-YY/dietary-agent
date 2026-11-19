\set ON_ERROR_STOP on

-- V2.1 增量：40 道简单家常基础菜 + 4 条有权威来源的缺失食材。
-- 设计原则：
-- 1. 只新增，不修改 DISH-001..DISH-060 及其配料关系；
-- 2. 食材营养来自中国食物成分查询平台，缺失字段保持 NULL；
-- 3. 配料克数优先采用国家卫生健康委食谱，或复用现有同类菜的项目标准化量；
-- 4. 新食材的过敏原未被来源明确核实时保留“未核查”，不声称安全；
-- 5. 整个脚本在单一事务中执行，可重复运行，冲突时整体回滚。

BEGIN;
SELECT pg_advisory_xact_lock(hashtextextended('diet-agent:v21-home-basics-40:2026-11-19', 0));

DO $$
BEGIN
  IF current_database() <> 'diet_agent' THEN
    RAISE EXCEPTION '目标数据库错误：当前为 %，要求 diet_agent', current_database();
  END IF;
  IF to_regclass('core.dish') IS NULL
     OR to_regclass('core.dish_ingredient') IS NULL
     OR to_regclass('core.ingredient') IS NULL THEN
    RAISE EXCEPTION '目标表不存在，停止迁移';
  END IF;
END $$;

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
       OR i.allergens IS DISTINCT FROM n.allergens
       OR i.allergen_status IS DISTINCT FROM n.allergen_status
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
  ('DISH-061','白米饭','主食',ARRAY['基础家常菜','常见','简单','主食'],'蒸煮','CR004',0,0,30,'https://www.nhc.gov.cn/cms-search/downFiles/cbd48e38de3d4b8bb3e2093c9fbd43a5.pdf','卫健委示例食谱：大米50g；不额外加油盐'),
  ('DISH-062','白馒头','主食',ARRAY['基础家常菜','常见','简单','主食','早餐'],'直接食用','CR001',0,0,NULL,'https://nlc.chinanutri.cn/fq/foodinfo/272.html','按食物成分来源的100g可食部设为可缩放标准份'),
  ('DISH-063','原味切片面包','主食',ARRAY['基础家常菜','常见','简单','主食','早餐'],'直接食用','CR001',0,0,NULL,'https://www.nhc.gov.cn/cms-search/downFiles/cbd48e38de3d4b8bb3e2093c9fbd43a5.pdf','卫健委示例食谱：切片面包35g'),
  ('DISH-064','蒸玉米','主食',ARRAY['基础家常菜','常见','简单','主食','早餐'],'清蒸','CR002',0,0,20,'https://www.nhc.gov.cn/cms-search/downFiles/63f752a17cfd4b4781f744477561866f.pdf','卫健委示例食谱：玉米100g；不额外加油盐'),
  ('DISH-065','清汤面','主食',ARRAY['基础家常菜','常见','简单','主食'],'水煮','CR004',0,0,12,'https://www.nhc.gov.cn/cms-search/downFiles/4fcbecd2c18e46baaf291bf46c2b79cd.pdf','卫健委示例食谱：面条75g；本条仅记录面条，不加入未称量汤料'),
  ('DISH-066','原味米粉','主食',ARRAY['基础家常菜','常见','简单','主食'],'水煮','CR004',0,0,12,'https://www.nhc.gov.cn/sps/c100087/202604/a69d2fce21e040dc96cbc40b923a06d3/files/%E9%99%84%E4%BB%B65.%E6%88%90%E4%BA%BA%E8%82%8C%E5%B0%91%E7%97%87%E9%A3%9F%E5%85%BB%E6%8C%87%E5%8D%97%EF%BC%882026%E5%B9%B4%E7%89%88%EF%BC%89.pdf','卫健委示例食谱：干米粉50g；不加入未称量汤料'),
  ('DISH-067','水煮鸡蛋','蛋豆类',ARRAY['基础家常菜','常见','简单','早餐','蛋白质来源'],'水煮','CR004',0,0,10,'https://www.nhc.gov.cn/cms-search/downFiles/cbd48e38de3d4b8bb3e2093c9fbd43a5.pdf','卫健委示例食谱：鸡蛋50g'),
  ('DISH-068','无糖豆浆','饮品',ARRAY['基础家常菜','常见','简单','早餐','豆类饮品'],'煮透后饮用','CR001',0,0,NULL,'https://www.nhc.gov.cn/sps/c100087/202404/90c64c79708740a1bca0ee31e524caf7.shtml','卫健委等量交换：豆浆约300g；不额外加糖'),
  ('DISH-069','纯牛奶','饮品',ARRAY['基础家常菜','常见','简单','早餐','奶类'],'直接饮用','CR001',0,0,NULL,'https://www.nhc.gov.cn/wjw/c100175/202005/7757e4f72e13402a97b42f785d7a335a.shtml','卫健委建议：液体奶300g；不按含乳饮料处理'),
  ('DISH-070','原味酸奶','饮品',ARRAY['基础家常菜','常见','简单','早餐','奶类'],'直接食用','CR001',0,0,NULL,'https://www.nhc.gov.cn/sps/c100087/202604/a69d2fce21e040dc96cbc40b923a06d3/files/%E9%99%84%E4%BB%B65.%E6%88%90%E4%BA%BA%E8%82%8C%E5%B0%91%E7%97%87%E9%A3%9F%E5%85%BB%E6%8C%87%E5%8D%97%EF%BC%882026%E5%B9%B4%E7%89%88%EF%BC%89.pdf','卫健委示例食谱：酸奶100g'),
  ('DISH-071','苹果','水果',ARRAY['基础家常菜','常见','简单','水果','即食'],'洗净直接食用','CR001',0,0,NULL,'https://www.nhc.gov.cn/wjw/c100378/202301/7faed9993c9b45aea158c5335346f282/files/1732844468018_41219.pdf','卫健委示例食谱：苹果200g'),
  ('DISH-072','香蕉','水果',ARRAY['基础家常菜','常见','简单','水果','即食'],'去皮直接食用','CR001',0,0,NULL,'https://www.nhc.gov.cn/cms-search/downFiles/63f752a17cfd4b4781f744477561866f.pdf','卫健委示例食谱：香蕉200g'),
  ('DISH-073','橙子','水果',ARRAY['基础家常菜','常见','简单','水果','即食'],'去皮直接食用','CR001',0,0,NULL,'https://www.nhc.gov.cn/sps/c100087/202604/a69d2fce21e040dc96cbc40b923a06d3/files/%E9%99%84%E4%BB%B65.%E6%88%90%E4%BA%BA%E8%82%8C%E5%B0%91%E7%97%87%E9%A3%9F%E5%85%BB%E6%8C%87%E5%8D%97%EF%BC%882026%E5%B9%B4%E7%89%88%EF%BC%89.pdf','卫健委示例食谱：橙子200g'),
  ('DISH-074','梨','水果',ARRAY['基础家常菜','常见','简单','水果','即食'],'洗净直接食用','CR001',0,0,NULL,'https://www.nhc.gov.cn/sps/c100087/202604/a69d2fce21e040dc96cbc40b923a06d3/files/%E9%99%84%E4%BB%B65.%E6%88%90%E4%BA%BA%E8%82%8C%E5%B0%91%E7%97%87%E9%A3%9F%E5%85%BB%E6%8C%87%E5%8D%97%EF%BC%882026%E5%B9%B4%E7%89%88%EF%BC%89.pdf','卫健委示例食谱：梨200g'),
  ('DISH-075','葡萄','水果',ARRAY['基础家常菜','常见','简单','水果','即食'],'洗净直接食用','CR001',0,0,NULL,'https://www.nhc.gov.cn/cms-search/downFiles/63f752a17cfd4b4781f744477561866f.pdf','卫健委示例食谱：葡萄200g'),
  ('DISH-076','西瓜','水果',ARRAY['基础家常菜','常见','简单','水果','即食'],'切块直接食用','CR001',0,0,NULL,'https://www.nhc.gov.cn/xcs/cbcl/201706/d7d8ff3889be445b8bfb86a5efea952f.shtml','按每日水果200至350g建议取200g可食部'),
  ('DISH-077','桃','水果',ARRAY['基础家常菜','常见','简单','水果','即食'],'洗净直接食用','CR001',0,0,NULL,'https://www.nhc.gov.cn/xcs/cbcl/201706/d7d8ff3889be445b8bfb86a5efea952f.shtml','按每日水果200至350g建议取200g可食部'),
  ('DISH-078','猕猴桃','水果',ARRAY['基础家常菜','常见','简单','水果','即食'],'去皮直接食用','CR001',0,0,NULL,'https://www.nhc.gov.cn/cms-search/downFiles/4fcbecd2c18e46baaf291bf46c2b79cd.pdf','卫健委示例食谱：猕猴桃100g'),
  ('DISH-079','卤鸡腿','畜禽肉类',ARRAY['基础家常菜','常见','简单','蛋白质来源','酱卤'],'少盐酱卤','CR016',0,0,35,'https://nlc.chinanutri.cn/fq/foodinfo/882.html','鸡腿按100g可食部标准份；姜和酱油各5g复用现有菜库称量口径；不额外加油盐糖'),
  ('DISH-080','白切鸡腿','畜禽肉类',ARRAY['基础家常菜','常见','简单','蛋白质来源'],'水煮','CR004',0,0,25,'https://nlc.chinanutri.cn/fq/foodinfo/882.html','鸡腿按100g可食部标准份；姜5g复用现有菜库称量口径；不额外加盐'),
  ('DISH-081','清蒸豆腐','蛋豆类',ARRAY['基础家常菜','常见','简单','蛋白质来源'],'清蒸','CR002',0,0.6,12,'https://nlc.chinanutri.cn/fq/foodinfo/333.html','豆腐按100g可食部标准份；盐0.6g复用现有清蒸菜口径'),
  ('DISH-082','白灼虾仁','水产类',ARRAY['基础家常菜','常见','简单','蛋白质来源'],'白灼','CR003',0,0.6,8,'https://nlc.chinanutri.cn/fq/foodinfo/1091.html','海虾100g可食部；盐0.6g复用现有白灼规则口径'),
  ('DISH-083','清蒸带鱼','水产类',ARRAY['基础家常菜','常见','简单','蛋白质来源'],'清蒸','CR002',0,0.6,15,'https://www.nhc.gov.cn/sps/c100088/202301/f01895a06c5349ef999f25da833c166d/files/1732844468278_20318.pdf','卫健委示例食谱：带鱼100g；姜5g、盐0.6g复用现有清蒸鱼口径'),
  ('DISH-084','清炖鲤鱼','水产类',ARRAY['基础家常菜','常见','简单','蛋白质来源'],'清炖','CR006',0,0.8,30,'https://www.nhc.gov.cn/cms-search/downFiles/63f752a17cfd4b4781f744477561866f.pdf','卫健委示例食谱：鲤鱼100g；姜5g、盐0.8g复用现有清炖菜口径'),
  ('DISH-085','清蒸鸡蛋羹','蛋豆类',ARRAY['基础家常菜','常见','简单','早餐','蛋白质来源'],'清蒸','CR002',0,0.6,12,'https://www.nhc.gov.cn/cms-search/downFiles/cbd48e38de3d4b8bb3e2093c9fbd43a5.pdf','鸡蛋50g采用卫健委早餐份量；盐0.6g复用现有清蒸规则口径'),
  ('DISH-086','盐水菜心','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'白灼','CR003',0,0.6,8,'https://nlc.chinanutri.cn/fq/foodinfo/453.html','菜心按100g可食部标准份；盐0.6g采用白灼规则默认口径'),
  ('DISH-087','白灼生菜','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'白灼','CR003',0,0.6,5,'https://www.nhc.gov.cn/cms-search/downFiles/4fcbecd2c18e46baaf291bf46c2b79cd.pdf','卫健委示例食谱：白灼生菜100g；盐0.6g采用白灼规则默认口径'),
  ('DISH-088','清炒生菜','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'快炒','CR009',4,0.8,6,'https://www.nhc.gov.cn/wjw/c100378/202301/7faed9993c9b45aea158c5335346f282/files/1732844468018_41219.pdf','卫健委炒时蔬：生菜200g；油4g盐0.8g复用现有清炒蔬菜口径'),
  ('DISH-089','蒜炒空心菜','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'快炒','CR009',4,0.8,7,'https://www.nhc.gov.cn/cms-search/downFiles/4fcbecd2c18e46baaf291bf46c2b79cd.pdf','卫健委示例食谱：空心菜100g；蒜5g、油4g盐0.8g复用现有清炒蔬菜口径'),
  ('DISH-090','清炒丝瓜','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'快炒','CR009',4,0.8,7,'https://www.nhc.gov.cn/cms-search/downFiles/4fcbecd2c18e46baaf291bf46c2b79cd.pdf','卫健委示例食谱：丝瓜150g；油4g盐0.8g复用现有清炒蔬菜口径'),
  ('DISH-091','白灼西兰花','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'白灼','CR003',0,0.6,7,'https://www.nhc.gov.cn/cms-search/downFiles/63f752a17cfd4b4781f744477561866f.pdf','卫健委示例食谱含西兰花100g；盐0.6g采用白灼规则默认口径'),
  ('DISH-092','盐水小白菜','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'白灼','CR003',0,0.6,6,'https://www.nhc.gov.cn/cms-search/downFiles/cbd48e38de3d4b8bb3e2093c9fbd43a5.pdf','卫健委水煮叶菜示例100g；盐0.6g采用白灼规则默认口径'),
  ('DISH-093','清炒大白菜','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'快炒','CR009',4,0.8,7,'https://www.nhc.gov.cn/cms-search/downFiles/cbd48e38de3d4b8bb3e2093c9fbd43a5.pdf','卫健委示例食谱：炒圆白菜80g；油4g盐0.8g复用现有清炒蔬菜口径'),
  ('DISH-094','清炒油菜','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'快炒','CR009',4,0.8,7,'https://www.nhc.gov.cn/sps/c100087/202604/a69d2fce21e040dc96cbc40b923a06d3/files/%E9%99%84%E4%BB%B65.%E6%88%90%E4%BA%BA%E8%82%8C%E5%B0%91%E7%97%87%E9%A3%9F%E5%85%BB%E6%8C%87%E5%8D%97%EF%BC%882026%E5%B9%B4%E7%89%88%EF%BC%89.pdf','卫健委示例食谱：油菜150g；油4g盐0.8g复用现有清炒蔬菜口径'),
  ('DISH-095','清炒菜心','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'快炒','CR009',4,0.8,7,'https://www.nhc.gov.cn/sps/c100087/202604/a69d2fce21e040dc96cbc40b923a06d3/files/%E9%99%84%E4%BB%B65.%E6%88%90%E4%BA%BA%E8%82%8C%E5%B0%91%E7%97%87%E9%A3%9F%E5%85%BB%E6%8C%87%E5%8D%97%EF%BC%882026%E5%B9%B4%E7%89%88%EF%BC%89.pdf','卫健委示例食谱：清炒菜薹150g；油4g盐0.8g复用现有清炒蔬菜口径'),
  ('DISH-096','清炒茼蒿','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'快炒','CR009',4,0.8,7,'https://www.nhc.gov.cn/sps/c100088/202301/f01895a06c5349ef999f25da833c166d/files/1732844468278_20318.pdf','卫健委示例食谱：炒茼蒿150g；油4g盐0.8g复用现有清炒蔬菜口径'),
  ('DISH-097','清炒苋菜','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'快炒','CR009',4,0.8,7,'https://www.nhc.gov.cn/sps/c100087/202604/a69d2fce21e040dc96cbc40b923a06d3/files/%E9%99%84%E4%BB%B65.%E6%88%90%E4%BA%BA%E8%82%8C%E5%B0%91%E7%97%87%E9%A3%9F%E5%85%BB%E6%8C%87%E5%8D%97%EF%BC%882026%E5%B9%B4%E7%89%88%EF%BC%89.pdf','卫健委示例食谱：米苋菜150g；油4g盐0.8g复用现有清炒蔬菜口径'),
  ('DISH-098','清炒西葫芦','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'快炒','CR009',4,0.8,7,'https://www.nhc.gov.cn/wjw/c100378/202301/7faed9993c9b45aea158c5335346f282/files/1732844468018_41219.pdf','卫健委炒时蔬：西葫芦200g；油4g盐0.8g复用现有清炒蔬菜口径'),
  ('DISH-099','蒸茄子','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'清蒸','CR002',0,0.6,12,'https://www.nhc.gov.cn/cms-search/downFiles/63f752a17cfd4b4781f744477561866f.pdf','卫健委示例食谱：茄子100g；盐0.6g采用清蒸规则默认口径'),
  ('DISH-100','白灼菜花','蔬菜类',ARRAY['基础家常菜','常见','简单','蔬菜'],'白灼','CR003',0,0.6,7,'https://nlc.chinanutri.cn/fq/foodinfo/464.html','菜花按100g可食部标准份；盐0.6g采用白灼规则默认口径');

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
WHERE NOT EXISTS (SELECT 1 FROM core.dish d WHERE d.dish_id = n.dish_id);

CREATE TEMP TABLE _v21_dish_ingredient (
  dish_id text NOT NULL,
  food_id text NOT NULL,
  amount_g numeric NOT NULL,
  role text NOT NULL,
  generated_from text NOT NULL DEFAULT 'v21_home_basics_20261119',
  PRIMARY KEY (dish_id, food_id, role, generated_from)
) ON COMMIT DROP;

INSERT INTO _v21_dish_ingredient (dish_id, food_id, amount_g, role) VALUES
  ('DISH-061','CN-280',50,'主料'),
  ('DISH-062','CN-272',100,'主料'),
  ('DISH-063','CN-1316',35,'主料'),
  ('DISH-064','CN-292',100,'主料'),
  ('DISH-065','CN-264',75,'主料'),
  ('DISH-066','CN-289',50,'主料'),
  ('DISH-067','CN-978',50,'主料'),
  ('DISH-068','CN-338',300,'主料'),
  ('DISH-069','CN-916',300,'主料'),
  ('DISH-070','CN-958',100,'主料'),
  ('DISH-071','CN-613',200,'主料'),
  ('DISH-072','CN-726',200,'主料'),
  ('DISH-073','CN-704',200,'主料'),
  ('DISH-074','CN-630',200,'主料'),
  ('DISH-075','CN-684',200,'主料'),
  ('DISH-076','CN-739',200,'主料'),
  ('DISH-077','CN-660',200,'主料'),
  ('DISH-078','CN-700',100,'主料'),
  ('DISH-079','CN-882',100,'主料'),('DISH-079','CN-528',5,'调味辅料'),('DISH-079','CN-1518',5,'调味料'),
  ('DISH-080','CN-882',100,'主料'),('DISH-080','CN-528',5,'调味辅料'),
  ('DISH-081','CN-333',100,'主料'),('DISH-081','CN-1565',0.6,'食盐'),
  ('DISH-082','CN-1091',100,'主料'),('DISH-082','CN-1565',0.6,'食盐'),
  ('DISH-083','CN-1030',100,'主料'),('DISH-083','CN-528',5,'调味辅料'),('DISH-083','CN-1565',0.6,'食盐'),
  ('DISH-084','CN-1012',100,'主料'),('DISH-084','CN-528',5,'调味辅料'),('DISH-084','CN-1565',0.8,'食盐'),
  ('DISH-085','CN-978',50,'主料'),('DISH-085','CN-1565',0.6,'食盐'),
  ('DISH-086','CN-453',100,'主料'),('DISH-086','CN-1565',0.6,'食盐'),
  ('DISH-087','CN-483',100,'主料'),('DISH-087','CN-1565',0.6,'食盐'),
  ('DISH-088','CN-483',200,'主料'),('DISH-088','CN-1510',4,'烹调油'),('DISH-088','CN-1565',0.8,'食盐'),
  ('DISH-089','CN-493',100,'主料'),('DISH-089','CN-436',5,'调味辅料'),('DISH-089','CN-1510',4,'烹调油'),('DISH-089','CN-1565',0.8,'食盐'),
  ('DISH-090','CN-429',150,'主料'),('DISH-090','CN-1510',4,'烹调油'),('DISH-090','CN-1565',0.8,'食盐'),
  ('DISH-091','CN-465',100,'主料'),('DISH-091','CN-1565',0.6,'食盐'),
  ('DISH-092','CN-452',100,'主料'),('DISH-092','CN-1565',0.6,'食盐'),
  ('DISH-093','CN-450',80,'主料'),('DISH-093','CN-1510',4,'烹调油'),('DISH-093','CN-1565',0.8,'食盐'),
  ('DISH-094','CN-457',150,'主料'),('DISH-094','CN-1510',4,'烹调油'),('DISH-094','CN-1565',0.8,'食盐'),
  ('DISH-095','CN-453',150,'主料'),('DISH-095','CN-1510',4,'烹调油'),('DISH-095','CN-1565',0.8,'食盐'),
  ('DISH-096','CN-488',150,'主料'),('DISH-096','CN-1510',4,'烹调油'),('DISH-096','CN-1565',0.8,'食盐'),
  ('DISH-097','CN-486',150,'主料'),('DISH-097','CN-1510',4,'烹调油'),('DISH-097','CN-1565',0.8,'食盐'),
  ('DISH-098','CN-431',200,'主料'),('DISH-098','CN-1510',4,'烹调油'),('DISH-098','CN-1565',0.8,'食盐'),
  ('DISH-099','CN-402',100,'主料'),('DISH-099','CN-1565',0.6,'食盐'),
  ('DISH-100','CN-464',100,'主料'),('DISH-100','CN-1565',0.6,'食盐');

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
      AND (di.amount_g IS DISTINCT FROM x.amount_g OR di.role IS DISTINCT FROM x.role)
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
WHERE NOT EXISTS (
  SELECT 1 FROM core.dish_ingredient di
  WHERE di.dish_id = x.dish_id AND di.ingredient_id = i.ingredient_id
    AND di.role = x.role AND di.generated_from = x.generated_from
);

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

COMMIT;

SELECT 'v21_home_basics_40' AS migration,
       count(*) FILTER (WHERE source_id='home-basics-v2.1-20261119') AS added_dishes,
       count(*) FILTER (WHERE dish_id BETWEEN 'DISH-001' AND 'DISH-060') AS preserved_original_dishes
FROM core.dish WHERE NOT is_deleted;
