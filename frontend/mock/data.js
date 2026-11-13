/**
 * Mock 数据层：为前端联调提供「契约一致」的数据与生成逻辑。
 * 注意：真实后端实现同一份契约（见 docs/agent-output-contract.md），
 * 这里的数值只用于演示结构，不代表营养学结论。
 */

const WEEKDAY_NAMES = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

/* ---------- 日期工具 ---------- */
export function pad2(n) {
  return String(n).padStart(2, '0')
}

export function dayInfo(offset = 0) {
  const now = new Date()
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + offset)
  return {
    iso: `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`,
    md: `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`,
    weekday: WEEKDAY_NAMES[d.getDay()],
    isToday: offset === 0
  }
}

/* ---------- 7 种关键微量 ---------- */
export const MICRO_DEFS = [
  { key: 'calcium', name: '钙', unit: 'mg', target: 800 },
  { key: 'iron', name: '铁', unit: 'mg', target: 15 },
  { key: 'zinc', name: '锌', unit: 'mg', target: 12 },
  { key: 'vitA', name: '维生素A', unit: 'μg', target: 800 },
  { key: 'vitB1', name: '维生素B1', unit: 'mg', target: 1.2 },
  { key: 'vitB2', name: '维生素B2', unit: 'mg', target: 1.3 },
  { key: 'vitC', name: '维生素C', unit: 'mg', target: 100 }
]

/* ---------- 菜谱模板（dish: [名称, 估量, kcal, 提示]） ---------- */
const MEAL_COLOR = { breakfast: '#e8942c', lunch: '#4a7c59', dinner: '#3b7fd4' }

const MEAL_META = {
  breakfast: { label: '早餐', time: '07:30' },
  lunch: { label: '午餐', time: '12:00' },
  dinner: { label: '晚餐', time: '18:30' }
}

