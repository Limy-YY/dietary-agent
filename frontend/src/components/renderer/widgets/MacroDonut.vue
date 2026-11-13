<template>
  <div class="donut-wrapper" :style="{ width: size + 'px', height: size + 'px' }">
    <div class="donut-chart" :style="{ background: gradient }"></div>
    <div class="donut-inner">
      <div class="donut-val" :style="{ fontSize: valueSize + 'px' }">{{ macro.center_value || '—' }}</div>
      <div class="donut-label">{{ macro.center_label || '' }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  macro: { type: Object, required: true },
  size: { type: Number, default: 90 },
  valueSize: { type: Number, default: 18 }
})

const COLORS = {
  protein: 'var(--chart-protein)',
  carb: 'var(--chart-carb)',
  fat: 'var(--chart-fat)'
}

const gradient = computed(() => {
  const segments = (props.macro && props.macro.segments) || []
  if (!segments.length) return 'var(--chart-empty)'

  let acc = 0
  const stops = segments.map((s) => {
    const from = acc
    acc += Math.max(0, Number(s.percent) || 0)
    const color = COLORS[s.color] || s.color || 'var(--chart-empty)'
    return `${color} ${from}% ${acc}%`
  })
  // 总和不足 100 时用浅色补齐，避免出现断口
  if (acc < 100) stops.push(`var(--chart-empty) ${acc}% 100%`)
  return `conic-gradient(${stops.join(', ')})`
})
</script>
