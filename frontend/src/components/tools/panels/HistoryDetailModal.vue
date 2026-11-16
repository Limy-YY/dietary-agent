<template>
  <el-dialog
    v-model="visible"
    :title="payload?.title || '历史方案'"
    width="720px"
    top="6vh"
    append-to-body
    class="history-detail-modal"
  >
    <div v-if="payload" class="hd">
      <div class="hd-head">
        <div class="hd-kv">
          <div class="kv-row"><span class="kv-k">周期</span><span class="kv-v">{{ payload.range_text }}</span></div>
          <div class="kv-row"><span class="kv-k">健康目标</span><span class="kv-v">{{ payload.goal_label || '—' }}</span></div>
          <div class="kv-row"><span class="kv-k">状态</span><span class="kv-v">{{ payload.is_executed ? '已执行' : '未执行' }}</span></div>
        </div>
      </div>

      <div class="hd-section-title">
        🍽️ 食谱概览
        <span v-if="dailyAvg !== null" class="hd-avg">{{ payload.days.length > 1 ? '日均约 ' : '全天约 ' }}{{ dailyAvg }} kcal</span>
      </div>
      <div v-for="(day, di) in payload.days" :key="di" class="hd-day">
        <div class="hd-day-head">{{ day.weekday }} · {{ day.date }}<span>{{ fmtKcal(day.kcal) }} kcal</span></div>
        <div class="meal-overview-wrap">
          <table class="meal-table">
            <tbody>
              <tr v-for="(s, si) in day.slots" :key="si">
                <td class="mt-meal">{{ s.label }}</td>
                <td class="mt-dish">{{ s.dish_text || '—' }}</td>
                <td class="mt-kcal"><span class="num">{{ fmtKcal(s.kcal) }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="hd-toggle-row">
        <div class="hd-section-title" style="margin: 0">👩‍🍳 详细食谱</div>
        <button class="hd-toggle-btn" @click="showDetail = !showDetail">{{ showDetail ? '收起做法' : '展开做法' }}</button>
      </div>
      <div v-if="showDetail">
        <div v-for="(day, di) in payload.days" :key="'dish-' + di" class="hd-day">
          <div class="hd-day-head">{{ day.weekday }} · {{ day.date }}</div>
          <div v-for="(s, si) in day.slots" :key="si" class="hd-slot-group">
            <div class="hd-slot-head">{{ s.label }} {{ s.time }}</div>
            <div v-for="(dish, fi) in s.dishes" :key="fi" class="hd-dish">
              <div class="hd-dish-head">
                <span class="hd-dish-name">{{ dish.name }}</span>
                <span v-if="dish.amount && dish.amount !== '—'" class="hd-dish-amount">{{ dish.amount }}</span>
                <span v-if="dish.tip" class="hd-dish-method">{{ dish.tip }}</span>
              </div>
              <div v-if="dish.ingredients && dish.ingredients.length" class="hd-dish-ing">食材：{{ dish.ingredients.join('；') }}</div>
            </div>
          </div>
        </div>
      </div>

      <div class="hd-section-title">📊 营养复盘</div>
      <div v-if="reportLoading" class="hd-note">正在加载营养复盘…</div>
      <div v-else-if="report"><ReportBlock :block="reportBlock" /></div>
      <div v-else class="hd-note">这份方案还没有营养复盘报告，可在对话里对我说「帮我生成一份膳食报告」。</div>
    </div>

    <template #footer>
      <el-button :loading="regenerating" @click="regenerate">照这个思路再排一次</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchReport } from '@/api/nutrition.js'
import { regeneratePlan } from '@/api/mealPlan.js'
import { fmtKcal } from '@/utils/schema.js'
import { useUi } from '@/composables/useUi.js'
import { usePanelStore } from '@/stores/panel.js'
import ReportBlock from '@/components/renderer/blocks/ReportBlock.vue'

const ui = useUi()
const panel = usePanelStore()

const visible = computed({
  get: () => ui.historyOpen,
  set: (v) => (ui.historyOpen = v)
})

