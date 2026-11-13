import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { streamChat } from '@/api/agent.js'
import { normalizeBlocks } from '@/utils/schema.js'
import { groupOf, uid } from '@/utils/format.js'
import { usePanelStore } from './panel.js'

const STORAGE_KEY = 'sz_sessions_v1'

function loadSessions() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.map((s) => ({
      id: String(s.id || uid('conv')),
      title: String(s.title || '新的对话'),
      createdAt: s.createdAt || new Date().toISOString(),
      updatedAt: s.updatedAt || s.createdAt || new Date().toISOString(),
      conversationId: s.conversationId || null,
      messages: Array.isArray(s.messages)
        ? s.messages.map((m) => ({
            id: m.id || uid('msg'),
            role: m.role === 'user' ? 'user' : 'ai',
            text: String(m.text || ''),
            blocks: Array.isArray(m.blocks) ? m.blocks : [],
            status: m.status || 'done',
            error: m.error || '',
            suggestions: Array.isArray(m.suggestions) ? m.suggestions : [],
            createdAt: m.createdAt || new Date().toISOString()
          }))
        : []
    }))
  } catch (e) {
    return []
  }
}

export const useChatStore = defineStore('chat', () => {
  const sessions = ref(loadSessions())
  const activeId = ref(sessions.value[0]?.id || '')
  const sending = ref(false)
  const abortController = ref(null)
  // 与 main.html 一致：首屏是问候语，只有「开启新对话」才展示欢迎页
  const showWelcome = ref(false)

  const activeSession = computed(() => sessions.value.find((s) => s.id === activeId.value) || null)
  const messages = computed(() => activeSession.value?.messages || [])
  const isWelcome = computed(() => showWelcome.value && !messages.value.length)
  const lastSuggestions = computed(() => {
    const list = messages.value
    for (let i = list.length - 1; i >= 0; i--) {
      if (list[i].role === 'ai' && list[i].status === 'done' && list[i].suggestions?.length) return list[i].suggestions
    }
    return []
  })

  const groupedSessions = computed(() => {
    const buckets = { 今天: [], '近 7 天': [], 更早: [] }
    const sorted = [...sessions.value].sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt))
    sorted.forEach((s) => {
      const g = groupOf(s.updatedAt)
      if (!buckets[g]) buckets[g] = []
      buckets[g].push(s)
    })
    return Object.entries(buckets)
      .filter(([, list]) => list.length)
      .map(([label, list]) => ({ label, list }))
  })

  function persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions.value))
    } catch (e) {
      /* 超配额时忽略，不影响使用 */
    }
  }

  function ensureSession() {
    if (activeSession.value) return activeSession.value
    const session = {
      id: uid('conv'),
      title: '新的对话',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      conversationId: null,
      messages: []
    }
    sessions.value.unshift(session)
    activeId.value = session.id
    persist()
    // 返回响应式代理，保证后续对流式内容的修改能被视图感知
    return sessions.value.find((s) => s.id === session.id) || session
  }

  function newChat() {
    if (sending.value) stop()
    const session = {
      id: uid('conv'),
      title: '新的对话',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      conversationId: null,
      messages: []
    }
    sessions.value.unshift(session)
    activeId.value = session.id
    showWelcome.value = true
    persist()
  }

  function switchSession(id) {
    if (sending.value) stop()
    showWelcome.value = false
    activeId.value = id
  }

  function renameSession(id, title) {
    const s = sessions.value.find((x) => x.id === id)
    if (!s) return
    const next = String(title || '').trim().slice(0, 24)
    if (!next) return
    s.title = next
    persist()
  }

  function removeSession(id) {
    const index = sessions.value.findIndex((x) => x.id === id)
    if (index < 0) return
    sessions.value.splice(index, 1)
    if (activeId.value === id) activeId.value = sessions.value[0]?.id || ''
    persist()
  }

  function stop() {
    if (abortController.value) {
      abortController.value.abort()
      abortController.value = null
    }
    sending.value = false
  }

  /**
   * 发送一条消息（用户输入或卡片固定话术），走 SSE 三事件流。
   * 不在此处做任何业务判断：正文与结构化边车都只按后端下发渲染。
   */
  async function send(text) {
    const content = String(text || '').trim()
    if (!content) {
      ElMessage('先写一句你想吃什么')
      return
    }
    if (sending.value) return

    const session = ensureSession()
    const panel = usePanelStore()
    showWelcome.value = false

    const userMsg = {
      id: uid('msg'),
      role: 'user',
      text: content,
      blocks: [],
      status: 'done',
      error: '',
      suggestions: [],
      createdAt: new Date().toISOString()
    }
    session.messages.push(userMsg)

    if (!session.title || session.title === '新的对话') {
      session.title = content.replace(/\s+/g, ' ').slice(0, 20)
    }
    session.updatedAt = new Date().toISOString()

    session.messages.push({
      id: uid('msg'),
      role: 'ai',
      text: '',
      blocks: [],
      status: 'streaming',
      error: '',
      suggestions: [],
      createdAt: new Date().toISOString()
    })

    // 必须取数组里的响应式代理再改，直接改 push 进去的原始对象不会触发视图更新
    const aiMsg = session.messages[session.messages.length - 1]

    sending.value = true
    const controller = new AbortController()
    abortController.value = controller
    persist()

    try {
      await streamChat({
        conversationId: session.conversationId,
        message: content,
        signal: controller.signal,
        onEvent: (evt) => {
          const payload = evt.data && typeof evt.data === 'object' ? evt.data : {}

          if (evt.event === 'message') {
            if (typeof payload.delta === 'string' && payload.delta) aiMsg.text += payload.delta
            if (payload.meta) {
              const blocks = normalizeBlocks(payload.meta)
              aiMsg.blocks = blocks
              if (blocks.some((b) => b.type === 'report')) panel.markReportUnread()
            }
            if (payload.conversation_id) session.conversationId = payload.conversation_id
            session.updatedAt = new Date().toISOString()
          }

          if (evt.event === 'done') {
            aiMsg.status = 'done'
            if (Array.isArray(payload.suggestions)) aiMsg.suggestions = payload.suggestions
            if (payload.conversation_id) session.conversationId = payload.conversation_id
            session.updatedAt = new Date().toISOString()
          }

          if (evt.event === 'error') {
            aiMsg.status = 'error'
            aiMsg.error = payload.message || '生成失败，请重试'
          }
        }
      })

      if (aiMsg.status === 'streaming') aiMsg.status = 'done'
      session.updatedAt = new Date().toISOString()
      // 对话完成后通知面板刷新：确认/换候选都可能在服务端改了数据
      panel.bump()
    } catch (e) {
      if (e.name === 'AbortError' || e.code === 'CANCELED') {
        aiMsg.status = 'stopped'
        if (!aiMsg.text) aiMsg.text = '（已停止本次生成）'
      } else {
        aiMsg.status = 'error'
        aiMsg.error = e.message || '网络异常，请稍后重试'
      }
    } finally {
      sending.value = false
      abortController.value = null
      persist()
    }
  }

  /** 重新生成最后一条回复 */
  async function retry(messageId) {
    const session = activeSession.value
    if (!session) return
    const index = session.messages.findIndex((m) => m.id === messageId)
    if (index < 0) return
    let userIndex = index
    while (userIndex >= 0 && session.messages[userIndex].role !== 'user') userIndex--
    if (userIndex < 0) return
    const text = session.messages[userIndex].text
    session.messages.splice(userIndex, session.messages.length - userIndex)
    await send(text)
  }

  function clearAll() {
    sessions.value = []
    activeId.value = ''
    persist()
  }

  return {
    sessions,
    activeId,
    sending,
    activeSession,
    messages,
    isWelcome,
    lastSuggestions,
    groupedSessions,
    ensureSession,
    newChat,
    switchSession,
    renameSession,
    removeSession,
    send,
    retry,
    stop,
    persist,
    clearAll
  }
})
