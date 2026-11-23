<template>
  <div class="recipe-card">
    <div class="card-head">
      <div>
        <h3>{{ title }}</h3>
        <p class="card-sub">{{ subtitle }}</p>
      </div>
      <div class="status-tag" :class="statusClass">{{ statusText }}</div>
    </div>

    <!-- 单餐：2~3 个候选 -->
    <div v-if="scope === 'meal'" class="cand-list">
      <div
        v-for="(c, i) in candidates"
        :key="c.candidate_id || i"
        class="cand"
        :class="{ on: pickedCandidateId === c.candidate_id, readonly }"
        @click="pickCandidate(c)"
      >
        <div class="cand-radio"></div>
        <div class="cand-main">
          <div class="cand-name">{{ c.name }}</div>
          <div class="cand-desc">{{ c.desc || '按档案份量做了微调' }}</div>
        </div>
        <div class="cand-kcal">{{ fmtKcal(c.kcal) }} kcal</div>
      </div>
      <div v-if="!candidates.length" class="cand-empty">这一餐暂无候选，换个说法试试（例如「推荐午餐搭配」）</div>
    </div>

    <!-- 一日三餐 / 自定义单日 -->
    <template v-else-if="!isMultiDay">
      <div
        v-for="(slot, i) in slots"
        :key="slot.slot_id || i"
        class="meal-row clickable"
        @click="openSlotRecipe(slot)"
      >
        <div class="meal-row-main">
          <div class="meal-type">
            {{ slot.label || MEAL_LABELS[slot.meal_type] || '一餐' }}
            <span v-if="slot.time">· {{ slot.time }}</span>
            <span class="meal-kcal">{{ fmtKcal(slot.kcal) }} / 本餐目标 {{ fmtKcal(slot.target_kcal) }} kcal</span>
          </div>
          <div class="meal-dish">{{ slot.dish_text }}</div>
          <div class="meal-meta">{{ slot.dish_count }} 道菜 · 点这里看用量和做法</div>
        </div>
        <div class="action-col">
          <button class="swap-btn" :disabled="readonly || isFixed || !slot.candidates.length || isSwapping(slot)" @click.stop="swap(slot)">
            {{ isSwapping(slot) ? '换一换…' : '换一换' }}
          </button>
        </div>
      </div>
    </template>

    <!-- 一周食谱：按天折叠（可同时展开多天） -->
    <div v-else class="week-list">
      <div class="week-list-toolbar">
        <button class="expand-all-btn" @click="toggleAllDays">{{ allOpen ? '全部收起' : '全部展开' }}</button>
      </div>
      <div v-for="(day, di) in days" :key="day.iso + di" class="week-day" :class="{ 'is-today': day.is_today, open: isOpen(di) }">
        <div class="week-day-head" @click="toggleDay(di)">
          <div class="wd-date">
            <div class="wd-day">
              {{ day.weekday }}
              <span v-if="day.is_today" class="wp-today">今天</span>
            </div>
            <div class="wd-num">{{ day.date }}</div>
          </div>
          <div class="wd-counts">
            <span v-for="(s, si) in day.slots" :key="si" class="wd-count">
              {{ (s.label || s.meal_type || '').charAt(0) }} {{ s.dish_count }}
            </span>
          </div>
          <div class="wd-kcal">{{ fmtKcal(day.kcal) }} / 已安排餐次目标 {{ fmtKcal(day.target_kcal) }} kcal</div>
          <span class="wd-chevron">▾</span>
        </div>
        <div class="week-day-body">
          <div v-for="(s, si) in day.slots" :key="si" class="wd-meal">
            <div class="wd-meal-main">
              <div class="wd-meal-head">
                <span class="wd-meal-type">{{ s.label }}</span>
                <span class="wd-meal-time">{{ s.time }}</span>
              </div>
              <div class="wd-meal-dishes">{{ s.dish_text }}</div>
            </div>
            <div class="wd-meal-side">
              <span class="wd-meal-kcal">{{ fmtKcal(s.kcal) }} / 本餐目标 {{ fmtKcal(s.target_kcal) }} kcal</span>
              <button class="wd-swap" :disabled="readonly || isFixed || !s.candidates.length || isSwapping(s)" @click.stop="swap(s)">
                {{ isSwapping(s) ? '换一换…' : '换一换' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="card-foot">
      <button
        class="card-foot-left"
        :disabled="readonly || chat.sending"
        :title="readonly ? '历史快照，请到当前规划查看搭配依据' : '让膳宝解释为什么这样搭'"
        @click="onReason"
      >💡 为什么这样搭？</button>
      <div class="action-col">
        <button class="fix-btn" :disabled="readonly || isFixed || confirming || chat.sending" @click="onConfirm">
          {{ isFixed ? '已确认' : confirming ? '确认中…' : '确认方案' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { MEAL_LABELS, PHRASE } from '@/constants/actions.js'
import { arr, fmtKcal } from '@/utils/schema.js'
import { useUi } from '@/composables/useUi.js'
import { useChatStore } from '@/stores/chat.js'

const props = defineProps({ block: { type: Object, required: true } })
const ui = useUi()
const chat = useChatStore()

// 默认展开「今天」；方案内没有今天时展开第一天。支持同时展开多天。
const openDays = ref(defaultOpenDays())

function defaultOpenDays() {
  const idx = arr(props.block.days).findIndex((d) => d.is_today)
  return [idx >= 0 ? idx : 0]
}

const allOpen = computed(() => {
  const n = days.value.length
  return n > 0 && openDays.value.length === n
})

function isOpen(di) {
  return openDays.value.includes(di)
}

function toggleDay(di) {
  const i = openDays.value.indexOf(di)
  if (i >= 0) openDays.value.splice(i, 1)
  else openDays.value.push(di)
}

function toggleAllDays() {
  openDays.value = allOpen.value ? [] : days.value.map((_, i) => i)
}
// 正在「换一换」的餐位 slot_id（用于按钮 spinner / 禁用）
const swapping = ref('')
// 确认方案进行中（含冲突退回对话的追问阶段）：置真期间禁用「确认方案」按钮，避免重复点
const confirming = ref(false)

const scope = computed(() => props.block.plan_key || props.block.scope || 'day')
const isMultiDay = computed(() => days.value.length > 1)

const title = computed(() => {
  const base = props.block.title || (isMultiDay.value ? '📅 多日食谱' : scope.value === 'meal' ? '🍱 单餐搭配' : '🗓️ 今日食谱')
  return props.block.display_index ? `方案${props.block.display_index} · ${base}` : base
})
const subtitle = computed(() => props.block.subtitle || '按你的档案估算份量')

const slots = computed(() => arr(props.block.slots))
const days = computed(() =>
  arr(props.block.days).map((d) => ({
    iso: d.iso || '',
    date: d.date || '',
    weekday: d.weekday || '',
    is_today: Boolean(d.is_today),
    kcal: d.kcal == null ? null : d.kcal,
    target_kcal: d.target_kcal == null ? null : d.target_kcal,
    slots: arr(d.slots)
  }))
)

const candidates = computed(() => {
  const first = slots.value[0]
  if (!first) return []
  if (first.candidates.length) return first.candidates
  return arr(props.block.candidates)
})

const pickedId = ref('')
const pickedCandidateId = computed({
  get: () => pickedId.value || slots.value[0]?.selected_candidate_id || candidates.value[0]?.candidate_id || '',
  set: (v) => (pickedId.value = v)
})

const status = computed(() => {
  const raw = props.block.status || 'draft'
  return raw === 'fixed' ? 'fixed' : raw === 'candidates' ? 'candidates' : 'draft'
})
const isFixed = computed(() => status.value === 'fixed')
const readonly = computed(() => Boolean(props.block.readonly))
const statusText = computed(() =>
  readonly.value ? '历史快照' : props.block.status_label || (isFixed.value ? '已生效' : '待确认')
)
const statusClass = computed(() => (readonly.value ? 'readonly' : isFixed.value ? 'fixed' : 'draft'))

// 就地更新（换一换/选用/确认）不再重建组件（__key 已改为稳定身份），这里显式复位局部状态，
// 清掉选中候选高亮 / 展开天数等残留（原 BUG-045 靠「换 key 重建」实现，改为 watch 复位，避免重放淡入动画）。
watch(
  () => props.block,
  () => {
    pickedId.value = ''
    openDays.value = defaultOpenDays()
  }
)

function isSwapping(slot) {
  return !!swapping.value && swapping.value === slot.slot_id
}

async function pickCandidate(c) {
  if (readonly.value || isFixed.value || chat.sending || swapping.value) return
  // 点的是当前已选中的候选：后端会报「该候选已是当前选中」，直接忽略，避免误弹「选用失败」
  if (c.candidate_id === pickedCandidateId.value) return
  const label = slots.value[0]?.label || MEAL_LABELS[slots.value[0]?.meal_type] || '这一餐'
  const prev = pickedId.value
  pickedCandidateId.value = c.candidate_id // 乐观选中，失败回退
  try {
    const ok = await chat.silentAction(PHRASE.choose(label, c.name), actionContext('choose_candidate', slots.value[0], c))
    if (!ok) pickedCandidateId.value = prev
  } catch (e) {
    ElMessage(e.message || '选用失败，请重试')
    pickedCandidateId.value = prev
  }
}

async function swap(slot) {
  if (readonly.value || isFixed.value || chat.sending || swapping.value) return
  const label = slot.label || MEAL_LABELS[slot.meal_type] || '这一餐'
  swapping.value = slot.slot_id
  try {
    await chat.silentAction(PHRASE.swap(label), actionContext('swap_candidate', slot))
  } catch (e) {
    ElMessage(e.message || '换候选失败，请重试')
  } finally {
    swapping.value = ''
  }
}

function actionContext(action, slot = null, candidate = null) {
  return {
    meal_plan_id: props.block.raw_id,
    meal_slot_id: slot?.slot_id,
    candidate_id: candidate?.candidate_id,
    action
  }
}

async function onConfirm() {
  if (readonly.value || isFixed.value || confirming.value || chat.sending) return
  confirming.value = true
  try {
    await chat.silentAction(PHRASE.confirm, actionContext('confirm'))
  } catch (e) {
    if (e && e.code === 2005) {
      // 同期已有固定方案冲突：静默路径会吞掉「替换/取消」按钮，
      // 退回对话路径（不带 context，避免后端把 current_plan 当聊天卡下发），
      // 方案定位交给 Agent 记住的「冲突目标方案」。await 让按钮在追问期间保持禁用。
      await chat.send(PHRASE.confirm)
    } else {
      ElMessage(e.message || '确认失败，请重试')
    }
  } finally {
    confirming.value = false
  }
}

function onReason() {
  chat.send(PHRASE.reason, actionContext('explain'))
}

function openSlotRecipe(slot) {
  ui.recipePayload = {
    title: `${slot.label || '这一餐'} · 详细食谱`,
    meals: [{ label: slot.label, time: slot.time, color: '', kcal: slot.kcal, dishes: slot.dishes }]
  }
  ui.recipeOpen = true
}
</script>

<style scoped>
.week-list-toolbar {
  display: flex;
  justify-content: flex-end;
  padding: 10px 20px 2px;
}

.cand-empty {
  font-size: 13px;
  color: var(--text-sub);
  padding: 6px 2px;
}

.cand.readonly { cursor: default; }
</style>
