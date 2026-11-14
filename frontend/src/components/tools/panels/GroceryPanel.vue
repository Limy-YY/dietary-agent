<template>
  <div>
    <div v-if="loading" class="sk-wrap">
      <div class="skeleton sk-line" style="width: 60%"></div>
      <div class="skeleton sk-line" style="width: 85%"></div>
      <div class="skeleton sk-line" style="width: 45%"></div>
    </div>

    <template v-else-if="groups.length">
      <div class="data-timestamp">🕐 清单生成于 {{ updatedText }} · 共 {{ total }} 项</div>

      <div class="grocery-progress">已买 {{ doneCount }}/{{ total }} 项</div>

      <div v-for="g in groups" :key="g.group_id">
        <div class="grocery-group-title">
          <span>{{ g.category }}</span>
          <span style="font-weight: 400; color: var(--text-sub); font-size: 11.5px">{{ g.items.length }} 项</span>
        </div>
        <label
          v-for="it in g.items"
          :key="it.item_id"
          class="grocery-item"
          :class="{ checked: checkedMap[it.item_id] }"
        >
          <input type="checkbox" v-model="checkedMap[it.item_id]" @change="index++" />
          <span class="gi-name">{{ it.name }}</span>
          <span class="gi-amount">{{ it.amount }}</span>
        </label>
      </div>
      <div class="grocery-note">数量为估算量，按实际采购调整；粮油等常备品类按家中存量自行增减。</div>
    </template>

    <template v-else-if="unfixed">
      <EmptyState
        icon="🛒"
        title="方案还没固定"
        desc="食材清单在方案固定后才会生成，
避免买到作废的候选菜品。"
        :actions="[{ icon: '✅', label: '确认当前方案', desc: '固定后自动拆解食材', phrase: '确认当前方案' }]"
        hint="💡 在对话卡片里点 <b>“确认方案”</b>，这里就会按类别列出需要采购的食材。"
        @action="onAction"
      />
    </template>

    <template v-else-if="error">
      <EmptyState icon="⚠️" title="加载失败" :desc="error" :actions="[{ label: '重新加载', phrase: 'reload' }]" @action="onAction" />
    </template>

    <template v-else>
      <EmptyState
        icon="🛒"
        title="暂未生成食材清单"
        desc="确认方案后，我会按类别拆解出
需要采购的食材及估算用量。"
        :actions="[{ icon: '🥗', label: '生成一日三餐', desc: '先让智能体为你配餐并确认', phrase: '生成一日三餐' }]"
        hint="💡 生成方案后，记得在卡片中点击 <b>“确认方案”</b>。"
        @action="onAction"
      />
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { fetchCurrentPlan } from '@/api/mealPlan.js'
import { fetchShoppingList } from '@/api/shopping.js'
import { normalizeGroups } from '@/utils/schema.js'
import { fmtDateTime } from '@/utils/format.js'
import { usePanelStore } from '@/stores/panel.js'
import { useChatStore } from '@/stores/chat.js'
import EmptyState from '@/components/common/EmptyState.vue'

const panel = usePanelStore()
const chat = useChatStore()

const loading = ref(false)
const error = ref('')
const unfixed = ref(false)
const groups = ref([])
const totalItems = ref(null)
const generatedAt = ref('')
const checkedMap = reactive({})
const index = ref(0)

const total = computed(() => {
  if (totalItems.value != null) return totalItems.value
  return groups.value.reduce((s, g) => s + g.items.length, 0)
})
const doneCount = computed(() =>
  groups.value.reduce((s, g) => s + g.items.filter((it) => checkedMap[it.item_id]).length, 0)
)
const updatedText = computed(() => (generatedAt.value ? fmtDateTime(generatedAt.value) : '刚刚'))

async function load() {
  loading.value = true
  error.value = ''
  unfixed.value = false
  try {
    const current = await fetchCurrentPlan()
    if (!current || current.meal_plan_id == null) {
      groups.value = []
      totalItems.value = null
      return
    }
    const list = await fetchShoppingList(current.meal_plan_id)
    if (list && list.error === 'unfixed') {
      unfixed.value = true
      groups.value = []
      return
    }
    groups.value = list ? normalizeGroups(list.groups) : []
    totalItems.value = list?.total_items ?? null
    generatedAt.value = list?.generated_at || ''
  } catch (e) {
    error.value = e.message || '清单加载失败'
    groups.value = []
  } finally {
    loading.value = false
  }
}

function onAction(a) {
  if (a.phrase === 'reload') load()
  else chat.send(a.phrase)
}

onMounted(load)
watch(() => panel.revision, load)
watch(() => panel.active, (v) => v === 'grocery' && load())
</script>

<style scoped>
.sk-wrap {
  padding-top: 8px;
}

.grocery-note {
  margin-top: 12px;
  font-size: 11.5px;
  color: var(--text-sub);
  line-height: 1.6;
}
</style>
