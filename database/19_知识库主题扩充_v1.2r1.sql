--
-- 19_知识库主题扩充_v1.2r1.sql
-- 用途：给 knowledge.knowledge_doc 补一批"非营养素"主题——病种、人群、膳食结构、过敏与食品安全。
--       现状（01 备份恢复后实测）：26 篇全部是 nutrient:<营养素>:overview，category 只覆盖
--       维生素/矿物质/脂肪酸/其他，检索时用户问"高血压能吃咸菜吗""孕妇能不能吃刺身"这类
--       场景化问题，召回的全是营养素条目，答不到点上。
--
-- 口径：
--   stable_key 统一 topic:<slug>，与既有 nutrient:<slug>:overview 分开命名空间，互不覆盖；
--   content 只写膳食层面的可执行建议，不写诊断、不写剂量处方、不写"治愈"；
--   ON CONFLICT (stable_key) DO UPDATE —— 重复执行只同步内容，不新增行，改过 content 会被
--   15 的 md5 比对识别出来重灌（knowledge.v_embedding_backlog 不看 category，新增自动入队）。
--
-- 修订记录：
--   2026-11-13  v1.2r1 初版，17 条主题（病种 6 / 人群 5 / 膳食结构 3 / 过敏与食品安全 3）。
--   2026-11-16  按营养岗《营养口径审核_19与21_v1.2》修订：
--               引文年份 2 处（高尿酸痛风、慢性肾病改 2024 版）、措辞 1 处（减重"肌肉占比才高"→脂肪占比高）、
--               安全边界 6 处（高血压富钾前提、哺乳期酒/水/咖啡因、孕期高汞鱼、剩饭蜡样芽孢杆菌、
--               过敏 GB 7718 版本与 eHF/AAF、慢性肾病蛋白口径与大豆制品），
--               并把 INSERT 与自检收进同一事务（BEGIN/COMMIT），校验抛异常整体回滚。
--   2026-11-17  按营养岗《19_待修改问题清单_v1.2》修订 5 处：
--               ① 长度阈值回退 750→600 字（原 750 是把 SQL_ASCII 库的字节数当字数，实测 159～270 字），
--                  另加 octet_length ≤ 1000 字节兜底，并在前置校验里拦住非 UTF8 库；
--               ② GB 7718 措辞改为 2011 版「宜」提示、2025 版（2027 实施）起强制；
--               ③ 牛奶过敏替代限定年龄：婴儿走 eHF/AAF，豆浆只给儿童/成人轻症；
--               ④ fatty_liver_diet、child_nutrition 的 source/source_id 补成多来源，与 guidelines 对齐；
--               ⑤ 自检 NOTICE 改为「当前 topic 总数」，不再冒称新增/更新条数。
--
--
-- 执行方式：psql -d diet_agent -f 19_知识库主题扩充_v1.2r1.sql
-- 依赖：12 已执行（表结构未变，但 title/content/category 的非空约束沿用）、14 已执行（无需扩展，只是入队）
--

\set ON_ERROR_STOP on
\pset pager off

-- ---------------------------------------------------------------------------
-- 0. 前置校验：确认目标库确实有这张表和 stable_key 的唯一约束
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF to_regclass('knowledge.knowledge_doc') IS NULL THEN
        RAISE EXCEPTION '找不到 knowledge.knowledge_doc，请先按 00→01→12 的顺序初始化';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'knowledge.knowledge_doc'::regclass
           AND contype  = 'u'
           AND conkey   = ARRAY[(SELECT attnum FROM pg_attribute
                                  WHERE attrelid = 'knowledge.knowledge_doc'::regclass
                                    AND attname  = 'stable_key')]::smallint[]
    ) THEN
        RAISE EXCEPTION 'knowledge.knowledge_doc 上没有 stable_key 唯一约束，ON CONFLICT 会失败';
    END IF;

    -- length() 只有在 UTF8 库上才按字符计；SQL_ASCII 库会退化成按字节，长度口径整体偏差。
    -- 2026-11-16 误判「补边界后有 6 条超过 600 字」就是拿 SQL_ASCII 库测出来的，这里直接拦住。
    IF current_setting('server_encoding') <> 'UTF8' THEN
        RAISE EXCEPTION '当前库 server_encoding 是 %，length() 会按字节计，请用 UTF8 编码建库', current_setting('server_encoding');
    END IF;

    RAISE NOTICE '前置校验通过：知识库表与 stable_key 唯一约束都在';
