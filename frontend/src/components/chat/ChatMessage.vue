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
      <template v-else>
        <div v-if="message.thinking" class="thinking-line">
          <span class="thinking-dot"></span>{{ message.thinking }}
        </div>
        <div v-else-if="thinkingRecord && message.status === 'done'" class="thinking-record">
          💭 {{ thinkingRecord }}
        </div>
        <div v-if="message.text" class="bubble md-bubble">
          <div class="md" v-html="bodyHtml" @click="onBubbleClick"></div>
          <span v-if="message.status === 'streaming'" class="caret"></span>
        </div>
        <div v-else-if="message.status === 'streaming' && !message.thinking" class="typing"><i></i><i></i><i></i></div>

        <!-- F5（IMP-063）：文末结构化来源卡片流 -->
        <div v-if="message.sources && message.sources.length" class="cite-sources">
          <div class="cite-sources-title">参考来源</div>
          <div
            v-for="(s, i) in message.sources"
            :id="`cite-card-${s.id}`"
            :key="s.id || i"
            class="cite-card"
          >
            <div class="cite-card-head">
              <span class="cite-card-index">{{ i + 1 }}</span>
              <a
                v-if="s.url"
                :href="s.url"
                target="_blank"
                rel="noopener noreferrer"
                class="cite-card-title"
              >{{ s.title || s.source || s.url }}</a>
              <span v-else class="cite-card-title">{{ s.title || s.source || '来源' }}</span>
              <span v-if="s.domain" class="cite-card-domain">{{ s.domain }}</span>
            </div>
            <div v-if="s.snippet" class="cite-card-snippet">{{ s.snippet }}</div>
          </div>
        </div>
      </template>

      <RendererHost
        v-for="block in message.blocks"
        :key="block.__key"
        :block="block"
        @phrase="(p) => $emit('phrase', p)"
      />

      <div v-if="showSuggestions" class="suggest-row">
        <button
          v-for="(s, i) in message.suggestions"
          :key="'sg' + i"
          class="suggest-chip"
          @click="$emit('phrase', s)"
        >{{ s }}</button>
      </div>

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
import { computed } from 'vue'
import RendererHost from '@/components/renderer/RendererHost.vue'
import ClarifyBlock from './ClarifyBlock.vue'
import { renderMarkdown } from '@/utils/markdown.js'

const props = defineProps({ message: { type: Object, required: true } })
defineEmits(['phrase', 'retry'])

/** F5：HTML 注入前转义，悬浮卡文案一律来自后端结构化引用，不直接拼原始字符串 */
function escapeHtml(v) {
  return String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]))
}

const sourceList = computed(() => props.message.sources || [])

/** 按正文编号 n 找对应引用：先按下标（第 n 条），再按 id 兜底 */
function sourceFor(n) {
  const list = sourceList.value
  return list[Number(n) - 1] || list.find((s) => String(s.id) === String(n)) || null
}

/** 悬浮卡内嵌在胶囊里（v-html 内无法挂 Vue 状态），字段先转义再拼 */
function tipHtml(src) {
  const title = escapeHtml(src.title || src.source || '参考来源')
  const snippet = src.snippet ? `<span class="cite-tip-snippet">${escapeHtml(src.snippet)}</span>` : ''
  const domain = src.domain ? `<span class="cite-tip-domain">${escapeHtml(src.domain)}</span>` : ''
  return `<span class="cite-tip-title">${title}</span>${snippet}${domain}`
}

/** F5：正文 [n] 命中结构化引用时替换为可点胶囊；未命中保持纯文本，不臆造来源 */
const bodyHtml = computed(() => {
  const html = renderMarkdown(props.message.text)
  if (!sourceList.value.length) return html
  return html.replace(/\[(\d+)\]/g, (m, n) => {
    const src = sourceFor(n)
    if (!src) return m
    return `<button type="button" class="cite-chip" data-cite="${escapeHtml(src.id)}" aria-label="引用 ${n}">[${escapeHtml(n)}]<span class="cite-tip">${tipHtml(src)}</span></button>`
  })
})

function jumpTo(id) {
  const el = document.getElementById(`cite-card-${id}`)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

/** v-html 胶囊点击代理：命中 data-cite 才滚动到文末来源卡 */
function onBubbleClick(ev) {
  const chip = ev.target.closest?.('.cite-chip')
  if (!chip) return
  jumpTo(chip.dataset.cite)
}

// 思考记录：过滤掉「理解需求 / 读取档案 / 整理回复」这类元步骤，只留核心动作，折叠成一行「已X」
const META_STEPS = ['正在理解你的需求', '正在读取档案', '正在整理回复']
const thinkingRecord = computed(() => {
  const actions = (props.message.thinkingSteps || []).filter((s) => !META_STEPS.includes(s))
  return actions.length ? actions.map((s) => '已' + s.replace(/^正在/, '')).join(' · ') : ''
})

// 快捷追问 chip：只在回复完成后、且有建议时展示（IMP-027）
const showSuggestions = computed(
  () => props.message.status === 'done' && (props.message.suggestions || []).length > 0
)
</script>

<style scoped>
/* 过程可见：思考步骤条 */
.thinking-line {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 0 6px;
  color: var(--text-sub, #7a7a7a);
  font-size: 13px;
}
.thinking-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #4a7c59;
  flex: none;
  animation: thinking-pulse 1s ease-in-out infinite;
}
@keyframes thinking-pulse {
  0%, 100% { opacity: 0.3; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.1); }
}