const WEEK_TEMPLATE = [
  [
    ['breakfast', 430, [
      ['全麦吐司', '2 片', 180, '配无糖豆浆。'],
      ['无糖豆浆', '250 ml', 90, '现磨更香。'],
      ['小番茄', '100 g', 30, '洗净直接吃。'],
      ['水煮蛋', '1 个', 80, '煮 8 分钟。']
    ]],
    ['lunch', 620, [
      ['糙米饭', '1 碗（熟重 150g）', 210, '提前泡米。'],
      ['香煎鸡胸肉', '120 g', 200, '少油煎，撒黑胡椒。'],
      ['清炒西兰花', '150 g', 80, '焯水后快炒。'],
      ['凉拌木耳', '80 g', 50, '加醋和蒜末。']
    ]],
    ['dinner', 630, [
      ['杂粮饭', '1 小碗', 180, '晚上主食减一点。'],
      ['清蒸鲈鱼', '150 g', 190, '蒸 8 分钟。'],
      ['蒜蓉生菜', '150 g', 70, '大火快炒 30 秒。'],
      ['冬瓜汤', '1 碗', 40, '加虾皮提鲜。']
    ]]
  ],
  [
    ['breakfast', 460, [
      ['鸡蛋饼', '1 张', 200, '面糊里加一把葱花。'],
      ['无糖酸奶', '150 g', 90, '配点水果更好吃。'],
      ['香蕉', '半根', 50, '运动前吃更合适。'],
      ['核桃', '2 个', 70, '一天两三个封顶。']
    ]],
    ['lunch', 680, [
      ['藜麦饭', '1 碗', 220, '藜麦混白米一起煮。'],
      ['黑椒牛柳', '110 g', 230, '牛肉提前用淀粉抓一下更嫩。'],
      ['蒜蓉空心菜', '150 g', 70, '茎部先下锅。'],
      ['番茄蛋汤', '1 碗', 80, '番茄先炒出汁再加水。']
    ]],
    ['dinner', 610, [
      ['杂粮饭', '1 小碗', 180, '控制在一小碗。'],
      ['白灼鸡毛菜', '150 g', 40, '水开下锅 30 秒。'],
      ['香煎鳕鱼', '130 g', 180, '少油，两面各 3 分钟。'],
      ['紫菜汤', '1 碗', 40, '紫菜一小把即可。']
    ]]
  ],
  [
    ['breakfast', 420, [
      ['小米粥', '1 碗', 130, '小米容易消化。'],
      ['水煮蛋', '1 个', 80, '煮 8 分钟。'],
      ['凉拌豆腐', '100 g', 90, '内酯豆腐加生抽和香油。'],
      ['橙子', '1 个', 60, '饭后半小时吃更好。']
    ]],
    ['lunch', 620, [
      ['糙米饭', '1 碗', 210, '提前泡米。'],
      ['豉汁蒸排骨', '100 g', 220, '选小排，蒸 20 分钟。'],
      ['清炒芥蓝', '150 g', 70, '焯水后再炒。'],
      ['冬瓜汤', '1 碗', 40, '不放油更好。']
    ]],
    ['dinner', 590, [
      ['玉米', '1 根', 120, '晚餐用玉米替主食。'],
      ['番茄龙利鱼', '130 g', 170, '番茄先炒软再下鱼。'],
      ['蒜蓉菠菜', '150 g', 70, '先焯水去草酸。']
    ]]
  ],
  [
    ['breakfast', 420, [
      ['燕麦粥', '1 碗（干燕麦 40g）', 150, '牛奶或水煮都行。'],
      ['水煮蛋', '1 个', 80, '冷水下锅，水开煮 8 分钟。'],
      ['蓝莓', '80 g', 45, '可用草莓替换。'],
      ['无糖豆浆', '200 ml', 80, '温热喝更舒服。']
    ]],
    ['lunch', 610, [
      ['二米饭', '1 碗（大米+小米）', 200, '小米占三成，香气更足。'],
      ['番茄炖牛腩', '120 g 牛腩', 230, '小火炖 40 分钟。'],
      ['清炒油麦菜', '150 g', 80, '大火快炒，别久煮。']
    ]],
    ['dinner', 630, [
      ['杂粮饭', '1 小碗', 180, '晚上主食控制在一小碗。'],
      ['白灼虾', '120 g', 130, '水开下锅 2 分钟。'],
      ['蒜蓉菠菜', '150 g', 70, '菠菜先焯水去草酸。'],
      ['紫菜蛋花汤', '1 碗', 50, '紫菜一小把就够。']
    ]]
  ],
  [
    ['breakfast', 440, [
      ['全麦吐司', '2 片', 180, '配一杯热豆浆。'],
      ['煎蛋', '1 个', 90, '不粘锅少油。'],
      ['牛油果', '1/4 个', 70, '压成泥抹在吐司上。'],
      ['小番茄', '100 g', 30, '洗净直接吃。']
    ]],
    ['lunch', 640, [
      ['荞麦面', '1 碗（干面 80g）', 210, '过凉水更筋道。'],
      ['卤鸡腿', '1 只（去皮）', 220, '去皮能省下不少脂肪。'],
      ['凉拌黄瓜', '150 g', 50, '拍碎后加蒜末和醋。'],
      ['溏心蛋', '1 个', 80, '煮 6 分半钟。']
    ]],
    ['dinner', 630, [
      ['糙米饭', '1 小碗', 180, '提前泡米口感更好。'],
      ['香菇滑鸡', '120 g 鸡腿肉', 210, '香菇先煸香。'],
      ['上汤娃娃菜', '150 g', 60, '用鸡汤打底，少放盐。']
    ]]
  ],
  [
    ['breakfast', 420, [
      ['红薯', '1 个（约 150g）', 150, '蒸或烤都行。'],
      ['无糖酸奶', '150 g', 90, '选配料表只有奶和菌的。'],
      ['水煮蛋', '1 个', 80, '一次煮几个放冰箱更省事。'],
      ['杏仁', '10 颗', 70, '一天一小把就够。']
    ]],
    ['lunch', 650, [
      ['意面', '1 份（干面 80g）', 220, '选全麦意面，升糖更慢。'],
      ['番茄肉酱', '100 g', 180, '用瘦牛肉末，少放油。'],
      ['清炒芦笋', '150 g', 70, '芦笋掰掉老根再炒。'],
      ['罗宋汤', '1 碗', 80, '番茄、洋葱、卷心菜一起炖。']
    ]],
    ['dinner', 610, [
      ['杂粮饭', '1 小碗', 180, '三色藜麦混白米。'],
      ['清蒸鳕鱼', '140 g', 160, '蒸 7 分钟。'],
      ['蒜蓉西兰花', '150 g', 80, '焯水后快炒。'],
      ['味增汤', '1 碗', 50, '味增最后放。']
    ]]
  ],
  [
    ['breakfast', 410, [
      ['玉米', '1 根', 120, '水煮 10 分钟。'],
      ['茶叶蛋', '1 个', 80, '提前一晚煮好更入味。'],
      ['无糖豆浆', '250 ml', 90, '可以加点燕麦一起打。'],
      ['苹果', '半个', 50, '带皮吃纤维更多。']
    ]],
    ['lunch', 620, [
      ['糙米饭', '1 碗', 210, '提前泡米。'],
      ['芹菜炒牛肉', '100 g 牛里脊', 200, '牛肉逆纹切，快炒不变硬。'],
      ['手撕包菜', '150 g', 60, '手撕比刀切更入味。'],
      ['凉拌海带丝', '80 g', 50, '加点醋更开胃。']
    ]],
    ['dinner', 620, [
      ['红薯', '1 个', 150, '晚餐用红薯替一部分米饭。'],
      ['香煎三文鱼', '120 g', 230, '鱼皮朝下先煎。'],
      ['清炒芥蓝', '150 g', 70, '焯水后再炒。']
    ]]
  ]
]

