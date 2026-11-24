-- 53_白名单增补_水果与家常菜13道.sql
-- 2026-11-23 · 把 A 裁剪时误关的 13 道菜加回生成池（is_generation_enabled = true）。
--   4 水果：桃 / 梨 / 葡萄 / 西瓜（补「缺水果」位）
--   9 家常：冬瓜排骨玉米汤、牛肉炖土豆、草鱼豆腐汤、紫菜蛋花汤、
--           肉末蒸蛋、燕麦牛奶粥、竹笋炒香菇、紫菜豆腐汤、清炒西葫芦
-- 幂等：对这 13 道菜开开关并 touch updated_at（触发 get_dish_facts 数据指纹失效），重复执行无副作用。

UPDATE core.dish
SET is_generation_enabled = true,
    updated_at = now()
WHERE NOT is_deleted
  AND dish_id NOT LIKE '%-LS'
  AND name IN (
    '桃', '梨', '葡萄', '西瓜',
    '冬瓜排骨玉米汤', '牛肉炖土豆', '草鱼豆腐汤', '紫菜蛋花汤',
    '肉末蒸蛋', '燕麦牛奶粥', '竹笋炒香菇', '紫菜豆腐汤', '清炒西葫芦'
  );
