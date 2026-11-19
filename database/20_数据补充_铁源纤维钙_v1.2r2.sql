-- v1.2r2：同步铁参考单行口径，并补齐60道菜计算所需的纤维、钙数据
-- 生成日期：2026-11-15；原始备份不变，本脚本可在其副本上执行。
BEGIN;

-- 1. 铁：女性50-64岁由两行并为通用单行12mg。
DO $$
DECLARE
    v_keep_id bigint;
    v_rows integer;
BEGIN
    SELECT nutrient_reference_id INTO v_keep_id
      FROM core.nutrient_reference
     WHERE nutrient_id = 'iron' AND sex = 'female' AND age_group = '50-64' AND life_stage = '普通'
     ORDER BY CASE WHEN menstrual_status = '有月经' THEN 0 ELSE 1 END, value DESC
     LIMIT 1;

    IF v_keep_id IS NULL THEN
        RAISE EXCEPTION '未找到铁·女性50-64岁参考行';
    END IF;

    DELETE FROM core.nutrient_reference
     WHERE nutrient_id = 'iron' AND sex = 'female' AND age_group = '50-64' AND life_stage = '普通'
       AND nutrient_reference_id <> v_keep_id;

    UPDATE core.nutrient_reference
       SET menstrual_status = '',
           value = 12,
           note = '女性50-64岁并回单行取12mg；原无月经10mg、有月经12mg。当前档案不采月经状态，为避免重复追问取保守侧。',
           source_row = source_row || jsonb_build_object(
               'review_decision', 'R2-merge-50-64-female-iron',
               'merged_from', jsonb_build_array(
                   jsonb_build_object('menstrual_status', '无月经', 'value', 10),
                   jsonb_build_object('menstrual_status', '有月经', 'value', 12)
               )
           )
     WHERE nutrient_reference_id = v_keep_id;

    SELECT count(*) INTO v_rows
      FROM core.nutrient_reference
     WHERE nutrient_id = 'iron' AND sex = 'female' AND age_group = '50-64' AND life_stage = '普通';
    IF v_rows <> 1 THEN
        RAISE EXCEPTION '铁·女性50-64岁应只保留1行，实际为%行', v_rows;
    END IF;
END $$;

UPDATE core.nutrient
   SET description = '男12、女18(18-49)；女50-64岁并回单行取12；女65岁后10；孕18/25/29、乳24。儿童0.3→16递增；12-14/15-17岁男16/女18。'
 WHERE nutrient_id = 'iron';

-- 2. 食材：只补原来为空的纤维或钙；不覆盖已有数值。
-- CN-1050: USDA SR28 NDB 15091（SEA BASS,MXD SP,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 0.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 0.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 15091（SEA BASS,MXD SP,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-1050' AND (fiber_g IS NULL);

-- CN-1052: USDA SR28 NDB 15236（SALMON,ATLANTIC,FARMED,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 0.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 0.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 15236（SALMON,ATLANTIC,FARMED,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-1052' AND (fiber_g IS NULL);

-- CN-1062: USDA SR28 NDB 15015（COD,ATLANTIC,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 0.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 0.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 15015（COD,ATLANTIC,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-1062' AND (fiber_g IS NULL);

-- CN-1091: USDA SR28 NDB 15149（CRUSTACEANS,SHRIMP,MXD SP,RAW (MAYBE PREVIOUSLY FROZEN)）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 0.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 0.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 15149（CRUSTACEANS,SHRIMP,MXD SP,RAW (MAYBE PREVIOUSLY FROZEN)）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-1091' AND (fiber_g IS NULL);

-- CN-1120: USDA SR28 NDB 15157（CLAM,MIXED SPECIES,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 0.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 0.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 15157（CLAM,MIXED SPECIES,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-1120' AND (fiber_g IS NULL);

-- CN-1274: USDA SR28 NDB 08120（CEREALS,OATS,REG & QUICK,NOT FORT,DRY）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 10.1),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 10.1, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 08120（CEREALS,OATS,REG & QUICK,NOT FORT,DRY）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-1274' AND (fiber_g IS NULL);

