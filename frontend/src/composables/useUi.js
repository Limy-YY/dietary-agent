import { reactive } from 'vue'

/** 全局轻量 UI 状态（弹窗、抽屉），避免为一次性状态再建 store */
const state = reactive({
  profileOpen: false,
  profileMode: 'view', // view | edit
  recipeOpen: false,
  recipePayload: null
})

export function useUi() {
  return state
}
