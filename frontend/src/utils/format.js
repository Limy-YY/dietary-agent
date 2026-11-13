export function pad2(n) {
  return String(n).padStart(2, '0')
}

/** ISO → HH:mm */
export function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso).slice(11, 16)
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}

/** ISO → YYYY-MM-DD HH:mm */
export function fmtDateTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}

/** ISO → MM-DD */
export function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 10)
  return `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

/** 相对时间：刚刚 / N 分钟前 / N 小时前 / MM-DD */
export function fmtRelative(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const diff = Date.now() - d.getTime()
  if (diff < 60_000) return '刚刚'
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86400_000) return `${Math.floor(diff / 3600_000)} 小时前`
  return fmtDate(iso)
}

export function fmtKcal(v) {
  const n = Number(v)
  return Number.isFinite(n) ? String(Math.round(n)) : '—'
}

/** 会话分组：今天 / 近 7 天 / 更早 */
export function groupOf(iso) {
  const d = new Date(iso || Date.now())
  const now = new Date()
  const sameDay =
    d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate()
  if (sameDay) return '今天'
  const diff = now.getTime() - d.getTime()
  if (diff < 7 * 86400_000) return '近 7 天'
  return '更早'
}

export function uid(prefix = 'id') {
  return `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}