-- CN-1506: USDA FoodData Central FDC 2710182（Coconut oil）
UPDATE core.ingredient
   SET calcium_mg = COALESCE(calcium_mg, 1),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('calcium_mg', jsonb_build_object('value', 1, 'unit', 'mg/100g', 'source', 'USDA FoodData Central FDC 2710182（Coconut oil）', 'source_url', 'https://fdc.nal.usda.gov/fdc-app.html#/food-details/2710182/nutrients', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-1506' AND (calcium_mg IS NULL);

-- CN-1510: USDA SR28 NDB 04053（OIL,OLIVE,SALAD OR COOKING）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 0.0),
       calcium_mg = COALESCE(calcium_mg, 1.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 0.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 04053（OIL,OLIVE,SALAD OR COOKING）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'), 'calcium_mg', jsonb_build_object('value', 1.0, 'unit', 'mg/100g', 'source', 'USDA SR28 NDB 04053（OIL,OLIVE,SALAD OR COOKING）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-1510' AND (fiber_g IS NULL OR calcium_mg IS NULL);

-- CN-1520: USDA SR28 NDB 02053（VINEGAR,DISTILLED）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 0.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 0.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 02053（VINEGAR,DISTILLED）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-1520' AND (fiber_g IS NULL);

-- CN-1565: USDA SR28 NDB 02047（SALT,TABLE）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 0.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 0.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 02047（SALT,TABLE）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-1565' AND (fiber_g IS NULL);

-- CN-259: USDA SR28 NDB 20481（WHEAT FLR,WHITE,ALL-PURPOSE,UNENR）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 2.7),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 2.7, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 20481（WHEAT FLR,WHITE,ALL-PURPOSE,UNENR）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-259' AND (fiber_g IS NULL);

-- CN-280: USDA SR28 NDB 20044（RICE,WHITE,LONG-GRAIN,REG,RAW,ENR）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 1.3),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 1.3, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 20044（RICE,WHITE,LONG-GRAIN,REG,RAW,ENR）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-280' AND (fiber_g IS NULL);

-- CN-292: USDA SR28 NDB 11900（CORN,SWEET,WHITE,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 2.7),
       calcium_mg = COALESCE(calcium_mg, 2.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 2.7, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11900（CORN,SWEET,WHITE,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'), 'calcium_mg', jsonb_build_object('value', 2.0, 'unit', 'mg/100g', 'source', 'USDA SR28 NDB 11900（CORN,SWEET,WHITE,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-292' AND (fiber_g IS NULL OR calcium_mg IS NULL);

-- CN-301: USDA SR28 NDB 20031（MILLET,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 8.5),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 8.5, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 20031（MILLET,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-301' AND (fiber_g IS NULL);

-- CN-313: USDA SR28 NDB 11352（POTATOES,FLESH & SKN,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 2.1),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 2.1, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11352（POTATOES,FLESH & SKN,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-313' AND (fiber_g IS NULL);

-- CN-316: USDA SR28 NDB 11507（SWEET POTATO,RAW,UNPREP）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 3.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 3.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11507（SWEET POTATO,RAW,UNPREP）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-316' AND (fiber_g IS NULL);

-- CN-333: USDA SR28 NDB 16126（TOFU,FIRM,PREP W/CA SULFATE&MAGNESIUM CHLORIDE (NIGARI)）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 0.9),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 0.9, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 16126（TOFU,FIRM,PREP W/CA SULFATE&MAGNESIUM CHLORIDE (NIGARI)）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-333' AND (fiber_g IS NULL);

-- CN-371: USDA SR28 NDB 11430（RADISHES,ORIENTAL,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 1.6),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 1.6, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11430（RADISHES,ORIENTAL,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-371' AND (fiber_g IS NULL);

-- CN-380: USDA SR28 NDB 11124（CARROTS,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 2.8),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 2.8, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11124（CARROTS,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-380' AND (fiber_g IS NULL);

-- CN-392: USDA SR28 NDB 11052（BEANS,SNAP,GREEN,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 2.7),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 2.7, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11052（BEANS,SNAP,GREEN,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-392' AND (fiber_g IS NULL);

-- CN-400: USDA SR28 NDB 11043（MUNG BNS,MATURE SEEDS,SPROUTED,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 1.8),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 1.8, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11043（MUNG BNS,MATURE SEEDS,SPROUTED,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-400' AND (fiber_g IS NULL);

-- CN-402: USDA SR28 NDB 11209（EGGPLANT,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 3.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 3.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11209（EGGPLANT,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-402' AND (fiber_g IS NULL);

-- CN-405: USDA SR28 NDB 11529（TOMATOES,RED,RIPE,RAW,YEAR RND AVERAGE）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 1.2),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 1.2, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11529（TOMATOES,RED,RIPE,RAW,YEAR RND AVERAGE）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-405' AND (fiber_g IS NULL);