/* ---------- 换候选池（按餐次） ---------- */
const CANDIDATE_POOL = {
  breakfast: [
    {
      name: '方案 A · 蒸红薯 + 无糖酸奶 + 水煮蛋',
      kcal: 320,
      desc: '少油好操作，饱腹感稳定到午饭',
      dishes: [
        ['蒸红薯', '1 个（约 150g）', 150, '蒸 20 分钟，带皮更香。'],
        ['无糖酸奶', '150 g', 90, '配料表只有奶和菌。'],
        ['水煮蛋', '1 个', 80, '煮 8 分钟。']
      ]
    },
    {
      name: '方案 B · 小米粥 + 茶叶蛋 + 凉拌豆腐',
      kcal: 300,
      desc: '温热好入口，肠胃负担轻',
      dishes: [
        ['小米粥', '1 碗', 130, '煮到米粒开花。'],
        ['茶叶蛋', '1 个', 80, '提前一晚煮好。'],
        ['凉拌豆腐', '100 g', 90, '内酯豆腐加生抽和香油。']
      ]
    },
    {
      name: '方案 C · 玉米 + 无糖豆浆 + 苹果',
      kcal: 260,
      desc: '纤维足、带走吃也方便',
      dishes: [
        ['玉米', '1 根', 120, '水煮 10 分钟。'],
        ['无糖豆浆', '250 ml', 90, '现磨更香。'],
        ['苹果', '半个', 50, '带皮吃纤维更多。']
      ]
    }
  ],
  lunch: [
    {
      name: '方案 A · 糙米饭 + 香煎鸡胸肉 + 清炒西兰花',
      kcal: 620,
      desc: '蛋白质 38g，少油好操作，下午不容易饿',
      dishes: [
        ['糙米饭', '1 碗（熟重 150g）', 210, '提前泡米 30 分钟。'],
        ['香煎鸡胸肉', '120 g', 200, '少油，两面各煎 3 分钟。'],
        ['清炒西兰花', '150 g', 80, '焯水 1 分钟后快炒。'],
        ['凉拌木耳', '80 g', 50, '加蒜末、生抽、香醋。']
      ]
    },
    {
      name: '方案 B · 荞麦面 + 卤鸡腿 + 凉拌黄瓜',
      kcal: 640,
      desc: '主食换成荞麦面，升糖更平缓',
      dishes: [
        ['荞麦面', '1 碗（干面 80g）', 210, '煮 5 分钟过凉水。'],
        ['卤鸡腿', '1 只（去皮）', 220, '小火卤 30 分钟。'],
        ['凉拌黄瓜', '150 g', 50, '拍碎加蒜末和醋。'],
        ['溏心蛋', '1 个', 80, '煮 6 分半钟。']
      ]
    },
    {
      name: '方案 C · 藜麦饭 + 黑椒牛柳 + 蒜蓉空心菜',
      kcal: 680,
      desc: '铁和锌更足，口味重一点',
      dishes: [
        ['藜麦饭', '1 碗', 220, '藜麦与白米 1:1 混煮。'],
        ['黑椒牛柳', '110 g', 230, '牛里脊逆纹切，快炒。'],
        ['蒜蓉空心菜', '150 g', 70, '先下茎后下叶。'],
        ['番茄蛋汤', '1 碗', 80, '番茄先炒出汁。']
      ]
    }
  ],
  dinner: [
    {
      name: '方案 A · 红薯 + 香煎三文鱼 + 清炒芥蓝',
      kcal: 450,
      desc: '用红薯替一部分主食，脂肪结构更好',
      dishes: [
        ['红薯', '1 个（约 150g）', 150, '晚餐主食替一半。'],
        ['香煎三文鱼', '120 g', 230, '鱼皮朝下先煎。'],
        ['清炒芥蓝', '150 g', 70, '焯水后再炒。']
      ]
    },
    {
      name: '方案 B · 杂粮饭 + 白灼虾 + 蒜蓉菠菜',
      kcal: 380,
      desc: '清淡少油，睡前 3 小时吃完更合适',
      dishes: [
        ['杂粮饭', '1 小碗', 180, '控制在一小碗。'],
        ['白灼虾', '120 g', 130, '水开下锅 2 分钟。'],
        ['蒜蓉菠菜', '150 g', 70, '先焯水去草酸。']
      ]
    },
    {
      name: '方案 C · 玉米 + 番茄龙利鱼 + 蒜蓉菠菜',
      kcal: 360,
      desc: '低脂高蛋白，牙口和肠胃都轻松',
      dishes: [
        ['玉米', '1 根', 120, '水煮 10 分钟。'],
        ['番茄龙利鱼', '130 g', 170, '番茄先炒软再下鱼。'],
        ['蒜蓉菠菜', '150 g', 70, '焯水后快炒。']
      ]
    }
  ]
}

