<template>
  <div class="schema-fallback">
    <div class="sf-title">收到一个前端未识别的结构：<strong>{{ block.type || 'unknown' }}</strong>（已原样展示，未报错）</div>
    <pre>{{ pretty }}</pre>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ block: { type: Object, required: true } })
const pretty = computed(() => {
  try {
    return JSON.stringify(props.block, null, 2)
  } catch (e) {
    return String(props.block)
  }
})
</script>