-- CN-410: USDA SR28 NDB 11951（PEPPERS,SWEET,YELLOW,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 0.9),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 0.9, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11951（PEPPERS,SWEET,YELLOW,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-410' AND (fiber_g IS NULL);

-- CN-419: USDA SR28 NDB 11593（WAXGOURD,(CHINESE PRESERVING MELON),RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 2.9),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 2.9, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11593（WAXGOURD,(CHINESE PRESERVING MELON),RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-419' AND (fiber_g IS NULL);

-- CN-422: USDA SR28 NDB 11205（CUCUMBER,WITH PEEL,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 0.5),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 0.5, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11205（CUCUMBER,WITH PEEL,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-422' AND (fiber_g IS NULL);

-- CN-425: USDA SR28 NDB 11024（BALSAM-PEAR (BITTER GOURD),PODS,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 2.8),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 2.8, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11024（BALSAM-PEAR (BITTER GOURD),PODS,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-425' AND (fiber_g IS NULL);

-- CN-426: USDA SR28 NDB 11422（PUMPKIN,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 0.5),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 0.5, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11422（PUMPKIN,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-426' AND (fiber_g IS NULL);

-- CN-431: USDA SR28 NDB 11477（SQUASH,SMMR,ZUCCHINI,INCL SKN,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 1.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 1.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11477（SQUASH,SMMR,ZUCCHINI,INCL SKN,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-431' AND (fiber_g IS NULL);

-- CN-436: USDA SR28 NDB 11215（GARLIC,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 2.1),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 2.1, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11215（GARLIC,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-436' AND (fiber_g IS NULL);

-- CN-441: USDA SR28 NDB 11291（ONIONS,SPRING OR SCALLIONS (INCL TOPS&BULB),RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 2.6),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 2.6, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11291（ONIONS,SPRING OR SCALLIONS (INCL TOPS&BULB),RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-441' AND (fiber_g IS NULL);

-- CN-444: USDA SR28 NDB 11282（ONIONS,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 1.7),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 1.7, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11282（ONIONS,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-444' AND (fiber_g IS NULL);

-- CN-445: USDA SR28 NDB 11156（CHIVES,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 2.5),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 2.5, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11156（CHIVES,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-445' AND (fiber_g IS NULL);

-- CN-450: USDA SR28 NDB 11119（CABBAGE,CHINESE (PE-TSAI),RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 1.2),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 1.2, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11119（CABBAGE,CHINESE (PE-TSAI),RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-450' AND (fiber_g IS NULL);

-- CN-452: USDA SR28 NDB 11116（CABBAGE,CHINESE (PAK-CHOI),RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 1.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 1.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11116（CABBAGE,CHINESE (PAK-CHOI),RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-452' AND (fiber_g IS NULL);

-- CN-457: USDA SR28 NDB 11116（CABBAGE,CHINESE (PAK-CHOI),RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 1.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 1.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11116（CABBAGE,CHINESE (PAK-CHOI),RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-457' AND (fiber_g IS NULL);

-- CN-464: USDA SR28 NDB 11135（CAULIFLOWER,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 2.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 2.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11135（CAULIFLOWER,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-464' AND (fiber_g IS NULL);

-- CN-465: USDA SR28 NDB 11090（BROCCOLI,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 2.6),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 2.6, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11090（BROCCOLI,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-465' AND (fiber_g IS NULL);

-- CN-473: USDA SR28 NDB 11457（SPINACH,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 2.2),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 2.2, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11457（SPINACH,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-473' AND (fiber_g IS NULL);

-- CN-479: USDA SR28 NDB 11143（CELERY,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 1.6),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 1.6, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11143（CELERY,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-479' AND (fiber_g IS NULL);

-- CN-525: USDA SR28 NDB 11601（YAM,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 4.1),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 4.1, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11601（YAM,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-525' AND (fiber_g IS NULL);

-- CN-528: USDA SR28 NDB 11216（GINGER ROOT,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 2.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 2.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11216（GINGER ROOT,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-528' AND (fiber_g IS NULL);

-- CN-575: USDA SR28 NDB 11950（MUSHROOMS,ENOKI,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 2.7),
       calcium_mg = COALESCE(calcium_mg, 0.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 2.7, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11950（MUSHROOMS,ENOKI,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'), 'calcium_mg', jsonb_build_object('value', 0.0, 'unit', 'mg/100g', 'source', 'USDA SR28 NDB 11950（MUSHROOMS,ENOKI,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-575' AND (fiber_g IS NULL OR calcium_mg IS NULL);

-- CN-577: USDA SR28 NDB 11260（MUSHROOMS,WHITE,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 1.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 1.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11260（MUSHROOMS,WHITE,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-577' AND (fiber_g IS NULL);

-- CN-584: USDA SR28 NDB 11238（MUSHROOMS,SHIITAKE,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 2.5),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 2.5, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11238（MUSHROOMS,SHIITAKE,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-584' AND (fiber_g IS NULL);

