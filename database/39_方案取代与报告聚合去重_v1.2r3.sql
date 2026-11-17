-- ============================================================
-- 39_方案取代与报告聚合去重_v1.2r3.sql
-- 用途：修复「同一时间段多次确认/固定 → 膳食报告重复累计」缺陷。
--
-- 两部分：
--   1) 报告聚合去重（止血）：app.recent_micro_balance 对同一餐位
--      (slot_date, meal_type, display_order) 只取 fixed_at 最新的一份；
--      （Python 侧 _load_selected_window 同步按同样口径去重，见 backend/app/routers/nutrition.py）
--   2) 方案取代（源头）：允许固定新方案时把日期重叠的旧 fixed 方案标记为
--      superseded，从源头避免同一时间段并存多份 fixed 方案。
--
-- 幂等：可重复执行（IF NOT EXISTS / DROP CONSTRAINT IF EXISTS / CREATE OR REPLACE）。
-- 应用方式（正在运行的本地库）：
--   docker cp 39_方案取代与报告聚合去重_v1.2r3.sql diet-agent-db:/tmp/39.sql
--   docker exec diet-agent-db psql -U postgres -d diet_agent -v ON_ERROR_STOP=1 -f /tmp/39.sql
-- ============================================================

-- 2.1 方案主表：取代维度列
ALTER TABLE app.meal_plan
    ADD COLUMN IF NOT EXISTS superseded_at timestamp with time zone;
ALTER TABLE app.meal_plan
    ADD COLUMN IF NOT EXISTS superseded_by_plan_id bigint;

COMMENT ON COLUMN app.meal_plan.superseded_at IS
    '被新方案取代的时间（status=superseded 时记录）';
COMMENT ON COLUMN app.meal_plan.superseded_by_plan_id IS
    '取代本方案的新方案 id（status=superseded 时记录）';

-- 2.2 状态枚举：加入 superseded
ALTER TABLE app.meal_plan DROP CONSTRAINT IF EXISTS meal_plan_status_check;
ALTER TABLE app.meal_plan ADD CONSTRAINT meal_plan_status_check
    CHECK (status = ANY (ARRAY['draft'::text, 'candidates'::text, 'fixed'::text, 'superseded'::text]));

-- 2.3 守卫触发器：放行 fixed -> superseded 流转
CREATE OR REPLACE FUNCTION app.guard_meal_plan_update() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_bad_slot_count integer;
    v_supersede boolean;
BEGIN
    -- 取代（fixed -> superseded）是唯一允许「离开 fixed」的流转，
    -- 仅用于固定新方案时对日期重叠的旧方案做覆盖标记。
    v_supersede := (OLD.status = 'fixed' AND NEW.status = 'superseded');

    IF OLD.status = 'fixed' AND NOT v_supersede THEN
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
        OR (OLD.status = 'fixed' AND NEW.status = 'superseded')
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

-- 1) 报告回溯聚合去重
CREATE OR REPLACE FUNCTION app.recent_micro_balance(p_user_id text, p_window_start date, p_window_end date) RETURNS TABLE(nutrient_id text, nutrient_name text, unit text, total_value numeric, selected_meal_count bigint, known_meal_count bigint, missing_meal_count bigint)
    LANGUAGE sql STABLE
    AS $_$
WITH selected_meals AS (
    SELECT DISTINCT ON (s.slot_date, s.meal_type, s.display_order)
           c.candidate_id, c.micro_estimate
    FROM app.meal_plan p
    JOIN app.meal_slot s ON s.meal_plan_id = p.meal_plan_id
    JOIN app.meal_candidate c ON c.candidate_id = s.selected_candidate_id
    WHERE p.user_id = p_user_id
      AND p.status = 'fixed'
      AND NOT p.is_deleted
      AND s.slot_date BETWEEN p_window_start AND p_window_end
    ORDER BY s.slot_date, s.meal_type, s.display_order,
             p.fixed_at DESC NULLS LAST, s.meal_slot_id DESC
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

COMMENT ON FUNCTION app.recent_micro_balance(text, date, date) IS
    '汇总指定用户、指定日期窗口内已固定方案的7种关键微量；同一餐位(slot_date,meal_type,display_order)多方案只取 fixed_at 最新一份；NULL保持未知并计入missing。';
