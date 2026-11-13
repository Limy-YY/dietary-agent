-- 创建应用专用数据库用户并按最小权限授权
-- 用途：后端应用连接账号（交付清单要求：应用不使用超级用户连接）
-- 执行：psql -U postgres -d diet_agent -f grant_diet_app.sql

CREATE ROLE diet_app LOGIN PASSWORD 'diet_app_dev';

-- schema 使用权限
GRANT USAGE ON SCHEMA core, knowledge, app TO diet_app;

-- 权威基准/知识层只读
GRANT SELECT ON ALL TABLES IN SCHEMA core TO diet_app;
GRANT SELECT ON ALL TABLES IN SCHEMA knowledge TO diet_app;

-- 业务层读写
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO diet_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA app TO diet_app;

-- app 层函数/视图执行
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app TO diet_app;

-- 未来新建对象自动继承授权
ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO diet_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT USAGE ON SEQUENCES TO diet_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA core GRANT SELECT ON TABLES TO diet_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA knowledge GRANT SELECT ON TABLES TO diet_app;