END
$$;

-- 事务从这里开始：INSERT 与自检同进同退，校验抛异常就整体回滚，
-- 不会出现"数据已落库、脚本却报失败"的半成品状态。
BEGIN;

-- ---------------------------------------------------------------------------
-- 1. 主题条目（17 条）
--    病种 6 + 人群 5 + 膳食结构 3 + 过敏与食品安全 3
-- ---------------------------------------------------------------------------
INSERT INTO knowledge.knowledge_doc
    (stable_key, title, content, category, source, source_id, meta_data)
VALUES
-- ===== 病种（6）=====
(
 'topic:hypertension_diet',
 '高血压人群膳食要点',
 '控盐是第一位的：每天食盐不超过 5 克，酱油、蚝油、鸡精、腌菜、火腿肠、挂面里的钠都要算进去，多数人真正的盐来自这些"看不见的咸"。'
 '日常可以按 DASH 思路吃——蔬菜每天 300～500 克、水果 200～350 克、奶 300 毫升、大豆和坚果 25～35 克，用钾多的天然食物对冲钠。'
 '但富钾是有前提的：合并肾功能不全、血钾偏高，或正在吃保钾利尿剂的人，富钾食物和低钠盐要先问医生。'
 '少吃加工肉和咸菜，少喝酒，体重超标的先减 5%～10%，收缩压往往就跟着下来。'
 '血压已经用药控制的，饮食调整不能替代药物，加减药要听医生的。',
 '病种',
 '成人高血压食养指南（2023年版）',
 'NHC-HTN-2023',
 '{"topic_type": "病种", "audience": "成人高血压人群", "aliases": ["高血压", "血压高", "DASH", "限盐"], "guidelines": ["成人高血压食养指南（2023年版）", "中国居民膳食指南（2022）"], "disclaimer": "膳食建议，不替代诊疗与用药", "chunk_version": "v1", "import_batch_id": 2}'
),
(
 'topic:diabetes_diet',
 '糖尿病与血糖偏高人群膳食要点',
 '三餐定时定量比"吃什么"更容易被忽略：主食每餐大约一拳头（生重 50～75 克，约合熟饭 100～150 克），粗细搭配，全谷杂豆占主食的三分之一到一半。'
 '吃饭顺序可以调成先吃菜、再吃肉蛋豆、最后吃主食，同样的饭菜餐后血糖波动会小一些。'
 '含糖饮料、果汁、蜂蜜水尽量不碰，水果放在两餐之间、每次一小把，优先选草莓、柚子、苹果这类水分多、甜度低的。'
 '用药或打胰岛素的人，主食量变化要和医生对过，别自己按经验减。',
 '病种',
 '成人糖尿病食养指南（2023年版）',
 'NHC-DM-2023',
 '{"topic_type": "病种", "audience": "成人糖尿病及血糖偏高人群", "aliases": ["糖尿病", "血糖高", "控糖", "低GI"], "guidelines": ["成人糖尿病食养指南（2023年版）", "中国居民膳食指南（2022）"], "disclaimer": "膳食建议，不替代诊疗与用药", "chunk_version": "v1", "import_batch_id": 2}'
),
(
 'topic:hyperlipidemia_diet',
 '血脂异常人群膳食要点',
 '先改脂肪的"质"再谈"量"：烹调油每天 25～30 克，少油炸少起酥，反式脂肪能避就避；饱和脂肪控制在总能量的 10% 以内。'
 '每周吃两次鱼（其中一次是深海鱼），每天一小把原味坚果，膳食纤维吃到 25～30 克，燕麦、豆类、苹果里的可溶性纤维对低密度脂蛋白有帮助。'
 '肥肉、动物内脏、奶油点心、椰子油要收着吃；瘦肉、去皮禽肉、豆制品是更稳的蛋白来源。'
 '血脂高到需要吃药的程度，饮食是配合项，不是替代项。',
 '病种',
 '成人高脂血症食养指南（2023年版）',
 'NHC-HL-2023',
 '{"topic_type": "病种", "audience": "血脂异常人群", "aliases": ["高血脂", "胆固醇高", "甘油三酯高", "低密度脂蛋白"], "guidelines": ["成人高脂血症食养指南（2023年版）", "中国居民膳食指南（2022）"], "disclaimer": "膳食建议，不替代诊疗", "chunk_version": "v1", "import_batch_id": 2}'
),
(
 'topic:hyperuricemia_diet',
 '高尿酸与痛风人群膳食要点',
 '嘌呤主要在动物内脏、浓肉汤火锅汤、沙丁鱼凤尾鱼这类小鱼、以及部分贝类里，这些要严格限量；瘦肉、禽肉、淡水鱼可以少量吃，别一顿全上。'
 '酒是明确要停的，尤其啤酒；含果糖的饮料、蜂蜜、大量果汁同样会推高尿酸，很多人只戒海鲜却没戒这两样。'
 '每天喝水 2000～3000 毫升，帮助尿酸排出；低脂奶和鸡蛋嘌呤很低，是安全的蛋白来源。'
 '急性发作期饮食要更严，同时按医生方案处理，别只靠忌口硬扛。',
 '病种',
 '成人高尿酸血症与痛风食养指南（2024年版）',
 'NHC-HUA-2024',
 '{"topic_type": "病种", "audience": "高尿酸血症与痛风人群", "aliases": ["痛风", "尿酸高", "嘌呤", "高尿酸血症"], "guidelines": ["成人高尿酸血症与痛风食养指南（2024年版）", "中国居民膳食指南（2022）"], "disclaimer": "膳食建议，不替代诊疗", "chunk_version": "v1", "import_batch_id": 2}'
),
(
 'topic:fatty_liver_diet',
 '脂肪肝人群膳食要点',
 '脂肪肝最有效的干预是减重：体重降 5%～10%，肝内脂肪往往明显减少，比单纯吃护肝片实在。'
 '要盯住两类东西——酒精和果糖。酒要戒，含糖饮料、甜点、浓缩果汁少碰；主食别全是精米白面，一半换成全谷杂豆和薯类。'
 '蛋白质要吃够（瘦肉、鱼、蛋、豆制品、低脂奶），减重太快、蛋白不够反而容易掉肌肉。'
 '每周至少 150 分钟中等强度有氧加两次抗阻，比只节食更稳。',
 '病种',
 '中国居民膳食指南（2022）+ 成人肥胖食养指南（2024年版）',
 'DG-2022+NHC-OB-2024',
 '{"topic_type": "病种", "audience": "非酒精性脂肪肝人群", "aliases": ["脂肪肝", "脂肪性肝病", "转氨酶高"], "guidelines": ["中国居民膳食指南（2022）", "成人肥胖食养指南（2024年版）"], "disclaimer": "膳食建议，不替代诊疗", "chunk_version": "v1", "import_batch_id": 2}'
),
(
 'topic:ckd_diet',
 '慢性肾脏病人群膳食要点',
 '肾病饮食是"分型分期"的，没有一套人人适用的模板：3～5 期非透析常见 0.6 克/公斤理想体重，具体配额由医生或营养师按肾功能个体化，不能自己往下压。'
 '通用原则是控钠（盐每天 5 克以内）、少吃加工食品以控磷（火腿、可乐、奶茶粉、内脏都是磷大户）；钾要不要限，看血钾化验，不能一律忌水果蔬菜。'
 '主食可以部分用低蛋白米面替代，优质蛋白优先给鸡蛋、奶、瘦肉、鱼和大豆制品（豆腐、豆浆）。'
 '这一条只作方向参考，具体配额必须落在医嘱上。',
 '病种',
 '成人慢性肾脏病食养指南（2024年版）',
 'NHC-CKD-2024',
 '{"topic_type": "病种", "audience": "慢性肾脏病人群", "aliases": ["慢性肾病", "肌酐高", "CKD", "低蛋白饮食"], "guidelines": ["成人慢性肾脏病食养指南（2024年版）"], "disclaimer": "仅供方向参考，蛋白与钾磷配额须遵医嘱", "chunk_version": "v1", "import_batch_id": 2}'
),
-- ===== 人群（5）=====
(
 'topic:pregnancy_nutrition',
 '孕期营养要点',
 '孕早期最要紧的是叶酸：从备孕前 3 个月起每天补 400 微克，吃到孕早期结束，同时多吃绿叶菜、豆类和动物肝脏（肝脏每周 1～2 次、每次 25 克左右即可，别过量）。'
 '孕中晚期铁和碘的需求上来：每天一两红肉补铁，用碘盐并每周吃 1～2 次海带紫菜；鱼虾每周 2～3 次，其中一次深海鱼补 DHA，但要避开鲨鱼、剑鱼、方头鱼这类高汞鱼。'
 '不需要"一人吃两人份"，能量按孕前体重和增重目标来，整个孕期增重建议在医生给的区间内。'
 '生的、半生的东西一律避开（刺身、溏心蛋、现挤奶、未洗净的生菜），酒和含酒精的菜也避开。',
 '人群',
 '中国居民膳食指南（2022）',
 'DG-2022',
 '{"topic_type": "人群", "audience": "备孕及孕期女性", "aliases": ["怀孕", "孕妇", "孕期", "备孕", "叶酸"], "guidelines": ["中国居民膳食指南（2022）"], "disclaimer": "膳食建议，补充剂剂量遵医嘱", "chunk_version": "v1", "import_batch_id": 2}'
),
(
 'topic:lactation_nutrition',
 '哺乳期营养要点',
 '哺乳期每天多消耗约 500 千卡，饭量比孕期还要松一点，但"多喝油汤"没必要——喝进去的脂肪不等于奶量，汤要撇油。'
 '蛋白质每天比孕前多 25 克，奶类吃到 300～500 毫升补钙，每周吃 1～2 次海带紫菜补碘，主食里掺些全谷杂豆。'
 '每天喝水 2000～2500 毫升（比孕前多 500～1000 毫升），出汗多再往上加；酒要完全避开，酒精会进乳汁；咖啡因每天不超过 200 毫克，浓茶、咖啡都要控量。'
 '饮食多样比"忌口清单"重要，除非孩子明确对某种食物过敏，不必大面积忌口。',
 '人群',
 '中国居民膳食指南（2022）',
 'DG-2022',
 '{"topic_type": "人群", "audience": "哺乳期女性", "aliases": ["哺乳期", "喂奶", "产后", "月子餐", "催奶"], "guidelines": ["中国居民膳食指南（2022）"], "disclaimer": "膳食建议，不替代诊疗", "chunk_version": "v1", "import_batch_id": 2}'
),
(
 'topic:elderly_nutrition',
 '65 岁以上人群膳食要点',
 '老年人最容易缺的不是热量而是蛋白质：每天每公斤体重 1.0～1.2 克，而且要摊到三餐，早餐一个蛋加一杯奶，午晚各一掌心肉或鱼，别都堆在晚饭。'
 '食物做软做烂、少食多餐，牙口不好就把肉剁成末、菜切细，硬扛着嚼不动只会越吃越少。'
 '钙和维生素 D 要跟上（奶 300～500 毫升、晒晒太阳），配合每周 2～3 次抗阻和平衡练习，防肌少症也防跌倒。'
 '吞咽容易呛的人，稀汤要增稠、吃饭别说话，必要时找医生评估。',
 '人群',
 '中国老年人膳食指南（2022）',
 'DG-2022',
 '{"topic_type": "人群", "audience": "65 岁以上老年人", "aliases": ["老年人", "老人", "肌少症", "养老餐"], "guidelines": ["中国居民膳食指南（2022）", "中国老年人膳食指南（2022）"], "disclaimer": "膳食建议，不替代诊疗", "chunk_version": "v1", "import_batch_id": 2}'
),
(
 'topic:child_nutrition',
 '学龄儿童膳食要点',
 '早餐要占全天能量的 25%～30%，有主食、有蛋白（蛋/奶/肉）、有一点蔬果，只吃一个包子就出门的早餐撑不到第四节课。'
 '每天奶 300 毫升以上，蔬菜 300 克左右、水果 200 克左右，每周吃一次动物肝脏或血制品补铁。'
 '含糖饮料是这年龄段最该管的一口：一瓶甜饮料的糖就接近一天上限，换成白水或淡茶。'
 '零食放在两餐之间、限量定时，别用来换"好好吃饭"。',
 '人群',
 '中国居民膳食指南（2022）+ 儿童青少年生长迟缓食养指南（2023年版）',
 'DG-2022+NHC-GR-2023',
 '{"topic_type": "人群", "audience": "6～17 岁学龄儿童", "aliases": ["儿童", "学生", "小学生", "学龄儿童", "早餐"], "guidelines": ["中国居民膳食指南（2022）", "儿童青少年生长迟缓食养指南（2023年版）"], "disclaimer": "膳食建议，不替代诊疗", "chunk_version": "v1", "import_batch_id": 2}'
),
(
 'topic:weight_loss_diet',
 '减重期膳食要点',
 '每天比需要量少 300～500 千卡，一周能掉 0.5～1 公斤，这个速度才留得住肌肉；饿到头晕的极低热量法，掉的多是水和肌肉，反弹也快。'
 '蛋白质不能减，反而要占到每公斤体重 1.2～1.5 克（鱼虾、鸡胸、蛋、豆制品、低脂奶），主食换成一半全谷杂豆加薯类，蔬菜吃到 500 克撑饱腹感。'
 '少油少糖是减法，不是"零油零碳水"：油每天仍要 20～25 克，否则脂溶性维生素和激素代谢会出问题。'
 '每周两次抗阻训练，掉下去的体重里脂肪占比较高、肌肉留得住。',
 '人群',
 '中国居民膳食指南（2022）',
 'DG-2022',
 '{"topic_type": "人群", "audience": "超重肥胖、减重需求人群", "aliases": ["减重", "减肥", "瘦身", "热量缺口", "轻断食"], "guidelines": ["中国居民膳食指南（2022）"], "disclaimer": "膳食建议，不替代诊疗", "chunk_version": "v1", "import_batch_id": 2}'
),
-- ===== 膳食结构（3）=====
(
 'topic:balance_plate',
 '平衡膳食餐盘与食物多样',
 '一餐按餐盘分：一半是蔬菜（深色占一半），四分之一是谷薯（其中一部分全谷杂豆），四分之一是鱼禽蛋瘦肉和豆制品，旁边配一杯奶。'
 '一天吃到 12 种以上食物、一周 25 种以上，比死磕某一种"超级食物"有用得多；同类食物之间换着吃（今天鱼明天鸡，今天米饭明天杂粮饭）。'
 '餐餐有蔬菜、天天有水果，主食不过精，是这套结构里最容易被丢掉的三条。',
 '膳食结构',
 '中国居民膳食指南（2022）',
 'DG-2022',
 '{"topic_type": "膳食结构", "audience": "一般健康成人", "aliases": ["膳食宝塔", "平衡膳食", "餐盘", "食物多样"], "guidelines": ["中国居民膳食指南（2022）"], "disclaimer": "一般人群膳食建议", "chunk_version": "v1", "import_batch_id": 2}'
),
(
 'topic:sodium_potassium_balance',
 '钠钾平衡与调味',
 '中国人平均每天吃盐接近 10 克，是推荐量的两倍；目标是把盐压到 5 克以内，同时把钾吃上去（蔬菜、水果、豆类、薯类、菌菇）。'
 '减盐的实操是"替换"而不是"硬少吃"：用醋、柠檬、葱姜蒜、花椒、香草提味，酱油换成蘸着吃而不是倒进去，出锅前再放盐。'
 '买包装食品看营养成分表的钠（每 100 克超过 600 毫克就算高钠），挂面、面包、饼干、话梅都是隐形盐大户。'
 '低钠盐（含氯化钾）对多数人可用，但肾功能不全、正在服保钾利尿剂的人要先问医生。',
 '膳食结构',
 '中国居民膳食指南（2022）',
 'DG-2022',
 '{"topic_type": "膳食结构", "audience": "一般人群，特别是需要控盐者", "aliases": ["减盐", "控钠", "低钠盐", "隐形盐", "钾"], "guidelines": ["中国居民膳食指南（2022）"], "disclaimer": "膳食建议，疾病人群用低钠盐前请咨询医生", "chunk_version": "v1", "import_batch_id": 2}'
),
(
 'topic:whole_grain_staple',
 '全谷杂豆与主食替换',
 '推荐每天谷类 200～300 克，其中全谷物和杂豆 50～150 克、薯类 50～100 克；现实里多数人这一类几乎是零。'
 '落地做法是先替换三分之一到一半：白米饭里掺糙米、燕麦米、藜麦，或者做成二米饭、杂粮粥；面条换成荞麦面、全麦面。'
 '杂豆（红豆、鹰嘴豆、芸豆）提前泡 2～4 小时再煮，口感和消化都更好；刚开始吃多会胀气，从一小把开始加量。',
 '膳食结构',
 '中国居民膳食指南（2022）',
 'DG-2022',
 '{"topic_type": "膳食结构", "audience": "一般人群", "aliases": ["全谷物", "杂粮", "杂豆", "粗粮", "主食替换"], "guidelines": ["中国居民膳食指南（2022）"], "disclaimer": "一般人群膳食建议，胃肠功能弱者逐步加量", "chunk_version": "v1", "import_batch_id": 2}'
),
-- ===== 过敏与食品安全（3）=====
(
 'topic:allergen_substitution',
 '常见食物过敏的替代思路',
 '国标 GB 7718-2011 对致敏物质是"宜"提示（推荐性，不是强制），2025 版（2027 年实施）起才强制标示；涉及含麸质谷物、甲壳类、鱼类、蛋类、花生、大豆、乳、坚果八类，配料表和"可能含有"提示都要看。'
 '替代按营养当量换：牛奶过敏先看年龄再看程度——婴儿（尤其 6 月龄以下）一律以深度水解或氨基酸配方（eHF/AAF）为主，不能拿豆浆替代；儿童和成人轻症才可换强化钙的无糖豆浆，普通豆奶饮料不能顶替；鸡蛋过敏用豆制品、瘦肉补蛋白；小麦过敏走米粉、玉米、荞麦、藜麦，面点要确认生产线无交叉污染。'
 '花生坚果过敏的人可以用烘烤的南瓜子、葵花籽补脂肪和蛋白，但要防同线加工；严重过敏必须按医生的急救方案来，饮食替代只是日常管理的一半。',
 '食物过敏与安全',
 '中国居民膳食指南（2022）',
 'DG-2022',
 '{"topic_type": "食物过敏与安全", "audience": "食物过敏人群及其照护者", "aliases": ["食物过敏", "过敏原", "牛奶过敏", "鸡蛋过敏", "麸质", "替代"], "guidelines": ["中国居民膳食指南（2022）", "GB 7718 预包装食品标签通则"], "disclaimer": "仅供膳食替代参考，严重过敏须遵医嘱并备急救方案", "chunk_version": "v1", "import_batch_id": 2}'
),
(
 'topic:food_safety_leftover',
 '剩饭菜与家庭食品安全',
 '做熟的菜 2 小时内进冰箱（夏天 1 小时），冷藏别超过 24 小时；绿叶菜、凉拌菜、海鲜最好一顿吃完，不留。'
 '再吃要彻底加热到中心烫手（70℃ 以上），汤类要滚开，微波炉加热要翻匀；剩米饭冷藏别超过 24 小时，做炒饭要彻底加热且只加热一次——蜡样芽孢杆菌不一定有馊味，靠闻判断不可靠。'
 '生熟案板刀具分开，冰箱里生食放下层；冰箱只是延缓变质，不是保险箱。',
 '食物过敏与安全',
 '中国居民膳食指南（2022）',
 'DG-2022',
 '{"topic_type": "食物过敏与安全", "audience": "家庭备餐者", "aliases": ["剩菜", "隔夜菜", "食品安全", "冰箱储存", "生熟分开"], "guidelines": ["中国居民膳食指南（2022）"], "disclaimer": "一般家庭食品安全建议", "chunk_version": "v1", "import_batch_id": 2}'
),
(
 'topic:raw_food_risk',
 '生食与半生食的风险人群',
 '刺身、溏心蛋、生腌、现挤生奶、未洗净的生菜，对健康成人是"可能拉肚子"，对孕妇、儿童、老人、免疫力低下的人是李斯特菌、沙门氏菌、创伤弧菌的高风险入口。'
 '这几类人群要全熟：蛋要蛋黄凝固，鱼虾要煮透，奶要经过巴氏杀菌或超高温灭菌，生食蔬果用流水搓洗、能去皮就去皮。'
 '外出就餐时，"半熟""现杀现吃"这类卖点恰恰是要避开的地方。',
 '食物过敏与安全',
 '中国居民膳食指南（2022）',
 'DG-2022',
 '{"topic_type": "食物过敏与安全", "audience": "孕妇、儿童、老人及免疫力低下者", "aliases": ["生食", "刺身", "溏心蛋", "李斯特菌", "生腌"], "guidelines": ["中国居民膳食指南（2022）"], "disclaimer": "一般食品安全建议，出现发热腹泻请就医", "chunk_version": "v1", "import_batch_id": 2}'
)
ON CONFLICT (stable_key) DO UPDATE
   SET title      = EXCLUDED.title,
       content    = EXCLUDED.content,
       category   = EXCLUDED.category,
       source     = EXCLUDED.source,
       source_id  = EXCLUDED.source_id,
       meta_data  = EXCLUDED.meta_data,
       is_deleted = false,
       updated_at = now();

