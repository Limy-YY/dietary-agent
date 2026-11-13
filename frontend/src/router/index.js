import { createRouter, createWebHistory } from 'vue-router'
import ChatView from '@/views/ChatView.vue'

const routes = [
  {
    path: '/',
    name: 'chat',
    component: ChatView,
    meta: { title: '膳宝 · 膳食搭配智能体' }
  },
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
