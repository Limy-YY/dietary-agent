--
-- PostgreSQL database dump
--

\restrict u0dyDwn1ff3XA00MRSdm9c8KbDOzk3mSgAfZ3M3t8fdZ9ar65j4SEiFyQIsfRGk

-- Dumped from database version 18.6 (Postgres.app)
-- Dumped by pg_dump version 18.6 (Postgres.app)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: app; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA app;


--
-- Name: audit; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA audit;


--
-- Name: core; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA core;


--
-- Name: knowledge; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA knowledge;


--
-- Name: staging; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA staging;


--
-- Name: age_in_months(date, date); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.age_in_months(p_birth_date date, p_as_of_date date DEFAULT CURRENT_DATE) RETURNS integer
    LANGUAGE sql STABLE
    AS $$
    SELECT CASE
        WHEN p_birth_date IS NULL OR p_as_of_date IS NULL OR p_birth_date > p_as_of_date THEN NULL
        ELSE (
            extract(year FROM age(p_as_of_date, p_birth_date))::integer * 12
            + extract(month FROM age(p_as_of_date, p_birth_date))::integer
        )
    END
$$;


--
-- Name: FUNCTION age_in_months(p_birth_date date, p_as_of_date date); Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON FUNCTION app.age_in_months(p_birth_date date, p_as_of_date date) IS '按出生日期和评价日期计算完整月龄；未来出生日期返回 NULL。';


--
-- Name: evaluate_daily_condition_nutrient_rule(text, date, text); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.evaluate_daily_condition_nutrient_rule(p_user_id text, p_intake_date date, p_rule_id text) RETURNS TABLE(user_id text, intake_date date, rule_id text, condition_id text, condition_status text, review_status text, production_ready boolean, comparator text, applied_target numeric, target_unit text, known_total numeric, record_count integer, missing_value_count integer, full_day_scope boolean, evaluation_status text, explanation_zh text)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'app', 'core'
    AS $$
    SELECT preview.*
    FROM core.condition_nutrient_rule r
    CROSS JOIN LATERAL app.preview_daily_condition_nutrient_rule(
        p_user_id, p_intake_date, p_rule_id
    ) preview
    WHERE r.rule_id = p_rule_id
      AND r.review_status = 'approved'
      AND r.is_active
$$;


--
-- Name: FUNCTION evaluate_daily_condition_nutrient_rule(p_user_id text, p_intake_date date, p_rule_id text); Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON FUNCTION app.evaluate_daily_condition_nutrient_rule(p_user_id text, p_intake_date date, p_rule_id text) IS '生产评估入口；未审核或未启用规则返回0行，不允许普通应用绕过。';


--
-- Name: evaluate_weekly_ul(jsonb, text, integer, text, text); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.evaluate_weekly_ul(p_daily_intakes jsonb, p_sex text, p_age_months integer, p_life_stage text DEFAULT '普通'::text, p_menstrual_status text DEFAULT NULL::text) RETURNS TABLE(nutrient_id text, nutrient_name text, unit text, days_recorded integer, weekly_total numeric, daily_average numeric, daily_max numeric, ul_value numeric, days_over_ul integer, evaluation_status text)
    LANGUAGE sql STABLE
    AS $$
    WITH raw_daily AS (
        SELECT
            (entry->>'date')::date AS intake_date,
            entry->>'nutrient_id' AS nutrient_id,
            (entry->>'amount')::numeric AS amount
        FROM jsonb_array_elements(coalesce(p_daily_intakes, '[]'::jsonb)) entry
        WHERE nullif(entry->>'date', '') IS NOT NULL
          AND nullif(entry->>'nutrient_id', '') IS NOT NULL
          AND nullif(entry->>'amount', '') IS NOT NULL
    ), daily AS (
        SELECT intake_date, nutrient_id, sum(amount) AS daily_amount
        FROM raw_daily
        GROUP BY intake_date, nutrient_id
    ), reference_candidates AS (
        SELECT *
        FROM app.match_nutrient_reference(
            p_sex, p_age_months, p_life_stage, p_menstrual_status
        )
    ), references_by_nutrient AS (
        SELECT
            nutrient_id,
            min(nutrient_name) AS nutrient_name,
            min(unit) AS unit,
            count(*) AS candidate_count,
            CASE WHEN count(*) = 1 THEN max(ul_value) ELSE NULL END AS ul_value
        FROM reference_candidates
        GROUP BY nutrient_id
    )
    SELECT
        d.nutrient_id,
        coalesce(r.nutrient_name, n.name_zh),
        coalesce(r.unit, n.unit),
        count(*)::integer,
        sum(d.daily_amount),
        round(avg(d.daily_amount), 4),
        max(d.daily_amount),
        r.ul_value,
        count(*) FILTER (
            WHERE r.ul_value IS NOT NULL AND d.daily_amount > r.ul_value
        )::integer,
        CASE
            WHEN coalesce(r.candidate_count, 0) = 0 THEN 'reference_not_found'
            WHEN r.candidate_count > 1 THEN 'needs_clarification'
            WHEN r.ul_value IS NULL THEN 'ul_not_available'
            WHEN count(*) FILTER (WHERE d.daily_amount > r.ul_value) > 0 THEN 'over_ul'
            ELSE 'within_ul'
        END
    FROM daily d
    LEFT JOIN references_by_nutrient r ON r.nutrient_id = d.nutrient_id
    LEFT JOIN core.nutrient n ON n.nutrient_id = d.nutrient_id
    GROUP BY d.nutrient_id, r.nutrient_name, n.name_zh, r.unit, n.unit,
             r.ul_value, r.candidate_count
    ORDER BY d.nutrient_id
$$;


--
-- Name: FUNCTION evaluate_weekly_ul(p_daily_intakes jsonb, p_sex text, p_age_months integer, p_life_stage text, p_menstrual_status text); Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON FUNCTION app.evaluate_weekly_ul(p_daily_intakes jsonb, p_sex text, p_age_months integer, p_life_stage text, p_menstrual_status text) IS '按每日摄入量计算每日最大值和超限天数；weekly_total 仅展示，不用于直接比较每日 UL。';


--
-- Name: guard_fixed_plan_children(); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.guard_fixed_plan_children() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_plan_id bigint;
    v_status text;
BEGIN
    IF TG_TABLE_NAME = 'meal_slot' THEN
        v_plan_id := COALESCE(NEW.meal_plan_id, OLD.meal_plan_id);
    ELSIF TG_TABLE_NAME = 'meal_candidate' THEN
        SELECT s.meal_plan_id INTO v_plan_id
        FROM app.meal_slot s
        WHERE s.meal_slot_id = COALESCE(NEW.meal_slot_id, OLD.meal_slot_id);
    ELSIF TG_TABLE_NAME = 'meal_candidate_dish' THEN
        SELECT s.meal_plan_id INTO v_plan_id
        FROM app.meal_candidate c
        JOIN app.meal_slot s ON s.meal_slot_id = c.meal_slot_id
        WHERE c.candidate_id = COALESCE(NEW.candidate_id, OLD.candidate_id);
    END IF;

    SELECT status INTO v_status
    FROM app.meal_plan
    WHERE meal_plan_id = v_plan_id;

    IF v_status = 'fixed' THEN
        RAISE EXCEPTION 'meal plan % is fixed; structural rows are read-only', v_plan_id
            USING ERRCODE = '55000';
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END
$$;


--
-- Name: guard_meal_plan_update(); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.guard_meal_plan_update() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_bad_slot_count integer;
BEGIN
    IF OLD.status = 'fixed' THEN
        IF ROW(
            NEW.user_id, NEW.plan_type, NEW.plan_date, NEW.goal_energy_kcal,
            NEW.macro_ratio, NEW.meals, NEW.sources, NEW.start_date, NEW.end_date,
            NEW.status, NEW.generation_request, NEW.generation_context,
            NEW.micro_balance_window_start, NEW.micro_balance_window_end,
            NEW.fixed_at, NEW.agent_version, NEW.data_version, NEW.derived_from_plan_id
        ) IS DISTINCT FROM ROW(
            OLD.user_id, OLD.plan_type, OLD.plan_date, OLD.goal_energy_kcal,
            OLD.macro_ratio, OLD.meals, OLD.sources, OLD.start_date, OLD.end_date,
            OLD.status, OLD.generation_request, OLD.generation_context,
            OLD.micro_balance_window_start, OLD.micro_balance_window_end,
            OLD.fixed_at, OLD.agent_version, OLD.data_version, OLD.derived_from_plan_id
        ) THEN
            RAISE EXCEPTION 'meal plan % is fixed and read-only', OLD.meal_plan_id
                USING ERRCODE = '55000';
        END IF;
    END IF;

    IF NOT (
        NEW.status = OLD.status
        OR (OLD.status = 'draft' AND NEW.status = 'candidates')
        OR (OLD.status = 'candidates' AND NEW.status = 'fixed')
    ) THEN
        RAISE EXCEPTION 'invalid meal plan status transition: % -> %',
            OLD.status, NEW.status USING ERRCODE = '23514';
    END IF;

    IF NEW.status IN ('candidates', 'fixed') AND OLD.status <> NEW.status THEN
        SELECT count(*) INTO v_bad_slot_count
        FROM app.meal_slot s
        LEFT JOIN LATERAL (
            SELECT count(*) AS candidate_count
            FROM app.meal_candidate c
            WHERE c.meal_slot_id = s.meal_slot_id
        ) x ON true
        WHERE s.meal_plan_id = NEW.meal_plan_id
          AND x.candidate_count NOT BETWEEN 2 AND 3;

        IF NOT EXISTS (
            SELECT 1 FROM app.meal_slot s
            WHERE s.meal_plan_id = NEW.meal_plan_id
        ) OR v_bad_slot_count > 0 THEN
            RAISE EXCEPTION 'plan % must have 2-3 candidates for every meal slot',
                NEW.meal_plan_id USING ERRCODE = '23514';
        END IF;
    END IF;

    IF NEW.status = 'fixed' AND OLD.status <> 'fixed' THEN
        IF EXISTS (
            SELECT 1 FROM app.meal_slot s
            WHERE s.meal_plan_id = NEW.meal_plan_id
              AND s.selected_candidate_id IS NULL
        ) THEN
            RAISE EXCEPTION 'plan % cannot be fixed before every slot selects a candidate',
                NEW.meal_plan_id USING ERRCODE = '23514';
        END IF;
        NEW.fixed_at := COALESCE(NEW.fixed_at, now());
    END IF;

    NEW.updated_at := now();
    RETURN NEW;
END
$$;


--
-- Name: match_nutrient_reference(text, integer, text, text); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.match_nutrient_reference(p_sex text, p_age_months integer, p_life_stage text DEFAULT '普通'::text, p_menstrual_status text DEFAULT NULL::text) RETURNS TABLE(nutrient_id text, nutrient_name text, unit text, reference_type text, reference_value numeric, ul_value numeric, sex text, age_group text, life_stage text, menstrual_status text, needs_clarification boolean)
    LANGUAGE sql STABLE
    AS $$
    WITH params AS (
        SELECT
            lower(nullif(btrim(p_sex), '')) AS requested_sex,
            p_age_months AS requested_age_months,
            CASE lower(coalesce(nullif(btrim(p_life_stage), ''), '普通'))
                WHEN 'preg_1' THEN '孕早期'
                WHEN 'preg_2' THEN '孕中期'
                WHEN 'preg_3' THEN '孕晚期'
                WHEN 'lactation' THEN '哺乳期'
                ELSE coalesce(nullif(btrim(p_life_stage), ''), '普通')
            END AS requested_life_stage,
            nullif(btrim(p_menstrual_status), '') AS requested_menstrual_status
    ), candidates AS (
        SELECT
            nr.nutrient_id,
            n.name_zh AS nutrient_name,
            n.unit,
            nr.reference_type,
            nr.value AS reference_value,
            nr.ul_value,
            nr.sex,
            nr.age_group,
            nr.life_stage,
            nr.menstrual_status
        FROM core.nutrient_reference nr
        JOIN core.nutrient n ON n.nutrient_id = nr.nutrient_id
        CROSS JOIN params p
        WHERE (nr.sex = p.requested_sex OR nr.sex = 'both')
          AND nr.life_stage = p.requested_life_stage
          AND (
              p.requested_life_stage <> '普通'
              OR (
                  p.requested_age_months IS NOT NULL
                  AND p.requested_age_months >= nr.age_min_months
                  AND (nr.age_max_months IS NULL OR p.requested_age_months <= nr.age_max_months)
              )
          )
          AND (
              nr.menstrual_status = ''
              OR p.requested_menstrual_status IS NULL
              OR nr.menstrual_status = p.requested_menstrual_status
          )
    )
    SELECT
        c.nutrient_id,
        c.nutrient_name,
        c.unit,
        c.reference_type,
        c.reference_value,
        c.ul_value,
        c.sex,
        c.age_group,
        c.life_stage,
        c.menstrual_status,
        count(*) OVER (PARTITION BY c.nutrient_id) > 1 AS needs_clarification
    FROM candidates c
    ORDER BY c.nutrient_id, c.menstrual_status
$$;


--
-- Name: FUNCTION match_nutrient_reference(p_sex text, p_age_months integer, p_life_stage text, p_menstrual_status text); Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON FUNCTION app.match_nutrient_reference(p_sex text, p_age_months integer, p_life_stage text, p_menstrual_status text) IS '按性别、月龄、生命阶段和月经状态匹配 RNI/AI/UL；候选不唯一时返回 needs_clarification=true。';


