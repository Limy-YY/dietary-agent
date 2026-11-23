-- ============================================================================
-- 47 · 配餐模块结构变更：§五 表结构 + A 裁剪白名单（窗口③ step1，2026-11-23）
-- 幂等可重跑；只改 core.dish / core.dish_ingredient / core.ingredient，不删行。
-- 供窗口② 后端消费：
--   dish_meta       —— §5.1 角色单一来源（role/breakfast/staple/family/commonness/complexity），
--                      由 meal_templates._ROWS 迁库，LS 变体不落 meta（后端经 base_dish_id 回查本菜）。
--   is_generation_enabled —— A 裁剪开关（默认 true；白名单外置 false，可逆，不删行）。
--   dish_ingredient.role CHECK —— §5.4 主料口径，锁 7 个规范值。
--   ingredient.nutrient_source —— §5.5 蛋白/脂肪来源软约束（首版按 category 推导，可后端细化）。
-- ============================================================================

BEGIN;

-- 1. core.dish 加列
ALTER TABLE core.dish ADD COLUMN IF NOT EXISTS dish_meta jsonb;
ALTER TABLE core.dish ADD COLUMN IF NOT EXISTS is_generation_enabled boolean NOT NULL DEFAULT true;

-- 2. core.ingredient 加 nutrient_source jsonb（蛋白/脂肪来源）
ALTER TABLE core.ingredient ADD COLUMN IF NOT EXISTS nutrient_source jsonb;

