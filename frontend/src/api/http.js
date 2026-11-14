import axios from 'axios'
import { ElMessage } from 'element-plus'

const TOKEN_KEY = 'sz_token'

export function getToken() {
  const cached = localStorage.getItem(TOKEN_KEY)
  if (cached) return cached
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

/** 业务错误码语义（v1.2 后端契约 §1.4），一字不差对齐 */
export const CODE_MESSAGES = {
  0: '成功',
  1001: '参数校验不通过，请检查填写内容',
  1002: '登录状态已失效，请重新登录',
  1003: '当前账号没有该操作权限',
  1004: '资源不存在',
  2001: '营养计算失败，请稍后再试',
  2002: '智能体调用失败，请稍后重试',
  2003: '结构化输出校验失败，请重试',
  2004: '数据源暂时不可用，请稍后再试',
  2005: '方案状态不允许该操作',
  2006: '当前条件下排不出可行方案',
  3001: '内容安全拦截，请调整表述后再试'
}

const RETRYABLE_CODES = [2001, 2002, 2003, 2004]

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
 * - data 直接是对象（列表为 {total,page,page_size,items}），不再有 profile/plan 包裹层
 * - 1004 资源不存在 → resolve(null)，交给面板渲染空态
 * - 1002 未授权 → 清 token 并广播
 * - 其余业务码 → 按 §1.4 语义弹提示并抛 ApiError
 */
http.interceptors.response.use(
  (response) => {
    const body = response.data
    if (!body || typeof body !== 'object' || !('code' in body)) return body

    if (body.code === 0) return body.data
    if (body.code === 1004) return null

    if (body.code === 1002) {
      ElMessage.error(CODE_MESSAGES[1002])
      setToken('')
      window.dispatchEvent(new CustomEvent('sz:unauthorized'))
      return Promise.reject(new ApiError(1002, body.message || CODE_MESSAGES[1002], { status: response.status }))
    }

    const hint = CODE_MESSAGES[body.code] || '请求失败，请稍后再试'
    ElMessage.error(body.message || hint)
    return Promise.reject(
      new ApiError(body.code, body.message || hint, {
        status: response.status,
        retryable: RETRYABLE_CODES.includes(body.code)
      })
    )
  },
  (error) => {
    if (axios.isCancel(error) || error.name === 'CanceledError') {
      return Promise.reject(new ApiError('CANCELED', '请求已取消'))
    }
    const status = error.response ? error.response.status : 0
    const msg =
      status === 401
        ? CODE_MESSAGES[1002]
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