--
-- Name: preview_daily_condition_nutrient_rule(text, date, text); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.preview_daily_condition_nutrient_rule(p_user_id text, p_intake_date date, p_rule_id text) RETURNS TABLE(user_id text, intake_date date, rule_id text, condition_id text, condition_status text, review_status text, production_ready boolean, comparator text, applied_target numeric, target_unit text, known_total numeric, record_count integer, missing_value_count integer, full_day_scope boolean, evaluation_status text, explanation_zh text)
    LANGUAGE sql STABLE
    AS $$
    WITH rule_context AS (
        SELECT
            p.user_id,
            r.rule_id,
            r.condition_id,
            p.conditions #>> ARRAY[r.condition_id, 'status'] AS condition_status,
            r.review_status,
            (r.review_status = 'approved' AND r.is_active) AS production_ready,
            r.comparator,
            coalesce(
                nullif(
                    p.conditions #>> ARRAY[
                        r.condition_id,
                        coalesce(r.evaluator->>'profile_override_key', '__none__')
                    ],
                    ''
                )::numeric,
                r.target_value
            ) AS applied_target,
            r.target_unit,
            r.evaluator->>'computed_key' AS computed_key
        FROM app.profile p
        JOIN core.condition_nutrient_rule r ON r.rule_id = p_rule_id
        WHERE p.user_id = p_user_id
          AND r.rule_kind IN ('nutrient_limit', 'nutrient_target')
    ), aggregate_intake AS (
        SELECT
            rc.*,
            count(nr.nutrition_result_id)::integer AS record_count,
            count(nr.nutrition_result_id) FILTER (
                WHERE NOT (nr.computed ? rc.computed_key)
                   OR nullif(nr.computed->>rc.computed_key, '') IS NULL
            )::integer AS missing_value_count,
            round(sum((nr.computed->>rc.computed_key)::numeric) FILTER (
                WHERE nr.computed ? rc.computed_key
                  AND nullif(nr.computed->>rc.computed_key, '') IS NOT NULL
            ), 4) AS known_total,
            coalesce(bool_and(mp.sources->>'data_scope' = 'full_day') FILTER (
                WHERE nr.nutrition_result_id IS NOT NULL
            ), false) AS full_day_scope
        FROM rule_context rc
        LEFT JOIN app.nutrition_result nr
          ON nr.user_id = rc.user_id
         AND (nr.sources->>'date')::date = p_intake_date
        LEFT JOIN app.meal_plan mp
          ON mp.meal_plan_id = nullif(nr.sources->>'meal_plan_id', '')::bigint
        GROUP BY rc.user_id, rc.rule_id, rc.condition_id, rc.condition_status,
                 rc.review_status, rc.production_ready, rc.comparator,
                 rc.applied_target, rc.target_unit, rc.computed_key
    ), evaluated AS (
        SELECT
            ai.*,
            CASE
                WHEN ai.condition_status IS DISTINCT FROM 'confirmed' THEN 'condition_not_active'
                WHEN ai.record_count = 0 THEN 'no_intake_data'
                WHEN ai.known_total IS NOT NULL
                 AND (
                    (ai.comparator = '<'  AND ai.known_total >= ai.applied_target)
                    OR (ai.comparator = '<=' AND ai.known_total > ai.applied_target)
                 ) THEN CASE
                    WHEN ai.missing_value_count > 0 OR NOT ai.full_day_scope
                        THEN 'limit_exceeded_known_minimum'
                    ELSE 'limit_exceeded'
                 END
                WHEN ai.missing_value_count > 0 THEN 'not_evaluable_missing_values'
                WHEN NOT ai.full_day_scope THEN 'insufficient_scope'
                ELSE 'within_candidate_limit'
            END AS evaluation_status
        FROM aggregate_intake ai
    )
    SELECT
        e.user_id,
        p_intake_date,
        e.rule_id,
        e.condition_id,
        e.condition_status,
        e.review_status,
        e.production_ready,
        e.comparator,
        e.applied_target,
        e.target_unit,
        e.known_total,
        e.record_count,
        e.missing_value_count,
        e.full_day_scope,
        e.evaluation_status,
        CASE e.evaluation_status
            WHEN 'condition_not_active' THEN '用户条件不是confirmed，规则不启用。'
            WHEN 'no_intake_data' THEN '当天没有可计算的摄入记录。'
            WHEN 'limit_exceeded_known_minimum' THEN '已知小计已经超过候选限制；即使数据不完整，也不能判定为达标。'
            WHEN 'limit_exceeded' THEN '完整的全天记录超过候选限制。'
            WHEN 'not_evaluable_missing_values' THEN '存在营养值缺失，不能判定是否达标。'
            WHEN 'insufficient_scope' THEN '只有部分餐次数据，不能据此判断全天是否达标。'
            WHEN 'within_candidate_limit' THEN '完整的全天记录未超过候选限制；仍须检查规则是否已审核。'
        END
    FROM evaluated e
$$;


--
-- Name: FUNCTION preview_daily_condition_nutrient_rule(p_user_id text, p_intake_date date, p_rule_id text); Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON FUNCTION app.preview_daily_condition_nutrient_rule(p_user_id text, p_intake_date date, p_rule_id text) IS '预览单日疾病营养规则；返回审核状态和数据范围，不把晚餐等部分数据误判为全天达标。';


--
-- Name: recent_micro_balance(text, date, date); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.recent_micro_balance(p_user_id text, p_window_start date, p_window_end date) RETURNS TABLE(nutrient_id text, nutrient_name text, unit text, total_value numeric, selected_meal_count bigint, known_meal_count bigint, missing_meal_count bigint)
    LANGUAGE sql STABLE
    AS $_$
WITH selected_meals AS (
    SELECT c.candidate_id, c.micro_estimate
    FROM app.meal_plan p
    JOIN app.meal_slot s ON s.meal_plan_id = p.meal_plan_id
    JOIN app.meal_candidate c ON c.candidate_id = s.selected_candidate_id
    WHERE p.user_id = p_user_id
      AND p.status = 'fixed'
      AND NOT p.is_deleted
      AND s.slot_date BETWEEN p_window_start AND p_window_end
), expanded AS (
    SELECT
        k.nutrient_id,
        k.name_zh,
        k.unit,
        k.display_order,
        sm.candidate_id,
        CASE
            WHEN jsonb_typeof(sm.micro_estimate -> k.nutrient_id) = 'number'
                THEN (sm.micro_estimate ->> k.nutrient_id)::numeric
            WHEN jsonb_typeof(sm.micro_estimate -> k.nutrient_id) = 'object'
                 AND COALESCE(sm.micro_estimate -> k.nutrient_id ->> 'value', '')
                     ~ '^-?[0-9]+([.][0-9]+)?$'
                THEN (sm.micro_estimate -> k.nutrient_id ->> 'value')::numeric
            ELSE NULL
        END AS nutrient_value
    FROM app.v_key_micronutrient k
    LEFT JOIN selected_meals sm ON true
)
SELECT
    e.nutrient_id,
    e.name_zh,
    e.unit,
    COALESCE(sum(e.nutrient_value), 0),
    count(e.candidate_id),
    count(e.nutrient_value),
    count(e.candidate_id) - count(e.nutrient_value)
FROM expanded e
GROUP BY e.nutrient_id, e.name_zh, e.unit
ORDER BY min(e.display_order);
$_$;


--
-- Name: FUNCTION recent_micro_balance(p_user_id text, p_window_start date, p_window_end date); Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON FUNCTION app.recent_micro_balance(p_user_id text, p_window_start date, p_window_end date) IS '汇总指定用户、指定日期窗口内已确认方案的7种关键微量；NULL保持未知并计入missing。';


--
-- Name: screen_dishes_for_allergens(text[]); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.screen_dishes_for_allergens(p_allergens text[]) RETURNS TABLE(dish_id text, dish_name text, matched_allergens text[], strict_allergens text[], unverified_food_ids text[], decision text, reason text)
    LANGUAGE sql STABLE
    AS $$
    SELECT
        d.dish_id,
        d.name,
        ARRAY(
            SELECT allergen
            FROM unnest(d.strict_allergens) allergen
            WHERE allergen = ANY(coalesce(p_allergens, ARRAY[]::text[]))
            ORDER BY allergen
        ),
        d.strict_allergens,
        d.unverified_food_ids,
        CASE
            WHEN coalesce(cardinality(p_allergens), 0) = 0 THEN 'eligible'
            WHEN d.strict_allergens && p_allergens THEN 'strict_exclude'
            WHEN cardinality(d.unverified_food_ids) > 0 THEN 'exclude_until_verified'
            ELSE 'eligible'
        END,
        CASE
            WHEN coalesce(cardinality(p_allergens), 0) = 0 THEN '用户未提供过敏原条件。'
            WHEN d.strict_allergens && p_allergens THEN '已确认配料命中用户过敏原，必须排除。'
            WHEN cardinality(d.unverified_food_ids) > 0 THEN '存在未核查配料，确认安全前不推荐。'
            ELSE '所有配料已核查，未命中用户过敏原。'
        END
    FROM app.v_dish_live_nutrition d
    ORDER BY
        CASE
            WHEN coalesce(cardinality(p_allergens), 0) = 0 THEN 0
            WHEN d.strict_allergens && p_allergens THEN 2
            WHEN cardinality(d.unverified_food_ids) > 0 THEN 1
            ELSE 0
        END,
        d.name,
        d.dish_id
$$;


--
-- Name: FUNCTION screen_dishes_for_allergens(p_allergens text[]); Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON FUNCTION app.screen_dishes_for_allergens(p_allergens text[]) IS '严格区分已确认命中、未核查和可推荐；未核查不得解释为安全。';


--
-- Name: search_ingredients(text, integer); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.search_ingredients(p_query text, p_limit integer DEFAULT 20) RETURNS TABLE(food_id text, name text, aliases text[], category text, state text, energy_kcal numeric, protein_g numeric, fat_g numeric, carbohydrate_g numeric, allergens text[], allergen_status text, match_type text)
    LANGUAGE sql STABLE
    AS $$
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
        END
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
$$;


--
-- Name: FUNCTION search_ingredients(p_query text, p_limit integer); Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON FUNCTION app.search_ingredients(p_query text, p_limit integer) IS '按名称和别名进行精确、前缀和包含搜索；不依赖中文分词扩展。';


--
-- Name: review_condition_rule(text, text, text, text, text, boolean); Type: FUNCTION; Schema: audit; Owner: -
--

CREATE FUNCTION audit.review_condition_rule(p_rule_id text, p_decision text, p_reviewer_name text, p_reviewer_role text, p_review_note text DEFAULT NULL::text, p_activate boolean DEFAULT false) RETURNS TABLE(review_id bigint, reviewed_rule_id text, resulting_review_status text, resulting_is_active boolean)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'audit', 'core', 'app'
    AS $$
DECLARE
    v_review_id bigint;
    v_result_status text;
BEGIN
    IF nullif(btrim(p_rule_id), '') IS NULL THEN
        RAISE EXCEPTION 'rule_id不能为空';
    END IF;

    IF p_decision NOT IN ('approved', 'changes_requested', 'rejected') THEN
        RAISE EXCEPTION 'decision必须为 approved、changes_requested 或 rejected';
    END IF;

    IF nullif(btrim(p_reviewer_name), '') IS NULL
       OR nullif(btrim(p_reviewer_role), '') IS NULL THEN
        RAISE EXCEPTION '审核人姓名和审核角色不能为空';
    END IF;

    IF p_activate AND p_decision <> 'approved' THEN
        RAISE EXCEPTION '只有approved决定可以同时启用规则';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM core.condition_nutrient_rule r WHERE r.rule_id = p_rule_id
    ) THEN
        RAISE EXCEPTION '规则不存在: %', p_rule_id;
    END IF;

    INSERT INTO audit.condition_rule_review (
        rule_id, decision, reviewer_name, reviewer_role, review_note
    )
    VALUES (
        p_rule_id,
        p_decision,
        btrim(p_reviewer_name),
        btrim(p_reviewer_role),
        nullif(btrim(p_review_note), '')
    )
    RETURNING condition_rule_review.review_id INTO v_review_id;

    v_result_status := CASE p_decision
        WHEN 'approved' THEN 'approved'
        WHEN 'changes_requested' THEN 'draft'
        WHEN 'rejected' THEN 'rejected'
    END;

    UPDATE core.condition_nutrient_rule r
    SET review_status = v_result_status,
        is_active = CASE WHEN p_decision = 'approved' THEN p_activate ELSE false END,
        updated_at = now()
    WHERE r.rule_id = p_rule_id;

    RETURN QUERY
    SELECT
        v_review_id,
        r.rule_id,
        r.review_status,
        r.is_active
    FROM core.condition_nutrient_rule r
    WHERE r.rule_id = p_rule_id;
END
$$;


--
-- Name: FUNCTION review_condition_rule(p_rule_id text, p_decision text, p_reviewer_name text, p_reviewer_role text, p_review_note text, p_activate boolean); Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON FUNCTION audit.review_condition_rule(p_rule_id text, p_decision text, p_reviewer_name text, p_reviewer_role text, p_review_note text, p_activate boolean) IS '受控规则审核入口；调用权限应只授予审核后台角色。审核资格须由组织流程核实，数据库只保存记录。';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: conversation; Type: TABLE; Schema: app; Owner: -
--