-- 3. dish_meta 迁库：170 道基础菜（faithful _ROWS 1:1）
UPDATE core.dish AS d SET dish_meta = v.meta::jsonb
FROM (VALUES
  ('DISH-001', '{"roles":["P"],"breakfast":"-","staple":"-","family":"鸡肉","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-002', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"鸡肉","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-003', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"鸡肉","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-004', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"鸡肉","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-005', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"鸡肉","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-006', '{"roles":["P"],"breakfast":"-","staple":"-","family":"鱼","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-007', '{"roles":["P","V","T"],"breakfast":"-","staple":"-","family":"鱼","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-008', '{"roles":["P"],"breakfast":"-","staple":"-","family":"鱼","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-009', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"虾","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-010', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"虾","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-011', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"虾","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-012', '{"roles":["P","V"],"breakfast":"L","staple":"-","family":"鸡蛋","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-013', '{"roles":["P","V","T"],"breakfast":"L","staple":"-","family":"鸡蛋","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-014', '{"roles":["P","V"],"breakfast":"E","staple":"-","family":"鸡蛋","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-015', '{"roles":["P","V","T"],"breakfast":"L","staple":"-","family":"豆腐","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-016', '{"roles":["P","V","T"],"breakfast":"L","staple":"-","family":"豆腐","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-017', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"豆腐","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-018', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"豆腐","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-019', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"牛肉","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-020', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"牛肉","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-021', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"猪肉","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-022', '{"roles":["V"],"breakfast":"-","staple":"-","family":"西兰花","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-023', '{"roles":["V"],"breakfast":"-","staple":"-","family":"菠菜","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-024', '{"roles":["V"],"breakfast":"-","staple":"-","family":"花椰菜","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-025', '{"roles":["V"],"breakfast":"-","staple":"-","family":"黄瓜","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-026', '{"roles":["V"],"breakfast":"L","staple":"-","family":"黄瓜","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-027', '{"roles":["V"],"breakfast":"-","staple":"-","family":"西葫芦","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-028', '{"roles":["V"],"breakfast":"-","staple":"-","family":"四季豆","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-029', '{"roles":["S","P"],"breakfast":"-","staple":"grain","family":"鹰嘴豆","commonness":2,"complexity":2,"reviewed":true}'::jsonb),
  ('DISH-030', '{"roles":["S","D","F"],"breakfast":"B","staple":"sweet","family":"燕麦","commonness":2,"complexity":2,"reviewed":true}'::jsonb),
  ('DISH-031', '{"roles":["P"],"breakfast":"-","staple":"-","family":"鱼","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-032', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"牛肉","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-033', '{"roles":["P","V","T"],"breakfast":"-","staple":"-","family":"牛肉","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-034', '{"roles":["V"],"breakfast":"L","staple":"-","family":"豆芽","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-035', '{"roles":["V"],"breakfast":"-","staple":"-","family":"茄子","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-036', '{"roles":["V"],"breakfast":"-","staple":"-","family":"苦瓜","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-037', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"鸡肉","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-038', '{"roles":["P","V","T"],"breakfast":"L","staple":"-","family":"豆腐","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-039', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"鸡肉","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-040', '{"roles":["V"],"breakfast":"-","staple":"-","family":"山药","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-041', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"牛肉","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-042', '{"roles":["P","V"],"breakfast":"L","staple":"-","family":"鸡蛋","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-043', '{"roles":["V"],"breakfast":"L","staple":"-","family":"油菜","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-044', '{"roles":["P","V"],"breakfast":"L","staple":"-","family":"豆腐","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-045', '{"roles":["P","V","T"],"breakfast":"L","staple":"-","family":"鸡蛋","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-046', '{"roles":["S"],"breakfast":"-","staple":"grain","family":"米饭","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-047', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"猪肉","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-048', '{"roles":["P","V","T"],"breakfast":"-","staple":"-","family":"猪肉","commonness":1,"complexity":2,"reviewed":true}'::jsonb),
  ('DISH-049', '{"roles":["S"],"breakfast":"C","staple":"porridge","family":"小米","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-050', '{"roles":["V"],"breakfast":"L","staple":"-","family":"海带","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-051', '{"roles":["P","V","T"],"breakfast":"L","staple":"-","family":"豆腐","commonness":1,"complexity":2,"reviewed":true}'::jsonb),
  ('DISH-052', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"牛肉","commonness":1,"complexity":2,"reviewed":true}'::jsonb),
  ('DISH-053', '{"roles":["P"],"breakfast":"-","staple":"-","family":"贝类","commonness":2,"complexity":2,"reviewed":true}'::jsonb),
  ('DISH-054', '{"roles":["V"],"breakfast":"-","staple":"-","family":"花生","commonness":2,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-055', '{"roles":["S","V","T"],"breakfast":"-","staple":"soupgrain","family":"小麦","commonness":1,"complexity":2,"reviewed":true}'::jsonb),
  ('DISH-056', '{"roles":["S"],"breakfast":"N","staple":"tuber","family":"红薯","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-057', '{"roles":["S"],"breakfast":"N","staple":"tuber","family":"南瓜","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-058', '{"roles":["S"],"breakfast":"-","staple":"grain","family":"米饭","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-059', '{"roles":["S","D"],"breakfast":"B","staple":"sweet","family":"燕麦","commonness":2,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-060', '{"roles":["V"],"breakfast":"-","staple":"-","family":"土豆","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-061', '{"roles":["P"],"breakfast":"-","staple":"-","family":"鱼","commonness":1,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-062', '{"roles":["P"],"breakfast":"-","staple":"-","family":"鱼","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-063', '{"roles":["P"],"breakfast":"L","staple":"-","family":"水产","commonness":2,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-064', '{"roles":["P","T"],"breakfast":"L","staple":"-","family":"鱼","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-065', '{"roles":["P","V","T"],"breakfast":"-","staple":"-","family":"鱼","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-066', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"鱼","commonness":2,"complexity":2,"reviewed":true}'::jsonb),
  ('DISH-067', '{"roles":["P","T"],"breakfast":"L","staple":"-","family":"鸡蛋","commonness":2,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-068', '{"roles":["P","V","T"],"breakfast":"-","staple":"-","family":"贝类","commonness":2,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-069', '{"roles":["P"],"breakfast":"-","staple":"-","family":"水产","commonness":1,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-070', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"水产","commonness":2,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-071', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"鸭肉","commonness":2,"complexity":2,"reviewed":true}'::jsonb),
  ('DISH-072', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"羊肉","commonness":2,"complexity":2,"reviewed":true}'::jsonb),
  ('DISH-073', '{"roles":["P"],"breakfast":"-","staple":"-","family":"羊肉","commonness":1,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-074', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"内脏","commonness":2,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-075', '{"roles":["P","V","T"],"breakfast":"-","staple":"-","family":"内脏","commonness":2,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-076', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"猪肉","commonness":1,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-077', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"猪肉","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-078', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"猪肉","commonness":2,"complexity":2,"reviewed":true}'::jsonb),
  ('DISH-079', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"内脏","commonness":2,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-080', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"鸭肉","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-081', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"猪肉","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-082', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"牛肉","commonness":2,"complexity":2,"reviewed":true}'::jsonb),
  ('DISH-083', '{"roles":["P","V"],"breakfast":"L","staple":"-","family":"豆腐","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-084', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"豆腐","commonness":2,"complexity":2,"reviewed":true}'::jsonb),
  ('DISH-085', '{"roles":["P","V"],"breakfast":"L","staple":"-","family":"豆腐","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-086', '{"roles":["P","V"],"breakfast":"E","staple":"-","family":"鸡蛋","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-087', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"豆制品","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-088', '{"roles":["P","V"],"breakfast":"E","staple":"-","family":"鸡蛋","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-089', '{"roles":["P","V"],"breakfast":"L","staple":"-","family":"鸡蛋","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-090', '{"roles":["P","V"],"breakfast":"L","staple":"-","family":"豆腐","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-091', '{"roles":["P","V"],"breakfast":"L","staple":"-","family":"豆腐","commonness":2,"complexity":2,"reviewed":true}'::jsonb),
  ('DISH-092', '{"roles":["P"],"breakfast":"-","staple":"-","family":"鸡蛋","commonness":1,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-093', '{"roles":["V"],"breakfast":"-","staple":"-","family":"-","commonness":1,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-094', '{"roles":["V"],"breakfast":"-","staple":"-","family":"-","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-095', '{"roles":["V"],"breakfast":"-","staple":"-","family":"-","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-096', '{"roles":["V"],"breakfast":"L","staple":"-","family":"-","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-097', '{"roles":["V"],"breakfast":"-","staple":"-","family":"-","commonness":1,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-098', '{"roles":["V"],"breakfast":"-","staple":"-","family":"-","commonness":1,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-099', '{"roles":["V"],"breakfast":"-","staple":"-","family":"-","commonness":2,"complexity":2,"reviewed":true}'::jsonb),
  ('DISH-100', '{"roles":["V"],"breakfast":"-","staple":"-","family":"-","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-101', '{"roles":["V"],"breakfast":"-","staple":"-","family":"-","commonness":1,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-102', '{"roles":["V"],"breakfast":"-","staple":"-","family":"-","commonness":1,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-103', '{"roles":["V"],"breakfast":"L","staple":"-","family":"-","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-104', '{"roles":["V"],"breakfast":"-","staple":"-","family":"-","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-105', '{"roles":["P","T"],"breakfast":"L","staple":"-","family":"豆腐","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-106', '{"roles":["P","V","T"],"breakfast":"-","staple":"-","family":"鸡蛋","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-107', '{"roles":["V","T"],"breakfast":"-","staple":"-","family":"-","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-108', '{"roles":["V","T"],"breakfast":"-","staple":"-","family":"-","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-109', '{"roles":["V","T"],"breakfast":"-","staple":"-","family":"-","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-110', '{"roles":["V","T"],"breakfast":"-","staple":"-","family":"-","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-111', '{"roles":["V","T"],"breakfast":"-","staple":"-","family":"-","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-112', '{"roles":["V","T"],"breakfast":"-","staple":"-","family":"-","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-113', '{"roles":["S","P","V"],"breakfast":"E","staple":"grain","family":"鸡蛋","commonness":1,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-114', '{"roles":["S","P","V"],"breakfast":"C","staple":"grain","family":"鸡肉","commonness":1,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-115', '{"roles":["S","V"],"breakfast":"C","staple":"grain","family":"-","commonness":1,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-116', '{"roles":["S"],"breakfast":"-","staple":"grain","family":"-","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-117', '{"roles":["S","D"],"breakfast":"B","staple":"porridge","family":"-","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-118', '{"roles":["S","D","F"],"breakfast":"B","staple":"sweet","family":"-","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-119', '{"roles":["S"],"breakfast":"N","staple":"grain","family":"-","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-120', '{"roles":["S"],"breakfast":"N","staple":"tuber","family":"-","commonness":0,"complexity":2,"reviewed":true}'::jsonb),
  ('DISH-121', '{"roles":["S"],"breakfast":"-","staple":"grain","family":"米饭","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-122', '{"roles":["S"],"breakfast":"C","staple":"grain","family":"小麦","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-123', '{"roles":["S"],"breakfast":"N","staple":"grain","family":"小麦","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-124', '{"roles":["S"],"breakfast":"N","staple":"grain","family":"玉米","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-125', '{"roles":["S"],"breakfast":"C","staple":"grain","family":"小麦","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-126', '{"roles":["S"],"breakfast":"C","staple":"grain","family":"米粉","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-127', '{"roles":["P"],"breakfast":"E","staple":"-","family":"鸡蛋","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-128', '{"roles":["P"],"breakfast":"M","staple":"-","family":"大豆","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-129', '{"roles":["D"],"breakfast":"M","staple":"-","family":"牛奶","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-130', '{"roles":["D"],"breakfast":"M","staple":"-","family":"牛奶","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-131', '{"roles":["F"],"breakfast":"F","staple":"-","family":"苹果","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-132', '{"roles":["F"],"breakfast":"F","staple":"-","family":"香蕉","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-133', '{"roles":["F"],"breakfast":"F","staple":"-","family":"橙子","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-134', '{"roles":["F"],"breakfast":"F","staple":"-","family":"梨","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-135', '{"roles":["F"],"breakfast":"F","staple":"-","family":"葡萄","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-136', '{"roles":["F"],"breakfast":"F","staple":"-","family":"西瓜","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-137', '{"roles":["F"],"breakfast":"F","staple":"-","family":"桃","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-138', '{"roles":["F"],"breakfast":"F","staple":"-","family":"猕猴桃","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-139', '{"roles":["P"],"breakfast":"-","staple":"-","family":"鸡肉","commonness":0,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-140', '{"roles":["P"],"breakfast":"-","staple":"-","family":"鸡肉","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-141', '{"roles":["P"],"breakfast":"L","staple":"-","family":"豆腐","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-142', '{"roles":["P"],"breakfast":"-","staple":"-","family":"虾","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-143', '{"roles":["P"],"breakfast":"-","staple":"-","family":"鱼","commonness":1,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-144', '{"roles":["P"],"breakfast":"-","staple":"-","family":"鱼","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-145', '{"roles":["P"],"breakfast":"E","staple":"-","family":"鸡蛋","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-146', '{"roles":["V"],"breakfast":"L","staple":"-","family":"菜心","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-147', '{"roles":["V"],"breakfast":"L","staple":"-","family":"生菜","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-148', '{"roles":["V"],"breakfast":"-","staple":"-","family":"生菜","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-149', '{"roles":["V"],"breakfast":"-","staple":"-","family":"空心菜","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-150', '{"roles":["V"],"breakfast":"-","staple":"-","family":"丝瓜","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-151', '{"roles":["V"],"breakfast":"L","staple":"-","family":"西兰花","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-152', '{"roles":["V"],"breakfast":"L","staple":"-","family":"小白菜","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-153', '{"roles":["V"],"breakfast":"-","staple":"-","family":"大白菜","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-154', '{"roles":["V"],"breakfast":"-","staple":"-","family":"油菜","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-155', '{"roles":["V"],"breakfast":"-","staple":"-","family":"菜心","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-156', '{"roles":["V"],"breakfast":"-","staple":"-","family":"茼蒿","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-157', '{"roles":["V"],"breakfast":"-","staple":"-","family":"苋菜","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-158', '{"roles":["V"],"breakfast":"-","staple":"-","family":"西葫芦","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-159', '{"roles":["V"],"breakfast":"L","staple":"-","family":"茄子","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-160', '{"roles":["V"],"breakfast":"L","staple":"-","family":"菜花","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-161', '{"roles":["P","V"],"breakfast":"E","staple":"-","family":"鸡蛋","commonness":1,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-162', '{"roles":["P"],"breakfast":"L","staple":"-","family":"鸡蛋","commonness":0,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-163', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"鸡肉","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-164', '{"roles":["P","V"],"breakfast":"-","staple":"-","family":"鸡肉","commonness":0,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-165', '{"roles":["P","T"],"breakfast":"-","staple":"-","family":"鸡肉","commonness":0,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-166', '{"roles":["P"],"breakfast":"-","staple":"-","family":"猪肉","commonness":0,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-167', '{"roles":["P"],"breakfast":"L","staple":"-","family":"豆腐","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-168', '{"roles":["P"],"breakfast":"-","staple":"-","family":"豆腐","commonness":0,"complexity":1,"reviewed":true}'::jsonb),
  ('DISH-169', '{"roles":["S"],"breakfast":"N","staple":"tuber","family":"土豆","commonness":0,"complexity":0,"reviewed":true}'::jsonb),
  ('DISH-170', '{"roles":["S"],"breakfast":"C","staple":"porridge","family":"米饭","commonness":0,"complexity":0,"reviewed":true}'::jsonb)
) AS v(dish_id, meta)
WHERE d.dish_id = v.dish_id;

-- 4. A 裁剪白名单：关闭「非生成池」菜（可逆开关，不删行）
-- 4a. 少盐变体：默认全摘，仅保留 4 道高盐主菜的少盐版
UPDATE core.dish SET is_generation_enabled = false
WHERE dish_id LIKE '%-LS' AND dish_id NOT IN ('DISH-002-LS', 'DISH-006-LS', 'DISH-019-LS', 'DISH-141-LS');
-- 4b. 基础菜：关闭 84 道（复杂度/重复/家族瘦身/蔬菜瘦身）
UPDATE core.dish SET is_generation_enabled = false
WHERE dish_id IN ('DISH-003', 'DISH-004', 'DISH-005', 'DISH-007', 'DISH-013', 'DISH-016', 'DISH-018', 'DISH-020', 'DISH-021', 'DISH-026', 'DISH-027', 'DISH-029', 'DISH-030', 'DISH-033', 'DISH-037', 'DISH-040', 'DISH-045', 'DISH-048', 'DISH-050', 'DISH-051', 'DISH-052', 'DISH-053', 'DISH-055', 'DISH-064', 'DISH-065', 'DISH-066', 'DISH-067', 'DISH-069', 'DISH-071', 'DISH-075', 'DISH-076', 'DISH-078', 'DISH-079', 'DISH-082', 'DISH-084', 'DISH-085', 'DISH-090', 'DISH-091', 'DISH-094', 'DISH-096', 'DISH-097', 'DISH-098', 'DISH-099', 'DISH-100', 'DISH-101', 'DISH-103', 'DISH-104', 'DISH-105', 'DISH-106', 'DISH-109', 'DISH-110', 'DISH-112', 'DISH-115', 'DISH-117', 'DISH-118', 'DISH-119', 'DISH-120', 'DISH-126', 'DISH-134', 'DISH-135', 'DISH-136', 'DISH-137', 'DISH-139', 'DISH-140', 'DISH-143', 'DISH-144', 'DISH-145', 'DISH-146', 'DISH-147', 'DISH-148', 'DISH-149', 'DISH-150', 'DISH-151', 'DISH-152', 'DISH-154', 'DISH-155', 'DISH-156', 'DISH-157', 'DISH-158', 'DISH-160', 'DISH-161', 'DISH-162', 'DISH-167', 'DISH-168');

-- 5. dish_ingredient.role CHECK 约束（锁 7 个规范值，§5.4）
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'dish_ingredient_role_check'
  ) THEN
    ALTER TABLE core.dish_ingredient
      ADD CONSTRAINT dish_ingredient_role_check
      CHECK (role IS NULL OR role IN ('主料','配菜','配料','调味辅料','调味料','烹调油','食盐'));
  END IF;
END $$;

-- 6. 蛋白/脂肪来源（§5.5，首版按 category 推导）
UPDATE core.ingredient SET nutrient_source = jsonb_build_object(
  'protein_source', CASE
    WHEN category IN ('禽肉','猪肉','牛肉','羊肉及其他畜肉','水产','蛋奶') THEN 'animal'
    WHEN category IN ('豆类与豆制品','坚果与种子') THEN 'plant'
    ELSE NULL END,
  'fat_source', CASE
    WHEN category IN ('蛋奶') THEN 'animal'
    WHEN category IN ('油脂','坚果与种子') THEN 'plant'
    ELSE NULL END
) WHERE NOT is_deleted;

-- 7. 自检：dish_meta 应覆盖全部 170 基础菜；白名单外应恰好关闭 43-4=39 少盐 + 其余基础菜
DO $$
DECLARE meta_missing int; base_on int; ls_on int; ls_off int;
BEGIN
  SELECT count(*) INTO meta_missing FROM core.dish d
   WHERE d.dish_id NOT LIKE '%-LS' AND NOT d.is_deleted AND d.dish_meta IS NULL;
  SELECT count(*) INTO base_on FROM core.dish
   WHERE dish_id NOT LIKE '%-LS' AND NOT is_deleted AND is_generation_enabled;
  SELECT count(*) INTO ls_on FROM core.dish
   WHERE dish_id LIKE '%-LS' AND NOT is_deleted AND is_generation_enabled;
  SELECT count(*) INTO ls_off FROM core.dish
   WHERE dish_id LIKE '%-LS' AND NOT is_deleted AND NOT is_generation_enabled;
  IF meta_missing <> 0 THEN RAISE EXCEPTION 'dish_meta 缺失 % 道基础菜', meta_missing; END IF;
  IF ls_on <> 4 THEN RAISE EXCEPTION '少盐变体开启数应为 4，实为 %', ls_on; END IF;
  IF ls_off <> 39 THEN RAISE EXCEPTION '少盐变体关闭数应为 39，实为 %', ls_off; END IF;
  RAISE NOTICE 'dish_meta 全覆盖 170；基础菜开启 %；少盐开 % / 关 %', base_on, ls_on, ls_off;
END $$;

COMMIT;
