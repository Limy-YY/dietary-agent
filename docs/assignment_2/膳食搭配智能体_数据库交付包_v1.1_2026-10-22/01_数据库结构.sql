--
-- PostgreSQL database dump
--

\restrict 1HlaOqI2S4PFz0mae0CBShgdmtosdc9GxDjG8LwZ4mXAdrTttIKO7NXe8Udx2CU

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
    CONSTRAINT meal_plan_plan_type_check CHECK ((plan_type = ANY (ARRAY['日'::text, '周'::text])))
);


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
-- Name: message; Type: TABLE; Schema: app; Owner: -
--

CREATE TABLE app.message (
    message_id bigint NOT NULL,
    conversation_id bigint NOT NULL,
    role text NOT NULL,
    content text,
    tool_calls jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
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
    CONSTRAINT profile_age_check CHECK ((age >= 0)),
    CONSTRAINT profile_height_cm_check CHECK ((height_cm > (0)::numeric)),
    CONSTRAINT profile_weight_kg_check CHECK ((weight_kg > (0)::numeric))
);


--
-- Name: COLUMN profile.conditions; Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON COLUMN app.profile.conditions IS 'JSON 对象；疾病条目状态使用 confirmed、suspected、unknown。';


--
-- Name: COLUMN profile.birth_date; Type: COMMENT; Schema: app; Owner: -
--

COMMENT ON COLUMN app.profile.birth_date IS '用于精确计算婴幼儿月龄和年龄边界；age 字段保留作兼容或展示。';


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
    CONSTRAINT ingredient_allergen_status_check CHECK ((allergen_status = ANY (ARRAY['已确认含'::text, '确认不含'::text, '未核查'::text]))),
    CONSTRAINT ingredient_calcium_mg_check CHECK ((calcium_mg >= (0)::numeric)),
    CONSTRAINT ingredient_carbohydrate_g_check CHECK ((carbohydrate_g >= (0)::numeric)),
    CONSTRAINT ingredient_cholesterol_mg_check CHECK ((cholesterol_mg >= (0)::numeric)),
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

COMMENT ON TABLE app.weekly_nutrition_report IS '周报中的 UL 风险默认按每日摄入最大值判断，不用七天总量直接比较每日 UL。';


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
-- Name: nutrient; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.nutrient (
    nutrient_id text NOT NULL,
    name_zh text NOT NULL,
    unit text NOT NULL,
    description text
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
    created_at timestamp with time zone DEFAULT now() NOT NULL
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
-- Name: conversation conversation_pkey; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.conversation
    ADD CONSTRAINT conversation_pkey PRIMARY KEY (conversation_id);


--
-- Name: meal_plan meal_plan_pkey; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.meal_plan
    ADD CONSTRAINT meal_plan_pkey PRIMARY KEY (meal_plan_id);


--
-- Name: message message_pkey; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.message
    ADD CONSTRAINT message_pkey PRIMARY KEY (message_id);


--
-- Name: nutrition_result nutrition_result_pkey; Type: CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.nutrition_result
    ADD CONSTRAINT nutrition_result_pkey PRIMARY KEY (nutrition_result_id);


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
-- Name: meal_plan meal_plan_user_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.meal_plan
    ADD CONSTRAINT meal_plan_user_id_fkey FOREIGN KEY (user_id) REFERENCES app.profile(user_id);


--
-- Name: message message_conversation_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.message
    ADD CONSTRAINT message_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES app.conversation(conversation_id);


--
-- Name: nutrition_result nutrition_result_user_id_fkey; Type: FK CONSTRAINT; Schema: app; Owner: -
--

ALTER TABLE ONLY app.nutrition_result
    ADD CONSTRAINT nutrition_result_user_id_fkey FOREIGN KEY (user_id) REFERENCES app.profile(user_id);


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
-- PostgreSQL database dump complete
--

\unrestrict 1HlaOqI2S4PFz0mae0CBShgdmtosdc9GxDjG8LwZ4mXAdrTttIKO7NXe8Udx2CU

