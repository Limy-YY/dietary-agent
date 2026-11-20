import http from './http.js'

/** GET /conversations：会话列表（分页结构 {total,page,page_size,items}，page 从 1 开始） */
export async function listConversations({ page = 1, pageSize = 100 } = {}) {
  const data = await http.get('/conversations', { params: { page, page_size: pageSize } })
  if (!data || typeof data !== 'object') return { total: 0, page, page_size: pageSize, items: [] }
  return {
    total: Number(data.total) || 0,
    page: Number(data.page) || page,
    page_size: Number(data.page_size) || pageSize,
    items: Array.isArray(data.items) ? data.items : []
  }
}

/** GET /conversations/{id}/messages：某会话消息（按 message_id 正序） */
export async function listMessages(conversationId, { page = 1, pageSize = 200 } = {}) {
  const data = await http.get(`/conversations/${encodeURIComponent(conversationId)}/messages`, {
    params: { page, page_size: pageSize }
  })
  if (!data || typeof data !== 'object') return { total: 0, page, page_size: pageSize, items: [] }
  return {
    total: Number(data.total) || 0,
    page: Number(data.page) || page,
    page_size: Number(data.page_size) || pageSize,
    items: Array.isArray(data.items) ? data.items : []
  }
}

/** PATCH /conversations/{id}：重命名 */
export async function renameConversation(conversationId, title) {
  await http.patch(`/conversations/${encodeURIComponent(conversationId)}`, { title })
}

/** DELETE /conversations/{id}：删除会话及其消息 */
export async function deleteConversation(conversationId) {
  await http.delete(`/conversations/${encodeURIComponent(conversationId)}`)
}
