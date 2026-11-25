<template>
  <el-dialog
    v-model="visible"
    :title="payload?.title || '详细食谱'"
    width="680px"
    append-to-body
    class="recipe-modal"
  >
    <div v-if="payload">
      <div v-if="dayCount > 1" class="rm-toolbar">
        <button class="expand-all-btn" @click="toggleAllDays">{{ allOpen ? '全部收起' : '全部展开' }}</button>
      </div>

      <div v-for="(g, gi) in groups" :key="gi">
        <!-- 多天：按天折叠（与「当前规划」面板一致） -->
        <div v-if="g.kind === 'day'" class="plan-day" :class="{ open: isOpen(gi) }">
          <div class="plan-day-head" @click="toggleDay(gi)">
            <span class="pd-label">{{ g.head.is_today ? '今天' : g.head.weekday }} · {{ g.head.date }}</span>
            <span class="pd-kcal">{{ fmtKcal(g.head.kcal) }} kcal</span>
            <span class="pd-chevron">▾</span>
          </div>
          <div class="plan-day-body">
            <RecipeMealList :meals="g.meals" />
          </div>
        </div>

        <!-- 单餐 / 单天：扁平列表 -->
        <RecipeMealList v-else :meals="g.meals" />
      </div>

      <div v-if="!groups.length" class="rm-empty">暂无食谱明细，可以先让膳宝生成一餐。</div>
    </div>
    <div class="modal-note">份量按档案估算；做法只保留要点，按自家口味调油盐即可。</div>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useUi } from '@/composables/useUi.js'
import { fmtKcal } from '@/utils/schema.js'
import RecipeMealList from './RecipeMealList.vue'

const ui = useUi()

const visible = computed({
  get: () => ui.recipeOpen,
  set: (v) => (ui.recipeOpen = v)
})

const payload = computed(() => ui.recipePayload)

// 多天完整食谱按天分组折叠；单餐/单天退化为扁平 meals（MealCardBlock.openSlotRecipe 仍传 meals）
const groups = computed(() => {
  const p = payload.value
  if (!p) return []
  const days = Array.isArray(p.days) && p.days.length ? p.days : null
  if (days) {
    return days.map((d) => ({
      kind: 'day',
      head: {
        weekday: d.weekday || '',
        date: d.date || '',
        is_today: Boolean(d.is_today),
        kcal: d.kcal == null ? null : d.kcal
      },
      meals: Array.isArray(d.meals) ? d.meals : []
    }))
  }
  return [{ kind: 'flat', meals: Array.isArray(p.meals) ? p.meals : [] }]
})

const dayCount = computed(() => groups.value.filter((g) => g.kind === 'day').length)

const openDays = ref([])
const allOpen = computed(() => dayCount.value > 0 && openDays.value.length === dayCount.value)

function isOpen(gi) {
  return openDays.value.includes(gi)
}

function toggleDay(gi) {
  const i = openDays.value.indexOf(gi)
  if (i >= 0) openDays.value.splice(i, 1)
  else openDays.value.push(gi)
}

function toggleAllDays() {
  openDays.value = allOpen.value
    ? []
    : groups.value.map((g, i) => (g.kind === 'day' ? i : -1)).filter((i) => i >= 0)
}

// 每次打开（新 payload）重置为「默认展开今天，无今天则第一天」
watch(
  () => payload.value,
  () => {
    const idxs = groups.value.map((g, i) => (g.kind === 'day' ? i : -1)).filter((i) => i >= 0)
    if (!idxs.length) {
      openDays.value = []
      return
    }
    const todayIdx = idxs.find((i) => groups.value[i].head.is_today)
    openDays.value = [todayIdx != null ? todayIdx : idxs[0]]
  }
)
</script>

<style scoped>
.rm-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}

/* 折叠日内的餐次区加内边距（全局 .plan-day-body 无 padding） */
.plan-day-body {
  padding: 12px 14px 0;
}

.rm-empty {
  font-size: 12.5px;
  color: var(--text-sub);
}
</style>
