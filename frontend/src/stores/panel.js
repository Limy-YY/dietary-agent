import { defineStore } from 'pinia'
import { ref } from 'vue'

export const usePanelStore = defineStore('panel', () => {
  /** 当前展开的面板 key：grocery | current_plan | history | report | '' */
  const active = ref('')
  /** 对话完成后自增，面板组件 watch 后重新拉取数据 */
  const revision = ref(0)
  /** 报告面板未读角标 */
  const unreadReports = ref(0)
  /** F6（IMP-064）：复用生成后要求「当前规划」面板直接展示的新方案 id；为空时按 /current 常规加载 */
  const focusPlanId = ref(null)

  function open(key) {
    active.value = key
    if (key === 'report') unreadReports.value = 0
  }

  function close() {
    active.value = ''
  }

  function toggle(key) {
    active.value = active.value === key ? '' : key
    if (active.value === 'report') unreadReports.value = 0
  }

  function bump() {
    revision.value += 1
  }

  function markReportUnread() {
    unreadReports.value += 1
  }

  /** F6：记下要直达展示的新草稿方案，并切到当前规划面板 */
  function showPlan(planId) {
    focusPlanId.value = planId ? String(planId) : null
    active.value = 'current_plan'
  }

  /** 新的正常配餐流程开始后清掉复用聚焦，避免面板一直钉在旧草稿上 */
  function clearFocusPlan() {
    focusPlanId.value = null
  }

  return { active, revision, unreadReports, focusPlanId, open, close, toggle, bump, markReportUnread, showPlan, clearFocusPlan }
})
