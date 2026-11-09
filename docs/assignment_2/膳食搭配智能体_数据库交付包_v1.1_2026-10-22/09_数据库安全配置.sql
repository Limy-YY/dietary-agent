\set ON_ERROR_STOP on

BEGIN;

REVOKE ALL ON SCHEMA audit, core, app, knowledge FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA audit, core, app, knowledge FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA audit, core, app, knowledge FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA audit, core, app, knowledge FROM PUBLIC;

COMMIT;

-- 本脚本只设置安全默认值，不创建真实登录账号或密码。
-- 后端数据库管理员应按最小权限原则单独 GRANT 所需视图和函数。
