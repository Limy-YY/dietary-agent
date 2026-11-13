import { getToken, apiBase, ApiError } from './http.js'

/**
 * 对话流：POST /api/agent/chat（SSE）
 * 事件：
 *   message → { delta }  正文增量
 *   message → { meta, conversation_id }  结构化边车（正文结束后一次下发）
 *   done    → { conversation_id, message_id, finish_reason, suggestions }
 *   error   → { code, message }
 *   ping    → 心跳，忽略
 */
export async function streamChat({ conversationId, message, signal, onEvent }) {
  const res = await fetch(`${apiBase()}/agent/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      Authorization: `Bearer ${getToken()}`
    },
    body: JSON.stringify({ conversation_id: conversationId || null, message }),
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

  // 后端若返回 JSON 错误（例如 1002），按错误处理而不是当成流
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

      // SSE 以空行分隔事件块
      let sep = buffer.indexOf('\n\n')
      while (sep !== -1) {
        const chunk = buffer.slice(0, sep)
        buffer = buffer.slice(sep + 2)
        const evt = parseChunk(chunk)
        if (evt) onEvent(evt)
        sep = buffer.indexOf('\n\n')
      }
    }

    // 兜底：部分代理会吞掉最后的空行
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
