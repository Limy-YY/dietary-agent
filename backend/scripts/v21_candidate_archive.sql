-- Run as database owner, separately from application code. Transactional and idempotent.
BEGIN;
ALTER TABLE app.meal_candidate ALTER COLUMN rank DROP NOT NULL;
-- Keep existing rank check (1..3 for non-NULL) and unique(slot,rank).
-- PostgreSQL permits multiple NULLs in this existing UNIQUE constraint.
DO $migration$
DECLARE definition text; old_clause text := 'WHERE c.meal_slot_id = s.meal_slot_id';
BEGIN
    SELECT pg_get_functiondef('app.guard_meal_plan_update()'::regprocedure) INTO definition;
    IF position(old_clause || ' AND c.rank IS NOT NULL' in definition) = 0 THEN
        IF position(old_clause in definition) = 0 THEN
            RAISE EXCEPTION 'Unexpected guard_meal_plan_update definition; migration aborted';
        END IF;
        definition := replace(definition, old_clause, old_clause || ' AND c.rank IS NOT NULL');
        EXECUTE definition;
    END IF;
END
$migration$;
COMMIT;
