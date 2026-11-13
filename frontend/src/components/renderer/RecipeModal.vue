<template>
  <el-dialog
    v-model="visible"
    :title="payload?.title || '详细食谱'"
    width="680px"
    append-to-body
    class="recipe-modal"
  >
    <div v-if="payload">
      <div v-for="(meal, mi) in meals" :key="mi" class="rm-meal">
        <div class="rm-meal-head">
          <span class="rm-meal-label" :style="{ borderColor: colorOf(meal) }">{{ meal.label }}</span>
          <span v-if="meal.time" class="rm-meal-time">{{ meal.time }}</span>
          <span class="rm-meal-kcal">{{ meal.kcal }} kcal</span>
        </div>
        <div v-for="(dish, di) in meal.dishes" :key="di" class="rm-dish">
          <div class="rm-dish-row">
            <span class="rm-dish-name">{{ dish.name }}</span>
            <span class="rm-dish-amount">{{ dish.amount }}</span>
            <span v-if="dish.kcal" class="rm-dish-kcal">{{ dish.kcal }} kcal</span>
          </div>
          <div v-if="dish.tip" class="rm-dish-tip">{{ dish.tip }}</div>
        </div>
        <div v-if="!meal.dishes.length" class="rm-dish-tip">暂无菜品明细</div>
      </div>
      <div v-if="!meals.length" class="rm-dish-tip">暂无食谱明细，可以先让膳宝生成一餐。</div>
    </div>
    <div class="modal-note">份量按档案估算；做法只保留要点，按自家口味调油盐即可。</div>
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'
import { useUi } from '@/composables/useUi.js'

const ui = useUi()

const visible = computed({
  get: () => ui.recipeOpen,
  set: (v) => (ui.recipeOpen = v)
})

const payload = computed(() => ui.recipePayload)
const meals = computed(() => (payload.value && Array.isArray(payload.value.meals) ? payload.value.meals : []))

const MEAL_COLORS = { 早餐: '#e8942c', 午餐: '#4a7c59', 晚餐: '#3b7fd4' }

function colorOf(meal) {
  const key = String(meal.label || '').replace(/^\S+\s*/, '')
  return MEAL_COLORS[key] || MEAL_COLORS[String(meal.label || '').trim()] || '#4a7c59'
}
</script>

<style scoped>
.rm-meal {
  margin-bottom: 16px;
}

.rm-meal-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 8px;
}

.rm-meal-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--brand-hover);
  border-left: 3px solid var(--brand);
  padding-left: 8px;
}

.rm-meal-time {
  font-size: 12px;
  color: var(--text-sub);
}

.rm-meal-kcal {
  margin-left: auto;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-main);
}

.rm-dish {
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--bg-subtle, #f7f8f6);
  margin-bottom: 6px;
}

.rm-dish-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.rm-dish-name {
  font-size: 13px;
  font-weight: 600;
}

.rm-dish-amount {
  font-size: 12px;
  color: var(--text-sub);
}

.rm-dish-kcal {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-sub);
}

.rm-dish-tip {
  font-size: 12.5px;
  color: var(--text-sub);
  line-height: 1.7;
  margin-top: 2px;
}
</style>