/* 完成后折叠成一行记录 */
.thinking-record {
  padding: 2px 0 6px;
  color: var(--text-sub, #9a9a9a);
  font-size: 12px;
}

/* markdown 正文样式（v-html 注入的内容不受 scoped 约束，用 :deep 命中） */
/* white-space 必须 normal：父级 .bubble 的 pre-wrap 会把 markdown 块间换行渲染成可见空行 */
.md { white-space: normal; font-size: 15px; line-height: 1.75; }
/* .bubble .md 提升优先级，压过 base.css 里 .msg.ai .bubble p{margin:0} */
.bubble .md :deep(p) { margin: 0 0 10px; }
.bubble .md :deep(p:last-child) { margin-bottom: 0; }

/* 标题：深色 + 字号阶梯 + 上大下小间距（对齐主流 LLM 客户端，不用彩色标题） */
.md :deep(h1),
.md :deep(h2),
.md :deep(h3),
.md :deep(h4) { color: var(--text-main); font-weight: 700; line-height: 1.35; }
.md :deep(h1) { font-size: 21px; margin: 22px 0 12px; }
.md :deep(h2) { font-size: 19px; margin: 20px 0 10px; }
.md :deep(h3) { font-size: 17px; margin: 18px 0 10px; }
.md :deep(h4) { font-size: 15px; font-weight: 650; margin: 14px 0 8px; }
/* 首个元素贴顶，避免开头空一块 */
.md :deep(> :first-child) { margin-top: 0; }

/* 列表：项间距放大 + 圆点浅品牌色 */
.md :deep(ul),
.md :deep(ol) { margin: 0 0 10px; padding-left: 20px; }
.md :deep(li) { margin: 4px 0; line-height: 1.7; }
.md :deep(li::marker) { color: var(--brand-medium); }

.md :deep(strong) { font-weight: 650; }
.md :deep(hr) { border: none; border-top: 1px solid var(--border-soft, #e5e7eb); margin: 12px 0; }

/* 表格：字号与正文同级、表头浅底、行 hover */
.md :deep(table) { border-collapse: collapse; margin: 0 0 12px; font-size: 14px; width: 100%; max-width: 100%; }
.md :deep(th),
.md :deep(td) { border: 1px solid var(--border-soft, #e5e7eb); padding: 8px 12px; text-align: left; vertical-align: top; }
.md :deep(th) { background: #f7faf8; font-weight: 600; color: var(--text-sub); }
.md :deep(tbody tr:hover) { background: #fafcfa; }

.md :deep(code) {
  background: #f2f4f3;
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 0.9em;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}
.md :deep(pre) { background: #f2f4f3; padding: 10px 12px; border-radius: 6px; overflow-x: auto; margin: 0 0 10px; }
.md :deep(pre code) { background: none; padding: 0; }
.md :deep(blockquote) { border-left: 3px solid #4a7c59; margin: 8px 0 0; padding: 2px 0 2px 10px; color: #9a9a9a; font-size: 12.5px; }
.md :deep(a) { color: #4a7c59; }

/* 快捷追问 chip（IMP-027）：回复完成后气泡下方一排可点追问 */
.suggest-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.suggest-chip {
  font-size: 12.5px;
  line-height: 1.4;
  color: var(--brand-hover, #3d6a4b);
  background: var(--brand-light, #eef3ee);
  border: 1px solid var(--brand-medium, #dce8df);
  border-radius: 999px;
  padding: 5px 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.suggest-chip:hover {
  background: var(--brand-medium, #dce8df);
}

/* F5（IMP-063）：正文引用胶囊 —— 小字号品牌色，行内不打断排版 */
.cite-chip {
  position: relative;
  display: inline-flex;
  align-items: center;
  padding: 0 5px;
  margin: 0 1px;
  border: 1px solid var(--brand-medium, #dce8df);
  border-radius: 5px;
  background: var(--brand-light, #eef3ee);
  color: var(--brand-hover, #3d6a4b);
  font-size: 11.5px;
  line-height: 1.5;
  cursor: pointer;
  vertical-align: baseline;
}

.cite-chip:hover {
  background: var(--brand-medium, #dce8df);
}

/* 悬浮卡：hover 胶囊时在上方展开，内容来自后端结构化引用 */
.cite-tip {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  z-index: 30;
  display: none;
  flex-direction: column;
  gap: 4px;
  width: 240px;
  padding: 10px 12px;
  background: #fff;
  border: 1px solid var(--border-soft, #e5e7eb);
  border-radius: 10px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.12);
  text-align: left;
  white-space: normal;
}

.cite-chip:hover .cite-tip {
  display: flex;
}

.cite-tip-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-main, #333);
  line-height: 1.5;
}

.cite-tip-snippet {
  font-size: 12px;
  color: var(--text-sub, #7a7a7a);
  line-height: 1.6;
}

.cite-tip-domain {
  font-size: 11px;
  color: var(--text-sub, #9a9a9a);
}

/* 文末来源卡片流 */
.cite-sources {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cite-sources-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-sub, #7a7a7a);
}

.cite-card {
  padding: 10px 12px;
  background: var(--bg-soft, #fafafa);
  border: 1px solid var(--border-soft, #eef0ee);
  border-radius: 10px;
}

.cite-card-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.cite-card-index {
  flex: none;
  width: 18px;
  height: 18px;
  border-radius: 5px;
  background: var(--brand-light, #eef3ee);
  color: var(--brand-hover, #3d6a4b);
  font-size: 11px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.cite-card-title {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--brand-hover, #3d6a4b);
  text-decoration: none;
}

.cite-card-title:hover {
  text-decoration: underline;
}

.cite-card-domain {
  flex: none;
  font-size: 11px;
  color: var(--text-sub, #9a9a9a);
}

.cite-card-snippet {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-sub, #7a7a7a);
  line-height: 1.6;
}
</style>
