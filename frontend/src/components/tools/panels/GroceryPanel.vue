<template>
  <div>
    <div v-if="loading" class="sk-wrap">
      <div class="skeleton sk-line" style="width: 60%"></div>
      <div class="skeleton sk-line" style="width: 85%"></div>
      <div class="skeleton sk-line" style="width: 45%"></div>
    </div>

    <template v-else-if="groups.length">
      <div class="data-timestamp">🕐 数据更新于 {{ updatedText }}</div>

      <div class="grocery-progress">已买 {{ doneCount }}/{{ total }} 项</div>

      <div v-if="hasDay" class="grocery-filter">
        <button class="gf-chip" :class="{ on: filter === 'all' }" @click="filter = 'all'">全部</button>
        <button
          v-for="d in dayOptions"
          :key="d"
          class="gf-chip"
          :class="{ on: filter === d }"
          @click="filter = d"
        >
          {{ d }}
        </button>
      </div>

      <div v-for="section in sections" :key="section.key">
        <div v-if="hasDay" class="grocery-day-head">
          <span class="gd-day">{{ section.day }}</span>
          <span class="gd-date">{{ section.date }}</span>
        </div>

        <div v-for="g in section.groups" :key="g.group_id">
          <div class="grocery-group-title">
            <span>{{ g.category }}</span>
          </div>
          <label
            v-for="it in g.items"
            :key="it.item_id"
            class="grocery-item"
            :class="{ checked: checkedMap[it.item_id] }"
          >
            <input type="checkbox" v-model="checkedMap[it.item_id]" @change="index++" />
            <span class="gi-name">{{ it.name }} {{ amountText(it.amount) }}</span>
          </label>
        </div>
      </div>
    </template>

    <template v-else-if="error">
      <EmptyState icon="⚠️" title="加载失败" :desc="error" :actions="[{ label: '重新加载', phrase: 'reload' }]" @action="onAction" />
    </template>

    <template v-else>
      <EmptyState
        icon="🛒"
        title="暂未生成食材清单"
        desc="确认食谱后，我会为你自动拆解出
需要采购的食材及用量。"
        :actions="[{ icon: '🥗', label: '生成一日三餐', desc: '先让智能体为你配餐并确认', phrase: '生成一日三餐' }]"
        hint="💡 生成食谱后，记得在对话框或卡片中点击 <b>“确认规划”</b>，这里才会更新哦。"
        @action="onAction"
      />
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
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
const groups = ref([])
const updatedAt = ref('')
const filter = ref('all')
const checkedMap = reactive({})
const index = ref(0)

const hasDay = computed(() => groups.value.some((g) => g.day))
const total = computed(() => groups.value.reduce((s, g) => s + g.items.length, 0))
const doneCount = computed(() => groups.value.reduce((s, g) => s + g.items.filter((it) => checkedMap[it.item_id]).length, 0))
const updatedText = computed(() => (updatedAt.value ? fmtDateTime(updatedAt.value) : '刚刚'))

const categories = computed(() => [...new Set(groups.value.map((g) => g.category))])
const dayOptions = computed(() => (hasDay.value ? [...new Set(groups.value.map((g) => g.day))] : []))

const sections = computed(() => {
  const map = new Map()
  groups.value
    .filter((g) => filter.value === 'all' || g.day === filter.value)
    .forEach((g) => {
      const key = hasDay.value ? g.day || '全部' : '全部'
      if (!map.has(key)) map.set(key, { key, day: key, date: g.day_date || '', groups: [] })
      map.get(key).groups.push(g)
    })
  return [...map.values()].filter((s) => s.groups.length)
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const list = await fetchShoppingList()
    groups.value = list ? normalizeGroups(list.groups) : []
    updatedAt.value = list?.updated_at || ''
  } catch (e) {
    error.value = e.message || '清单加载失败'
    groups.value = []
  } finally {
    loading.value = false
  }
}

function amountText(amount) {
  if (!amount) return ''
  return /[（(]/.test(amount) ? amount : `(${amount})`
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
</style>
