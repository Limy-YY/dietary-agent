<template>
  <div>
    <div v-if="loading" class="sk-wrap">
      <div class="skeleton sk-line" style="width: 55%"></div>
      <div class="skeleton sk-line" style="width: 80%"></div>
      <div class="skeleton sk-line" style="width: 40%"></div>
    </div>

    <template v-else-if="plan">
      <div class="data-timestamp">🕒 方案更新于 {{ updatedText }}</div>

      <div class="plan-overview">
        <div class="po-head">
          <div>
            <div class="po-title">{{ plan.title || '当前规划' }}</div>
            <div class="po-target">{{ plan.goal_text || plan.subtitle }}</div>
          </div>
          <span class="type-tag" :class="isFixed ? 'live' : 'archive'">{{ isFixed ? '已生效' : '草稿' }}</span>
        </div>
        <div class="po-cal-compact">
          <span class="num">{{ firstDayKcal }}</span>
          <span class="unit">kcal {{ target ? `/ 目标 ${target}` : '' }}</span>
        </div>
      </div>

      <div
        v-for="(day, di) in plan.days"
        :key="day.date + di"
        class="plan-day"
        :class="{ open: openDay === di }"
      >
        <div class="plan-day-head" @click="openDay = openDay === di ? -1 : di">
          <span class="pd-label">{{ day.is_today ? '今天' : day.weekday }} · {{ day.date }}</span>
          <span class="pd-kcal">{{ day.kcal }} kcal</span>
          <span class="pd-chevron">▾</span>
        </div>
        <div class="plan-day-body">
          <div class="meal-overview-wrap">
            <table class="meal-table">
              <tbody>
                <tr v-for="(slot, si) in day.slots" :key="si">
                  <td class="mt-meal">{{ slot.label }}</td>
                  <td class="mt-dish">{{ slot.dish_text }}</td>
                  <td class="mt-kcal"><span class="num">{{ slot.kcal }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="plan-actions">
        <button class="plan-btn-secondary" @click="openRecipe">看完整食谱</button>
      </div>
    </template>

    <template v-else-if="error">
      <EmptyState icon="⚠️" title="加载失败" :desc="error" :actions="[{ label: '重新加载', phrase: 'reload' }]" @action="onAction" />
    </template>

    <template v-else>
      <EmptyState
        icon="📅"
        title="暂无进行中的规划"
        desc="你还没有确认今天的食谱。
配餐并确认后，可在这里查看详细食谱和成分。"
        :actions="[{ icon: '✨', label: '生成一日三餐', desc: '先让智能体为你配餐并确认', phrase: '生成一日三餐' }]"
        hint="💡 生成食谱后，记得在对话框或卡片中点击 <b>“确认规划”</b>，这里才会更新哦。"
        @action="onAction"
      />
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { fetchCurrentPlan } from '@/api/mealPlan.js'
import { normalizePlan } from '@/utils/schema.js'
import { fmtDateTime } from '@/utils/format.js'
import { usePanelStore } from '@/stores/panel.js'
import { useChatStore } from '@/stores/chat.js'
import { useUi } from '@/composables/useUi.js'
import EmptyState from '@/components/common/EmptyState.vue'

const panel = usePanelStore()
const chat = useChatStore()
const ui = useUi()

const loading = ref(false)
const error = ref('')
const plan = ref(null)
const openDay = ref(0)

const isFixed = computed(() => plan.value?.status === 'fixed')
const target = computed(() => plan.value?.target_kcal || 0)
const firstDayKcal = computed(() => (plan.value?.days?.[0]?.kcal ? plan.value.days[0].kcal : plan.value?.total_kcal || 0))
const updatedText = computed(() => (plan.value?.updated_at ? fmtDateTime(plan.value.updated_at) : '—'))

async function load() {
  loading.value = true
  error.value = ''
  try {
    const raw = await fetchCurrentPlan()
    plan.value = raw ? normalizePlan(raw) : null
    openDay.value = Math.max(0, plan.value?.days?.findIndex((d) => d.is_today) ?? 0)
  } catch (e) {
    error.value = e.message || '方案加载失败'
    plan.value = null
  } finally {
    loading.value = false
  }
}

function send(phrase) {
  chat.send(phrase)
}

function openRecipe() {
  if (!plan.value) return
  ui.recipePayload = {
    title: `${plan.value.title} · 完整食谱`,
    meals: plan.value.days.flatMap((d) =>
      d.slots.map((s) => ({ label: `${d.weekday} ${s.label}`, time: s.time, kcal: s.kcal, dishes: s.dishes }))
    )
  }
  ui.recipeOpen = true
}

function onAction(a) {
  if (a.phrase === 'reload') load()
  else send(a.phrase)
}

onMounted(load)
watch(() => panel.revision, load)
watch(() => panel.active, (v) => v === 'current_plan' && load())
</script>

<style scoped>
.sk-wrap {
  padding-top: 8px;
}
</style>