/* ---------- 微量覆盖（演示数值） ---------- */
const MICRO_BY_SCOPE = {
  day: [
    ['钙', '99%', 99, 'ok', '约 790 mg'],
    ['铁', '87%', 87, 'ok', '约 13 mg'],
    ['锌', '92%', 92, 'ok', '约 11 mg'],
    ['维生素A', '88%', 88, 'ok', '约 700 μg'],
    ['维生素B1', '92%', 92, 'ok', '约 1.1 mg'],
    ['维生素B2', '92%', 92, 'ok', '约 1.2 mg'],
    ['维生素C', '92%', 92, 'ok', '约 92 mg']
  ],
  meal: [
    ['钙', '26%', 26, 'warn', '约 210 mg'],
    ['铁', '33%', 33, 'ok', '约 5 mg'],
    ['锌', '33%', 33, 'ok', '约 4 mg'],
    ['维生素A', '30%', 30, 'ok', '约 240 μg'],
    ['维生素B1', '28%', 28, 'warn', '约 0.34 mg'],
    ['维生素B2', '25%', 25, 'warn', '约 0.33 mg'],
    ['维生素C', '20%', 20, 'danger', '约 20 mg']
  ],
  week: [
    ['钙', '96%', 96, 'ok', '日均约 770 mg'],
    ['铁', '91%', 91, 'ok', '约 13.7 mg'],
    ['锌', '93%', 93, 'ok', '约 11.2 mg'],
    ['维生素A', '90%', 90, 'ok', '约 720 μg'],
    ['维生素B1', '94%', 94, 'ok', '约 1.13 mg'],
    ['维生素B2', '92%', 92, 'ok', '约 1.2 mg'],
    ['维生素C', '95%', 95, 'ok', '约 95 mg']
  ]
}

const MACRO_BY_SCOPE = {
  day: ['1680', 'kcal 全天', [['蛋白质', 22, 'protein', '达标', 'ok', '约 92g / 目标 95g'], ['碳水', 53, 'carb', '达标', 'ok', '约 208g / 目标 230g'], ['脂肪', 25, 'fat', '合理', 'blue', '约 46g / 目标 55g']]],
  meal: ['620', 'kcal 本餐', [['蛋白质', 32, 'protein', '达标', 'ok', '约 38g'], ['碳水', 45, 'carb', '达标', 'ok', '约 70g'], ['脂肪', 23, 'fat', '合理', 'blue', '约 16g']]],
  week: ['1685', 'kcal 日均', [['蛋白质', 22, 'protein', '达标', 'ok', '日均约 90g'], ['碳水', 53, 'carb', '达标', 'ok', '日均约 210g'], ['脂肪', 25, 'fat', '合理', 'blue', '日均约 47g']]]
}

