<template>
  <div class="recipe-card">
    <div class="card-head">
      <div>
        <h3>{{ block.title || '完整食谱' }}</h3>
        <p class="card-sub">{{ block.subtitle || '含用量与做法，按身高体重估算份量' }}</p>
      </div>
      <button class="dish-toggle-btn" @click="openRecipe">展开成弹窗</button>
    </div>

    <div style="padding: 16px 20px 4px">
      <div v-for="(day, di) in days" :key="day.date + di" style="margin-bottom: 14px">
        <div v-if="days.length > 1" class="plan-detail-day-title">
          <span>第 {{ di + 1 }} 天 · {{ day.weekday }}</span>
          <span class="pdd-kcal">{{ day.date }} · 全天 {{ day.kcal }} kcal</span>
        </div>

        <div class="meal-overview-wrap">
          <table class="meal-table">
            <thead>
              <tr>
                <th class="mt-meal">餐次</th>
                <th class="mt-dish">菜品</th>
                <th class="mt-kcal">热量</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(slot, si) in day.slots" :key="si">
                <td class="mt-meal">{{ slot.label }}</td>
                <td class="mt-dish">{{ slot.dish_text }}</td>
                <td class="mt-kcal">
                  <span class="num">{{ slot.kcal }}</span><span class="unit">kcal</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="dish-section-head">
          <div class="dish-section-title">🍳 详细食谱</div>
          <button class="dish-toggle-btn" @click="toggleDish(di)">
            {{ openDish[di] ? '收起做法' : '看做法' }}
          </button>
        </div>

        <div v-show="openDish[di]">
          <div v-for="(slot, si) in day.slots" :key="'d' + si">
            <div v-for="(dish, di2) in slot.dishes" :key="di2" class="dish-card">
              <div class="dc-head">
                <span class="dc-meal">{{ slot.label }}</span>
                <h4>{{ dish.name }}</h4>
              </div>
              <div class="dc-body">
                <div class="dc-ingredients">
                  <strong>用量：</strong>{{ dish.amount || '适量' }}
                  <span v-if="dish.kcal"> · {{ dish.kcal }} kcal</span>
                  <span v-if="slot.oil_g || slot.salt_g"> · 油约 {{ slot.oil_g || 0 }} g / 盐约 {{ slot.salt_g || 0 }} g</span>
                </div>
                <div style="font-size: 13px; font-weight: 600; margin-bottom: 6px">做法：</div>
                <ol class="dc-steps">
                  <li v-for="(step, si2) in stepsOf(dish)" :key="si2">{{ step }}</li>
                </ol>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="!days.length" class="empty-inline">这个方案没有可展示的餐次数据。</div>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive } from 'vue'
import { arr, normalizeSlot } from '@/utils/schema.js'
import { useUi } from '@/composables/useUi.js'

const props = defineProps({ block: { type: Object, required: true } })
const ui = useUi()
const openDish = reactive({})

const days = computed(() =>
  arr(props.block.days).map((d) => ({
    date: d.date || '',
    weekday: d.weekday || '',
    kcal: Number(d.kcal) || 0,
    slots: arr(d.slots || d.meals).map(normalizeSlot)
  }))
)

function stepsOf(dish) {
  if (arr(dish.steps).length) return dish.steps
  if (dish.tip) return [dish.tip, '按个人口味调整盐和油，别久煮。']
  return ['按家常做法烹饪，控制油盐用量即可。']
}

function toggleDish(i) {
  openDish[i] = !openDish[i]
}

function openRecipe() {
  ui.recipePayload = {
    title: props.block.title || '完整食谱',
    meals: days.value.flatMap((d) =>
      d.slots.map((s) => ({ label: d.weekday ? `${d.weekday} ${s.label}` : s.label, time: s.time, kcal: s.kcal, dishes: s.dishes }))
    )
  }
  ui.recipeOpen = true
}
</script>

<style scoped>
.plan-detail-day-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--brand-hover);
  margin: 4px 0 8px;
}

.pdd-kcal {
  margin-left: auto;
  font-weight: 400;
  font-size: 12px;
  color: var(--text-sub);
}

.empty-inline {
  font-size: 13px;
  color: var(--text-sub);
  padding: 8px 0 12px;
}
</style>