-- CN-605: USDA SR28 NDB 11445（SEAWEED,KELP,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 1.3),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 1.3, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 11445（SEAWEED,KELP,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-605' AND (fiber_g IS NULL);

-- CN-611: USDA FoodData Central FDC 2709988（Seaweed, dried）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 5.6),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 5.6, 'unit', 'g/100g', 'source', 'USDA FoodData Central FDC 2709988（Seaweed, dried）', 'source_url', 'https://fdc.nal.usda.gov/fdc-app.html#/food-details/2709988/nutrients', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-611' AND (fiber_g IS NULL);

-- CN-726: USDA SR28 NDB 09040（BANANAS,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 2.6),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 2.6, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 09040（BANANAS,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-726' AND (fiber_g IS NULL);

-- CN-763: USDA SR28 NDB 16087（PEANUTS,ALL TYPES,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 8.5),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 8.5, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 16087（PEANUTS,ALL TYPES,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-763' AND (fiber_g IS NULL);

-- CN-784: USDA SR28 NDB 10218（PORK,FRSH,LOIN,TENDERLOIN,LN&FAT,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 0.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 0.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 10218（PORK,FRSH,LOIN,TENDERLOIN,LN&FAT,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-784' AND (fiber_g IS NULL);

-- CN-794: USDA SR28 NDB 10088（PORK,FRSH,SPARERIBS,LN&FAT,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 0.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 0.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 10088（PORK,FRSH,SPARERIBS,LN&FAT,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-794' AND (fiber_g IS NULL);

-- CN-830: USDA SR28 NDB 13047（BEEF,GRASS-FED,GROUND,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 0.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 0.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 13047（BEEF,GRASS-FED,GROUND,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-830' AND (fiber_g IS NULL);

-- CN-880: USDA SR28 NDB 05057（CHICKEN,BROILERS OR FRYERS,BREAST,MEAT&SKN,RAW）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 0.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 0.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 05057（CHICKEN,BROILERS OR FRYERS,BREAST,MEAT&SKN,RAW）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-880' AND (fiber_g IS NULL);

-- CN-958: USDA SR28 NDB 01116（YOGURT,PLN,WHL MILK,8 GRAMS PROT PER 8 OZ）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 0.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 0.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 01116（YOGURT,PLN,WHL MILK,8 GRAMS PROT PER 8 OZ）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-958' AND (fiber_g IS NULL);

-- CN-978: USDA SR28 NDB 01123（EGG,WHL,RAW,FRSH）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 0.0),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 0.0, 'unit', 'g/100g', 'source', 'USDA SR28 NDB 01123（EGG,WHL,RAW,FRSH）', 'source_url', 'https://fdc.nal.usda.gov/download-datasets/', 'data_quality', 'approx'))),
       updated_at = now()
 WHERE food_id = 'CN-978' AND (fiber_g IS NULL);

-- FDC-169704: USDA FoodData Central FDC 169704（Rice, brown, long-grain, cooked）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 1.6),
       calcium_mg = COALESCE(calcium_mg, 3),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 1.6, 'unit', 'g/100g', 'source', 'USDA FoodData Central FDC 169704（Rice, brown, long-grain, cooked）', 'source_url', 'https://fdc.nal.usda.gov/fdc-app.html#/food-details/169704/nutrients', 'data_quality', 'official'), 'calcium_mg', jsonb_build_object('value', 3, 'unit', 'mg/100g', 'source', 'USDA FoodData Central FDC 169704（Rice, brown, long-grain, cooked）', 'source_url', 'https://fdc.nal.usda.gov/fdc-app.html#/food-details/169704/nutrients', 'data_quality', 'official'))),
       updated_at = now()
 WHERE food_id = 'FDC-169704' AND (fiber_g IS NULL OR calcium_mg IS NULL);

