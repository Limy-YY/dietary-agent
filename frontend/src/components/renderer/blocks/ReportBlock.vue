<template>
  <div class="report-card" :class="{ expanded }">
    <div class="rc-head" @click="expanded = !expanded">
      <div style="min-width: 0">
        <div class="rc-title">📊 {{ report.headline }}</div>
        <div class="rc-meta">
          {{ report.meta.range_text }}
          <span v-if="report.meta.valid_days">· 有效 {{ report.meta.valid_days }} 天</span>
          <span v-if="report.meta.total_meals"> · {{ report.meta.total_meals }} 餐</span>
          <span class="rc-basis">日均口径</span>
        </div>
      </div>
      <button class="rc-toggle">{{ expanded ? '收起' : '展开查看' }}</button>
    </div>

    <div v-if="expanded" class="rc-body">
      <div class="rp-section">
        <div class="rp-section-title">🥗 宏量供能比（日均）</div>
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
        <div v-if="report.micro.overall_pct != null" class="rp-micro-overall">
          综合达标率 <b>{{ report.micro.overall_pct }}%</b>
          <template v-if="report.micro.evaluable_count != null && report.micro.total_count != null">
            · 可评估 {{ report.micro.evaluable_count }}/{{ report.micro.total_count }} 项
          </template>
        </div>
        <div class="rp-micro-grid">
          <div v-for="(m, i) in report.micro.items" :key="i" class="rp-micro">
            <MicroRing :item="m" :size="42" />
            <div class="rp-micro-name">{{ m.name }}</div>
            <div v-if="m.valid_days != null && m.valid_days > 0" class="rp-micro-note-item">
              {{ fmtNum(m.achieved_days) }}/{{ fmtNum(m.valid_days) }} 天达标
            </div>
            <div v-else class="rp-micro-note-item">无日数据</div>
            <div class="rp-micro-flags">
              <span v-if="m.over_days > 0" class="rp-flag over">超标 {{ fmtNum(m.over_days) }} 天</span>
              <span v-if="m.under_days > 0" class="rp-flag under">不足 {{ fmtNum(m.under_days) }} 天</span>
            </div>
          </div>
        </div>
        <p class="rp-micro-note">达标天数按「当日摄入 ≥ 每日参考量 80% 且未超每日上限」计；仅统计有数据的日期，数据不足的日期不计入。</p>
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

      <div v-if="report.insights.length" class="rp-insights">
        <h5>关键结论</h5>
        <ul>
          <li v-for="(t, i) in report.insights" :key="i">{{ t }}</li>
        </ul>
      </div>
    </div>

    <!-- 数据质量与完整度：常驻，不折叠 -->
    <div class="rc-quality">
      <div v-if="report.plan_stats && report.plan_stats.total_plans != null" class="rc-quality-line">
        <span class="rc-quality-label">覆盖范围</span>
        <span>
          共 {{ fmtNum(report.plan_stats.total_plans) }} 份已固定方案 ·
          {{ fmtNum(report.plan_stats.executed_plans) }} 份已执行
        </span>
      </div>
      <div class="rc-quality-line">
        <span class="rc-quality-label">数据完整度</span>
        <span>
          共 {{ fmtNum(report.completeness.meal_count) }} 餐 · 已知
          {{ fmtNum(report.completeness.known_meal_count) }} 餐 · 缺失
          {{ fmtNum(report.completeness.missing_meal_count) }} 餐
        </span>
      </div>
      <div v-for="(n, i) in report.data_quality_notes" :key="'q' + i" class="rc-quality-line">
        <span class="rc-quality-label">数据说明</span>
        <span>{{ n }}</span>
      </div>
      <div v-if="report.reference_hints.length" class="rc-quality-line">
        <span class="rc-quality-label">参考口径</span>
        <span>{{ report.reference_hints.join('；') }}</span>
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

const CTRL_TEXT = { ok: '合适', high: '偏高', low: '偏低', unknown: '数据不足' }
function ctrlText(s) {
  return CTRL_TEXT[s] || '—'
}

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

.rc-quality {
  border-top: 1px solid var(--border-soft, #eee);
  padding: 10px 18px 12px;
  background: var(--bg-soft, #fafafa);
  font-size: 11.5px;
  color: var(--text-sub);
  line-height: 1.7;
}

.rc-quality-line {
  display: flex;
  gap: 8px;
}

.rc-quality-label {
  flex: none;
  color: var(--text-main, #333);
  font-weight: 600;
}
</style>
