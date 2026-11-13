<template>
  <div class="msg" :class="message.role">
    <template v-if="message.role === 'user'">
      <div class="bubble">{{ message.text }}</div>
    </template>

    <template v-else>
      <div v-if="message.text" class="bubble">
        {{ message.text }}<span v-if="message.status === 'streaming'" class="caret"></span>
      </div>
      <div v-else-if="message.status === 'streaming'" class="typing"><i></i><i></i><i></i></div>

      <RendererHost
        v-for="block in message.blocks"
        :key="block.__key"
        :block="block"
        @phrase="(p) => $emit('phrase', p)"
      />

      <div v-if="message.status === 'stopped'" class="bubble" style="color: var(--text-sub); font-size: 13px">
        已停止生成，可以继续追问或重新发送。
      </div>

      <div v-if="message.error" class="msg-error">
        <span>⚠️ {{ message.error }}</span>
        <button @click="$emit('retry', message.id)">重试</button>
      </div>
    </template>
  </div>
</template>

<script setup>
import RendererHost from '@/components/renderer/RendererHost.vue'

defineProps({ message: { type: Object, required: true } })
defineEmits(['phrase', 'retry'])
</script>
