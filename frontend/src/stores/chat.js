import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { streamChat } from '@/api/agent.js'
import { listConversations, listMessages, renameConversation, deleteConversation } from '@/api/conversation.js'
import { getToken } from '@/api/http.js'
import { normalizeArtifact } from '@/utils/schema.js'
import { groupOf, uid } from '@/utils/format.js'
import { usePanelStore } from './panel.js'

/**
 * 会话列表后端化（IMP-001）：会话与消息以后端 conversation/message 表为准，
 * localStorage 只留 token 与 UI 偏好，不再存业务数据。
 * 结构化块（餐卡/清单/报告）随 assistant 消息以「快照」落 app.message.structured_output，
 * 历史回看时前端用 normalizeArtifact 原样还原（方案 A）；current_plan/quick_actions 瞬时块不落。
 */

/** 后端会话摘要 → 前端 session 对象 */
function toSession(item) {
  return {
    id: String(item.conversation_id),
    conversationId: item.conversation_id,
    title: item.title || '新的对话',
    createdAt: item.created_at,
    updatedAt: item.updated_at || item.created_at,
    messageCount: item.message_count || 0,
    lastMessage: item.last_message || '',
    messages: [],
    _hydrated: false,
    _loading: false
  }
}

/** 后端消息 → 前端 message 对象：正文 + 结构化块（从 structured_output 快照还原） */
function toMessage(item) {
  const blocks = []
  const structured = item.structured_output
  if (structured && Array.isArray(structured.blocks)) {
    for (const b of structured.blocks) {
      if (b && b.type && b.payload) {
        const block = normalizeArtifact(b.type, b.payload)
        if (block && block.type && block.type !== 'unknown') {
          block.readonly = true // 历史快照只读，禁用「换一换 / 确认」等修改动作
          blocks.push(block)
        }
      }
    }
  }
  return {
    id: String(item.message_id),
    role: item.role === 'user' ? 'user' : 'ai',
    text: item.content || '',
    blocks,
    status: 'done',
    error: '',
    suggestions: [],
    clarify: null,
    createdAt: item.created_at,
    thinking: '',
    thinkingSteps: []
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
  const sessions = ref([])
  const activeId = ref('')
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

  /** 把后端 conversation_id 采纳为会话唯一 id：首次发送时从临时 id 迁移到后端 id */
  function adoptConversation(session, conversationId) {
    if (conversationId == null) return
    session.conversationId = conversationId
    const newId = String(conversationId)
    if (session.id !== newId) {
      if (activeId.value === session.id) activeId.value = newId
      session.id = newId
    }
  }

  /** 懒加载某会话的历史消息（文本）。已在加载 / 已加载 / 无后端 id 时跳过。 */
  async function hydrateSession(session) {
    if (!session || session._hydrated || session._loading || session.conversationId == null) return
    session._loading = true
    try {
      const { items } = await listMessages(session.conversationId, { pageSize: 200 })
      session.messages = items.map(toMessage)
      session._hydrated = true
    } catch (e) {
      /* 历史消息加载失败不打断使用，下次切回可重试 */
    } finally {
      session._loading = false
    }
  }

  /** 从后端拉取会话列表（初始化时调用一次）。 */
  async function refreshSessions() {
    if (!getToken()) return
    try {
      const { items } = await listConversations({ pageSize: 100 })
      sessions.value = items.map(toSession)
      if (!activeId.value || !sessions.value.some((s) => s.id === activeId.value)) {
        const first = sessions.value[0]
        activeId.value = first?.id || ''
        if (first) hydrateSession(first)
      }
    } catch (e) {
      /* 会话列表加载失败不阻塞新建会话 */
    }
  }

  /** 尚未落库的临时会话（conversationId=null，等首条消息由后端返回 id 后采纳） */
  function newSessionDraft() {
    return {
      id: uid('conv'),
      conversationId: null,
      title: '新的对话',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      messageCount: 0,
      lastMessage: '',
      messages: [],
      _hydrated: true,
      _loading: false
    }
  }

  function ensureSession() {
    if (activeSession.value) return activeSession.value
    const session = newSessionDraft()
    sessions.value.unshift(session)
    activeId.value = session.id
    // 返回响应式代理，保证后续对流式内容的修改能被视图感知
    return sessions.value.find((s) => s.id === session.id) || session
  }

  function newChat() {
    if (sending.value) stop()
    const session = newSessionDraft()
    sessions.value.unshift(session)
    activeId.value = session.id
    showWelcome.value = true
  }

  function switchSession(id) {
    if (sending.value) stop()
    showWelcome.value = false
    activeId.value = id
    const s = sessions.value.find((x) => x.id === id)
    if (s) hydrateSession(s)
  }

  async function renameSession(id, title) {
    const s = sessions.value.find((x) => x.id === id)
    if (!s) return
    const next = String(title || '').trim().slice(0, 24)
    if (!next) return
    if (s.conversationId != null) {
      await renameConversation(s.conversationId, next)
    }
    s.title = next
  }

  async function removeSession(id) {
    const index = sessions.value.findIndex((x) => x.id === id)
    if (index < 0) return
    const s = sessions.value[index]
    if (s.conversationId != null) {
      await deleteConversation(s.conversationId)
    }
    sessions.value.splice(index, 1)
    if (activeId.value === id) {
      activeId.value = sessions.value[0]?.id || ''
      const next = sessions.value[0]
      if (next) hydrateSession(next)
    }
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
  async function send(text, context = null) {
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
      session.title = content.replace(/\s+/g, ' ').slice(0, 30)
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

    try {
      await streamChat({
        conversationId: session.conversationId,
        message: content,
        context,
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

            // 方案卡：确认(fixed)就地替换旧卡；换候选/调整(candidates)作为新卡追加，
            // 让对话里的调整能直接看到新方案（点「换一换」按钮走 silentAction，仍原地更新）。
            const fixedCard = block.type === 'meal_card' && block.status === 'fixed'
            const replacedInPlace = fixedCard && replaceMealCardInPlace(session, block, aiMsg)
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
            // done 是「流结束」信号，不是「成功」信号；若前面已收到 error，保持 error 态，
            // 避免错误被 done 覆盖成「成功」（BUG-044）。
            if (aiMsg.status !== 'error') aiMsg.status = 'done'
            aiMsg.thinking = '' // 兜底：确保思考步骤条不残留
            if (payload.conversation_id) adoptConversation(session, payload.conversation_id)
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
      aiMsg.thinking = '' // 兜底：流正常结束但未收到 done 事件时，也不残留过程状态
      session.updatedAt = new Date().toISOString()
      // 对话完成后通知面板刷新：生成/确认/报告都可能在服务端改了固定方案、清单、历史或报告
      panel.bump()
    } catch (e) {
      if (e.name === 'AbortError' || e.code === 'CANCELED') {
        aiMsg.status = 'stopped'
        aiMsg.thinking = '' // 停止后清除「正在生成…」过程状态，避免思考步骤条残留
        if (!aiMsg.text) aiMsg.text = '（已停止本次生成）'
      } else {
        aiMsg.status = 'error'
        aiMsg.error = e.message || '网络异常，请稍后重试'
      }
    } finally {
      sending.value = false
      abortController.value = null
    }
  }

  /**
   * 静默动作：不发 user/AI 气泡，只消费结构化产物并把方案卡就地更新。
   * 用于「换一换 / 选用候选」这类轻量按钮操作——聊天流不产生任何消息，
   * 仅卡片 spinner + 原地刷新；失败时抛错，由调用方 toast 提示。
   */
  async function silentAction(text, context = null) {
    const content = String(text || '').trim()
    if (!content || sending.value) return false

    const session = ensureSession()

    sending.value = true
    const controller = new AbortController()
    abortController.value = controller

    let errorMsg = ''
    let errorCode = null
    let completed = false
    let matchingCard = false
    try {
      await streamChat({
        conversationId: session.conversationId,
        message: content,
        context,
        signal: controller.signal,
        silent: true,
        onEvent: (evt) => {
          const payload = evt.data && typeof evt.data === 'object' ? evt.data : {}
          // 只消费方案卡，丢弃正文文本（静默，不产生对话气泡）
          if (evt.event === 'artifact' && payload.type === 'meal_card') {
            const block = normalizeArtifact(payload.type, payload.payload || {})
            if (!context?.meal_plan_id || String(block.raw_id) === String(context.meal_plan_id)) {
              matchingCard = true
              replaceMealCardInPlace(session, block)
              session.updatedAt = new Date().toISOString()
            }
          }
          if (evt.event === 'done') {
            if (payload.conversation_id) adoptConversation(session, payload.conversation_id)
            completed = payload.finish_reason === 'stop'
          }
          if (evt.event === 'clarify') errorMsg = payload.question || '需要补充信息'
          if (evt.event === 'error') {
            errorMsg = payload.message || '操作失败'
            errorCode = payload.code ?? null
          }
        }
      })

      if (errorMsg) {
        const err = new Error(errorMsg)
        err.code = errorCode
        throw err
      }
      if (!completed || !matchingCard) throw new Error('未获操作成功确认，请刷新方案核对。')
      // 确认会影响当前方案、清单和历史；换候选/选用只更新原卡片。
      if (context?.action === 'confirm') usePanelStore().bump()
      return true
    } catch (e) {
      if (e.name === 'AbortError' || e.code === 'CANCELED') return false
      throw e
    } finally {
      sending.value = false
      abortController.value = null
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
    showWelcome.value = false
  }

  // 初始化：从后端拉会话列表（无 token 时跳过，不触发鉴权提示）
  refreshSessions()

  return {
    sessions,
    activeId,
    sending,
    activeSession,
    messages,
    isWelcome,
    lastSuggestions,
    groupedSessions,
    refreshSessions,
    ensureSession,
    newChat,
    switchSession,
    renameSession,
    removeSession,
    send,
    silentAction,
    retry,
    stop,
    clearAll
  }
})