const INSIGHTS_BY_SCOPE = {
  day: [
    '蛋白质达标，减脂期有助于维持肌肉。',
    '膳食纤维充足，利于平稳血糖与饱腹感。',
    '晚餐清淡少油，适合睡前 3 小时完成进食。'
  ],
  meal: [
    '这一餐蛋白质充足，适合作为日常午餐。',
    '主食选粗粮，升糖更平稳，下午不容易饿。',
    '再配一份绿叶蔬菜汤或水果，可补上维生素 C。'
  ],
  week: [
    '整周方案已按天拆解，建议按 2~3 天分批采购，食材更新鲜。',
    '七日菜式尽量不重复，蛋白质来源覆盖肉、蛋、奶、豆与鱼。',
    '周末两天蛋白质略高、蔬菜量也够，适合作为运动日的搭配。'
  ]
}

export const SOURCES = [
  { title: '中国居民膳食指南（2022）', publisher: '中国营养学会', published_at: '2022-04-26', url: 'http://dg.cnsoc.org/' },
  { title: '中国食物成分表（标准版 第6版）', publisher: '中国疾病预防控制中心营养与健康所', published_at: '2018-08-01', url: 'https://www.chinanutri.cn/' },
  { title: '中国居民膳食营养素参考摄入量（2023版）', publisher: '中国营养学会', published_at: '2023-09-01', url: 'https://www.cnsoc.org/' }
]

/* ---------- 构建 ---------- */
function toDish(mealType, idx, d) {
  return {
    dish_id: `${mealType}-${idx}`,
    name: d[0],
    amount: d[1],
    kcal: d[2],
    oil_g: 3,
    salt_g: 1.2,
    tip: d[3] || '',
    is_staple: /米|面|吐司|馒头|红薯|玉米|藜麦|燕麦|小米|麦|饼|面包/.test(d[0])
  }
}

function buildSlot(mealType, kcal, dishArr, idx) {
  const meta = MEAL_META[mealType]
  return {
    slot_id: `s-${idx}-${mealType}`,
    meal_type: mealType,
    label: meta.label,
    time: meta.time,
    color: MEAL_COLOR[mealType],
    kcal,
    macro: {
      protein_g: Math.round((kcal * 0.22) / 4),
      carb_g: Math.round((kcal * 0.5) / 4),
      fat_g: Math.round((kcal * 0.28) / 9)
    },
    oil_g: mealType === 'breakfast' ? 2 : 6,
    salt_g: mealType === 'breakfast' ? 1.0 : 1.8,
    dishes: dishArr.map((d, i) => toDish(mealType, i, d)),
    candidates: CANDIDATE_POOL[mealType].map((c, i) => ({
      candidate_id: `${mealType}-c${i}`,
      name: c.name,
      kcal: c.kcal,
      desc: c.desc,
      dishes: c.dishes.map((d, j) => toDish(mealType, j, d))
    })),
    selected_candidate_id: `${mealType}-c0`,
    micro_coverage: MICRO_BY_SCOPE.meal.map(([name, value, ring, status, note]) => ({
      name, value, ring_percent: ring, status, note
    }))
  }
}

function macroBlock(scope) {
  const [center_value, center_label, segments] = MACRO_BY_SCOPE[scope]
  return {
    center_value,
    center_label,
    segments: segments.map(([name, percent, color, tag, tag_level, desc]) => ({
      name, percent, color, tag, tag_level, desc
    }))
  }
}

function microBlock(scope, title) {
  const list = MICRO_BY_SCOPE[scope] || MICRO_BY_SCOPE.week
  return {
    title,
    items: list.map(([name, value, ring, status, note]) => ({
      name, value, ring_percent: ring, status, note
    }))
  }
}

