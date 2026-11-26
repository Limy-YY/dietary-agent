<template>
  <div class="report-card" :class="{ expanded }">
    <div class="rc-head" @click="expanded = !expanded">
      <div style="min-width: 0">
        <div class="rc-title">📊 {{ report.headline }}</div>
        <div class="rc-meta">
          {{ report.meta.range_text }}
          <span v-if="report.meta.valid_days">· 共 {{ report.meta.valid_days }} 天</span>
          <span v-if="report.meta.total_meals"> · {{ report.meta.total_meals }} 餐</span>
          <el-tooltip placement="top" effect="dark" :content="dailyBasisTip">
            <span class="rc-basis">按已记录餐次</span>
          </el-tooltip>
        </div>
        <div class="rc-summary">{{ summaryLine }}</div>
      </div>
      <button class="rc-toggle">{{ expanded ? '收起' : '展开查看' }}</button>
    </div>

    <div v-if="expanded" class="rc-body">
      <div class="rp-section">
        <div class="rp-section-title">
          🥗 宏量供能比（日均）
          <el-tooltip placement="top" effect="dark" :content="dailyBasisTip">
            <span class="rp-info-dot">ⓘ</span>
          </el-tooltip>
        </div>
        <div class="rp-donut-row">
          <div class="rp-donut">
            <div class="rp-donut-chart">
              <MacroDonut :macro="report.macro" :size="84" :value-size="17" />
            </div>
          </div>
          <div class="rp-legend">
            <div v-for="(seg, i) in report.macro.segments" :key="i" class="rp-legend-item">
              <span class="rp-legend-dot" :class="seg.color"></span>
              <div class="rp-legend-info">
                <div class="rp-legend-top">
                  <span class="rp-legend-name">{{ seg.name }} {{ seg.percent === null ? '—' : seg.percent + '%' }}</span>
                  <span v-if="seg.tag" :class="['rp-legend-tag', seg.tag_level]">{{ seg.tag }}</span>
                </div>
                <div class="rp-legend-desc">{{ seg.desc }}</div>
              </div>
            </div>
          </div>
        </div>
        <div class="rp-extra">
          <div v-for="m in report.extra_metrics" :key="m.key" class="rp-extra-item">
            <span class="rp-extra-name">{{ m.name }}</span>
            <span class="rp-extra-val">
              <span class="rp-extra-num">{{ fmtNum(m.value) }}</span><span class="rp-extra-unit">{{ m.unit }}</span>
              <span v-if="m.reference != null" class="rp-extra-ref">/ {{ m.ref_label }} {{ fmtNum(m.reference) }}{{ m.unit }}</span>
              <span v-else class="rp-extra-ref">/ 参考值缺失</span>
              <span :class="['rp-extra-tag', m.status]">{{ ctrlText(m.status) }}</span>
            </span>
          </div>
        </div>
      </div>

      <div class="rp-section">
        <div class="rp-section-title">🔬 {{ report.micro.title }}</div>
        <div v-if="report.coverage && report.coverage.full_days != null" class="rp-micro-overall">
          完整 {{ report.coverage.full_days }} 天 · 部分 {{ report.coverage.partial_days }} 天 · 无记录 {{ report.coverage.empty_days }} 天
          <template v-if="report.micro.evaluable_count != null && report.micro.total_count != null">
            · 可评估 {{ report.micro.evaluable_count }}/{{ report.micro.total_count }} 项
          </template>
        </div>
        <div class="rp-micro-grid">
          <div v-for="(m, i) in report.micro.items" :key="i" class="rp-micro">
            <MicroRing :item="m" :size="42" />
            <div class="rp-micro-name">{{ m.name }}</div>
            <div v-if="m.intake != null && m.target != null" class="rp-micro-note-item">
              完整天日均 {{ fmtNum(m.intake) }}{{ m.unit }} / 参考 {{ fmtNum(m.target) }}{{ m.unit }}
            </div>
            <div v-if="m.covered_pct == null" class="rp-micro-note-item">
              {{ report.coverage && report.coverage.full_days > 0 ? '该微量部分餐次缺数据，不判达标' : '无完整天，不判达标' }}
            </div>
            <div v-else class="rp-micro-note-item">
              {{ fmtNum(m.achieved_days) }}/{{ fmtNum(m.valid_days) }} 天达标
            </div>
            <div class="rp-micro-flags">
              <span v-if="m.over_days > 0" class="rp-flag over">超标 {{ fmtNum(m.over_days) }} 天</span>
              <span v-if="m.under_days > 0" class="rp-flag under">不足 {{ fmtNum(m.under_days) }} 天</span>
            </div>
          </div>
        </div>
        <p class="rp-micro-note">环形百分比 = 完整天（三餐齐全）日均摄入 ÷ 每日参考量；「N/M 天达标」按「当日摄入 ≥ 参考量 80% 且未超每日上限」计。部分记录天不计入、不外推。</p>
      </div>

      <div v-if="report.daily_trend.length" class="rp-section">
        <div class="rp-section-title">📈 每日热量</div>
        <div class="rp-trend">
          <div v-for="(d, i) in report.daily_trend" :key="i" class="rp-bar-wrap" :title="`${d.date} · ${d.calories === null || d.calories === undefined ? '—' : d.calories} kcal`">
            <span class="rp-bar-val">{{ d.calories === null || d.calories === undefined ? '—' : d.calories }}</span>
            <div class="rp-bar-area">
              <div class="rp-bar" :class="d.status" :style="{ height: barHeight(d) }"></div>
            </div>
            <div class="rp-bar-date">{{ d.show_date ? d.label || d.date : '' }}</div>
          </div>
        </div>
      </div>

      <div v-if="hasInsights" class="rp-insights">
        <h5>关键结论</h5>
        <p v-if="!report.insights.legacy && report.insights.verdict" class="rp-verdict">
          {{ report.insights.verdict }}
        </p>
        <template v-if="report.insights.legacy">
          <ul class="rp-insight-list">
            <li v-for="(t, i) in report.insights.items" :key="i" class="rp-insight neutral">{{ t }}</li>
          </ul>
        </template>
        <template v-else>
          <div v-if="report.insights.plan.length" class="rp-insight-group">本方案</div>
          <ul v-if="report.insights.plan.length" class="rp-insight-list">
            <li v-for="(t, i) in report.insights.plan" :key="'p' + i" :class="['rp-insight', t.level]">{{ t.text }}</li>
          </ul>
          <div v-if="report.insights.advice.length" class="rp-insight-group">建议</div>
          <ul v-if="report.insights.advice.length" class="rp-insight-list">
            <li v-for="(t, i) in report.insights.advice" :key="'a' + i" class="rp-insight advice">{{ t.text }}</li>
          </ul>
          <div v-if="report.insights.trend.length" class="rp-insight-group">长期回看</div>
          <ul v-if="report.insights.trend.length" class="rp-insight-list">
            <li v-for="(t, i) in report.insights.trend" :key="'t' + i" class="rp-insight trend">{{ t.text }}</li>
          </ul>
        </template>
      </div>
    </div>

    <!-- 数据口径与说明：默认收起，概况已在标题下用一句话交代，避免术语刷屏 -->
    <div v-if="hasDetail" class="rc-foot">
      <button type="button" class="rc-foot-toggle" @click="detailOpen = !detailOpen">
        数据口径与说明
        <span class="rc-foot-caret">{{ detailOpen ? '收起' : '展开' }}</span>
      </button>
      <div v-if="detailOpen" class="rc-quality">
        <p v-for="(n, i) in report.data_quality_notes" :key="'q' + i" class="rc-quality-line">{{ n }}</p>
        <p v-if="report.reference_hints.length" class="rc-quality-line">
          {{ report.reference_hints.join('；') }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import MacroDonut from '../widgets/MacroDonut.vue'
import MicroRing from '../widgets/MicroRing.vue'
import { fmtNum, normalizeReport } from '@/utils/schema.js'

const props = defineProps({ block: { type: Object, required: true } })
const report = computed(() => (props.block?.meta ? props.block : normalizeReport(props.block)))
const expanded = ref(Boolean(props.block.expanded))
const detailOpen = ref(false)

const hasInsights = computed(() => {
  const ins = report.value.insights || {}
  if (ins.legacy) return ins.items.length > 0
  return Boolean(ins.verdict) || ins.plan.length > 0 || ins.advice.length > 0 || ins.trend.length > 0
})

// 详情注记是否值得给一个入口：没有内容就不放折叠按钮
const hasDetail = computed(() => {
  const notes = report.value.data_quality_notes || []
  const hints = report.value.reference_hints || []
  return notes.length > 0 || hints.length > 0
})

// 覆盖范围 + 数据完整度翻译成一句人话，替代原来四行带标签的溯源注记
const summaryLine = computed(() => {
  const c = report.value.completeness || {}
  const p = report.value.plan_stats || {}
  const days = report.value.meta?.valid_days
  const parts = []

  if (c.meal_count != null) {
    let s = `记录 ${fmtNum(c.meal_count)} 餐`
    if (days) s += `（${fmtNum(days)} 天有记录）`
    if (c.missing_meal_count > 0) s += `，其中 ${fmtNum(c.missing_meal_count)} 餐缺数据`
    parts.push(s)
  }
  if (p.total_plans != null) {
    let s = `覆盖 ${fmtNum(p.total_plans)} 份方案`
    if (p.executed_plans > 0) s += `（已执行 ${fmtNum(p.executed_plans)} 份）`
    parts.push(s)
  }
  parts.push('数据为估算值，仅供参考')
  return parts.join(' · ')
})

const CTRL_TEXT = { ok: '合适', high: '偏高', low: '偏低', unknown: '数据不足' }
function ctrlText(s) {
  return CTRL_TEXT[s] || '—'
}

const dailyBasisTip =
  '摄入达成率 = 完整天（三餐齐全）日均摄入 ÷ 每日参考量；部分记录天不计入、也不外推。达标天数只统计三餐齐全的完整天'

const maxCalories = computed(() => {
  const list = report.value.daily_trend.map((d) => Number(d.calories) || 0)
  return Math.max(...list, 1)
})

function barHeight(d) {
  const h = Math.round(((Number(d.calories) || 0) / maxCalories.value) * 100)
  return `${Math.max(4, h)}%`
}
</script>

<style scoped>
.rp-info-dot {
  display: inline-block;
  margin-left: 4px;
  font-size: 12px;
  color: var(--text-sub);
  cursor: help;
  vertical-align: middle;
}

.rp-info-dot:hover {
  color: var(--brand-hover);
}

.rp-donut-chart {
  position: absolute;
  inset: 0;
}

.rp-donut-chart :deep(.donut-wrapper) {
  width: 84px;
  height: 84px;
}

.rp-extra {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--border-soft, #e8e8e8);
}

.rp-extra-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.rp-extra-name {
  font-size: 11.5px;
  color: var(--text-sub);
}

.rp-extra-val {
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: baseline;
  gap: 5px;
}

.rp-extra-num {
  font-weight: 600;
}

.rp-extra-unit {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-sub);
  margin-right: 2px;
}

