<template>
  <div class="recipe-card">
    <div class="card-head">
      <div>
        <h3>{{ block.title || '详细食谱' }}</h3>
        <p class="card-sub">{{ block.subtitle || '用量按你的身高体重估算' }}</p>
      </div>
      <button class="dish-toggle-btn" @click="openModal">全屏查看</button>
    </div>

    <div style="padding: 14px 20px 18px">
      <div v-for="(meal, mi) in meals" :key="mi" class="dish-card">
        <div class="dc-head">
          <span class="dc-meal">{{ meal.label }}{{ meal.time ? ' · ' + meal.time : '' }}</span>
          <h4>{{ meal.title || '本餐菜品' }}</h4>
        </div>
        <div class="dc-body">
          <div v-for="(dish, di) in meal.dishes" :key="di" style="margin-bottom: 10px">
            <div style="display: flex; align-items: baseline; gap: 8px">
              <span style="font-weight: 600; font-size: 13px">{{ dish.name }}</span>
              <span style="font-size: 12px; color: var(--text-sub)">{{ dish.amount }}</span>
              <span v-if="dish.kcal" style="margin-left: auto; font-size: 12px; color: var(--text-sub)">{{ dish.kcal }} kcal</span>
            </div>
            <div style="font-size: 12.5px; color: var(--text-sub); line-height: 1.7">
              {{ dish.tip || '少油少盐，按家常做法烹饪即可。' }}
            </div>
          </div>
          <div v-if="!meal.dishes.length" style="font-size: 12.5px; color: var(--text-sub)">这一餐暂无菜品明细</div>
        </div>
      </div>
      <div v-if="!meals.length" style="font-size: 13px; color: var(--text-sub)">暂无食谱明细</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { arr, pick } from '@/utils/schema.js'
import { useUi } from '@/composables/useUi.js'

const props = defineProps({ block: { type: Object, required: true } })
const ui = useUi()

const meals = computed(() =>
  arr(pick(props.block, 'meals', 'slots', 'recipes')).map((m) => ({
    label: pick(m, 'label', 'meal_type', 'name') || '本餐',
    time: pick(m, 'time') || '',
    title: pick(m, 'dish_text', 'title') || '',
    kcal: Number(pick(m, 'kcal')) || 0,
    dishes: arr(pick(m, 'dishes', 'items')).map((d) => ({
      name: pick(d, 'name') || '菜品',
      amount: pick(d, 'amount', 'portion') || '',
      kcal: pick(d, 'kcal') || '',
      tip: pick(d, 'tip', 'note') || ''
    }))
  }))
)

function openModal() {
  ui.recipePayload = { title: props.block.title || '详细食谱', meals: meals.value }
  ui.recipeOpen = true
}
</script>
