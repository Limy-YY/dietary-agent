import axios from 'axios'
import { ElMessage } from 'element-plus'

const TOKEN_KEY = 'sz_token'

export function getToken() {
  const cached = localStorage.getItem(TOKEN_KEY)
  if (cached) return cached
  // 本地联调：默认带一个演示 JWT，避免每次手动登录
  if (import.meta.env.VITE_USE_MOCK !== 'false' && import.meta.env.VITE_DEMO_TOKEN) {
    localStorage.setItem(TOKEN_KEY, import.meta.env.VITE_DEMO_TOKEN)
    return import.meta.env.VITE_DEMO_TOKEN
  }
  return ''
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export function apiBase() {
  if (import.meta.env.VITE_USE_MOCK !== 'false') return '/api'
  return `${import.meta.env.VITE_API_BASE || ''}/api`
}

export class ApiError extends Error {
  constructor(code, message, { status = 0, retryable = false } = {}) {
    super(message || '请求失败')
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.retryable = retryable
  }
}

const http = axios.create({
  baseURL: apiBase(),
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' }
})

http.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

/**
 * 统一响应：{ code, message, data }
 * - code === 0      → 取 data
 * - code === 1004   → 空态，resolve(null)，由调用方渲染空态
 * - code === 1002   → 登录态失效，提示并跳登录
 * - 其他            → 抛出 ApiError（可重试由 retryable 标记）
 */
http.interceptors.response.use(
  (response) => {
    const body = response.data
    if (!body || typeof body !== 'object' || !('code' in body)) return body

    if (body.code === 0) return body.data
    if (body.code === 1004) return null

    if (body.code === 1002) {
      ElMessage.error('登录状态已失效，请重新登录')
      setToken('')
      window.dispatchEvent(new CustomEvent('sz:unauthorized'))
      return Promise.reject(new ApiError(1002, body.message, { status: response.status }))
    }

    const hint = body.code === 2002 ? '参数不合法' : body.code === 2003 ? '生成失败，请重试' : '请求失败'
    ElMessage.error(body.message || hint)
    return Promise.reject(
      new ApiError(body.code, body.message || hint, { status: response.status, retryable: body.code === 2003 })
    )
  },
  (error) => {
    if (axios.isCancel(error) || error.name === 'CanceledError') {
      return Promise.reject(new ApiError('CANCELED', '请求已取消'))
    }
    const status = error.response ? error.response.status : 0
    const msg =
      status === 401
        ? '登录状态已失效，请重新登录'
        : status === 404
        ? '接口不存在，请检查后端服务'
        : status >= 500
        ? '服务暂时不可用，请稍后再试'
        : error.message === 'Network Error'
        ? '网络连接异常，请检查本地服务是否启动'
        : '请求失败，请稍后再试'

    if (status !== 401) ElMessage.error(msg)
    if (status === 401) {
      setToken('')
      window.dispatchEvent(new CustomEvent('sz:unauthorized'))
    }
    return Promise.reject(new ApiError(status || 'NETWORK', msg, { status, retryable: true }))
  }
)

export default http
