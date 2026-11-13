<template>
  <div class="report-card" :class="{ expanded }">
    <div class="rc-head" @click="expanded = !expanded">
      <div style="min-width: 0">
        <div class="rc-title">📊 {{ report.headline }}</div>
        <div class="rc-meta">
          {{ report.meta.range_start }} ~ {{ report.meta.range_end }}
          <span v-if="report.meta.valid_days">· 有效 {{ report.meta.valid_days }} 天</span>
          <span v-if="report.meta.total_meals"> · {{ report.meta.total_meals }} 餐</span>
        </div>
        <div v-if="report.summary_text" class="rc-summary">{{ report.summary_text }}</div>
      </div>
      <button class="rc-toggle">{{ expanded ? '收起' : '展开查看' }}</button>
    </div>

    <div v-if="expanded" class="rc-body">
      <div class="rp-section">
        <div class="rp-section-title">🥗 宏量供能比</div>
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
                  <span class="rp-legend-name">{{ seg.name }} {{ seg.percent }}%</span>
                  <span v-if="seg.tag" class="rp-legend-tag" :class="seg.tag_level">{{ seg.tag }}</span>
                </div>
                <div class="rp-legend-desc">{{ seg.desc }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="rp-section">
        <div class="rp-section-title">🔬 {{ report.micro.title }}</div>
        <div class="rp-micro-grid">
          <div v-for="(m, i) in report.micro.items" :key="i" class="rp-micro">
            <MicroRing :item="m" :size="42" />
            <div class="rp-micro-name">{{ m.name }}</div>
          </div>
        </div>
      </div>

      <div v-if="report.daily_trend.length" class="rp-section">
        <div class="rp-section-title">📈 每日热量</div>
        <div class="rp-trend">
          <div v-for="(d, i) in report.daily_trend" :key="i" class="rp-bar-wrap" :title="`${d.date} · ${d.calories} kcal`">
            <span class="rp-bar-val">{{ d.calories }}</span>
            <div class="rp-bar-area">
              <div class="rp-bar" :class="d.status" :style="{ height: barHeight(d) }"></div>
            </div>
            <div class="rp-bar-date">{{ d.show_date ? d.date : '' }}</div>
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
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import MacroDonut from '../widgets/MacroDonut.vue'
import MicroRing from '../widgets/MicroRing.vue'
import { normalizeReport } from '@/utils/schema.js'

const props = defineProps({ block: { type: Object, required: true } })
const report = computed(() => normalizeReport(props.block))
const expanded = ref(Boolean(props.block.expanded))

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
</style>
