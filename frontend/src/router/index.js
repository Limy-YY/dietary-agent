import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'chat',
    // 路由懒加载（IMP-005）：按需拉取页面 chunk，减小首屏主包
    component: () => import('@/views/ChatView.vue'),
    meta: { title: '膳宝 · 膳食搭配智能体' }
  },
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