.rp-extra-ref {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-sub);
}

.rp-extra-tag {
  font-size: 10px;
  font-weight: 500;
  padding: 0 5px;
  border-radius: 4px;
  background: var(--bg-soft, #f2f3f5);
  color: var(--text-sub);
}

.rp-extra-tag.ok {
  color: var(--chart-protein);
  background: rgba(76, 175, 80, 0.12);
}

.rp-extra-tag.high {
  color: var(--chart-danger);
  background: rgba(239, 83, 80, 0.12);
}

.rp-extra-tag.low {
  color: var(--chart-warn);
  background: rgba(255, 152, 0, 0.12);
}

.rp-bar.neutral {
  background: var(--chart-empty, #f0f0f0);
}

.rp-micro-note-item {
  margin-top: 2px;
  font-size: 10px;
  color: var(--text-sub);
  white-space: nowrap;
}

.rp-micro-flags {
  margin-top: 3px;
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.rp-flag {
  font-size: 10px;
  line-height: 1.5;
  padding: 0 5px;
  border-radius: 4px;
  white-space: nowrap;
}

.rp-flag.over {
  color: var(--chart-danger);
  background: rgba(239, 83, 80, 0.12);
}

.rp-flag.under {
  color: var(--chart-warn);
  background: rgba(255, 152, 0, 0.12);
}

.rp-micro-note {
  margin-top: 10px;
  font-size: 11.5px;
  color: var(--text-sub);
  line-height: 1.6;
}

.rc-summary {
  margin-top: 3px;
  font-size: 11.5px;
  color: var(--text-sub);
  line-height: 1.6;
}

.rc-foot {
  padding: 8px 18px 10px;
  border-top: 1px solid var(--border-soft, #eee);
  background: var(--bg-soft, #fafafa);
}

.rc-foot-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  border: none;
  background: none;
  font-family: inherit;
  font-size: 11.5px;
  color: var(--text-sub);
  cursor: pointer;
}

.rc-foot-toggle:hover {
  color: var(--brand-hover);
}

.rc-foot-caret {
  color: var(--brand-hover);
}

.rc-quality {
  margin-top: 6px;
  font-size: 11px;
  color: var(--text-sub);
  line-height: 1.7;
}

.rc-quality-line {
  margin: 0;
}

.rc-quality-line + .rc-quality-line {
  margin-top: 2px;
}
</style>
