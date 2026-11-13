<template>
  <div class="chat-input-area">
    <div class="preset-chips-wrap">
      <button
        v-for="c in chips"
        :key="c.key"
        class="chip"
        :class="{ report: c.report }"
        :disabled="sending"
        @click="$emit('send', c.phrase)"
      >
        {{ c.text }}
      </button>
    </div>

    <div class="input-wrap">
      <textarea
        ref="taEl"
        v-model="draft"
        rows="1"
        placeholder="和助手聊聊，咨询配餐或营养建议"
        :disabled="sending"
        @input="autoGrow"
        @keydown="onKeydown"
      ></textarea>

      <button v-if="sending" class="send-btn" title="停止生成" @click="$emit('stop')">
        <svg viewBox="0 0 24 24"><rect x="7" y="7" width="10" height="10" rx="1.5" /></svg>
      </button>
      <button v-else class="send-btn" title="发送" @click="submit">
        <svg viewBox="0 0 24 24"><path d="M12 20V4M5 11l7-7 7 7" /></svg>
      </button>
    </div>
  </div>
</template>

<script setup>
import { nextTick, ref } from 'vue'
import { PRESET_CHIPS } from '@/constants/actions.js'

const props = defineProps({
  sending: { type: Boolean, default: false }
})
const emit = defineEmits(['send', 'stop'])

const draft = ref('')
const taEl = ref(null)

/** 固定 5 个快捷，和 main.html 原型一致；后端 suggestions 不再往这里叠加 */
const chips = PRESET_CHIPS

function autoGrow() {
  nextTick(() => {
    const el = taEl.value
    if (!el) return
    el.style.height = '32px'
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`
    el.style.overflowY = el.scrollHeight > 120 ? 'auto' : 'hidden'
  })
}

function submit() {
  if (props.sending) return
  emit('send', draft.value.trim())
  draft.value = ''
  nextTick(autoGrow)
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submit()
  }
}
</script>
