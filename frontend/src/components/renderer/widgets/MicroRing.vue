<template>
  <div class="micro-ring-wrapper" :style="{ width: size + 'px', height: size + 'px' }">
    <svg class="micro-ring" :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`">
      <circle class="track" :cx="size / 2" :cy="size / 2" :r="radius" />
      <circle
        class="progress"
        :class="item.status"
        :cx="size / 2"
        :cy="size / 2"
        :r="radius"
        :stroke-dasharray="dash"
      />
    </svg>
    <div class="micro-val" :style="{ fontSize: valFontSize }">{{ item.value }}</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  item: { type: Object, required: true },
  size: { type: Number, default: 44 }
})

const radius = computed(() => props.size / 2 - 2)
const circumference = computed(() => 2 * Math.PI * radius.value)
const dash = computed(() => {
  const pct = Math.min(100, Math.max(0, Number(props.item.percent) || 0))
  return `${(circumference.value * pct) / 100} ${circumference.value}`
})

// 中心文字按长度自适应字号：短值（—/92%）正常，长值（167.9%）缩到能居中放下
const valFontSize = computed(() => {
  const len = String(props.item.value || '').length
  const base = props.size < 40 ? 10 : 11
  if (len <= 3) return `${base}px`
  if (len <= 5) return `${base - 1}px`
  return `${base - 2}px`
})
</script>

<style scoped>
.micro-ring .progress.neutral {
  stroke: var(--chart-empty);
}
</style>