-- FDC-170420: USDA FoodData Central FDC 170420（Peas, green, cooked, boiled, drained, without salt）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 5.5),
       calcium_mg = COALESCE(calcium_mg, 27),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 5.5, 'unit', 'g/100g', 'source', 'USDA FoodData Central FDC 170420（Peas, green, cooked, boiled, drained, without salt）', 'source_url', 'https://fdc.nal.usda.gov/fdc-app.html#/food-details/170420/nutrients', 'data_quality', 'official'), 'calcium_mg', jsonb_build_object('value', 27, 'unit', 'mg/100g', 'source', 'USDA FoodData Central FDC 170420（Peas, green, cooked, boiled, drained, without salt）', 'source_url', 'https://fdc.nal.usda.gov/fdc-app.html#/food-details/170420/nutrients', 'data_quality', 'official'))),
       updated_at = now()
 WHERE food_id = 'FDC-170420' AND (fiber_g IS NULL OR calcium_mg IS NULL);

-- FDC-173757: USDA FoodData Central FDC 173757（Chickpeas, mature seeds, cooked, boiled, without salt）
UPDATE core.ingredient
   SET fiber_g = COALESCE(fiber_g, 7.6),
       calcium_mg = COALESCE(calcium_mg, 49),
       source_row = source_row || jsonb_build_object('supplemental_nutrients', COALESCE(source_row->'supplemental_nutrients', '{}'::jsonb) || jsonb_build_object('fiber_g', jsonb_build_object('value', 7.6, 'unit', 'g/100g', 'source', 'USDA FoodData Central FDC 173757（Chickpeas, mature seeds, cooked, boiled, without salt）', 'source_url', 'https://fdc.nal.usda.gov/fdc-app.html#/food-details/173757/nutrients', 'data_quality', 'official'), 'calcium_mg', jsonb_build_object('value', 49, 'unit', 'mg/100g', 'source', 'USDA FoodData Central FDC 173757（Chickpeas, mature seeds, cooked, boiled, without salt）', 'source_url', 'https://fdc.nal.usda.gov/fdc-app.html#/food-details/173757/nutrients', 'data_quality', 'official'))),
       updated_at = now()
 WHERE food_id = 'FDC-173757' AND (fiber_g IS NULL OR calcium_mg IS NULL);

-- 3. 同步一级质量标记。57 种食材都补了估算纤维，因此整行采用保守的 approx 标记；
--    各营养素的详细来源和质量仍保留在 source_row.supplemental_nutrients 中。
UPDATE core.ingredient
   SET data_quality = 'approx',
       updated_at = now()
 WHERE source_row ? 'supplemental_nutrients'
   AND (source_row->'supplemental_nutrients' ? 'fiber_g'
        OR source_row->'supplemental_nutrients' ? 'calcium_mg');

-- 4. 按配料克数重算60道菜的纤维和钙，保存在 nutrition_snapshot。
WITH totals AS (
    SELECT di.dish_id,
           round(sum(di.amount_g * i.fiber_g / 100.0), 1) AS dish_fiber_g,
           round(sum(di.amount_g * i.calcium_mg / 100.0), 1) AS dish_calcium_mg,
           count(*) AS ingredient_count
      FROM core.dish_ingredient di
      JOIN core.ingredient i ON i.ingredient_id = di.ingredient_id
     GROUP BY di.dish_id
    HAVING count(*) = count(i.fiber_g) AND count(*) = count(i.calcium_mg)
)
UPDATE core.dish d
   SET nutrition_snapshot = d.nutrition_snapshot || jsonb_build_object(
           'dish_fiber_g', t.dish_fiber_g,
           'dish_calcium_mg', t.dish_calcium_mg,
           'fiber_calcium_data_quality', 'approx',
           'fiber_calcium_recomputed_from', 'core.ingredient × amount_g / 100; 未按烹饪损耗修正',
           'ingredient_count', t.ingredient_count
       ),
       updated_at = now()
  FROM totals t
 WHERE d.dish_id = t.dish_id;

-- 5. 收尾检查。
DO $$
DECLARE
    v_dish_rows integer;
    v_iron_rows integer;
BEGIN
    SELECT count(*) INTO v_dish_rows
      FROM core.dish
     WHERE nutrition_snapshot ? 'dish_fiber_g' AND nutrition_snapshot ? 'dish_calcium_mg';
    SELECT count(*) INTO v_iron_rows
      FROM core.nutrient_reference
     WHERE nutrient_id = 'iron' AND sex = 'female' AND age_group = '50-64' AND life_stage = '普通';
    IF v_dish_rows <> 60 THEN RAISE EXCEPTION '纤维、钙已重算的菜式应为60道，实际为%道', v_dish_rows; END IF;
    IF v_iron_rows <> 1 THEN RAISE EXCEPTION '铁·女性50-64岁应为1行，实际为%行', v_iron_rows; END IF;
END $$;

COMMIT;