function nutritionOf(scope) {
  return {
    scope,
    macro: macroBlock(scope),
    micro: microBlock(scope, scope === 'month' ? '关键微量月达标率（天）' : scope === 'week' ? '关键微量周达标率（天）' : '关键微量元素覆盖'),
    insights: INSIGHTS_BY_SCOPE[scope] || INSIGHTS_BY_SCOPE.day,
    coverage: { level: 'ok', text: '7 项关键微量均在参考范围内，跨日动态平衡已生效' }
  }
}

let planSeq = 1

export function buildPlan(planType) {
  const days = []
  const count = planType === 'week' ? 7 : 1
  for (let i = 0; i < count; i++) {
    const tpl = WEEK_TEMPLATE[planType === 'week' ? i : 0]
    // 单餐（推荐一餐）只保留午餐 slot，避免出现「只有一道菜却给了三餐表」的错位
    const meals = planType === 'meal' ? tpl.filter((m) => m[0] === 'lunch') : tpl
    const info = dayInfo(i)
    const slots = meals.map((m, idx) => buildSlot(m[0], m[1], m[2], i * 3 + idx))
    days.push({
      date: info.md,
      iso: info.iso,
      weekday: info.weekday,
      is_today: info.isToday,
      kcal: meals.reduce((s, m) => s + m[1], 0),
      slots
    })
  }

  const firstDay = days[0]
  const plan = {
    plan_id: `plan_${Date.now()}_${planSeq++}`,
    plan_type: planType,
    status: 'draft',
    title: planType === 'week' ? '接下来七天食谱' : planType === 'meal' ? '午餐方案' : '今日三餐',
    subtitle:
      planType === 'week'
        ? `${days[0].date} ~ ${days[days.length - 1].date} · 日均约 ${Math.round(days.reduce((s, d) => s + d.kcal, 0) / days.length)} kcal`
        : planType === 'meal'
          ? `${firstDay.date} ${firstDay.weekday} · 午餐约 ${firstDay.kcal} kcal · 3 个候选可选`
          : `${firstDay.date} ${firstDay.weekday} · 全天约 ${firstDay.kcal} kcal`,
    range_text:
      planType === 'week'
        ? `${days[0].date} ~ ${days[days.length - 1].date}`
        : `${firstDay.date} ${firstDay.weekday}`,
    plan_date: firstDay.iso,
    goal_energy_kcal: 1850,
    goal_text: '减脂 · 目标 1850 kcal',
    macro_ratio: { protein: 0.22, carb: 0.53, fat: 0.25 },
    days,
    nutrition: nutritionOf(planType === 'week' ? 'week' : planType === 'meal' ? 'meal' : 'day'),
    sources: SOURCES,
    reason_points:
      planType === 'meal'
        ? [
            '单餐热量控制在本餐区间（约 620～680 kcal），蛋白质不低于 30g。',
            '主食选粗粮或荞麦面，升糖更平缓，下午不容易饿。',
            '已按你的档案规避花生及其制品，过敏原是硬性限制。'
          ]
        : [
            '三餐热量按 30% / 40% / 30% 分配，结构与减脂目标一致。',
            '蛋白质来源覆盖蛋、禽、鱼、豆，早餐也有优质蛋白。',
            '主食选糙米、杂粮和红薯，比白米饭升糖更平稳。',
            '已排除花生及含花生的酱料，过敏原为硬性约束。'
          ],
    updated_at: new Date().toISOString(),
    executed: false
  }
  return plan
}

export function planSummary(plan) {
  return {
    plan_id: plan.plan_id,
    title: plan.title,
    plan_type: plan.plan_type,
    range_text: plan.range_text,
    status: plan.status,
    executed: plan.executed,
    kcal: plan.days[0].kcal,
    created_at: plan.updated_at
  }
}

/* ---------- 食材清单 ---------- */
function categorize(name) {
  if (/菜|瓜|茄|椒|芦笋|木耳|海带|菌|菇|笋|菠菜|芥蓝|空心菜|油麦菜|娃娃菜|包菜|鸡毛菜|秋葵|番茄|西兰花|萝卜|白菜/.test(name)) return '🥬 蔬菜类'
  if (/鸡|牛|猪|鱼|虾|肉|排|三文鱼|鳕鱼|鲈鱼|龙利鱼|鸡胸|鸡腿|排骨|蛋/.test(name)) return '🍗 肉禽蛋水产'
  if (/米|面|吐司|馒头|红薯|玉米|藜麦|燕麦|小米|麦|饼|面包/.test(name)) return '🌾 主食杂粮'
  if (/蓝莓|苹果|香蕉|橙子|牛油果|核桃|杏仁|莓|香蕉|梨/.test(name)) return '🍎 水果坚果'
  if (/豆浆|酸奶|牛奶|豆腐|豆/.test(name)) return '🥛 奶豆饮品'
  return '🧂 其他'
}