const payload = computed(() => ui.historyPayload)

const report = ref(null)
const reportLoading = ref(false)
const regenerating = ref(false)
const showDetail = ref(false)

const reportBlock = computed(() => (report.value ? { ...report.value, expanded: true } : null))

const dailyAvg = computed(() => {
  const vals = (payload.value?.days || [])
    .map((d) => d.kcal)
    .filter((v) => v !== null && v !== undefined && Number.isFinite(Number(v)))
  if (!vals.length) return null
  return Math.round(vals.reduce((s, v) => s + Number(v), 0) / vals.length)
})

async function loadReport() {
  const id = payload.value?.plan_id
  if (!id) {
    report.value = null
    return
  }
  reportLoading.value = true
  try {
    report.value = await fetchReport({ mealPlanId: id })
  } catch (e) {
    report.value = null
  } finally {
    reportLoading.value = false
  }
}

async function regenerate() {
  const id = payload.value?.plan_id
  if (!id) return
  regenerating.value = true
  try {
    await regeneratePlan(id)
    ElMessage.success('已按这个思路排了新方案')
    panel.bump()
    visible.value = false
  } catch (e) {
    ElMessage.error(e.message || '再排失败')
  } finally {
    regenerating.value = false
  }
}

watch(visible, (v) => {
  if (v) loadReport()
  else report.value = null
})
</script>

<style scoped>
.hd {
  max-height: 68vh;
  overflow-y: auto;
}

.hd-head {
  padding: 12px 14px;
  background: var(--bg-soft, #fafafa);
  border-radius: 10px;
  margin-bottom: 6px;
}

.hd-kv {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
  font-size: 13px;
}

.kv-row {
  display: flex;
  gap: 8px;
}

.kv-k {
  color: var(--text-sub);
}

.kv-v {
  font-weight: 600;
  color: var(--text-main, #333);
}

.hd-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-main);
  margin: 18px 0 10px;
}

.hd-avg {
  font-weight: 400;
  font-size: 12px;
  color: var(--text-sub);
  margin-left: 6px;
}

.hd-day {
  margin-bottom: 12px;
}

.hd-day-head {
  display: flex;
  justify-content: space-between;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--brand-hover);
  margin-bottom: 6px;
  padding-right: 76px; /* 与 .meal-table 的 mt-kcal 热量列（76px）左缘对齐 */
}

.hd-day-head span {
  font-weight: 400;
  color: var(--text-sub);
}

.hd-toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 18px 0 10px;
  padding-right: 76px; /* 「展开做法」与热量列左缘对齐，而不是贴死弹窗右缘 */
}

.hd-toggle-btn {
  font-size: 12px;
  color: var(--brand);
  cursor: pointer;
  border: none;
  background: none;
  padding: 0;
}

.hd-toggle-btn:hover {
  color: var(--brand-hover);
}

.hd-slot-group {
  margin-bottom: 10px;
}

.hd-slot-head {
  font-size: 12px;
  font-weight: 600;
  color: var(--brand-hover);
  margin-bottom: 6px;
  padding-left: 8px;
  border-left: 3px solid var(--brand);
}

.hd-dish {
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--bg-subtle, #f7f8f6);
  margin-bottom: 6px;
}

.hd-dish-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.hd-dish-name {
  font-size: 13px;
  font-weight: 600;
}

.hd-dish-amount {
  font-size: 12px;
  color: var(--text-sub);
}

.hd-dish-method {
  font-size: 11px;
  color: var(--brand-hover);
  background: var(--brand-light, #eef4f0);
  padding: 0 6px;
  border-radius: 4px;
}

.hd-dish-ing {
  font-size: 12px;
  color: var(--text-sub);
  line-height: 1.7;
  margin-top: 4px;
}

.hd-note {
  font-size: 12.5px;
  color: var(--text-sub);
  line-height: 1.7;
  padding: 10px 12px;
  background: var(--bg-soft, #fafafa);
  border-radius: 8px;
}
</style>
