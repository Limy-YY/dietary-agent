<template>
  <aside class="tool-panel" :class="{ open: panel.active }">
    <div class="panel-inner">
      <div class="panel-header-title">
        <span class="panel-head-ico" v-html="ICONS[panel.active]"></span>
        <span>{{ currentTitle }}</span>
        <span class="type-tag" :class="PANELS.find((x) => x.key === panel.active)?.type">
          {{ PANEL_TYPES[panel.active] }}
        </span>
        <button class="panel-close" title="收起面板" @click="panel.close()">✕</button>
      </div>
      <div class="panel-body">
        <component :is="currentComp" v-if="panel.active" />
      </div>
    </div>
  </aside>

  <aside class="icon-sidebar">
    <button class="toggle-sidebar-btn" title="收起 / 展开工具" @click="iconsCollapsed = !iconsCollapsed">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="4" y="3" width="16" height="10" rx="2" ry="2" />
        <polyline points="8 17 12 21 16 17" />
      </svg>
    </button>

    <div class="tools-group" :class="{ hidden: iconsCollapsed }">
      <button
        v-for="p in PANELS"
        :key="p.key"
        :data-key="p.key"
        class="tool-icon"
        :class="{ active: panel.active === p.key }"
        @click="panel.toggle(p.key)"
      >
        <span class="tool-ico" v-html="ICONS[p.key]"></span>
        <span class="tool-label">
          <span class="line">{{ p.line1 }}</span>
          <span class="line">{{ p.line2 }}</span>
        </span>
        <span v-if="p.key === 'report' && panel.unreadReports" class="tool-badge">{{ panel.unreadReports }}</span>
      </button>
    </div>
  </aside>
</template>

<script setup>
import { computed, markRaw, ref } from 'vue'
import { PANELS, PANEL_TITLES, PANEL_TYPES } from '@/constants/actions.js'
import { usePanelStore } from '@/stores/panel.js'
import GroceryPanel from './panels/GroceryPanel.vue'
import CurrentPlanPanel from './panels/CurrentPlanPanel.vue'
import HistoryPanel from './panels/HistoryPanel.vue'
import ReportPanel from './panels/ReportPanel.vue'

const panel = usePanelStore()
const iconsCollapsed = ref(false)

/* 与 main.html 原型一致的线性图标 */
const ICONS = {
  grocery:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>',
  current_plan:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
  history:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
  report:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/></svg>'
}

const COMPONENTS = {
  grocery: markRaw(GroceryPanel),
  current_plan: markRaw(CurrentPlanPanel),
  history: markRaw(HistoryPanel),
  report: markRaw(ReportPanel)
}

const currentComp = computed(() => COMPONENTS[panel.active] || null)
const currentTitle = computed(() => PANEL_TITLES[panel.active] || '')
</script>
