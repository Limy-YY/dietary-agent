<template>
  <div class="msg" :class="message.role">
    <template v-if="message.role === 'user'">
      <div class="bubble">{{ message.text }}</div>
    </template>

    <template v-else>
      <ClarifyBlock
        v-if="message.clarify"
        :question="message.clarify.question || message.text"
        :missing-fields="message.clarify.missing_fields || []"
      />
      <div v-else-if="message.text" class="bubble md-bubble">
        <div class="md" v-html="renderMarkdown(message.text)"></div>
        <span v-if="message.status === 'streaming'" class="caret"></span>
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
import ClarifyBlock from './ClarifyBlock.vue'
import { renderMarkdown } from '@/utils/markdown.js'

defineProps({ message: { type: Object, required: true } })
defineEmits(['phrase', 'retry'])
</script>

<style scoped>
/* markdown 正文样式（v-html 注入的内容不受 scoped 约束，用 :deep 命中） */
/* white-space 必须 normal：父级 .bubble 的 pre-wrap 会把 markdown 块间换行渲染成可见空行 */
.md { white-space: normal; }
/* .bubble .md 提升优先级，压过 base.css 里 .msg.ai .bubble p{margin:0} */
.bubble .md :deep(p) { margin: 0 0 8px; }
.bubble .md :deep(p:last-child) { margin-bottom: 0; }
.md :deep(ul),
.md :deep(ol) { margin: 0 0 8px; padding-left: 18px; }
.md :deep(li) { margin: 2px 0; }
.md :deep(h1),
.md :deep(h2),
.md :deep(h3),
.md :deep(h4) { margin: 12px 0 4px; font-weight: 600; line-height: 1.4; }
.md :deep(h2),
.md :deep(h3) { color: #4a7c59; }
.md :deep(h2) { font-size: 16px; }
.md :deep(h3) { font-size: 15px; }
.md :deep(strong) { font-weight: 600; }
.md :deep(hr) { border: none; border-top: 1px solid var(--border-soft, #e5e7eb); margin: 8px 0; }
.md :deep(table) { border-collapse: collapse; margin: 0 0 8px; font-size: 13.5px; max-width: 100%; }
.md :deep(th),
.md :deep(td) { border: 1px solid var(--border-soft, #e5e7eb); padding: 6px 10px; text-align: left; vertical-align: top; }
.md :deep(th) { background: #f2f4f3; font-weight: 600; }
.md :deep(code) {
  background: #f2f4f3;
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 0.9em;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}
.md :deep(pre) { background: #f2f4f3; padding: 10px 12px; border-radius: 6px; overflow-x: auto; margin: 0 0 8px; }
.md :deep(pre code) { background: none; padding: 0; }
.md :deep(blockquote) { border-left: 3px solid #4a7c59; margin: 0 0 8px; padding: 2px 0 2px 10px; color: #7a7a7a; }
.md :deep(a) { color: #4a7c59; }
</style>
