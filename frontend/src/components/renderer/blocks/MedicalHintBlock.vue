<template>
  <div class="medical-hint">
    <span class="mh-icon">⚠️</span>
    <div style="min-width: 0">
      <div class="mh-title">{{ block.title || '这不是医学诊断' }}</div>
      <div class="mh-text">{{ text }}</div>
      <button v-if="block.action_label" class="mh-action" @click="$emit('phrase', block.action_label)">
        {{ block.action_label }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { pick } from '@/utils/schema.js'

const props = defineProps({ block: { type: Object, required: true } })
defineEmits(['phrase'])

const text = computed(() => pick(props.block, 'text', 'content', 'desc') || '')
</script>
