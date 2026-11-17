import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { streamChat } from '@/api/agent.js'
import { normalizeArtifact } from '@/utils/schema.js'
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
            clarify: m.clarify || null,
            createdAt: m.createdAt || new Date().toISOString()
          }))
        : []
    }))
  } catch (e) {
    return []
  }
}

/** 就地更新同一 meal_plan_id 的方案卡：找到更早消息里的同 raw_id 卡就 splice 替换。返回是否命中。 */
function replaceMealCardInPlace(session, block, excludeMsg = null) {
  if (!block || block.type !== 'meal_card' || !block.raw_id) return false
  for (let i = session.messages.length - 1; i >= 0; i--) {
    const msg = session.messages[i]
    if (excludeMsg && msg === excludeMsg) continue
    const idx = (msg.blocks || []).findIndex(
      (b) => b.type === 'meal_card' && b.raw_id === block.raw_id
    )
    if (idx >= 0) {
      msg.blocks.splice(idx, 1, block)
      return true
    }
  }
  return false
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
      clarify: null,
      thinking: '',
      thinkingSteps: [],
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

          // message：正文增量（v1.2 为 {type:'text', content}）
          if (evt.event === 'message') {
            if (payload.type === 'text' && typeof payload.content === 'string' && payload.content) {
              aiMsg.thinking = '' // 正文开始，隐藏思考步骤
              aiMsg.text += payload.content
            }
            session.updatedAt = new Date().toISOString()
          }

          // status：过程可见（正在读取档案 / 生成方案 / 换候选等思考步骤）
          if (evt.event === 'status') {
            aiMsg.thinking = payload.stage || ''
            const steps = aiMsg.thinkingSteps
            if (payload.stage && steps[steps.length - 1] !== payload.stage) {
              steps.push(payload.stage)
            }
            session.updatedAt = new Date().toISOString()
          }

          // artifact：结构化产物，按 type 分发到注册表
          if (evt.event === 'artifact') {
            if (!payload.type) return
            const block = normalizeArtifact(payload.type, payload.payload || {})

            // 方案卡就地更新：同一 meal_plan_id 的卡若已出现在更早的消息里，就原地替换，
            // 不再往当前气泡追加（换候选/选用/确认都复用同一张卡，避免对话里堆出多张过期卡）。
            const replacedInPlace = replaceMealCardInPlace(session, block, aiMsg)
            if (!replacedInPlace) {
              const sameIndex = aiMsg.blocks.findIndex(
                (b) => b.type === block.type && (!b.raw_id || b.raw_id === block.raw_id)
              )
              if (sameIndex >= 0) aiMsg.blocks.splice(sameIndex, 1, block)
              else aiMsg.blocks.push(block)
            }

            if (block.type === 'nutrition_report' && block.report_type !== 'plan') panel.markReportUnread()
            session.updatedAt = new Date().toISOString()
          }

          // clarify：信息不足，后端要求追问
          if (evt.event === 'clarify') {
            aiMsg.clarify = {
              question: payload.question || '还需要补充一些信息',
              missing_fields: Array.isArray(payload.missing_fields) ? payload.missing_fields : []
            }
            if (!aiMsg.text) aiMsg.text = aiMsg.clarify.question
            session.updatedAt = new Date().toISOString()
          }

          if (evt.event === 'done') {
            aiMsg.status = 'done'
            aiMsg.thinking = '' // 兜底：确保思考步骤条不残留
            if (payload.conversation_id) session.conversationId = payload.conversation_id
            if (payload.meal_plan_id != null) aiMsg.meal_plan_id = payload.meal_plan_id
            session.updatedAt = new Date().toISOString()
          }

          // error：{code,message}，code 语义与 REST 一致
          if (evt.event === 'error') {
            aiMsg.status = 'error'
            aiMsg.error = payload.message || '生成失败，请重试'
          }
        }
      })

      if (aiMsg.status === 'streaming') aiMsg.status = 'done'
      session.updatedAt = new Date().toISOString()
      // 对话完成后通知面板刷新：生成/确认/报告都可能在服务端改了固定方案、清单、历史或报告
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

  /**
   * 静默动作：不发 user/AI 气泡，只消费结构化产物并把方案卡就地更新。
   * 用于「换一换 / 选用候选」这类轻量按钮操作——聊天流不产生任何消息，
   * 仅卡片 spinner + 原地刷新；失败时抛错，由调用方 toast 提示。
   */
  async function silentAction(text) {
    const content = String(text || '').trim()
    if (!content || sending.value) return false

    const session = ensureSession()

    sending.value = true
    const controller = new AbortController()
    abortController.value = controller

    let errorMsg = ''
    try {
      await streamChat({
        conversationId: session.conversationId,
        message: content,
        signal: controller.signal,
        silent: true,
        onEvent: (evt) => {
          const payload = evt.data && typeof evt.data === 'object' ? evt.data : {}
          // 只消费方案卡，丢弃正文文本（静默，不产生对话气泡）
          if (evt.event === 'artifact' && payload.type === 'meal_card') {
            const block = normalizeArtifact(payload.type, payload.payload || {})
            replaceMealCardInPlace(session, block)
            session.updatedAt = new Date().toISOString()
          }
          if (evt.event === 'done' && payload.conversation_id) {
            session.conversationId = payload.conversation_id
          }
          if (evt.event === 'error') {
            errorMsg = payload.message || '操作失败'
          }
        }
      })

      if (errorMsg) throw new Error(errorMsg)
      // 换候选/选用只改「草稿候选」的选中项，不影响固定方案/食材清单/历史/报告，
      // 故不触发全局面板刷新（否则点「换一换」右侧工具栏会整体重载）。
      return true
    } catch (e) {
      if (e.name === 'AbortError' || e.code === 'CANCELED') return false
      throw e
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
    silentAction,
    retry,
    stop,
    persist,
    clearAll
  }
})
