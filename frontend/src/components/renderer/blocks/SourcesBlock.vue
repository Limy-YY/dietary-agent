<template>
  <div class="sources-block">
    <div class="sources-title">
      <span>📚</span>
      <span>{{ block.title || '参考来源' }}</span>
    </div>
    <a
      v-for="(s, i) in items"
      :key="i"
      class="source-item"
      :href="s.url || '#'"
      target="_blank"
      rel="noopener noreferrer"
      @click="onClick($event, s)"
    >
      <div class="source-name">{{ s.title || s.name || '未命名来源' }}</div>
      <div class="source-meta">
        <span v-if="s.publisher">{{ s.publisher }}</span>
        <span v-if="s.published_at"> · {{ s.published_at }}</span>
      </div>
      <div v-if="s.snippet" class="source-snippet">{{ s.snippet }}</div>
    </a>
    <div v-if="!items.length" class="source-meta">暂无来源信息</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { arr } from '@/utils/schema.js'

const props = defineProps({ block: { type: Object, required: true } })
const items = computed(() => arr(props.block.items))

function onClick(e, s) {
  if (!s.url) e.preventDefault()
}
</script>
