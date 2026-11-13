-- 食材接口字段暴露：数据 v1.1 已入库字段透传（组长方案三步之第 1/2 步）
-- 适用：后端岗执行 × 数据岗（请并入数据库交付包同步，避免覆盖回滚）
-- 2026-10-22

-- 第 1 步：视图 v_ingredient_search 新增 sfa_g / iodine_ug / data_quality / source_note
-- 注：CREATE OR REPLACE VIEW 不允许改变已有列顺序，新列追加在末尾（接口按列名取值，不受顺序影响）
CREATE OR REPLACE VIEW app.v_ingredient_search AS
SELECT food_id, name, aliases, category, state, edible_portion_pct,
       energy_kcal, protein_g, fat_g, carbohydrate_g, fiber_g,
       sodium_mg, potassium_mg, calcium_mg, magnesium_mg,
       allergens, allergen_status,
       purine_level,
       source_url,
       ((protein_g IS NULL) OR (fat_g IS NULL) OR (carbohydrate_g IS NULL)) AS has_missing_macro,
       concat_ws(' ', name, array_to_string(aliases, ' '), category, state) AS search_text,
       sfa_g,
       (micro_nutrients->>'iodine_ug')::numeric AS iodine_ug,
       source_row->>'data_quality' AS data_quality,
       source_row->>'source_note' AS source_note
FROM core.ingredient
WHERE NOT is_deleted;

-- 第 2 步：函数 search_ingredients 出参新增五列（purine_level / sfa_g / iodine_ug / data_quality / source_note）
-- 注：CREATE OR REPLACE FUNCTION 不允许改变返回表结构，必须先 DROP 再 CREATE
DROP FUNCTION IF EXISTS app.search_ingredients(text, integer);
CREATE FUNCTION app.search_ingredients(p_query text, p_limit integer DEFAULT 20)
 RETURNS TABLE(food_id text, name text, aliases text[], category text, state text, energy_kcal numeric, protein_g numeric, fat_g numeric, carbohydrate_g numeric, allergens text[], allergen_status text, match_type text, purine_level text, sfa_g numeric, iodine_ug numeric, data_quality text, source_note text)
 LANGUAGE sql
 STABLE
AS $function$
    SELECT
        v.food_id,
        v.name,
        v.aliases,
        v.category,
        v.state,
        v.energy_kcal,
        v.protein_g,
        v.fat_g,
        v.carbohydrate_g,
        v.allergens,
        v.allergen_status,
        CASE
            WHEN v.name = btrim(p_query) THEN 'name_exact'
            WHEN btrim(p_query) = ANY(v.aliases) THEN 'alias_exact'
            WHEN v.name ILIKE btrim(p_query) || '%' THEN 'name_prefix'
            WHEN EXISTS (
                SELECT 1 FROM unnest(v.aliases) alias_name
                WHERE alias_name ILIKE btrim(p_query) || '%'
            ) THEN 'alias_prefix'
            ELSE 'contains'
        END,
        v.purine_level,
        v.sfa_g,
        v.iodine_ug,
        v.data_quality,
        v.source_note
    FROM app.v_ingredient_search v
    WHERE nullif(btrim(p_query), '') IS NOT NULL
      AND (
          v.name ILIKE '%' || btrim(p_query) || '%'
          OR EXISTS (
              SELECT 1 FROM unnest(v.aliases) alias_name
              WHERE alias_name ILIKE '%' || btrim(p_query) || '%'
          )
      )
    ORDER BY
        CASE
            WHEN v.name = btrim(p_query) THEN 0
            WHEN btrim(p_query) = ANY(v.aliases) THEN 1
            WHEN v.name ILIKE btrim(p_query) || '%' THEN 2
            ELSE 3
        END,
        v.name,
        v.food_id
    LIMIT least(greatest(coalesce(p_limit, 20), 1), 100)
$function$;
