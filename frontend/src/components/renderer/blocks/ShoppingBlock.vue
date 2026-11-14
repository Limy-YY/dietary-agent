<template>
  <div class="recipe-card">
    <div class="card-head">
      <div>
        <h3>🛒 {{ block.title || '食材清单' }}</h3>
        <p class="card-sub">{{ block.summary || '按类别归好了，照着买就行' }}</p>
      </div>
      <div class="status-tag draft">共 {{ total }} 项</div>
    </div>

    <div style="padding: 10px 20px 14px">
      <div v-for="(g, gi) in groups" :key="g.group_id || gi" style="margin-bottom: 12px">
        <div class="grocery-group-title">
          <span>{{ g.category }}</span>
          <span style="font-weight: 400; color: var(--text-sub); font-size: 11.5px">{{ g.items.length }} 项</span>
        </div>
        <div v-for="(it, ii) in g.items" :key="it.item_id || ii" class="grocery-item" style="cursor: default">
          <span class="gi-name">{{ it.name }}</span>
          <span class="gi-amount">{{ it.amount }}</span>
        </div>
      </div>
      <div v-if="!groups.length" class="card-sub">清单还是空的，确认方案后我按类别归好。</div>
      <div v-if="groups.length" class="grocery-note">数量为估算量，按实际采购调整；粮油等常备品类按家中存量自行增减。</div>
    </div>

    <div class="card-foot">
      <span class="card-sub" style="margin: 0">面板里可以边买边勾</span>
      <div class="action-col">
        <button class="fix-btn" @click="openPanel">打开食材清单</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { normalizeGroups } from '@/utils/schema.js'
import { usePanelStore } from '@/stores/panel.js'

const props = defineProps({ block: { type: Object, required: true } })
const panel = usePanelStore()

const groups = computed(() => normalizeGroups(props.block.groups))
const total = computed(() => {
  if (props.block.total_items != null) return props.block.total_items
  return groups.value.reduce((s, g) => s + g.items.length, 0)
})

function openPanel() {
  panel.open('grocery')
}
</script>

<style scoped>
.grocery-note {
  margin-top: 10px;
  font-size: 11.5px;
  color: var(--text-sub);
  line-height: 1.6;
}
</style>