CREATE TABLE app.conversation (
    conversation_id bigint NOT NULL,
    user_id text NOT NULL,
    title text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: conversation_conversation_id_seq; Type: SEQUENCE; Schema: app; Owner: -
--

ALTER TABLE app.conversation ALTER COLUMN conversation_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME app.conversation_conversation_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: meal_candidate; Type: TABLE; Schema: app; Owner: -
--

CREATE TABLE app.meal_candidate (
    candidate_id bigint NOT NULL,
    meal_slot_id bigint NOT NULL,
    rank integer NOT NULL,
    reason_codes jsonb DEFAULT '[]'::jsonb NOT NULL,
    why_text text,
    macro_estimate jsonb DEFAULT '{}'::jsonb NOT NULL,
    micro_estimate jsonb DEFAULT '{}'::jsonb NOT NULL,
    oil_salt_estimate jsonb DEFAULT '{}'::jsonb NOT NULL,
    eating_order_advice text,
    sources jsonb DEFAULT '[]'::jsonb NOT NULL,
    agent_output_version text,
    explanation_generated_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT meal_candidate_rank_check CHECK (((rank >= 1) AND (rank <= 3)))
);


--
-- Name: meal_candidate_candidate_id_seq; Type: SEQUENCE; Schema: app; Owner: -
--

ALTER TABLE app.meal_candidate ALTER COLUMN candidate_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME app.meal_candidate_candidate_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: meal_candidate_dish; Type: TABLE; Schema: app; Owner: -
--

CREATE TABLE app.meal_candidate_dish (
    candidate_id bigint NOT NULL,
    dish_id text NOT NULL,
    role text NOT NULL,
    servings numeric DEFAULT 1 NOT NULL,
    estimated_g numeric,
    portion_text text,
    method_override text,
    display_order integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT meal_candidate_dish_display_order_check CHECK ((display_order > 0)),
    CONSTRAINT meal_candidate_dish_estimated_g_check CHECK (((estimated_g IS NULL) OR (estimated_g > (0)::numeric))),
    CONSTRAINT meal_candidate_dish_role_check CHECK ((role = ANY (ARRAY['主食'::text, '菜'::text]))),
    CONSTRAINT meal_candidate_dish_servings_check CHECK ((servings > (0)::numeric))
);


--
-- Name: meal_plan; Type: TABLE; Schema: app; Owner: -
--

CREATE TABLE app.meal_plan (
    meal_plan_id bigint NOT NULL,
    user_id text NOT NULL,
    plan_type text NOT NULL,
    plan_date date NOT NULL,
    goal_energy_kcal numeric,
    macro_ratio jsonb DEFAULT '{}'::jsonb NOT NULL,
    meals jsonb NOT NULL,
    sources jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    generation_request text,
    generation_context jsonb DEFAULT '{}'::jsonb NOT NULL,
    micro_balance_window_start date,
    micro_balance_window_end date,
    fixed_at timestamp with time zone,
    agent_version text,
    data_version text DEFAULT 'v1.2'::text NOT NULL,
    derived_from_plan_id bigint,
    is_deleted boolean DEFAULT false NOT NULL,
    deleted_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT meal_plan_deleted_at_check CHECK (((is_deleted AND (deleted_at IS NOT NULL)) OR ((NOT is_deleted) AND (deleted_at IS NULL)))),
    CONSTRAINT meal_plan_fixed_at_check CHECK ((((status = 'fixed'::text) AND (fixed_at IS NOT NULL)) OR ((status <> 'fixed'::text) AND (fixed_at IS NULL)))),
    CONSTRAINT meal_plan_micro_window_check CHECK (((micro_balance_window_start IS NULL) OR (micro_balance_window_end IS NULL) OR (micro_balance_window_end >= micro_balance_window_start))),
    CONSTRAINT meal_plan_period_check CHECK ((end_date >= start_date)),
    CONSTRAINT meal_plan_plan_type_v2_check CHECK ((plan_type = ANY (ARRAY['餐'::text, '日'::text, '多日'::text, '周'::text, '自定义'::text]))),
    CONSTRAINT meal_plan_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'candidates'::text, 'fixed'::text])))
);


--
-- Name: COLUMN meal_plan.meals; Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON COLUMN app.meal_plan.meals IS 'v1.1兼容快照；V2新方案的餐位和候选写入规范化子表。';


--
-- Name: COLUMN meal_plan.derived_from_plan_id; Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON COLUMN app.meal_plan.derived_from_plan_id IS '恢复历史方案或基于旧方案调整时，指向原方案；固定方案本身不原地修改。';


--
-- Name: meal_plan_meal_plan_id_seq; Type: SEQUENCE; Schema: app; Owner: -
--

ALTER TABLE app.meal_plan ALTER COLUMN meal_plan_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME app.meal_plan_meal_plan_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: meal_slot; Type: TABLE; Schema: app; Owner: -
--

CREATE TABLE app.meal_slot (
    meal_slot_id bigint NOT NULL,
    meal_plan_id bigint NOT NULL,
    slot_date date NOT NULL,
    meal_type text NOT NULL,
    display_order integer DEFAULT 1 NOT NULL,
    target_macro jsonb DEFAULT '{}'::jsonb NOT NULL,
    selected_candidate_id bigint,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT meal_slot_display_order_check CHECK ((display_order > 0))
);


--
-- Name: meal_slot_meal_slot_id_seq; Type: SEQUENCE; Schema: app; Owner: -
--

ALTER TABLE app.meal_slot ALTER COLUMN meal_slot_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME app.meal_slot_meal_slot_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: message; Type: TABLE; Schema: app; Owner: -
--

CREATE TABLE app.message (
    message_id bigint NOT NULL,
    conversation_id bigint NOT NULL,
    role text NOT NULL,
    content text,
    tool_calls jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    referenced_plan_id bigint,
    intent text,
    needs_clarification boolean DEFAULT false NOT NULL,
    structured_output jsonb DEFAULT '{}'::jsonb NOT NULL,
    agent_version text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT message_intent_check CHECK (((intent IS NULL) OR (intent = ANY (ARRAY['inquiry'::text, 'meal_plan'::text, 'adjustment'::text])))),
    CONSTRAINT message_role_check CHECK ((role = ANY (ARRAY['user'::text, 'assistant'::text, 'tool'::text])))
);


--
-- Name: message_message_id_seq; Type: SEQUENCE; Schema: app; Owner: -
--

ALTER TABLE app.message ALTER COLUMN message_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME app.message_message_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: nutrition_report; Type: TABLE; Schema: app; Owner: -
--

CREATE TABLE app.nutrition_report (
    nutrition_report_id bigint NOT NULL,
    user_id text NOT NULL,
    report_type text NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    meal_plan_id bigint,
    summary jsonb DEFAULT '{}'::jsonb NOT NULL,
    macro_summary jsonb DEFAULT '{}'::jsonb NOT NULL,
    key_micro_summary jsonb DEFAULT '{}'::jsonb NOT NULL,
    completeness jsonb DEFAULT '{}'::jsonb NOT NULL,
    sources jsonb DEFAULT '[]'::jsonb NOT NULL,
    agent_version text,
    generated_at timestamp with time zone DEFAULT now() NOT NULL,
    source_weekly_report_id bigint,
    CONSTRAINT nutrition_report_period_check CHECK ((period_end >= period_start)),
    CONSTRAINT nutrition_report_type_check CHECK ((report_type = ANY (ARRAY['plan'::text, 'week'::text, 'month'::text, 'custom'::text])))
);


--
-- Name: nutrition_report_nutrition_report_id_seq; Type: SEQUENCE; Schema: app; Owner: -
--

ALTER TABLE app.nutrition_report ALTER COLUMN nutrition_report_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME app.nutrition_report_nutrition_report_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: nutrition_report_plan; Type: TABLE; Schema: app; Owner: -
--

CREATE TABLE app.nutrition_report_plan (
    nutrition_report_id bigint NOT NULL,
    meal_plan_id bigint NOT NULL
);


--
-- Name: nutrition_result; Type: TABLE; Schema: app; Owner: -
--

CREATE TABLE app.nutrition_result (
    nutrition_result_id bigint NOT NULL,
    user_id text NOT NULL,
    target_type text NOT NULL,
    target_id text NOT NULL,
    amount_g numeric NOT NULL,
    method text NOT NULL,
    computed jsonb NOT NULL,
    sources jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT nutrition_result_amount_g_check CHECK ((amount_g > (0)::numeric)),
    CONSTRAINT nutrition_result_method_check CHECK ((method = ANY (ARRAY['生重'::text, '成品'::text]))),
    CONSTRAINT nutrition_result_target_type_check CHECK ((target_type = ANY (ARRAY['食材'::text, '菜式'::text])))
);


--
-- Name: nutrition_result_nutrition_result_id_seq; Type: SEQUENCE; Schema: app; Owner: -
--

ALTER TABLE app.nutrition_result ALTER COLUMN nutrition_result_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME app.nutrition_result_nutrition_result_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: plan_adjustment; Type: TABLE; Schema: app; Owner: -
--

CREATE TABLE app.plan_adjustment (
    adjustment_id bigint NOT NULL,
    meal_plan_id bigint NOT NULL,
    meal_slot_id bigint NOT NULL,
    request_message_id bigint,
    previous_candidate_id bigint,
    new_candidate_id bigint NOT NULL,
    instruction text NOT NULL,
    nutrition_change jsonb DEFAULT '{}'::jsonb NOT NULL,
    tool_name text NOT NULL,
    tool_version text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT plan_adjustment_candidate_change_check CHECK (((previous_candidate_id IS NULL) OR (previous_candidate_id <> new_candidate_id)))
);


--
-- Name: plan_adjustment_adjustment_id_seq; Type: SEQUENCE; Schema: app; Owner: -
--

ALTER TABLE app.plan_adjustment ALTER COLUMN adjustment_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME app.plan_adjustment_adjustment_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: profile; Type: TABLE; Schema: app; Owner: -
--

CREATE TABLE app.profile (
    profile_id bigint NOT NULL,
    user_id text NOT NULL,
    sex text,
    age integer,
    height_cm numeric,
    weight_kg numeric,
    activity_level text,
    goal text,
    allergies text[] DEFAULT '{}'::text[] NOT NULL,
    taboos text[] DEFAULT '{}'::text[] NOT NULL,
    conditions jsonb DEFAULT '{}'::jsonb NOT NULL,
    extras jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    birth_date date,
    name text,
    avatar text,
    gender text,
    goal_code text,
    cooking_equipment text[] DEFAULT '{}'::text[] NOT NULL,
    religious_ethical text[] DEFAULT '{}'::text[] NOT NULL,
    target_calories numeric,
    profile_version integer DEFAULT 1 NOT NULL,
    CONSTRAINT profile_age_check CHECK ((age >= 0)),
    CONSTRAINT profile_height_cm_check CHECK ((height_cm > (0)::numeric)),
    CONSTRAINT profile_target_calories_check CHECK (((target_calories IS NULL) OR (target_calories > (0)::numeric))),
    CONSTRAINT profile_weight_kg_check CHECK ((weight_kg > (0)::numeric))
);


--
-- Name: COLUMN profile.sex; Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON COLUMN app.profile.sex IS 'v1.1兼容字段；V2新接口使用gender。';


--
-- Name: COLUMN profile.goal; Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON COLUMN app.profile.goal IS 'v1.1兼容字段；V2新接口使用goal_code。';


--
-- Name: COLUMN profile.conditions; Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON COLUMN app.profile.conditions IS '疾病及确认状态JSON；规则判断只使用已确诊且满足执行条件的记录。';


--
-- Name: COLUMN profile.birth_date; Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON COLUMN app.profile.birth_date IS '用于精确计算婴幼儿月龄和年龄边界；age 字段保留作兼容或展示。';


--
-- Name: COLUMN profile.target_calories; Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON COLUMN app.profile.target_calories IS '由确定性工具按BMR×1.4计算，仅作份量量级参考，不由用户直接填写。';


--
-- Name: profile_profile_id_seq; Type: SEQUENCE; Schema: app; Owner: -
--

ALTER TABLE app.profile ALTER COLUMN profile_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME app.profile_profile_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: shopping_list; Type: TABLE; Schema: app; Owner: -
--

CREATE TABLE app.shopping_list (
    shopping_list_id bigint NOT NULL,
    meal_plan_id bigint NOT NULL,
    items jsonb DEFAULT '[]'::jsonb NOT NULL,
    generated_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT shopping_list_items_array_check CHECK ((jsonb_typeof(items) = 'array'::text))
);


--
-- Name: COLUMN shopping_list.items; Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON COLUMN app.shopping_list.items IS 'JSON数组；每项至少含ingredient_id、name、estimated_quantity、unit。数量为估算值，不含常备状态。';


--
-- Name: shopping_list_shopping_list_id_seq; Type: SEQUENCE; Schema: app; Owner: -
--

ALTER TABLE app.shopping_list ALTER COLUMN shopping_list_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME app.shopping_list_shopping_list_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: v_condition_rule_branch_acceptance; Type: VIEW; Schema: app; Owner: -
--

