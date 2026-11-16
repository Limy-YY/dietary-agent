-- 给测试岗/联调同学的数据库只读账号（可重复执行）
--
-- 用法（Windows PowerShell，deploy 容器的库）：
--   docker cp scripts/grant_readonly.sql diet-agent-db:/tmp/grant_readonly.sql
--   docker exec diet-agent-db psql -U postgres -d diet_agent -f /tmp/grant_readonly.sql
--
-- 用法（bash）：
--   docker exec -i diet-agent-db psql -U postgres -d diet_agent < scripts/grant_readonly.sql
--
-- 注意：须以 postgres 超级用户身份执行（diet_app 是 NOLOGIN 角色会直接失败）。
-- 结果：diet_ro / diet_ro_readonly，仅能 SELECT app / core / knowledge 三个 schema，
-- 写操作（INSERT / UPDATE / DELETE / DDL）一律 permission denied。

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'diet_ro') THEN
    CREATE ROLE diet_ro LOGIN PASSWORD 'diet_ro_readonly';
  END IF;
END $$;

GRANT CONNECT ON DATABASE diet_agent TO diet_ro;
GRANT USAGE ON SCHEMA app, core, knowledge TO diet_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA app, core, knowledge TO diet_ro;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA app, core, knowledge TO diet_ro;

-- 之后新建的表也自动只读（本脚本须以 diet_app 身份执行，默认权限才对 diet_app 建的对象生效）
ALTER DEFAULT PRIVILEGES FOR ROLE diet_app IN SCHEMA app GRANT SELECT ON TABLES TO diet_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE diet_app IN SCHEMA core GRANT SELECT ON TABLES TO diet_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE diet_app IN SCHEMA knowledge GRANT SELECT ON TABLES TO diet_ro;

-- 收掉 public 的默认权限，避免以后新对象意外可写
REVOKE ALL ON SCHEMA public FROM diet_ro;