-- ---------------------------------------------------------------------------
-- 2. 自检：条数、分类分布、17 个 key 是否齐全、有没有重复
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    v_total      integer;
    v_new        integer;
    v_missing    text;
    v_dup        integer;
    v_short      integer;
BEGIN
    SELECT count(*) INTO v_total FROM knowledge.knowledge_doc WHERE NOT is_deleted;

    SELECT count(*) INTO v_new
      FROM knowledge.knowledge_doc
     WHERE stable_key LIKE 'topic:%';

    SELECT string_agg(k, ', ') INTO v_missing
      FROM (VALUES
        ('topic:hypertension_diet'), ('topic:diabetes_diet'), ('topic:hyperlipidemia_diet'),
        ('topic:hyperuricemia_diet'), ('topic:fatty_liver_diet'), ('topic:ckd_diet'),
        ('topic:pregnancy_nutrition'), ('topic:lactation_nutrition'), ('topic:elderly_nutrition'),
        ('topic:child_nutrition'), ('topic:weight_loss_diet'), ('topic:balance_plate'),
        ('topic:sodium_potassium_balance'), ('topic:whole_grain_staple'),
        ('topic:allergen_substitution'), ('topic:food_safety_leftover'), ('topic:raw_food_risk')
      ) AS t(k)
     WHERE NOT EXISTS (
        SELECT 1 FROM knowledge.knowledge_doc d WHERE d.stable_key = t.k AND NOT d.is_deleted
     );

    SELECT count(*) INTO v_dup
      FROM (SELECT stable_key FROM knowledge.knowledge_doc GROUP BY stable_key HAVING count(*) > 1) x;

    -- 2026-11-17 修正口径：length() 在 UTF8 库上数的是字符，octet_length() 数的是字节（中文约 3 字节/字）。
    -- 17 条实测 159～319 字、455～881 字节，600 字上限留有余量，不需要放宽；
    -- 上一版把 750 写进注释和校验，是拿 SQL_ASCII 库测出来的字节数当成了字数。
    -- 另加 1000 字节兜底（约 330 字）：字数达标但中文堆得过密时，单条切片仍会撑大 RAG 的 chunk。
    SELECT count(*) INTO v_short
      FROM knowledge.knowledge_doc
     WHERE stable_key LIKE 'topic:%'
       AND (length(content) < 100 OR length(content) > 600 OR octet_length(content) > 1000);

    IF v_missing IS NOT NULL THEN
        RAISE EXCEPTION '主题条目缺失：%', v_missing;
    END IF;
    IF v_dup > 0 THEN
        RAISE EXCEPTION 'stable_key 出现重复 % 组', v_dup;
    END IF;
    IF v_short > 0 THEN
        RAISE EXCEPTION '有 % 条主题条目正文长度不在 100～600 字之间，或超过 1000 字节', v_short;
    END IF;

    RAISE NOTICE '主题扩充完成：当前 topic 总数 % 条，知识库有效总数 % 条', v_new, v_total;