CREATE VIEW app.v_condition_rule_branch_acceptance AS
 SELECT 'within_limit'::text AS test_case,
    p.user_id,
    p.intake_date,
    p.rule_id,
    p.condition_id,
    p.condition_status,
    p.review_status,
    p.production_ready,
    p.comparator,
    p.applied_target,
    p.target_unit,
    p.known_total,
    p.record_count,
    p.missing_value_count,
    p.full_day_scope,
    p.evaluation_status,
    p.explanation_zh
   FROM app.preview_daily_condition_nutrient_rule('TEST-RULE-BASE'::text, '2026-10-26'::date, 'HTN-SODIUM-WHO-NHC-2000'::text) p(user_id, intake_date, rule_id, condition_id, condition_status, review_status, production_ready, comparator, applied_target, target_unit, known_total, record_count, missing_value_count, full_day_scope, evaluation_status, explanation_zh)
UNION ALL
 SELECT 'over_limit'::text AS test_case,
    p.user_id,
    p.intake_date,
    p.rule_id,
    p.condition_id,
    p.condition_status,
    p.review_status,
    p.production_ready,
    p.comparator,
    p.applied_target,
    p.target_unit,
    p.known_total,
    p.record_count,
    p.missing_value_count,
    p.full_day_scope,
    p.evaluation_status,
    p.explanation_zh
   FROM app.preview_daily_condition_nutrient_rule('TEST-RULE-BASE'::text, '2026-10-27'::date, 'HTN-SODIUM-WHO-NHC-2000'::text) p(user_id, intake_date, rule_id, condition_id, condition_status, review_status, production_ready, comparator, applied_target, target_unit, known_total, record_count, missing_value_count, full_day_scope, evaluation_status, explanation_zh)
UNION ALL
 SELECT 'missing_value'::text AS test_case,
    p.user_id,
    p.intake_date,
    p.rule_id,
    p.condition_id,
    p.condition_status,
    p.review_status,
    p.production_ready,
    p.comparator,
    p.applied_target,
    p.target_unit,
    p.known_total,
    p.record_count,
    p.missing_value_count,
    p.full_day_scope,
    p.evaluation_status,
    p.explanation_zh
   FROM app.preview_daily_condition_nutrient_rule('TEST-RULE-BASE'::text, '2026-10-28'::date, 'HTN-SODIUM-WHO-NHC-2000'::text) p(user_id, intake_date, rule_id, condition_id, condition_status, review_status, production_ready, comparator, applied_target, target_unit, known_total, record_count, missing_value_count, full_day_scope, evaluation_status, explanation_zh)
UNION ALL
 SELECT 'personal_override'::text AS test_case,
    p.user_id,
    p.intake_date,
    p.rule_id,
    p.condition_id,
    p.condition_status,
    p.review_status,
    p.production_ready,
    p.comparator,
    p.applied_target,
    p.target_unit,
    p.known_total,
    p.record_count,
    p.missing_value_count,
    p.full_day_scope,
    p.evaluation_status,
    p.explanation_zh
   FROM app.preview_daily_condition_nutrient_rule('TEST-RULE-OVERRIDE'::text, '2026-10-29'::date, 'HTN-SODIUM-WHO-NHC-2000'::text) p(user_id, intake_date, rule_id, condition_id, condition_status, review_status, production_ready, comparator, applied_target, target_unit, known_total, record_count, missing_value_count, full_day_scope, evaluation_status, explanation_zh);


--
-- Name: VIEW v_condition_rule_branch_acceptance; Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON VIEW app.v_condition_rule_branch_acceptance IS '完全虚构的规则分支验收结果，不用于真实营养判断。';


--
-- Name: v_condition_rule_catalog; Type: VIEW; Schema: app; Owner: -
--

CREATE VIEW app.v_condition_rule_catalog AS
SELECT
    NULL::text AS rule_id,
    NULL::text AS condition_id,
    NULL::text AS condition_name_zh,
    NULL::text AS rule_name_zh,
    NULL::text AS rule_kind,
    NULL::text AS nutrient_id,
    NULL::text AS nutrient_name_zh,
    NULL::text AS action,
    NULL::text AS comparator,
    NULL::numeric AS target_value,
    NULL::text AS target_unit,
    NULL::text AS time_basis,
    NULL::jsonb AS population,
    NULL::jsonb AS selector,
    NULL::text AS message_zh,
    NULL::text AS safety_note_zh,
    NULL::text AS review_status,
    NULL::boolean AS medical_review_required,
    NULL::boolean AS is_active,
    NULL::boolean AS production_ready,
    NULL::jsonb AS sources;


--
-- Name: VIEW v_condition_rule_catalog; Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON VIEW app.v_condition_rule_catalog IS '应用可读规则目录；production_ready=false 的规则只能预览或人工审核，不得自动给用户下结论。';


--
-- Name: condition_rule_review; Type: TABLE; Schema: audit; Owner: -
--

CREATE TABLE audit.condition_rule_review (
    review_id bigint NOT NULL,
    rule_id text NOT NULL,
    decision text NOT NULL,
    reviewer_name text NOT NULL,
    reviewer_role text NOT NULL,
    review_note text,
    reviewed_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT condition_rule_review_decision_check CHECK ((decision = ANY (ARRAY['approved'::text, 'changes_requested'::text, 'rejected'::text])))
);


--
-- Name: TABLE condition_rule_review; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON TABLE audit.condition_rule_review IS '营养师或医生对规则的审批记录；不允许只改 is_active 而跳过审核流程。';


--
-- Name: v_condition_rule_review_queue; Type: VIEW; Schema: app; Owner: -
--

CREATE VIEW app.v_condition_rule_review_queue AS
 SELECT c.rule_id,
    c.condition_id,
    c.condition_name_zh,
    c.rule_name_zh,
    c.rule_kind,
    c.target_value,
    c.target_unit,
    c.time_basis,
    c.review_status,
    c.is_active,
    c.production_ready,
    jsonb_array_length(c.sources) AS source_count,
    last_review.decision AS last_decision,
    last_review.reviewer_name AS last_reviewer_name,
    last_review.reviewer_role AS last_reviewer_role,
    last_review.reviewed_at AS last_reviewed_at
   FROM (app.v_condition_rule_catalog c
     LEFT JOIN LATERAL ( SELECT r.decision,
            r.reviewer_name,
            r.reviewer_role,
            r.reviewed_at
           FROM audit.condition_rule_review r
          WHERE (r.rule_id = c.rule_id)
          ORDER BY r.reviewed_at DESC, r.review_id DESC
         LIMIT 1) last_review ON (true));


--
-- Name: VIEW v_condition_rule_review_queue; Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON VIEW app.v_condition_rule_review_queue IS '规则审核工作台数据源；没有审核记录不等于审核通过。';


--
-- Name: dish; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.dish (
    dish_id text NOT NULL,
    name text NOT NULL,
    aliases text[] DEFAULT '{}'::text[] NOT NULL,
    category text,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    method_text text,
    cooking_rule_id text NOT NULL,
    servings numeric DEFAULT 1 NOT NULL,
    default_oil_g numeric DEFAULT 0 NOT NULL,
    default_salt_g numeric DEFAULT 0 NOT NULL,
    cook_time_min integer,
    nutrition_snapshot jsonb DEFAULT '{}'::jsonb NOT NULL,
    avoid_snapshot jsonb DEFAULT '{}'::jsonb NOT NULL,
    source_row jsonb NOT NULL,
    import_batch_id bigint NOT NULL,
    source text,
    source_id text,
    is_deleted boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT dish_default_oil_g_check CHECK ((default_oil_g >= (0)::numeric)),
    CONSTRAINT dish_default_salt_g_check CHECK ((default_salt_g >= (0)::numeric)),
    CONSTRAINT dish_servings_check CHECK ((servings > (0)::numeric))
);


--
-- Name: dish_ingredient; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.dish_ingredient (
    dish_ingredient_id bigint NOT NULL,
    dish_id text NOT NULL,
    ingredient_id bigint NOT NULL,
    amount_g numeric NOT NULL,
    cooked_amount_g numeric,
    role text,
    is_optional boolean DEFAULT false NOT NULL,
    generated_from text,
    source_snapshot jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT dish_ingredient_amount_g_check CHECK ((amount_g > (0)::numeric)),
    CONSTRAINT dish_ingredient_cooked_amount_g_check CHECK ((cooked_amount_g > (0)::numeric))
);


--
-- Name: ingredient; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.ingredient (
    ingredient_id bigint NOT NULL,
    food_id text NOT NULL,
    name text NOT NULL,
    aliases text[] DEFAULT '{}'::text[] NOT NULL,
    category text NOT NULL,
    state text NOT NULL,
    edible_portion_pct numeric(6,2) NOT NULL,
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
    sfa_g numeric,
    micro_nutrients jsonb DEFAULT '{}'::jsonb NOT NULL,
    fatty_acids jsonb DEFAULT '{}'::jsonb NOT NULL,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    allergens text[] DEFAULT '{}'::text[] NOT NULL,
    allergen_status text NOT NULL,
    purine_level text,
    cooked_factor numeric,
    oil_absorption_g_per_100g numeric,
    source_url text NOT NULL,
    source_id bigint,
    source_row jsonb NOT NULL,
    import_batch_id bigint NOT NULL,
    version text,
    is_deleted boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    data_quality text DEFAULT 'check'::text NOT NULL,
    CONSTRAINT ingredient_allergen_status_check CHECK ((allergen_status = ANY (ARRAY['已确认含'::text, '确认不含'::text, '未核查'::text]))),
    CONSTRAINT ingredient_calcium_mg_check CHECK ((calcium_mg >= (0)::numeric)),
    CONSTRAINT ingredient_carbohydrate_g_check CHECK ((carbohydrate_g >= (0)::numeric)),
    CONSTRAINT ingredient_cholesterol_mg_check CHECK ((cholesterol_mg >= (0)::numeric)),
    CONSTRAINT ingredient_data_quality_check CHECK ((data_quality = ANY (ARRAY['official'::text, 'approx'::text, 'check'::text]))),
    CONSTRAINT ingredient_edible_portion_pct_check CHECK (((edible_portion_pct >= (0)::numeric) AND (edible_portion_pct <= (100)::numeric))),
    CONSTRAINT ingredient_energy_kcal_check CHECK ((energy_kcal >= (0)::numeric)),
    CONSTRAINT ingredient_fat_g_check CHECK ((fat_g >= (0)::numeric)),
    CONSTRAINT ingredient_fiber_g_check CHECK ((fiber_g >= (0)::numeric)),
    CONSTRAINT ingredient_magnesium_mg_check CHECK ((magnesium_mg >= (0)::numeric)),
    CONSTRAINT ingredient_potassium_mg_check CHECK ((potassium_mg >= (0)::numeric)),
    CONSTRAINT ingredient_protein_g_check CHECK ((protein_g >= (0)::numeric)),
    CONSTRAINT ingredient_sfa_g_check CHECK ((sfa_g >= (0)::numeric)),
    CONSTRAINT ingredient_sodium_mg_check CHECK ((sodium_mg >= (0)::numeric))
);


--
-- Name: COLUMN ingredient.data_quality; Type: COMMENT; Schema: core; Owner: -
--

COMMENT ON COLUMN core.ingredient.data_quality IS '数据质量三态：official=权威来源直接对应；approx=估算；check=待核查。';


--
-- Name: v_dish_live_nutrition; Type: VIEW; Schema: app; Owner: -
--

CREATE VIEW app.v_dish_live_nutrition AS
 WITH nutrition AS (
         SELECT d_1.dish_id,
            (count(*))::integer AS ingredient_count,
                CASE
                    WHEN (count(*) FILTER (WHERE (i.energy_kcal IS NULL)) > 0) THEN NULL::numeric
                    ELSE round(sum(((di.amount_g * i.energy_kcal) / (100)::numeric)), 1)
                END AS energy_kcal,
                CASE
                    WHEN (count(*) FILTER (WHERE (i.protein_g IS NULL)) > 0) THEN NULL::numeric
                    ELSE round(sum(((di.amount_g * i.protein_g) / (100)::numeric)), 1)
                END AS protein_g,
                CASE
                    WHEN (count(*) FILTER (WHERE (i.sodium_mg IS NULL)) > 0) THEN NULL::numeric
                    ELSE round(sum(((di.amount_g * i.sodium_mg) / (100)::numeric)), 1)
                END AS sodium_mg,
                CASE
                    WHEN (count(*) FILTER (WHERE (i.calcium_mg IS NULL)) > 0) THEN NULL::numeric
                    ELSE round(sum(((di.amount_g * i.calcium_mg) / (100)::numeric)), 1)
                END AS calcium_mg,
            (count(*) FILTER (WHERE (i.energy_kcal IS NULL)) = 0) AS energy_complete,
            (count(*) FILTER (WHERE (i.protein_g IS NULL)) = 0) AS protein_complete,
            (count(*) FILTER (WHERE (i.sodium_mg IS NULL)) = 0) AS sodium_complete,
            (count(*) FILTER (WHERE (i.calcium_mg IS NULL)) = 0) AS calcium_complete,
            COALESCE(array_agg(DISTINCT i.food_id ORDER BY i.food_id) FILTER (WHERE (i.allergen_status = '未核查'::text)), ARRAY[]::text[]) AS unverified_food_ids
           FROM ((core.dish d_1
             JOIN core.dish_ingredient di ON ((di.dish_id = d_1.dish_id)))
             JOIN core.ingredient i ON ((i.ingredient_id = di.ingredient_id)))
          WHERE ((NOT d_1.is_deleted) AND (NOT i.is_deleted))
          GROUP BY d_1.dish_id
        ), allergens AS (
         SELECT d_1.dish_id,
            COALESCE(array_agg(DISTINCT allergen.allergen ORDER BY allergen.allergen) FILTER (WHERE ((i.allergen_status = '已确认含'::text) AND (allergen.allergen IS NOT NULL))), ARRAY[]::text[]) AS strict_allergens
           FROM (((core.dish d_1
             JOIN core.dish_ingredient di ON ((di.dish_id = d_1.dish_id)))
             JOIN core.ingredient i ON ((i.ingredient_id = di.ingredient_id)))
             LEFT JOIN LATERAL unnest(i.allergens) allergen(allergen) ON (true))
          WHERE ((NOT d_1.is_deleted) AND (NOT i.is_deleted))
          GROUP BY d_1.dish_id
        )
 SELECT d.dish_id,
    d.name,
    d.tags,
    d.method_text,
    d.cooking_rule_id,
    d.servings,
    d.default_oil_g,
    d.default_salt_g,
    nutrition.ingredient_count,
    nutrition.energy_kcal,
    nutrition.protein_g,
    nutrition.sodium_mg,
    nutrition.energy_complete,
    nutrition.protein_complete,
    nutrition.sodium_complete,
    allergens.strict_allergens,
    nutrition.unverified_food_ids,
    (cardinality(nutrition.unverified_food_ids) = 0) AS allergen_verification_complete,
    d.source,
    d.source_id,
    nutrition.calcium_mg,
    nutrition.calcium_complete
   FROM ((core.dish d
     JOIN nutrition ON ((nutrition.dish_id = d.dish_id)))
     JOIN allergens ON ((allergens.dish_id = d.dish_id)))
  WHERE (NOT d.is_deleted);


