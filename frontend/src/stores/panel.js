import { defineStore } from 'pinia'
import { ref } from 'vue'

export const usePanelStore = defineStore('panel', () => {
  /** 当前展开的面板 key：grocery | current_plan | history | report | '' */
  const active = ref('')
  /** 对话完成后自增，面板组件 watch 后重新拉取数据 */
  const revision = ref(0)
  /** 报告面板未读角标 */
  const unreadReports = ref(0)

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

  return { active, revision, unreadReports, open, close, toggle, bump, markReportUnread }
})
