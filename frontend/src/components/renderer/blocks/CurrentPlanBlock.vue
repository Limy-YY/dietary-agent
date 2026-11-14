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

    <div v-if="plan && plan.days.length" style="padding: 8px 20px 14px">
      <div v-for="(day, di) in plan.days" :key="day.iso + di" class="cp-day">
        <div class="cp-day-head">
          <span>{{ day.weekday }} · {{ day.date }}</span>
          <span class="cp-day-kcal">{{ fmtNum(day.kcal) }} kcal</span>
        </div>
        <div v-for="(s, si) in day.slots" :key="si" class="cp-slot">
          <span class="cp-slot-label">{{ s.label }} {{ s.time }}</span>
          <span class="cp-slot-dish">{{ s.dish_text || '—' }}</span>
          <span class="cp-slot-kcal">{{ fmtNum(s.kcal) }} kcal</span>
        </div>
      </div>
    </div>
    <div v-else class="cp-empty">还没有生效的方案。先让我配一份，确认后这里就会显示。</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { fmtNum } from '@/utils/schema.js'

const props = defineProps({ block: { type: Object, required: true } })
const plan = computed(() => props.block.plan || null)
</script>

<style scoped>
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