export function buildShoppingList(plan) {
  const groups = []
  const days = plan.days || []
  const multiDay = plan.plan_type === 'week'
  days.forEach((day, di) => {
    const byCat = {}
    day.slots.forEach((slot) => {
      slot.dishes.forEach((d) => {
        const cat = categorize(d.name)
        if (!byCat[cat]) byCat[cat] = []
        if (!byCat[cat].some((x) => x.name === d.name)) {
          byCat[cat].push({ name: d.name, amount: d.amount, is_staple: !!d.is_staple })
        }
      })
    })
    Object.keys(byCat).forEach((cat) => {
      groups.push({
        group_id: `g-${di}-${cat}`,
        day: multiDay ? (di === 0 ? '今天' : day.weekday) : null,
        day_date: multiDay ? day.date : null,
        category: cat,
        items: byCat[cat].map((it, i) => ({
          item_id: `it-${di}-${i}-${it.name}`,
          name: it.name,
          amount: it.amount,
          is_staple: it.is_staple,
          checked: false
        }))
      })
    })
  })
  return {
    meal_plan_id: plan.plan_id,
    updated_at: plan.updated_at,
    groups
  }
}

/* ---------- 近七天历史摄入（用于报告，演示用） ---------- */
function seededHistory() {
  const rows = []
  for (let i = 6; i >= 0; i--) {
    const info = dayInfo(-i)
    const jitter = Math.round(Math.sin(i * 1.7) * 180)
    rows.push({
      date: info.iso,
      label: info.md,
      meals: i % 5 === 0 ? 2 : 3,
      calories: 1720 + jitter,
      protein: 88 + Math.round(Math.sin(i * 1.3) * 6),
      carb: 212 + Math.round(jitter * 0.1),
      fat: 48 + Math.round(jitter * 0.03),
      micros: {
        calcium: 760 + Math.round(Math.abs(Math.sin(i)) * 120),
        iron: 12 + Math.round(Math.abs(Math.cos(i)) * 5),
        zinc: 10 + Math.round(Math.abs(Math.sin(i * 0.5)) * 4),
        vitA: 680 + Math.round(Math.abs(Math.cos(i * 0.7)) * 150),
        vitB1: 1.0 + Math.abs(Math.sin(i * 0.3)) * 0.4,
        vitB2: 1.1 + Math.abs(Math.cos(i * 0.4)) * 0.3,
        vitC: 82 + Math.round(Math.abs(Math.sin(i * 0.6)) * 40)
      }
    })
  }
  return rows
}