--
-- Name: VIEW v_dish_live_nutrition; Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON VIEW app.v_dish_live_nutrition IS '按当前食材事实表实时重算菜谱营养与过敏原，不依赖旧快照。';


--
-- Name: v_ingredient_search; Type: VIEW; Schema: app; Owner: -
--

CREATE VIEW app.v_ingredient_search AS
 SELECT food_id,
    name,
    aliases,
    category,
    state,
    edible_portion_pct,
    energy_kcal,
    protein_g,
    fat_g,
    carbohydrate_g,
    fiber_g,
    sodium_mg,
    potassium_mg,
    calcium_mg,
    magnesium_mg,
    allergens,
    allergen_status,
    purine_level,
    source_url,
    ((protein_g IS NULL) OR (fat_g IS NULL) OR (carbohydrate_g IS NULL)) AS has_missing_macro,
    concat_ws(' '::text, name, array_to_string(aliases, ' '::text), category, state) AS search_text
   FROM core.ingredient i
  WHERE (NOT is_deleted);


--
-- Name: VIEW v_ingredient_search; Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON VIEW app.v_ingredient_search IS '面向应用的食材搜索视图；保留 NULL，不把缺失营养值显示为 0。';


--
-- Name: nutrient; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.nutrient (
    nutrient_id text NOT NULL,
    name_zh text NOT NULL,
    unit text NOT NULL,
    description text
);


--
-- Name: v_key_micronutrient; Type: VIEW; Schema: app; Owner: -
--

CREATE VIEW app.v_key_micronutrient AS
 SELECT nutrient_id,
    name_zh,
    unit,
        CASE nutrient_id
            WHEN 'calcium'::text THEN 1
            WHEN 'iron'::text THEN 2
            WHEN 'zinc'::text THEN 3
            WHEN 'vitamin_a'::text THEN 4
            WHEN 'vitamin_b1'::text THEN 5
            WHEN 'vitamin_b2'::text THEN 6
            WHEN 'vitamin_c'::text THEN 7
            ELSE NULL::integer
        END AS display_order
   FROM core.nutrient n
  WHERE (nutrient_id = ANY (ARRAY['calcium'::text, 'iron'::text, 'zinc'::text, 'vitamin_a'::text, 'vitamin_b1'::text, 'vitamin_b2'::text, 'vitamin_c'::text]));


--
-- Name: VIEW v_key_micronutrient; Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON VIEW app.v_key_micronutrient IS '产品V2动态平衡的7种关键微量；参考目标仍由core.nutrient_reference匹配。';


--
-- Name: v_production_condition_rules; Type: VIEW; Schema: app; Owner: -
--

CREATE VIEW app.v_production_condition_rules WITH (security_barrier='true') AS
 SELECT rule_id,
    condition_id,
    condition_name_zh,
    rule_name_zh,
    rule_kind,
    nutrient_id,
    nutrient_name_zh,
    action,
    comparator,
    target_value,
    target_unit,
    time_basis,
    population,
    selector,
    message_zh,
    safety_note_zh,
    sources
   FROM app.v_condition_rule_catalog
  WHERE ((review_status = 'approved'::text) AND is_active AND production_ready);


--
-- Name: VIEW v_production_condition_rules; Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON VIEW app.v_production_condition_rules IS '普通应用唯一可读的疾病规则目录，只包含已审核且已启用规则。';


--
-- Name: weekly_nutrition_report; Type: TABLE; Schema: app; Owner: -
--

CREATE TABLE app.weekly_nutrition_report (
    weekly_report_id bigint NOT NULL,
    user_id text NOT NULL,
    week_start date NOT NULL,
    week_end date NOT NULL,
    summary jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT weekly_nutrition_report_check CHECK ((week_end >= week_start))
);


--
-- Name: TABLE weekly_nutrition_report; Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON TABLE app.weekly_nutrition_report IS 'v1.1兼容表；V2新报告使用app.nutrition_report。';


--
-- Name: weekly_nutrition_report_weekly_report_id_seq; Type: SEQUENCE; Schema: app; Owner: -
--

ALTER TABLE app.weekly_nutrition_report ALTER COLUMN weekly_report_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME app.weekly_nutrition_report_weekly_report_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: condition_rule_review_review_id_seq; Type: SEQUENCE; Schema: audit; Owner: -
--

ALTER TABLE audit.condition_rule_review ALTER COLUMN review_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME audit.condition_rule_review_review_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: import_batch; Type: TABLE; Schema: audit; Owner: -
--

CREATE TABLE audit.import_batch (
    import_batch_id bigint NOT NULL,
    dataset_name text NOT NULL,
    dataset_version text,
    original_file_name text NOT NULL,
    original_sha256 text NOT NULL,
    imported_at timestamp with time zone DEFAULT now() NOT NULL,
    imported_by text DEFAULT CURRENT_USER,
    status text DEFAULT 'loaded'::text NOT NULL,
    notes text,
    CONSTRAINT import_batch_status_check CHECK ((status = ANY (ARRAY['loaded'::text, 'validated'::text, 'promoted'::text, 'rejected'::text])))
);


--
-- Name: import_batch_import_batch_id_seq; Type: SEQUENCE; Schema: audit; Owner: -
--

ALTER TABLE audit.import_batch ALTER COLUMN import_batch_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME audit.import_batch_import_batch_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: import_issue; Type: TABLE; Schema: audit; Owner: -
--

CREATE TABLE audit.import_issue (
    issue_id bigint NOT NULL,
    import_batch_id bigint NOT NULL,
    severity text NOT NULL,
    dataset_name text NOT NULL,
    record_key text,
    field_name text,
    issue_code text NOT NULL,
    issue_detail text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    resolved_at timestamp with time zone,
    resolution_detail text,
    CONSTRAINT import_issue_severity_check CHECK ((severity = ANY (ARRAY['P0'::text, 'P1'::text, 'P2'::text])))
);


--
-- Name: import_issue_issue_id_seq; Type: SEQUENCE; Schema: audit; Owner: -
--

ALTER TABLE audit.import_issue ALTER COLUMN issue_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME audit.import_issue_issue_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: schema_migration; Type: TABLE; Schema: audit; Owner: -
--

CREATE TABLE audit.schema_migration (
    migration_id text NOT NULL,
    description text NOT NULL,
    applied_at timestamp with time zone DEFAULT now() NOT NULL,
    applied_by text DEFAULT CURRENT_USER NOT NULL
);


--
-- Name: condition_nutrient_rule; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.condition_nutrient_rule (
    rule_id text NOT NULL,
    condition_id text NOT NULL,
    rule_name_zh text NOT NULL,
    rule_kind text NOT NULL,
    nutrient_id text,
    action text NOT NULL,
    comparator text,
    target_value numeric,
    target_value_upper numeric,
    target_unit text,
    time_basis text,
    population jsonb DEFAULT '{}'::jsonb NOT NULL,
    selector jsonb DEFAULT '{}'::jsonb NOT NULL,
    evaluator jsonb DEFAULT '{}'::jsonb NOT NULL,
    message_zh text NOT NULL,
    safety_note_zh text,
    source_interpretation text,
    review_status text DEFAULT 'pending_medical_review'::text NOT NULL,
    medical_review_required boolean DEFAULT true NOT NULL,
    is_active boolean DEFAULT false NOT NULL,
    version text NOT NULL,
    effective_from date,
    effective_to date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT condition_nutrient_rule_action_check CHECK ((action = ANY (ARRAY['limit'::text, 'prefer'::text, 'review_required'::text, 'not_evaluable'::text]))),
    CONSTRAINT condition_nutrient_rule_check CHECK (((rule_kind <> ALL (ARRAY['nutrient_limit'::text, 'nutrient_target'::text])) OR ((nutrient_id IS NOT NULL) AND (target_value IS NOT NULL) AND (target_unit IS NOT NULL)))),
    CONSTRAINT condition_nutrient_rule_check1 CHECK (((NOT is_active) OR (review_status = 'approved'::text))),
    CONSTRAINT condition_nutrient_rule_check2 CHECK (((effective_to IS NULL) OR (effective_from IS NULL) OR (effective_to >= effective_from))),
    CONSTRAINT condition_nutrient_rule_comparator_check CHECK (((comparator = ANY (ARRAY['<'::text, '<='::text, '>='::text, '>'::text, 'range'::text])) OR (comparator IS NULL))),
    CONSTRAINT condition_nutrient_rule_review_status_check CHECK ((review_status = ANY (ARRAY['draft'::text, 'pending_medical_review'::text, 'approved'::text, 'rejected'::text, 'retired'::text]))),
    CONSTRAINT condition_nutrient_rule_rule_kind_check CHECK ((rule_kind = ANY (ARRAY['nutrient_limit'::text, 'nutrient_target'::text, 'pattern_preference'::text, 'review_gate'::text])))
);


--
-- Name: TABLE condition_nutrient_rule; Type: COMMENT; Schema: core; Owner: -
--

COMMENT ON TABLE core.condition_nutrient_rule IS '经结构化但尚需审核的疾病/目标营养规则；只有 approved 且 is_active=true 才能进入正式自动决策。';


--
-- Name: condition_rule_source; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.condition_rule_source (
    rule_id text NOT NULL,
    source_id bigint NOT NULL,
    source_role text NOT NULL,
    source_detail text,
    CONSTRAINT condition_rule_source_source_role_check CHECK ((source_role = ANY (ARRAY['threshold'::text, 'pattern'::text, 'safety'::text, 'context'::text, 'correction'::text])))
);


--
-- Name: TABLE condition_rule_source; Type: COMMENT; Schema: core; Owner: -
--

COMMENT ON TABLE core.condition_rule_source IS '逐条记录规则的阈值、膳食模式、安全提示等来源，避免一个来源被错误用于所有规则。';


--
-- Name: cooking_rule; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.cooking_rule (
    rule_id text NOT NULL,
    cooking_method text NOT NULL,
    aliases text[] DEFAULT '{}'::text[] NOT NULL,
    oil_g_min numeric NOT NULL,
    oil_g_max numeric NOT NULL,
    oil_g_default numeric NOT NULL,
    oil_level text NOT NULL,
    salt_equiv_g_min numeric NOT NULL,
    salt_equiv_g_max numeric NOT NULL,
    salt_equiv_g_default numeric NOT NULL,
    salt_level text NOT NULL,
    added_sugar_g_min numeric NOT NULL,
    added_sugar_g_max numeric NOT NULL,
    added_sugar_g_default numeric NOT NULL,
    added_sugar_level text NOT NULL,
    method_applicability text,
    core_assumptions text,
    adjustment_rules text,
    source_meta jsonb DEFAULT '{}'::jsonb NOT NULL,
    import_batch_id bigint NOT NULL,
    CONSTRAINT cooking_rule_check CHECK (((oil_g_min <= oil_g_default) AND (oil_g_default <= oil_g_max))),
    CONSTRAINT cooking_rule_check1 CHECK (((salt_equiv_g_min <= salt_equiv_g_default) AND (salt_equiv_g_default <= salt_equiv_g_max))),
    CONSTRAINT cooking_rule_check2 CHECK (((added_sugar_g_min <= added_sugar_g_default) AND (added_sugar_g_default <= added_sugar_g_max)))
);


--
-- Name: data_source; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.data_source (
    source_id bigint NOT NULL,
    source_name text NOT NULL,
    source_url text,
    publisher text,
    version text,
    accessed_on date,
    notes text
);


