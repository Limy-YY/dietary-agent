<template>
  <div class="anchor-bar">
    <button
      v-for="(a, i) in items"
      :key="i"
      class="anchor-btn"
      @click="go(a)"
    >
      <span>{{ PANEL_ICONS[a.panel] || '↗' }}</span>
      <span>{{ a.label || PANEL_TITLES[a.panel] || '查看详情' }}</span>
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { arr, pick } from '@/utils/schema.js'
import { PANEL_TITLES } from '@/constants/actions.js'
import { usePanelStore } from '@/stores/panel.js'

const props = defineProps({ block: { type: Object, required: true } })
const panel = usePanelStore()

const PANEL_ICONS = {
  grocery: '🛒',
  current_plan: '📋',
  history: '🗂️',
  report: '📊'
}

const items = computed(() =>
  arr(pick(props.block, 'items', 'anchors', 'actions')).map((a) => ({
    panel: pick(a, 'panel', 'target', 'key') || '',
    label: pick(a, 'label', 'text', 'title') || ''
  }))
)

function go(a) {
  if (a.panel) panel.open(a.panel)
}
</script>
