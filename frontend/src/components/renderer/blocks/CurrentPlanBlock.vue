<template>
  <div class="recipe-card">
    <div class="card-head">
      <div>
        <h3>📋 {{ plan ? plan.title : '当前规划' }}</h3>
        <p class="card-sub">
          {{ plan ? plan.range_text : '暂无进行中的规划' }}
          <span v-if="plan && plan.status"> · {{ plan.status === 'fixed' ? '已生效' : '待确认' }}</span>
        </p>
      </div>
      <div v-if="plan" class="status-tag" :class="plan.status === 'fixed' ? 'fixed' : 'draft'">
        {{ plan.status === 'fixed' ? '已生效' : '待确认' }}
      </div>
    </div>

    <!-- 多天：按天折叠（与 MealCardBlock 一周视图一致） -->
    <div v-if="plan && plan.days.length > 1" class="cp-days">
      <div class="cp-days-toolbar">
        <button class="expand-all-btn" @click="toggleAllDays">{{ allOpen ? '全部收起' : '全部展开' }}</button>
      </div>
      <div v-for="(day, di) in plan.days" :key="day.iso + di" class="week-day" :class="{ open: isOpen(di) }">
        <div class="week-day-head" @click="toggleDay(di)">
          <div class="wd-date">
            <div class="wd-day">
              {{ day.weekday }}
              <span v-if="day.is_today" class="wp-today">今天</span>
            </div>
            <div class="wd-num">{{ day.date }}</div>
          </div>
          <div class="wd-kcal">{{ fmtKcal(day.kcal) }} kcal</div>
          <span class="wd-chevron">▾</span>
        </div>
        <div class="week-day-body">
          <div v-for="(s, si) in day.slots" :key="si" class="cp-slot">
            <span class="cp-slot-label">{{ s.label }} {{ s.time }}</span>
            <span class="cp-slot-dish">{{ s.dish_text || '—' }}</span>
            <span class="cp-slot-kcal">{{ fmtKcal(s.kcal) }} kcal</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 单天：平铺（无折叠意义） -->
    <div v-else-if="plan && plan.days.length" class="cp-single">
      <div v-for="(day, di) in plan.days" :key="day.iso + di" class="cp-day">
        <div class="cp-day-head">
          <span>{{ day.weekday }} · {{ day.date }}</span>
          <span class="cp-day-kcal">{{ fmtKcal(day.kcal) }} kcal</span>
        </div>
        <div v-for="(s, si) in day.slots" :key="si" class="cp-slot">
          <span class="cp-slot-label">{{ s.label }} {{ s.time }}</span>
          <span class="cp-slot-dish">{{ s.dish_text || '—' }}</span>
          <span class="cp-slot-kcal">{{ fmtKcal(s.kcal) }} kcal</span>
        </div>
      </div>
    </div>
    <div v-else class="cp-empty">还没有生效的方案。先让我配一份，确认后这里就会显示。</div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { fmtKcal } from '@/utils/schema.js'

const props = defineProps({ block: { type: Object, required: true } })
const plan = computed(() => props.block.plan || null)

// 多天时按天折叠：默认展开「今天」（无今天则第一天），支持同时展开多天
const openDays = ref([])

const allOpen = computed(() => {
  const n = plan.value?.days?.length || 0
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
  const days = plan.value?.days || []
  openDays.value = allOpen.value ? [] : days.map((_, i) => i)
}

// 新方案（不同 plan_id）重置展开态；同一方案内的内容更新（固定/换候选）不重置，保留浏览位置
watch(
  () => plan.value?.plan_id,
  () => {
    const days = plan.value?.days || []
    const todayIdx = days.findIndex((d) => d.is_today)
    openDays.value = days.length ? [todayIdx >= 0 ? todayIdx : 0] : []
  },
  { immediate: true }
)
</script>

<style scoped>
/* 多天折叠列表：贴边，与 MealCardBlock 的 week-list 对齐 */
.cp-days-toolbar {
  display: flex;
  justify-content: flex-end;
  padding: 10px 20px 2px;
}

.cp-single {
  padding: 8px 20px 14px;
}

.cp-day {
  margin-bottom: 12px;
}
.cp-day-head {
  display: flex;
  justify-content: space-between;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--brand-hover);
  margin-bottom: 6px;
}
.cp-day-kcal {
  font-weight: 400;
  color: var(--text-sub);
}
.cp-slot {
  display: flex;
  align-items: baseline;
  gap: 10px;
  font-size: 13px;
  padding: 5px 0;
  border-bottom: 1px dashed var(--border-soft, #eee);
}
.cp-slot-label {
  flex: none;
  color: var(--text-sub);
  width: 82px;
}
.cp-slot-dish {
  flex: 1;
  min-width: 0;
}
.cp-slot-kcal {
  flex: none;
  color: var(--text-sub);
  font-size: 12px;
}
.cp-empty {
  padding: 14px 20px 16px;
  font-size: 13px;
  color: var(--text-sub);
}
</style>
