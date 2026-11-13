<template>
  <div class="recipe-card nutrition-card">
    <div class="card-head">
      <div>
        <h3>📊 营养结构</h3>
        <p class="card-sub">{{ scopeLabel }} · 宏量供能比与 7 项关键微量</p>
      </div>
      <span v-if="coverageText" class="coverage-tag" :class="coverageLevel">{{ coverageText }}</span>
    </div>

    <div style="padding: 16px 20px 18px">
      <div class="donut-card">
        <MacroDonut :macro="nutrition.macro" :size="90" />
        <div class="nutri-legend">
          <div v-for="(seg, i) in nutrition.macro.segments" :key="i" class="legend-item">
            <span class="legend-dot" :class="seg.color"></span>
            <div class="legend-info">
              <div class="legend-top">
                <span class="legend-name">{{ seg.name }} {{ seg.percent }}%</span>
                <span v-if="seg.tag" class="legend-tag" :class="seg.tag_level">{{ seg.tag }}</span>
              </div>
              <div class="legend-desc">{{ seg.desc }}</div>
            </div>
          </div>
          <div v-if="!nutrition.macro.segments.length" class="legend-desc">暂无宏量数据</div>
        </div>
      </div>

      <div class="nutri-title" style="margin-top: 18px">🔬 {{ nutrition.micro.title }}</div>
      <MicroGrid :items="nutrition.micro.items" />

      <div v-for="(tip, i) in nutrition.insights" :key="'i' + i" class="plan-insight">{{ tip }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import MacroDonut from '../widgets/MacroDonut.vue'
import MicroGrid from '../widgets/MicroGrid.vue'
import { normalizeNutrition } from '@/utils/schema.js'

const props = defineProps({ block: { type: Object, required: true } })

const nutrition = computed(() => normalizeNutrition(props.block))

const SCOPE_LABELS = { day: '全天', meal: '本餐', week: '日均', month: '月均' }
const scopeLabel = computed(() => SCOPE_LABELS[nutrition.value.scope] || '本方案')

const coverageText = computed(() => {
  const c = nutrition.value.coverage
  if (!c) return ''
  return typeof c === 'string' ? c : c.text || ''
})
const coverageLevel = computed(() => {
  const c = nutrition.value.coverage
  return c && typeof c === 'object' && c.level === 'warn' ? 'warn' : 'ok'
})
</script>

<style scoped>
.nutrition-card {
  margin-top: 8px;
}
</style>
