<template>
  <div v-if="actions.length" class="quick-actions">
    <button
      v-for="(a, i) in actions"
      :key="i"
      class="qa-btn"
      :class="i === 0 ? 'qa-primary' : 'qa-ghost'"
      :disabled="consumed || chat.sending"
      @click="onClick(a)"
    >{{ a.label }}</button>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useChatStore } from '@/stores/chat.js'

const props = defineProps({ block: { type: Object, required: true } })
const chat = useChatStore()

const actions = computed(() =>
  props.block && Array.isArray(props.block.actions) ? props.block.actions : []
)

// 一次性按钮：点过「替换/取消」后即禁用，避免重复点出第二次追问
const consumed = ref(false)

function onClick(a) {
  if (consumed.value || !a.phrase || chat.sending) return
  consumed.value = true
  chat.send(a.phrase)
}
</script>

<style scoped>
.quick-actions {
  display: flex;
  gap: 10px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.qa-btn {
  border-radius: 999px;
  padding: 6px 18px;
  font-size: 14px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.qa-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.qa-primary {
  background: #4a7c59;
  color: #fff;
}
.qa-primary:hover {
  background: #3d6849;
}
.qa-ghost {
  background: #fff;
  color: #4a7c59;
  border-color: #cfe0d3;
}
.qa-ghost:hover {
  background: #f0f5f1;
}
</style>
