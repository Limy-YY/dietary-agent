<template>
  <div class="empty-state">
    <div class="es-icon">{{ icon }}</div>
    <div class="es-title">{{ title }}</div>
    <div v-if="desc" class="es-desc">{{ desc }}</div>
    <div v-if="actions.length" class="es-actions">
      <button v-for="(a, i) in actions" :key="i" class="es-action" @click="onAction(a)">
        <span class="es-action-icon">{{ a.icon || '✨' }}</span>
        <span class="es-action-text">
          <span class="es-action-title">{{ a.label }}</span>
          <span v-if="a.desc" class="es-action-desc">{{ a.desc }}</span>
        </span>
      </button>
    </div>
    <div v-if="hint" class="es-hint" v-html="hint"></div>
  </div>
</template>

<script setup>
const props = defineProps({
  icon: { type: String, default: '🍽️' },
  title: { type: String, default: '还没有内容' },
  desc: { type: String, default: '' },
  actions: { type: Array, default: () => [] },
  hint: { type: String, default: '' }
})
const emit = defineEmits(['action'])

function onAction(a) {
  emit('action', a)
}
</script>
