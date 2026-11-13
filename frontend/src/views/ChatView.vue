<template>
  <div class="app-shell">
    <SessionSidebar :collapsed="leftCollapsed" />

    <button class="sidebar-toggle-btn" title="收起 / 展开会话列表" @click="leftCollapsed = !leftCollapsed">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <line x1="9" y1="3" x2="9" y2="21" />
      </svg>
    </button>

    <main class="chat-main">
      <ChatPane />
    </main>

    <ToolRail />

    <ProfileModal />
    <RecipeModal />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import SessionSidebar from '@/components/sidebar/SessionSidebar.vue'
import ChatPane from '@/components/chat/ChatPane.vue'
import ToolRail from '@/components/tools/ToolRail.vue'
import ProfileModal from '@/components/profile/ProfileModal.vue'
import RecipeModal from '@/components/renderer/RecipeModal.vue'
import { useProfileStore } from '@/stores/profile.js'

const leftCollapsed = ref(false)
const profile = useProfileStore()

onMounted(() => {
  profile.load()
  window.addEventListener('sz:unauthorized', () => {
    ElMessage.warning('登录已失效，重新登录后可继续使用')
  })
})
</script>
