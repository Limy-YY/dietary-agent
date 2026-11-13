<template>
  <aside class="sidebar-left" :class="{ collapsed }">
    <div class="logo-area">
      <div class="model-logo"><img :src="logo" alt="膳宝" /></div>
      <span class="model-name">膳宝</span>
      <span class="model-desc">膳食智能体</span>
    </div>

    <button class="new-chat-btn" @click="chat.newChat()"><span>＋</span> 开启新对话</button>

    <div class="chat-history-list">
      <template v-for="group in chat.groupedSessions" :key="group.label">
        <div class="history-label">{{ group.label }}</div>
        <div
          v-for="s in group.list"
          :key="s.id"
          class="history-item"
          :class="{ active: s.id === chat.activeId }"
          @click="chat.switchSession(s.id)"
        >
          <span>{{ s.title }}</span>
          <el-dropdown trigger="click" placement="bottom-end" @command="(cmd) => onCommand(cmd, s)">
            <span class="more-btn" @click.stop>···</span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="rename">重命名</el-dropdown-item>
                <el-dropdown-item command="delete" divided>删除会话</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </template>

      <div v-if="!chat.groupedSessions.length" class="history-empty">还没有会话，点上面「开启新对话」</div>
    </div>

    <div class="sidebar-user">
      <div v-if="menuOpen" class="user-menu">
        <button class="menu-item" @click="openProfile"><span>👤</span> 个人档案</button>
        <div class="menu-divider"></div>
        <button class="menu-item" @click="logout"><span>🚪</span> 退出登录</button>
      </div>
      <button class="user-profile-btn" @click.stop="menuOpen = !menuOpen">
        <div class="avatar-img">
          <img v-if="isImageAvatar" :src="profile.avatar" alt="头像" />
          <span v-else>{{ profile.avatar }}</span>
        </div>
        <div class="user-info">
          <div class="user-name">{{ profile.name }}</div>
          <div class="user-status">
            {{ profile.goalText ? profile.goalText + '期进行中' : '档案未完善' }}
          </div>
        </div>
        <span style="color: #bdbdbd; font-size: 18px">⋯</span>
      </button>
    </div>
  </aside>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useChatStore } from '@/stores/chat.js'
import { useProfileStore } from '@/stores/profile.js'
import { useUi } from '@/composables/useUi.js'
import { setToken } from '@/api/http.js'
import logo from '@/assets/logo.jpg'

defineProps({ collapsed: { type: Boolean, default: false } })

const chat = useChatStore()
const profile = useProfileStore()
const ui = useUi()
const menuOpen = ref(false)

const isImageAvatar = computed(() => String(profile.avatar || '').startsWith('data:image'))

async function onCommand(cmd, session) {
  if (cmd === 'rename') {
    try {
      const { value } = await ElMessageBox.prompt('给这个会话起个名字', '重命名', {
        inputValue: session.title,
        inputPattern: /^.{1,24}$/,
        inputErrorMessage: '1～24 个字符',
        confirmButtonText: '保存',
        cancelButtonText: '取消'
      })
      chat.renameSession(session.id, value)
      ElMessage.success('会话已重命名')
    } catch (e) {
      /* 用户取消 */
    }
    return
  }

  if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm(`删除「${session.title}」？本机记录会被清掉。`, '删除会话', {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      })
      chat.removeSession(session.id)
      ElMessage.success('会话已删除')
    } catch (e) {
      /* 用户取消 */
    }
  }
}

function openProfile() {
  menuOpen.value = false
  ui.profileMode = 'view'
  ui.profileOpen = true
}

function logout() {
  menuOpen.value = false
  setToken('')
  ElMessage('演示环境没有接入账号系统，已清空本地登录态')
}

function onDocClick(e) {
  if (!e.target.closest('.sidebar-user')) menuOpen.value = false
}

onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
</script>

<style scoped>
.history-empty {
  font-size: 12.5px;
  color: var(--text-sub);
  padding: 10px 12px;
  line-height: 1.7;
}

.more-btn :deep(span) {
  display: inline-flex;
}
</style>