export function buildReport(scope = 'week') {
  const target = { calories: 1850, protein: 95, carb: 230, fat: 55 }
  let days = seededHistory()
  if (scope === 'month') {
    const extra = []
    for (let i = 0; i < 23; i++) {
      const info = dayInfo(-30 + i)
      const calJitter = Math.round((Math.sin(i * 1.7) + Math.cos(i * 0.8)) * 200)
      extra.push({
        date: info.iso,
        label: info.md,
        meals: 3,
        calories: 1650 + calJitter,
        protein: 82 + Math.round(Math.sin(i * 1.3) * 8),
        carb: 210 + Math.round(calJitter * 0.13),
        fat: 52 + Math.round(calJitter * 0.03),
        micros: {
          calcium: 680 + Math.round(Math.abs(Math.sin(i)) * 150),
          iron: 10 + Math.round(Math.abs(Math.cos(i)) * 6),
          zinc: 8 + Math.round(Math.abs(Math.sin(i * 0.5)) * 5),
          vitA: 650 + Math.round(Math.abs(Math.cos(i * 0.7)) * 200),
          vitB1: 0.9 + Math.abs(Math.sin(i * 0.3)) * 0.5,
          vitB2: 1.0 + Math.abs(Math.cos(i * 0.4)) * 0.4,
          vitC: 60 + Math.round(Math.abs(Math.sin(i * 0.6)) * 60)
        }
      })
    }
    days = [...extra, ...days]
  }

  const validDays = days.length
  const sum = (k) => days.reduce((s, d) => s + d[k], 0)
  const avg = (k) => Math.round(sum(k) / validDays)
  const totalCal = avg('protein') * 4 + avg('carb') * 4 + avg('fat') * 9
  const pPct = Math.round((avg('protein') * 4 * 100) / totalCal)
  const cPct = Math.round((avg('carb') * 4 * 100) / totalCal)
  const fPct = 100 - pPct - cPct

  const microItems = MICRO_DEFS.map((m) => {
    const achieved = days.filter((d) => d.micros[m.key] >= m.target).length
    const ratio = achieved / validDays
    return {
      name: m.name,
      value: `${achieved}/${validDays}`,
      ring_percent: Math.round(ratio * 100),
      status: ratio >= 0.8 ? 'ok' : ratio >= 0.5 ? 'warn' : 'danger',
      note: `${validDays} 天中 ${achieved} 天达标`
    }
  })

  const lowMicros = microItems.filter((m) => m.ring_percent < 70)
  const insights = []
  if (pPct < 15) insights.push(`蛋白质占比偏低（日均 ${avg('protein')}g），建议每餐加一份优质蛋白。`)
  else if (pPct > 25) insights.push(`蛋白质占比偏高（${pPct}%），注意搭配蔬菜与全谷物。`)
  else insights.push(`蛋白质占比 ${pPct}%，落在合理区间，继续保持。`)
  if (lowMicros.length) insights.push(`${lowMicros.map((m) => m.name).join('、')} 达标天数偏少，建议在方案里针对性补足。`)
  else insights.push('7 项关键微量达标情况良好，跨日动态平衡起效。')
  if (scope === 'month') insights.push('本月热量波动在目标区间内，没有连续高热量日。')
  insights.push('膳食纤维与油盐控制稳定，符合“结构优先于数值”的取舍。')

  const trend = days.map((d, i) => ({
    date: d.label,
    calories: d.calories,
    show_date: i % 5 === 0,
    status: d.calories > target.calories * 1.15 ? 'over' : d.calories < target.calories * 0.6 ? 'low' : 'ok'
  }))

  return {
    report_id: `report_${Date.now()}`,
    scope,
    headline: scope === 'week' ? '上周膳食报告' : '本月膳食报告',
    meta: {
      scope,
      range_start: days[0].label,
      range_end: days[days.length - 1].label,
      generated_at: new Date().toISOString(),
      valid_days: validDays,
      total_meals: days.reduce((s, d) => s + d.meals, 0),
      target_kcal: target.calories
    },
    summary_text: `共覆盖 ${validDays} 天、${days.reduce((s, d) => s + d.meals, 0)} 餐。日均 ${avg('calories')} kcal，蛋白质 ${avg('protein')}g（${pPct}%）。`,
    macro: {
      center_value: `${avg('calories')}`,
      center_label: 'kcal 日均',
      segments: [
        { name: '蛋白质', percent: pPct, color: 'protein', tag: pPct >= 15 && pPct <= 25 ? '达标' : '注意', tag_level: pPct >= 15 && pPct <= 25 ? 'ok' : 'warn', desc: `日均 ${avg('protein')}g / 目标 ${target.protein}g` },
        { name: '碳水', percent: cPct, color: 'carb', tag: cPct >= 45 && cPct <= 65 ? '达标' : '注意', tag_level: cPct >= 45 && cPct <= 65 ? 'ok' : 'warn', desc: `日均 ${avg('carb')}g / 目标 ${target.carb}g` },
        { name: '脂肪', percent: fPct, color: 'fat', tag: fPct >= 20 && fPct <= 30 ? '合理' : '注意', tag_level: fPct >= 20 && fPct <= 30 ? 'blue' : 'warn', desc: `日均 ${avg('fat')}g / 目标 ${target.fat}g` }
      ]
    },
    micro: {
      title: scope === 'week' ? '关键微量周达标率（天）' : '关键微量月达标率（天）',
      items: microItems
    },
    daily_trend: trend,
    insights
  }
}

export const MICRO_UNIT = MICRO_DEFS

export { CANDIDATE_POOL }
