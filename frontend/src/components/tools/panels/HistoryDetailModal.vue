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
          <div class="kv-row"><span class="kv-k">状态</span><span class="kv-v">{{ payload.is_executed ? '已执行' : '未执行' }} · {{ payload.status_label }}</span></div>
        </div>
      </div>

      <div class="hd-section-title">🍽️ 食谱概览</div>
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

      <div class="hd-section-title">📊 营养复盘</div>
      <div v-if="reportLoading" class="hd-note">正在加载营养复盘…</div>
      <div v-else-if="report"><ReportBlock :block="reportBlock" /></div>
      <div v-else class="hd-note">这份方案还没有营养复盘报告，可在对话里对我说「帮我生成一份膳食报告」。</div>
    </div>

    <template #footer>
      <el-button :loading="regenerating" @click="regenerate">照这个思路再排一次</el-button>
      <el-button @click="visible = false">关闭</el-button>
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

const reportBlock = computed(() => (report.value ? { ...report.value, expanded: true } : null))

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
}

.hd-day-head span {
  font-weight: 400;
  color: var(--text-sub);
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
