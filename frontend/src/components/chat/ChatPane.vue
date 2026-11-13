<template>
  <header class="chat-header">
    <div class="model-title">
      <div class="model-logo"><img :src="logo" alt="膳宝" /></div>
      <span class="model-name">膳宝</span>
      <span class="model-desc">膳食智能体</span>
    </div>
    <span class="badge">AI 已读取档案</span>
  </header>

  <div ref="scrollEl" class="chat-scroll" @scroll="onScroll">
    <WelcomeScreen v-if="chat.isWelcome" @pick="send" />
    <div v-else-if="!chat.messages.length" class="msg ai">
      <div class="bubble">
        <p class="greet-hi">你好，我是膳宝。</p>
        <p class="greet-sub">按你的档案配餐、算份量。右侧四个按钮放着食材清单、当前规划、历史方案和膳食报告，下面这些快捷按钮可以直接试。</p>
      </div>
    </div>
    <ChatMessage
      v-for="m in chat.messages"
      :key="m.id"
      :message="m"
      @phrase="send"
      @retry="(id) => chat.retry(id)"
    />
  </div>

  <ChatComposer
    :sending="chat.sending"
    @send="send"
    @stop="chat.stop()"
  />
</template>

<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'
import ChatMessage from './ChatMessage.vue'
import ChatComposer from './ChatComposer.vue'
import WelcomeScreen from './WelcomeScreen.vue'
import { useChatStore } from '@/stores/chat.js'
import logo from '@/assets/logo.jpg'

const chat = useChatStore()
const scrollEl = ref(null)
const autoStick = ref(true)

function onScroll() {
  const el = scrollEl.value
  if (!el) return
  autoStick.value = el.scrollHeight - el.scrollTop - el.clientHeight < 140
}

function scrollToBottom(force = false) {
  nextTick(() => {
    const el = scrollEl.value
    if (!el) return
    if (force || autoStick.value) el.scrollTop = el.scrollHeight
  })
}

// 新消息进入时强制滚到底部
watch(
  () => chat.messages.length,
  () => {
    autoStick.value = true
    scrollToBottom(true)
  }
)

// 流式增量：跟随最后一条消息的高度变化
watch(
  () => {
    const last = chat.messages[chat.messages.length - 1]
    if (!last) return ''
    return `${last.text.length}:${last.blocks.length}:${last.status}`
  },
  () => scrollToBottom(false)
)

function send(text) {
  autoStick.value = true
  chat.send(text)
}

// 进入会话（含首屏恢复历史、切换会话）一律落到最新一条，而不是停在最早的记录
function jumpToLatest() {
  autoStick.value = true
  scrollToBottom(true)
  setTimeout(() => scrollToBottom(true), 120)
  setTimeout(() => scrollToBottom(true), 420)
}

onMounted(jumpToLatest)
watch(() => chat.activeId, jumpToLatest)
watch(
  () => chat.messages[0]?.id,
  () => {
    if (chat.messages.length) jumpToLatest()
  }
)

defineExpose({ scrollToBottom })
</script>
