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
        :class="{ on: pickedCandidateId === c.candidate_id }"
        @click="pickCandidate(c)"
      >
        <div class="cand-radio"></div>
        <div class="cand-main">
          <div class="cand-name">{{ c.name }}</div>
          <div class="cand-desc">{{ c.desc || '按档案份量做了微调' }}</div>
        </div>
        <div class="cand-kcal">{{ fmtNum(c.kcal) }} kcal</div>
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
            <span class="meal-kcal">{{ fmtNum(slot.kcal) }} kcal</span>
          </div>
          <div class="meal-dish">{{ slot.dish_text }}</div>
          <div class="meal-meta">{{ slot.dish_count }} 道菜 · 点这里看用量和做法</div>
        </div>
        <div class="action-col">
          <button class="swap-btn" :disabled="isFixed || !slot.candidates.length" @click.stop="swap(slot)">
            换一换
          </button>
        </div>
      </div>
    </template>

    <!-- 一周食谱：按天折叠 -->
    <div v-else class="week-list">
      <div v-for="(day, di) in days" :key="day.iso + di" class="week-day" :class="{ 'is-today': day.is_today, open: openDay === di }">
        <div class="week-day-head" @click="openDay = openDay === di ? -1 : di">
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
          <div class="wd-kcal">{{ fmtNum(day.kcal) }} kcal</div>
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
              <span class="wd-meal-kcal">{{ fmtNum(s.kcal) }} kcal</span>
              <button class="wd-swap" :disabled="isFixed || !s.candidates.length" @click.stop="swap(s)">
                换一换
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="card-foot">
      <button class="card-foot-left" @click="onReason">💡 为什么这样搭？</button>
      <div class="action-col">
        <button class="fix-btn" :disabled="isFixed" @click="onConfirm">
          {{ isFixed ? '已确认' : '确认方案' }}
        </button>
      </div>
    </div>

    <el-dialog v-model="reasonOpen" title="这套方案是怎么搭出来的" width="560px" append-to-body>
      <p v-if="reasonSummary" style="font-size: 13.5px; color: var(--text-sub); margin-bottom: 12px">
        {{ reasonSummary }}
      </p>
      <div class="rp-insights" style="margin-top: 0">
        <h5>营养结构</h5>
        <ul>
          <li v-for="(p, i) in reasonPoints" :key="i">{{ p }}</li>
        </ul>
      </div>
      <div class="modal-note">份量按身高体重估算，只作参考；身体有特殊情况请先问医生。</div>
      <template #footer>
        <el-button @click="reasonOpen = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { MEAL_LABELS, PHRASE } from '@/constants/actions.js'
import { arr, fmtNum } from '@/utils/schema.js'
import { useUi } from '@/composables/useUi.js'

const props = defineProps({ block: { type: Object, required: true } })
const emit = defineEmits(['phrase'])
const ui = useUi()

const reasonOpen = ref(false)
const openDay = ref(0)

const scope = computed(() => props.block.plan_key || props.block.scope || 'day')
const isMultiDay = computed(() => days.value.length > 1)

const title = computed(() => {
  if (props.block.title) return props.block.title
  return isMultiDay.value ? '📅 多日食谱' : scope.value === 'meal' ? '🍱 单餐搭配' : '🗓️ 今日食谱'
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
const statusText = computed(() => props.block.status_label || (isFixed.value ? '已生效' : '待确认'))
const statusClass = computed(() => (isFixed.value ? 'fixed' : 'draft'))

const reasonSummary = computed(() => {
  const r = props.block.reason
  if (typeof r === 'string') return r
  return (r && r.summary) || ''
})
const reasonPoints = computed(() => {
  const hints = arr(props.block.reference_hints)
  const notes = arr(props.block.data_quality_notes)
  return [...hints, ...notes]
})

function pickCandidate(c) {
  if (isFixed.value) return
  pickedCandidateId.value = c.candidate_id
  const label = slots.value[0]?.label || MEAL_LABELS[slots.value[0]?.meal_type] || '这一餐'
  emit('phrase', PHRASE.choose(label, c.name))
}

function swap(slot) {
  if (isFixed.value) return
  const label = slot.label || MEAL_LABELS[slot.meal_type] || '这一餐'
  emit('phrase', PHRASE.swap(label))
}

function onConfirm() {
  if (isFixed.value) return
  emit('phrase', PHRASE.confirm)
}

function onReason() {
  if (reasonPoints.value.length) reasonOpen.value = true
  else emit('phrase', PHRASE.reason)
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
.cand-empty {
  font-size: 13px;
  color: var(--text-sub);
  padding: 6px 2px;
}
</style>