END
$$;

COMMIT;

SELECT check_item, result
  FROM (VALUES
        ('database_name',          current_database()::text),
        ('knowledge_total',        (SELECT count(*)::text FROM knowledge.knowledge_doc WHERE NOT is_deleted)),
        ('nutrient_rows',          (SELECT count(*)::text FROM knowledge.knowledge_doc WHERE stable_key LIKE 'nutrient:%')),
        ('topic_rows',             (SELECT count(*)::text FROM knowledge.knowledge_doc WHERE stable_key LIKE 'topic:%')),
        ('cat_维生素',             (SELECT count(*)::text FROM knowledge.knowledge_doc WHERE category = '维生素' AND NOT is_deleted)),
        ('cat_矿物质',             (SELECT count(*)::text FROM knowledge.knowledge_doc WHERE category = '矿物质' AND NOT is_deleted)),
        ('cat_脂肪酸',             (SELECT count(*)::text FROM knowledge.knowledge_doc WHERE category = '脂肪酸' AND NOT is_deleted)),
        ('cat_其他',               (SELECT count(*)::text FROM knowledge.knowledge_doc WHERE category = '其他' AND NOT is_deleted)),
        ('cat_病种',               (SELECT count(*)::text FROM knowledge.knowledge_doc WHERE category = '病种' AND NOT is_deleted)),
        ('cat_人群',               (SELECT count(*)::text FROM knowledge.knowledge_doc WHERE category = '人群' AND NOT is_deleted)),
        ('cat_膳食结构',           (SELECT count(*)::text FROM knowledge.knowledge_doc WHERE category = '膳食结构' AND NOT is_deleted)),
        ('cat_食物过敏与安全',     (SELECT count(*)::text FROM knowledge.knowledge_doc WHERE category = '食物过敏与安全' AND NOT is_deleted)),
        ('min_content_len',        (SELECT min(length(content))::text FROM knowledge.knowledge_doc WHERE stable_key LIKE 'topic:%')),
        ('max_content_len',        (SELECT max(length(content))::text FROM knowledge.knowledge_doc WHERE stable_key LIKE 'topic:%')),
        ('max_content_bytes',      (SELECT max(octet_length(content))::text FROM knowledge.knowledge_doc WHERE stable_key LIKE 'topic:%')),
        ('duplicate_keys',         (SELECT count(*)::text FROM (SELECT stable_key FROM knowledge.knowledge_doc GROUP BY stable_key HAVING count(*) > 1) x)),
        ('backlog_after_19',       (SELECT count(*)::text FROM knowledge.v_embedding_backlog))
       ) AS v(check_item, result)
 ORDER BY check_item;
