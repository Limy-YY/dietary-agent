-- 建后端服务的数据库登录账号（可重复执行）
--
-- 背景：database/03_应用账号与权限.sql 里的 diet_app 是 NOLOGIN 权限组，不能直接登录，
-- 后端必须用自己的 LOGIN 账号并加入该组。库重建（空卷重跑十步）后这个账号不会自动出现，
-- 表现为 /api/health 返回 {"status":"degraded","database":"unavailable"}。
--
-- 用法（Windows PowerShell）：
--   docker cp scripts/grant_backend_login.sql diet-agent-db:/tmp/grant_backend_login.sql
--   docker exec diet-agent-db psql -U postgres -d diet_agent -f /tmp/grant_backend_login.sql
--
-- 执行后 backend/.env 的 DATABASE_URL 用：
--   postgresql+psycopg://diet_backend:diet_backend_dev@localhost:5432/diet_agent
--
-- 权限口径：继承 diet_app 组 —— core / knowledge 只读，app / audit 可写，不是超级用户。

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'diet_backend') THEN
    CREATE ROLE diet_backend LOGIN PASSWORD 'diet_backend_dev';
  END IF;
END $$;

GRANT diet_app TO diet_backend;

-- 验证：应当输出 app_prof_insert=true / core_dish_insert=false / super=false
DO $$
DECLARE
  has_app boolean := has_table_privilege('diet_backend', 'app.profile', 'INSERT');
  has_core boolean := has_table_privilege('diet_backend', 'core.dish', 'INSERT');
  is_super boolean := (SELECT rolsuper FROM pg_roles WHERE rolname = 'diet_backend');
BEGIN
  RAISE NOTICE 'grant_backend_login: app_prof_insert=% core_dish_insert=% super=%', has_app, has_core, is_super;
END $$;
