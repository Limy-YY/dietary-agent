import { getToken, apiBase, ApiError } from './http.js'

/**
 * 对话流：POST /api/agent/chat（SSE，v1.2 事件流）
 * event: X\ndata: {json}\n\n
 *   message  → { type: 'text', content: '...' }            正文增量
 *   artifact → { type: 'meal_card'|'shopping_list'|'current_plan'|'nutrition_report', payload }
 *   clarify  → { question, missing_fields[] }              信息不足，必须追问
 *   error    → { code, message }                           业务错误码同 REST
 *   done     → { conversation_id, meal_plan_id, finish_reason }
 * 请求体：{ conversation_id?, message, context?{ meal_plan_id } }
 */
export async function streamChat({ conversationId, message, context, signal, onEvent }) {
  const bodyPayload = { message }
  if (conversationId) bodyPayload.conversation_id = conversationId
  if (context && context.meal_plan_id != null) bodyPayload.context = { meal_plan_id: context.meal_plan_id }

  const res = await fetch(`${apiBase()}/agent/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      Authorization: `Bearer ${getToken()}`
    },
    body: JSON.stringify(bodyPayload),
    signal
  })

  if (!res.ok) {
    let detail = ''
    try {
      const body = await res.json()
      detail = body.message || ''
      throw new ApiError(body.code || res.status, detail || '对话请求失败', { status: res.status, retryable: true })
    } catch (e) {
      if (e instanceof ApiError) throw e
      throw new ApiError(res.status, detail || `对话请求失败（${res.status}）`, { status: res.status, retryable: true })
    }
  }

  const contentType = res.headers.get('content-type') || ''
  if (!res.body || !contentType.includes('text/event-stream')) {
    let body = null
    try {
      body = await res.json()
    } catch (e) {
      body = null
    }
    throw new ApiError(body?.code || 'PROTOCOL', body?.message || '服务未返回流式响应', { retryable: true })
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let sep = buffer.indexOf('\n\n')
      while (sep !== -1) {
        const chunk = buffer.slice(0, sep)
        buffer = buffer.slice(sep + 2)
        const evt = parseChunk(chunk)
        if (evt) onEvent(evt)
        sep = buffer.indexOf('\n\n')
      }
    }

    if (buffer.trim()) {
      const evt = parseChunk(buffer)
      if (evt) onEvent(evt)
    }
  } finally {
    try {
      reader.releaseLock()
    } catch (e) {
      /* 已释放 */
    }
  }
}

function parseChunk(chunk) {
  let event = 'message'
  const dataLines = []
  chunk.split(/\r?\n/).forEach((line) => {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  })
  if (!dataLines.length) return null
  const raw = dataLines.join('\n')
  let data = raw
  try {
    data = JSON.parse(raw)
  } catch (e) {
    /* 保留原始字符串 */
  }
  return { event, data }
}