--
-- Name: data_source_source_id_seq; Type: SEQUENCE; Schema: core; Owner: -
--

ALTER TABLE core.data_source ALTER COLUMN source_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME core.data_source_source_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: dietary_rule_set; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.dietary_rule_set (
    rule_set_id bigint NOT NULL,
    rule_set_name text NOT NULL,
    version text NOT NULL,
    payload jsonb NOT NULL,
    source_meta jsonb DEFAULT '{}'::jsonb NOT NULL,
    import_batch_id bigint NOT NULL,
    is_active boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: dietary_rule_set_rule_set_id_seq; Type: SEQUENCE; Schema: core; Owner: -
--

ALTER TABLE core.dietary_rule_set ALTER COLUMN rule_set_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME core.dietary_rule_set_rule_set_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: dish_ingredient_dish_ingredient_id_seq; Type: SEQUENCE; Schema: core; Owner: -
--

ALTER TABLE core.dish_ingredient ALTER COLUMN dish_ingredient_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME core.dish_ingredient_dish_ingredient_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: food_id_mapping; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.food_id_mapping (
    old_food_id text NOT NULL,
    old_food_name text,
    new_food_id text NOT NULL,
    new_food_name text,
    mapping_basis text,
    import_batch_id bigint NOT NULL
);


--
-- Name: goal_structure_map; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.goal_structure_map (
    goal_code text NOT NULL,
    goal_name text NOT NULL,
    macro_policy jsonb NOT NULL,
    oil_salt_sugar_policy jsonb DEFAULT '{}'::jsonb NOT NULL,
    ingredient_method_policy jsonb DEFAULT '{}'::jsonb NOT NULL,
    activity_factor numeric DEFAULT 1.4 NOT NULL,
    energy_policy text NOT NULL,
    source_note text NOT NULL,
    version text DEFAULT 'product-v2.0'::text NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT goal_structure_map_activity_factor_check CHECK ((activity_factor > (0)::numeric)),
    CONSTRAINT goal_structure_map_code_check CHECK ((goal_code = ANY (ARRAY['maintain'::text, 'fat_loss'::text, 'muscle_gain'::text, 'glucose_control'::text, 'digestive_health'::text])))
);


--
-- Name: TABLE goal_structure_map; Type: COMMENT; Schema: core; Owner: -
--

COMMENT ON TABLE core.goal_structure_map IS '项目级健康目标结构映射；数值与倾向来自产品方案 V2.0，不表述为通用医学标准。';


--
-- Name: health_condition; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.health_condition (
    condition_id text NOT NULL,
    name_zh text NOT NULL,
    category text NOT NULL,
    aliases text[] DEFAULT '{}'::text[] NOT NULL,
    description text,
    activation_status text DEFAULT 'confirmed'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT health_condition_category_check CHECK ((category = ANY (ARRAY['慢性疾病'::text, '健康目标'::text, '食物过敏'::text, '其他'::text])))
);


--
-- Name: ingredient_ingredient_id_seq; Type: SEQUENCE; Schema: core; Owner: -
--

ALTER TABLE core.ingredient ALTER COLUMN ingredient_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME core.ingredient_ingredient_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: nutrient_reference; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.nutrient_reference (
    nutrient_reference_id bigint NOT NULL,
    nutrient_id text NOT NULL,
    sex text NOT NULL,
    age_group text NOT NULL,
    age_min_months integer,
    age_max_months integer,
    life_stage text DEFAULT '普通'::text NOT NULL,
    menstrual_status text DEFAULT ''::text NOT NULL,
    reference_type text NOT NULL,
    value numeric,
    ul_value numeric,
    note text,
    source_id bigint,
    source_row jsonb NOT NULL,
    import_batch_id bigint NOT NULL,
    version text,
    CONSTRAINT nutrient_reference_reference_type_check CHECK ((reference_type = ANY (ARRAY['RNI'::text, 'AI'::text])))
);


--
-- Name: nutrient_reference_nutrient_reference_id_seq; Type: SEQUENCE; Schema: core; Owner: -
--

ALTER TABLE core.nutrient_reference ALTER COLUMN nutrient_reference_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME core.nutrient_reference_nutrient_reference_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: symptom_nutrient_map; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.symptom_nutrient_map (
    symptom_nutrient_map_id bigint NOT NULL,
    symptom text NOT NULL,
    aliases text[] DEFAULT '{}'::text[] NOT NULL,
    nutrient_id text NOT NULL,
    advice text NOT NULL,
    evidence_level text,
    source_id bigint,
    is_reviewed boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    review_status text DEFAULT 'pending'::text NOT NULL,
    reviewer text,
    reviewed_at timestamp with time zone,
    is_active boolean DEFAULT false NOT NULL,
    CONSTRAINT symptom_nutrient_map_review_fields_check CHECK (((review_status <> 'approved'::text) OR ((reviewer IS NOT NULL) AND (reviewed_at IS NOT NULL) AND (source_id IS NOT NULL)))),
    CONSTRAINT symptom_nutrient_map_review_status_check CHECK ((review_status = ANY (ARRAY['pending'::text, 'approved'::text, 'rejected'::text])))
);


--
-- Name: symptom_nutrient_map_symptom_nutrient_map_id_seq; Type: SEQUENCE; Schema: core; Owner: -
--

ALTER TABLE core.symptom_nutrient_map ALTER COLUMN symptom_nutrient_map_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME core.symptom_nutrient_map_symptom_nutrient_map_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: knowledge_doc; Type: TABLE; Schema: knowledge; Owner: -
--

CREATE TABLE knowledge.knowledge_doc (
    knowledge_doc_id bigint NOT NULL,
    stable_key text NOT NULL,
    title text NOT NULL,
    content text NOT NULL,
    category text NOT NULL,
    source text NOT NULL,
    source_id text,
    meta_data jsonb DEFAULT '{}'::jsonb NOT NULL,
    is_deleted boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE knowledge_doc; Type: COMMENT; Schema: knowledge; Owner: -
--

COMMENT ON TABLE knowledge.knowledge_doc IS '嵌入模型和向量维度确认前不创建 embedding 列。';


--
-- Name: knowledge_doc_knowledge_doc_id_seq; Type: SEQUENCE; Schema: knowledge; Owner: -
--

ALTER TABLE knowledge.knowledge_doc ALTER COLUMN knowledge_doc_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME knowledge.knowledge_doc_knowledge_doc_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: nutrient_knowledge; Type: TABLE; Schema: knowledge; Owner: -
--

CREATE TABLE knowledge.nutrient_knowledge (
    nutrient_id text NOT NULL,
    payload jsonb NOT NULL,
    import_batch_id bigint NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: cooking_rule_raw; Type: TABLE; Schema: staging; Owner: -
--

CREATE TABLE staging.cooking_rule_raw (
    import_batch_id bigint NOT NULL,
    row_no integer NOT NULL,
    rule_id text,
    cooking_method text,
    aliases text,
    oil_g_min text,
    oil_g_max text,
    oil_g_default text,
    oil_level text,
    salt_equiv_g_min text,
    salt_equiv_g_max text,
    salt_equiv_g_default text,
    salt_level text,
    added_sugar_g_min text,
    added_sugar_g_max text,
    added_sugar_g_default text,
    added_sugar_level text,
    method_applicability text,
    core_assumptions text,
    adjustment_rules text
);


--
-- Name: document_raw; Type: TABLE; Schema: staging; Owner: -
--

CREATE TABLE staging.document_raw (
    import_batch_id bigint NOT NULL,
    document_type text NOT NULL,
    source_path text NOT NULL,
    payload jsonb NOT NULL
);


--
-- Name: food_id_mapping_raw; Type: TABLE; Schema: staging; Owner: -
--

CREATE TABLE staging.food_id_mapping_raw (
    import_batch_id bigint NOT NULL,
    row_no integer NOT NULL,
    old_food_id text,
    old_food_name text,
    new_food_id text,
    new_food_name text,
    mapping_basis text
);


--
-- Name: food_raw; Type: TABLE; Schema: staging; Owner: -
--

CREATE TABLE staging.food_raw (
    import_batch_id bigint NOT NULL,
    row_no integer NOT NULL,
    food_id text,
    name text,
    aliases text,
    category text,
    state text,
    source_url text,
    edible_pct text,
    water_g text,
    energy_kj text,
    energy_kcal text,
    protein_g text,
    fat_g text,
    cholesterol_mg text,
    ash_g text,
    carbohydrate_g text,
    fiber_g text,
    carotene_ug text,
    vitamin_a_ug text,
    vitamin_e_ate text,
    vitamin_b1_mg text,
    vitamin_b2_mg text,
    vitamin_b3_mg text,
    vitamin_c_mg text,
    calcium_mg text,
    phosphorus_mg text,
    potassium_mg text,
    sodium_mg text,
    magnesium_mg text,
    iron_mg text,
    zinc_mg text,
    selenium_ug text,
    copper_mg text,
    manganese_mg text,
    iodine_ug text,
    sfa_pct text,
    sfa_g text,
    mufa_pct text,
    mufa_g text,
    pufa_pct text,
    pufa_g text,
    fatty_acid_total_pct text,
    fatty_acid_total_g text,
    tags text,
    allergens text,
    allergen_status text,
    purine_level text
);


--
-- Name: conversation conversation_pkey; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.conversation
    ADD CONSTRAINT conversation_pkey PRIMARY KEY (conversation_id);


--
-- Name: meal_candidate_dish meal_candidate_dish_pkey; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.meal_candidate_dish
    ADD CONSTRAINT meal_candidate_dish_pkey PRIMARY KEY (candidate_id, dish_id);


--
-- Name: meal_candidate meal_candidate_id_slot_key; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.meal_candidate
    ADD CONSTRAINT meal_candidate_id_slot_key UNIQUE (candidate_id, meal_slot_id);


--
-- Name: meal_candidate meal_candidate_pkey; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.meal_candidate
    ADD CONSTRAINT meal_candidate_pkey PRIMARY KEY (candidate_id);


--
-- Name: meal_candidate meal_candidate_slot_rank_key; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.meal_candidate
    ADD CONSTRAINT meal_candidate_slot_rank_key UNIQUE (meal_slot_id, rank);


--
-- Name: meal_plan meal_plan_pkey; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.meal_plan
    ADD CONSTRAINT meal_plan_pkey PRIMARY KEY (meal_plan_id);


--
-- Name: meal_slot meal_slot_pkey; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.meal_slot
    ADD CONSTRAINT meal_slot_pkey PRIMARY KEY (meal_slot_id);


--
-- Name: meal_slot meal_slot_plan_date_type_order_key; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.meal_slot
    ADD CONSTRAINT meal_slot_plan_date_type_order_key UNIQUE (meal_plan_id, slot_date, meal_type, display_order);


--
-- Name: message message_pkey; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.message
    ADD CONSTRAINT message_pkey PRIMARY KEY (message_id);


--
-- Name: nutrition_report nutrition_report_pkey; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.nutrition_report
    ADD CONSTRAINT nutrition_report_pkey PRIMARY KEY (nutrition_report_id);


--
-- Name: nutrition_report_plan nutrition_report_plan_pkey; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.nutrition_report_plan
    ADD CONSTRAINT nutrition_report_plan_pkey PRIMARY KEY (nutrition_report_id, meal_plan_id);


--
-- Name: nutrition_report nutrition_report_source_weekly_report_id_key; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.nutrition_report
    ADD CONSTRAINT nutrition_report_source_weekly_report_id_key UNIQUE (source_weekly_report_id);


--
-- Name: nutrition_result nutrition_result_pkey; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.nutrition_result
    ADD CONSTRAINT nutrition_result_pkey PRIMARY KEY (nutrition_result_id);


--
-- Name: plan_adjustment plan_adjustment_pkey; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.plan_adjustment
    ADD CONSTRAINT plan_adjustment_pkey PRIMARY KEY (adjustment_id);


--
-- Name: profile profile_pkey; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.profile
    ADD CONSTRAINT profile_pkey PRIMARY KEY (profile_id);


--
-- Name: profile profile_user_id_key; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.profile
    ADD CONSTRAINT profile_user_id_key UNIQUE (user_id);


--
-- Name: shopping_list shopping_list_meal_plan_id_key; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.shopping_list
    ADD CONSTRAINT shopping_list_meal_plan_id_key UNIQUE (meal_plan_id);


--
-- Name: shopping_list shopping_list_pkey; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.shopping_list
    ADD CONSTRAINT shopping_list_pkey PRIMARY KEY (shopping_list_id);


--
-- Name: weekly_nutrition_report weekly_nutrition_report_pkey; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.weekly_nutrition_report
    ADD CONSTRAINT weekly_nutrition_report_pkey PRIMARY KEY (weekly_report_id);


--
-- Name: weekly_nutrition_report weekly_nutrition_report_user_id_week_start_week_end_key; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.weekly_nutrition_report
    ADD CONSTRAINT weekly_nutrition_report_user_id_week_start_week_end_key UNIQUE (user_id, week_start, week_end);


--
-- Name: condition_rule_review condition_rule_review_pkey; Type: CONSTRAINT; Schema: audit; Owner: -
--

ALTER TABLE ONLY audit.condition_rule_review
    ADD CONSTRAINT condition_rule_review_pkey PRIMARY KEY (review_id);


--
-- Name: import_batch import_batch_pkey; Type: CONSTRAINT; Schema: audit; Owner: -
--

ALTER TABLE ONLY audit.import_batch
    ADD CONSTRAINT import_batch_pkey PRIMARY KEY (import_batch_id);


--
-- Name: import_issue import_issue_pkey; Type: CONSTRAINT; Schema: audit; Owner: -
--

ALTER TABLE ONLY audit.import_issue
    ADD CONSTRAINT import_issue_pkey PRIMARY KEY (issue_id);


--
-- Name: schema_migration schema_migration_pkey; Type: CONSTRAINT; Schema: audit; Owner: -
--

ALTER TABLE ONLY audit.schema_migration
    ADD CONSTRAINT schema_migration_pkey PRIMARY KEY (migration_id);


--
-- Name: condition_nutrient_rule condition_nutrient_rule_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.condition_nutrient_rule
    ADD CONSTRAINT condition_nutrient_rule_pkey PRIMARY KEY (rule_id);


--
-- Name: condition_rule_source condition_rule_source_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.condition_rule_source
    ADD CONSTRAINT condition_rule_source_pkey PRIMARY KEY (rule_id, source_id, source_role);


--
-- Name: cooking_rule cooking_rule_cooking_method_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.cooking_rule
    ADD CONSTRAINT cooking_rule_cooking_method_key UNIQUE (cooking_method);


--
-- Name: cooking_rule cooking_rule_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.cooking_rule
    ADD CONSTRAINT cooking_rule_pkey PRIMARY KEY (rule_id);


--
-- Name: data_source data_source_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.data_source
    ADD CONSTRAINT data_source_pkey PRIMARY KEY (source_id);


--
-- Name: data_source data_source_source_name_source_url_version_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.data_source
    ADD CONSTRAINT data_source_source_name_source_url_version_key UNIQUE (source_name, source_url, version);


--
-- Name: dietary_rule_set dietary_rule_set_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dietary_rule_set
    ADD CONSTRAINT dietary_rule_set_pkey PRIMARY KEY (rule_set_id);


--
-- Name: dietary_rule_set dietary_rule_set_rule_set_name_version_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dietary_rule_set
    ADD CONSTRAINT dietary_rule_set_rule_set_name_version_key UNIQUE (rule_set_name, version);


--
-- Name: dish_ingredient dish_ingredient_dish_id_ingredient_id_role_generated_from_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dish_ingredient
    ADD CONSTRAINT dish_ingredient_dish_id_ingredient_id_role_generated_from_key UNIQUE (dish_id, ingredient_id, role, generated_from);


--
-- Name: dish_ingredient dish_ingredient_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dish_ingredient
    ADD CONSTRAINT dish_ingredient_pkey PRIMARY KEY (dish_ingredient_id);


--
-- Name: dish dish_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dish
    ADD CONSTRAINT dish_pkey PRIMARY KEY (dish_id);


--
-- Name: food_id_mapping food_id_mapping_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.food_id_mapping
    ADD CONSTRAINT food_id_mapping_pkey PRIMARY KEY (old_food_id);


--
-- Name: goal_structure_map goal_structure_map_goal_name_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.goal_structure_map
    ADD CONSTRAINT goal_structure_map_goal_name_key UNIQUE (goal_name);


--
-- Name: goal_structure_map goal_structure_map_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.goal_structure_map
    ADD CONSTRAINT goal_structure_map_pkey PRIMARY KEY (goal_code);


--
-- Name: health_condition health_condition_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.health_condition
    ADD CONSTRAINT health_condition_pkey PRIMARY KEY (condition_id);


--
-- Name: ingredient ingredient_food_id_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.ingredient
    ADD CONSTRAINT ingredient_food_id_key UNIQUE (food_id);


--
-- Name: ingredient ingredient_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.ingredient
    ADD CONSTRAINT ingredient_pkey PRIMARY KEY (ingredient_id);


--
-- Name: nutrient nutrient_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.nutrient
    ADD CONSTRAINT nutrient_pkey PRIMARY KEY (nutrient_id);


--
-- Name: nutrient_reference nutrient_reference_nutrient_id_sex_age_group_life_stage_men_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.nutrient_reference
    ADD CONSTRAINT nutrient_reference_nutrient_id_sex_age_group_life_stage_men_key UNIQUE (nutrient_id, sex, age_group, life_stage, menstrual_status, reference_type, version);


--
-- Name: nutrient_reference nutrient_reference_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.nutrient_reference
    ADD CONSTRAINT nutrient_reference_pkey PRIMARY KEY (nutrient_reference_id);


--
-- Name: symptom_nutrient_map symptom_nutrient_map_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.symptom_nutrient_map
    ADD CONSTRAINT symptom_nutrient_map_pkey PRIMARY KEY (symptom_nutrient_map_id);


--
-- Name: knowledge_doc knowledge_doc_pkey; Type: CONSTRAINT; Schema: knowledge; Owner: -
--

ALTER TABLE ONLY knowledge.knowledge_doc
    ADD CONSTRAINT knowledge_doc_pkey PRIMARY KEY (knowledge_doc_id);


--
-- Name: knowledge_doc knowledge_doc_stable_key_key; Type: CONSTRAINT; Schema: knowledge; Owner: -
--

ALTER TABLE ONLY knowledge.knowledge_doc
    ADD CONSTRAINT knowledge_doc_stable_key_key UNIQUE (stable_key);


--
-- Name: nutrient_knowledge nutrient_knowledge_pkey; Type: CONSTRAINT; Schema: knowledge; Owner: -
--

ALTER TABLE ONLY knowledge.nutrient_knowledge
    ADD CONSTRAINT nutrient_knowledge_pkey PRIMARY KEY (nutrient_id);


--
-- Name: cooking_rule_raw cooking_rule_raw_pkey; Type: CONSTRAINT; Schema: staging; Owner: -
--

ALTER TABLE ONLY staging.cooking_rule_raw
    ADD CONSTRAINT cooking_rule_raw_pkey PRIMARY KEY (import_batch_id, row_no);


--
-- Name: document_raw document_raw_pkey; Type: CONSTRAINT; Schema: staging; Owner: -
--

ALTER TABLE ONLY staging.document_raw
    ADD CONSTRAINT document_raw_pkey PRIMARY KEY (import_batch_id, document_type, source_path);


--
-- Name: food_id_mapping_raw food_id_mapping_raw_pkey; Type: CONSTRAINT; Schema: staging; Owner: -
--

ALTER TABLE ONLY staging.food_id_mapping_raw
    ADD CONSTRAINT food_id_mapping_raw_pkey PRIMARY KEY (import_batch_id, row_no);


--
-- Name: food_raw food_raw_pkey; Type: CONSTRAINT; Schema: staging; Owner: -
--

ALTER TABLE ONLY staging.food_raw
    ADD CONSTRAINT food_raw_pkey PRIMARY KEY (import_batch_id, row_no);


--
-- Name: meal_candidate_dish_dish_idx; Type: INDEX; Schema: app; Owner: -
--

CREATE INDEX meal_candidate_dish_dish_idx ON app.meal_candidate_dish USING btree (dish_id);


--
-- Name: meal_candidate_slot_idx; Type: INDEX; Schema: app; Owner: -
--

CREATE INDEX meal_candidate_slot_idx ON app.meal_candidate USING btree (meal_slot_id, rank);


--
-- Name: meal_plan_user_period_idx; Type: INDEX; Schema: app; Owner: -
--

CREATE INDEX meal_plan_user_period_idx ON app.meal_plan USING btree (user_id, start_date DESC, end_date DESC) WHERE (NOT is_deleted);


--
-- Name: meal_plan_user_status_idx; Type: INDEX; Schema: app; Owner: -
--

CREATE INDEX meal_plan_user_status_idx ON app.meal_plan USING btree (user_id, status, fixed_at DESC) WHERE (NOT is_deleted);


--
-- Name: meal_slot_plan_date_idx; Type: INDEX; Schema: app; Owner: -
--

CREATE INDEX meal_slot_plan_date_idx ON app.meal_slot USING btree (meal_plan_id, slot_date, display_order);


--
-- Name: message_conversation_created_idx; Type: INDEX; Schema: app; Owner: -
--

CREATE INDEX message_conversation_created_idx ON app.message USING btree (conversation_id, created_at);


--
-- Name: message_referenced_plan_idx; Type: INDEX; Schema: app; Owner: -
--

CREATE INDEX message_referenced_plan_idx ON app.message USING btree (referenced_plan_id) WHERE (referenced_plan_id IS NOT NULL);


--
-- Name: nutrition_report_user_period_idx; Type: INDEX; Schema: app; Owner: -
--

CREATE INDEX nutrition_report_user_period_idx ON app.nutrition_report USING btree (user_id, period_start DESC, period_end DESC);


--
-- Name: plan_adjustment_plan_created_idx; Type: INDEX; Schema: app; Owner: -
--

CREATE INDEX plan_adjustment_plan_created_idx ON app.plan_adjustment USING btree (meal_plan_id, created_at DESC);


--
-- Name: idx_condition_rule_condition; Type: INDEX; Schema: core; Owner: -
--

CREATE INDEX idx_condition_rule_condition ON core.condition_nutrient_rule USING btree (condition_id, review_status, is_active);


--
-- Name: ingredient_aliases_gin_idx; Type: INDEX; Schema: core; Owner: -
--

CREATE INDEX ingredient_aliases_gin_idx ON core.ingredient USING gin (aliases);


--
-- Name: ingredient_allergens_gin_idx; Type: INDEX; Schema: core; Owner: -
--

CREATE INDEX ingredient_allergens_gin_idx ON core.ingredient USING gin (allergens);


--
-- Name: ingredient_data_quality_idx; Type: INDEX; Schema: core; Owner: -
--

CREATE INDEX ingredient_data_quality_idx ON core.ingredient USING btree (data_quality) WHERE (NOT is_deleted);


--
-- Name: ingredient_name_idx; Type: INDEX; Schema: core; Owner: -
--

CREATE INDEX ingredient_name_idx ON core.ingredient USING btree (name);


--
-- Name: ingredient_tags_gin_idx; Type: INDEX; Schema: core; Owner: -
--

CREATE INDEX ingredient_tags_gin_idx ON core.ingredient USING gin (tags);


--
-- Name: v_condition_rule_catalog _RETURN; Type: RULE; Schema: app; Owner: -
--

CREATE OR REPLACE VIEW app.v_condition_rule_catalog AS
 SELECT r.rule_id,
    r.condition_id,
    c.name_zh AS condition_name_zh,
    r.rule_name_zh,
    r.rule_kind,
    r.nutrient_id,
    n.name_zh AS nutrient_name_zh,
    r.action,
    r.comparator,
    r.target_value,
    r.target_unit,
    r.time_basis,
    r.population,
    r.selector,
    r.message_zh,
    r.safety_note_zh,
    r.review_status,
    r.medical_review_required,
    r.is_active,
    ((r.review_status = 'approved'::text) AND r.is_active) AS production_ready,
    COALESCE(jsonb_agg(jsonb_build_object('source_name', ds.source_name, 'source_url', ds.source_url, 'source_role', rs.source_role, 'source_detail', rs.source_detail) ORDER BY rs.source_role, ds.source_name) FILTER (WHERE (ds.source_id IS NOT NULL)), '[]'::jsonb) AS sources
   FROM ((((core.condition_nutrient_rule r
     JOIN core.health_condition c ON ((c.condition_id = r.condition_id)))
     LEFT JOIN core.nutrient n ON ((n.nutrient_id = r.nutrient_id)))
     LEFT JOIN core.condition_rule_source rs ON ((rs.rule_id = r.rule_id)))
     LEFT JOIN core.data_source ds ON ((ds.source_id = rs.source_id)))
  GROUP BY r.rule_id, c.name_zh, n.name_zh;


--
-- Name: meal_candidate trg_guard_fixed_plan_candidate; Type: TRIGGER; Schema: app; Owner: -
--

CREATE TRIGGER trg_guard_fixed_plan_candidate BEFORE INSERT OR DELETE OR UPDATE ON app.meal_candidate FOR EACH ROW EXECUTE FUNCTION app.guard_fixed_plan_children();


--
-- Name: meal_candidate_dish trg_guard_fixed_plan_candidate_dish; Type: TRIGGER; Schema: app; Owner: -
--

CREATE TRIGGER trg_guard_fixed_plan_candidate_dish BEFORE INSERT OR DELETE OR UPDATE ON app.meal_candidate_dish FOR EACH ROW EXECUTE FUNCTION app.guard_fixed_plan_children();


--
-- Name: meal_slot trg_guard_fixed_plan_meal_slot; Type: TRIGGER; Schema: app; Owner: -
--

CREATE TRIGGER trg_guard_fixed_plan_meal_slot BEFORE INSERT OR DELETE OR UPDATE ON app.meal_slot FOR EACH ROW EXECUTE FUNCTION app.guard_fixed_plan_children();


--
-- Name: meal_plan trg_guard_meal_plan_update; Type: TRIGGER; Schema: app; Owner: -
--

CREATE TRIGGER trg_guard_meal_plan_update BEFORE UPDATE ON app.meal_plan FOR EACH ROW EXECUTE FUNCTION app.guard_meal_plan_update();


--
-- Name: meal_candidate_dish meal_candidate_dish_candidate_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.meal_candidate_dish
    ADD CONSTRAINT meal_candidate_dish_candidate_id_fkey FOREIGN KEY (candidate_id) REFERENCES app.meal_candidate(candidate_id) ON DELETE CASCADE;


--
-- Name: meal_candidate_dish meal_candidate_dish_dish_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.meal_candidate_dish
    ADD CONSTRAINT meal_candidate_dish_dish_id_fkey FOREIGN KEY (dish_id) REFERENCES core.dish(dish_id);


--
-- Name: meal_candidate meal_candidate_meal_slot_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.meal_candidate
    ADD CONSTRAINT meal_candidate_meal_slot_id_fkey FOREIGN KEY (meal_slot_id) REFERENCES app.meal_slot(meal_slot_id) ON DELETE CASCADE;


--
-- Name: meal_plan meal_plan_derived_from_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.meal_plan
    ADD CONSTRAINT meal_plan_derived_from_fkey FOREIGN KEY (derived_from_plan_id) REFERENCES app.meal_plan(meal_plan_id);


--
-- Name: meal_plan meal_plan_user_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.meal_plan
    ADD CONSTRAINT meal_plan_user_id_fkey FOREIGN KEY (user_id) REFERENCES app.profile(user_id);


--
-- Name: meal_slot meal_slot_meal_plan_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.meal_slot
    ADD CONSTRAINT meal_slot_meal_plan_id_fkey FOREIGN KEY (meal_plan_id) REFERENCES app.meal_plan(meal_plan_id) ON DELETE CASCADE;


--
-- Name: meal_slot meal_slot_selected_candidate_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.meal_slot
    ADD CONSTRAINT meal_slot_selected_candidate_fkey FOREIGN KEY (selected_candidate_id, meal_slot_id) REFERENCES app.meal_candidate(candidate_id, meal_slot_id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: message message_conversation_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.message
    ADD CONSTRAINT message_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES app.conversation(conversation_id);


--
-- Name: message message_referenced_plan_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.message
    ADD CONSTRAINT message_referenced_plan_id_fkey FOREIGN KEY (referenced_plan_id) REFERENCES app.meal_plan(meal_plan_id);


--
-- Name: nutrition_report nutrition_report_meal_plan_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.nutrition_report
    ADD CONSTRAINT nutrition_report_meal_plan_id_fkey FOREIGN KEY (meal_plan_id) REFERENCES app.meal_plan(meal_plan_id);


--
-- Name: nutrition_report_plan nutrition_report_plan_meal_plan_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.nutrition_report_plan
    ADD CONSTRAINT nutrition_report_plan_meal_plan_id_fkey FOREIGN KEY (meal_plan_id) REFERENCES app.meal_plan(meal_plan_id);


--
-- Name: nutrition_report_plan nutrition_report_plan_nutrition_report_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.nutrition_report_plan
    ADD CONSTRAINT nutrition_report_plan_nutrition_report_id_fkey FOREIGN KEY (nutrition_report_id) REFERENCES app.nutrition_report(nutrition_report_id) ON DELETE CASCADE;


--
-- Name: nutrition_report nutrition_report_user_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.nutrition_report
    ADD CONSTRAINT nutrition_report_user_id_fkey FOREIGN KEY (user_id) REFERENCES app.profile(user_id);


--
-- Name: nutrition_result nutrition_result_user_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.nutrition_result
    ADD CONSTRAINT nutrition_result_user_id_fkey FOREIGN KEY (user_id) REFERENCES app.profile(user_id);


--
-- Name: plan_adjustment plan_adjustment_meal_plan_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.plan_adjustment
    ADD CONSTRAINT plan_adjustment_meal_plan_id_fkey FOREIGN KEY (meal_plan_id) REFERENCES app.meal_plan(meal_plan_id);


--
-- Name: plan_adjustment plan_adjustment_meal_slot_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.plan_adjustment
    ADD CONSTRAINT plan_adjustment_meal_slot_id_fkey FOREIGN KEY (meal_slot_id) REFERENCES app.meal_slot(meal_slot_id);


--
-- Name: plan_adjustment plan_adjustment_new_candidate_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.plan_adjustment
    ADD CONSTRAINT plan_adjustment_new_candidate_id_fkey FOREIGN KEY (new_candidate_id) REFERENCES app.meal_candidate(candidate_id);


--
-- Name: plan_adjustment plan_adjustment_previous_candidate_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.plan_adjustment
    ADD CONSTRAINT plan_adjustment_previous_candidate_id_fkey FOREIGN KEY (previous_candidate_id) REFERENCES app.meal_candidate(candidate_id);


--
-- Name: plan_adjustment plan_adjustment_request_message_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.plan_adjustment
    ADD CONSTRAINT plan_adjustment_request_message_id_fkey FOREIGN KEY (request_message_id) REFERENCES app.message(message_id);


--
-- Name: profile profile_goal_code_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.profile
    ADD CONSTRAINT profile_goal_code_fkey FOREIGN KEY (goal_code) REFERENCES core.goal_structure_map(goal_code);


--
-- Name: shopping_list shopping_list_meal_plan_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.shopping_list
    ADD CONSTRAINT shopping_list_meal_plan_id_fkey FOREIGN KEY (meal_plan_id) REFERENCES app.meal_plan(meal_plan_id) ON DELETE CASCADE;


--
-- Name: weekly_nutrition_report weekly_nutrition_report_user_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.weekly_nutrition_report
    ADD CONSTRAINT weekly_nutrition_report_user_id_fkey FOREIGN KEY (user_id) REFERENCES app.profile(user_id);


--
-- Name: condition_rule_review condition_rule_review_rule_id_fkey; Type: FK CONSTRAINT; Schema: audit; Owner: -
--

ALTER TABLE ONLY audit.condition_rule_review
    ADD CONSTRAINT condition_rule_review_rule_id_fkey FOREIGN KEY (rule_id) REFERENCES core.condition_nutrient_rule(rule_id);


--
-- Name: import_issue import_issue_import_batch_id_fkey; Type: FK CONSTRAINT; Schema: audit; Owner: -
--

ALTER TABLE ONLY audit.import_issue
    ADD CONSTRAINT import_issue_import_batch_id_fkey FOREIGN KEY (import_batch_id) REFERENCES audit.import_batch(import_batch_id);


--
-- Name: condition_nutrient_rule condition_nutrient_rule_condition_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.condition_nutrient_rule
    ADD CONSTRAINT condition_nutrient_rule_condition_id_fkey FOREIGN KEY (condition_id) REFERENCES core.health_condition(condition_id);


--
-- Name: condition_nutrient_rule condition_nutrient_rule_nutrient_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.condition_nutrient_rule
    ADD CONSTRAINT condition_nutrient_rule_nutrient_id_fkey FOREIGN KEY (nutrient_id) REFERENCES core.nutrient(nutrient_id);


--
-- Name: condition_rule_source condition_rule_source_rule_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.condition_rule_source
    ADD CONSTRAINT condition_rule_source_rule_id_fkey FOREIGN KEY (rule_id) REFERENCES core.condition_nutrient_rule(rule_id) ON DELETE CASCADE;


--
-- Name: condition_rule_source condition_rule_source_source_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.condition_rule_source
    ADD CONSTRAINT condition_rule_source_source_id_fkey FOREIGN KEY (source_id) REFERENCES core.data_source(source_id);


--
-- Name: cooking_rule cooking_rule_import_batch_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.cooking_rule
    ADD CONSTRAINT cooking_rule_import_batch_id_fkey FOREIGN KEY (import_batch_id) REFERENCES audit.import_batch(import_batch_id);


--
-- Name: dietary_rule_set dietary_rule_set_import_batch_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dietary_rule_set
    ADD CONSTRAINT dietary_rule_set_import_batch_id_fkey FOREIGN KEY (import_batch_id) REFERENCES audit.import_batch(import_batch_id);


--
-- Name: dish dish_cooking_rule_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dish
    ADD CONSTRAINT dish_cooking_rule_id_fkey FOREIGN KEY (cooking_rule_id) REFERENCES core.cooking_rule(rule_id);


--
-- Name: dish dish_import_batch_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dish
    ADD CONSTRAINT dish_import_batch_id_fkey FOREIGN KEY (import_batch_id) REFERENCES audit.import_batch(import_batch_id);


--
-- Name: dish_ingredient dish_ingredient_dish_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dish_ingredient
    ADD CONSTRAINT dish_ingredient_dish_id_fkey FOREIGN KEY (dish_id) REFERENCES core.dish(dish_id);


--
-- Name: dish_ingredient dish_ingredient_ingredient_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dish_ingredient
    ADD CONSTRAINT dish_ingredient_ingredient_id_fkey FOREIGN KEY (ingredient_id) REFERENCES core.ingredient(ingredient_id);


--
-- Name: food_id_mapping food_id_mapping_import_batch_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.food_id_mapping
    ADD CONSTRAINT food_id_mapping_import_batch_id_fkey FOREIGN KEY (import_batch_id) REFERENCES audit.import_batch(import_batch_id);


--
-- Name: food_id_mapping food_id_mapping_new_food_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.food_id_mapping
    ADD CONSTRAINT food_id_mapping_new_food_id_fkey FOREIGN KEY (new_food_id) REFERENCES core.ingredient(food_id);


--
-- Name: ingredient ingredient_import_batch_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.ingredient
    ADD CONSTRAINT ingredient_import_batch_id_fkey FOREIGN KEY (import_batch_id) REFERENCES audit.import_batch(import_batch_id);


--
-- Name: ingredient ingredient_source_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.ingredient
    ADD CONSTRAINT ingredient_source_id_fkey FOREIGN KEY (source_id) REFERENCES core.data_source(source_id);


--
-- Name: nutrient_reference nutrient_reference_import_batch_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.nutrient_reference
    ADD CONSTRAINT nutrient_reference_import_batch_id_fkey FOREIGN KEY (import_batch_id) REFERENCES audit.import_batch(import_batch_id);


--
-- Name: nutrient_reference nutrient_reference_nutrient_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.nutrient_reference
    ADD CONSTRAINT nutrient_reference_nutrient_id_fkey FOREIGN KEY (nutrient_id) REFERENCES core.nutrient(nutrient_id);


--
-- Name: nutrient_reference nutrient_reference_source_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.nutrient_reference
    ADD CONSTRAINT nutrient_reference_source_id_fkey FOREIGN KEY (source_id) REFERENCES core.data_source(source_id);


--
-- Name: symptom_nutrient_map symptom_nutrient_map_nutrient_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.symptom_nutrient_map
    ADD CONSTRAINT symptom_nutrient_map_nutrient_id_fkey FOREIGN KEY (nutrient_id) REFERENCES core.nutrient(nutrient_id);


--
-- Name: symptom_nutrient_map symptom_nutrient_map_source_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.symptom_nutrient_map
    ADD CONSTRAINT symptom_nutrient_map_source_id_fkey FOREIGN KEY (source_id) REFERENCES core.data_source(source_id);


--
-- Name: nutrient_knowledge nutrient_knowledge_import_batch_id_fkey; Type: FK CONSTRAINT; Schema: knowledge; Owner: -
--

ALTER TABLE ONLY knowledge.nutrient_knowledge
    ADD CONSTRAINT nutrient_knowledge_import_batch_id_fkey FOREIGN KEY (import_batch_id) REFERENCES audit.import_batch(import_batch_id);


--
-- Name: nutrient_knowledge nutrient_knowledge_nutrient_id_fkey; Type: FK CONSTRAINT; Schema: knowledge; Owner: -
--

ALTER TABLE ONLY knowledge.nutrient_knowledge
    ADD CONSTRAINT nutrient_knowledge_nutrient_id_fkey FOREIGN KEY (nutrient_id) REFERENCES core.nutrient(nutrient_id);


--
-- Name: cooking_rule_raw cooking_rule_raw_import_batch_id_fkey; Type: FK CONSTRAINT; Schema: staging; Owner: -
--

ALTER TABLE ONLY staging.cooking_rule_raw
    ADD CONSTRAINT cooking_rule_raw_import_batch_id_fkey FOREIGN KEY (import_batch_id) REFERENCES audit.import_batch(import_batch_id);


--
-- Name: document_raw document_raw_import_batch_id_fkey; Type: FK CONSTRAINT; Schema: staging; Owner: -
--

ALTER TABLE ONLY staging.document_raw
    ADD CONSTRAINT document_raw_import_batch_id_fkey FOREIGN KEY (import_batch_id) REFERENCES audit.import_batch(import_batch_id);


--
-- Name: food_id_mapping_raw food_id_mapping_raw_import_batch_id_fkey; Type: FK CONSTRAINT; Schema: staging; Owner: -
--

ALTER TABLE ONLY staging.food_id_mapping_raw
    ADD CONSTRAINT food_id_mapping_raw_import_batch_id_fkey FOREIGN KEY (import_batch_id) REFERENCES audit.import_batch(import_batch_id);


--
-- Name: food_raw food_raw_import_batch_id_fkey; Type: FK CONSTRAINT; Schema: staging; Owner: -
--

ALTER TABLE ONLY staging.food_raw
    ADD CONSTRAINT food_raw_import_batch_id_fkey FOREIGN KEY (import_batch_id) REFERENCES audit.import_batch(import_batch_id);


--
-- PostgreSQL database dump complete
--

\unrestrict u0dyDwn1ff3XA00MRSdm9c8KbDOzk3mSgAfZ3M3t8fdZ9ar65j4SEiFyQIsfRGk

