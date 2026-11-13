<template>
  <div>
    <div v-if="report" class="grocery-filter" style="margin-bottom: 12px">
      <button
        v-for="s in SCOPES"
        :key="s.key"
        class="gf-chip"
        :class="{ on: scope === s.key }"
        @click="switchScope(s.key)"
      >
        {{ s.label }}
      </button>
    </div>

    <div v-if="loading" class="sk-wrap">
      <div class="skeleton sk-line" style="width: 65%"></div>
      <div class="skeleton" style="height: 90px; margin-bottom: 10px"></div>
      <div class="skeleton sk-line" style="width: 80%"></div>
    </div>

    <template v-else-if="report">
      <div class="data-timestamp">🕒 生成于 {{ generatedText }}</div>

      <div class="rp-insights" style="margin-top: 0">
        <h5>{{ report.headline }}</h5>
        <div style="font-size: 12.5px; color: var(--text-sub); line-height: 1.8">
          {{ report.meta.range_start }} ~ {{ report.meta.range_end }}
          <span v-if="report.meta.valid_days"> · 有效 {{ report.meta.valid_days }} 天</span>
          <span v-if="report.meta.total_meals"> · {{ report.meta.total_meals }} 餐</span>
        </div>
        <div style="font-size: 12.5px; line-height: 1.8; margin-top: 4px">{{ report.summary_text }}</div>
      </div>

      <div class="rp-section">
        <div class="rp-section-title">🥗 宏量供能比</div>
        <div class="rp-donut-row">
          <div class="rp-donut">
            <MacroDonut :macro="report.macro" :size="84" :value-size="17" />
          </div>
          <div class="rp-legend">
            <div v-for="(seg, i) in report.macro.segments" :key="i" class="rp-legend-item">
              <span class="rp-legend-dot" :class="seg.color"></span>
              <div class="rp-legend-info">
                <div class="rp-legend-top">
                  <span class="rp-legend-name">{{ seg.name }} {{ seg.percent }}%</span>
                  <span v-if="seg.tag" class="rp-legend-tag" :class="seg.tag_level">{{ seg.tag }}</span>
                </div>
                <div class="rp-legend-desc">{{ seg.desc }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="rp-section">
        <div class="rp-section-title">🔬 {{ report.micro.title }}</div>
        <div class="rp-micro-grid">
          <div v-for="(m, i) in report.micro.items" :key="i" class="rp-micro">
            <MicroRing :item="m" :size="40" />
            <div class="rp-micro-name">{{ m.name }}</div>
          </div>
        </div>
      </div>

      <div v-if="report.daily_trend.length" class="rp-section">
        <div class="rp-section-title">📈 每日热量（{{ report.daily_trend.length }} 天）</div>
        <div class="rp-trend" :style="{ height: trendHeight }">
          <div v-for="(d, i) in report.daily_trend" :key="i" class="rp-bar-wrap" :title="`${d.date} · ${d.calories} kcal`">
            <div class="rp-bar-area">
              <div class="rp-bar" :class="d.status" :style="{ height: barHeight(d) }"></div>
            </div>
            <div class="rp-bar-date">{{ d.show_date ? d.date : '' }}</div>
          </div>
        </div>
      </div>

      <div v-if="report.insights.length" class="rp-insights">
        <h5>关键结论</h5>
        <ul>
          <li v-for="(t, i) in report.insights" :key="i">{{ t }}</li>
        </ul>
      </div>
    </template>

    <template v-else-if="error">
      <EmptyState icon="⚠️" title="加载失败" :desc="error" :actions="[{ label: '重新加载', phrase: 'reload' }]" @action="onAction" />
    </template>

    <template v-else>
      <EmptyState
        icon="📄"
        title="暂未生成膳食报告"
        desc="膳食报告会汇总你一段时间的配餐记录，
分析营养摄入趋势并给出智能建议。"
        :actions="[
          { icon: '📊', label: '生成周膳食报告', desc: '回顾最近 7 天的营养摄入情况', phrase: '生成周膳食报告' },
          { icon: '📈', label: '生成月膳食报告', desc: '查看本月整体饮食趋势与建议', phrase: '生成月膳食报告' }
        ]"
        hint="💡 也可以在底部输入框直接对我说：<br><b>“帮我生成一份周膳食报告”</b> 或 <b>“看看这个月吃得怎么样”</b>"
        @action="onAction"
      />
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { fetchReport } from '@/api/nutrition.js'
import { normalizeReport } from '@/utils/schema.js'
import { fmtDateTime } from '@/utils/format.js'
import { usePanelStore } from '@/stores/panel.js'
import { useChatStore } from '@/stores/chat.js'
import EmptyState from '@/components/common/EmptyState.vue'
import MacroDonut from '@/components/renderer/widgets/MacroDonut.vue'
import MicroRing from '@/components/renderer/widgets/MicroRing.vue'

const SCOPES = [
  { key: 'auto', label: '当前方案' },
  { key: 'week', label: '近 7 天' },
  { key: 'month', label: '本月' }
]

const panel = usePanelStore()
const chat = useChatStore()

const loading = ref(false)
const error = ref('')
const report = ref(null)
const scope = ref('auto')

const generatedText = computed(() => (report.value?.meta.generated_at ? fmtDateTime(report.value.meta.generated_at) : '—'))
const trendHeight = computed(() => (report.value?.daily_trend.length > 10 ? '84px' : '110px'))

const maxCalories = computed(() => {
  const list = (report.value?.daily_trend || []).map((d) => Number(d.calories) || 0)
  return Math.max(...list, 1)
})

function barHeight(d) {
  return `${Math.max(4, Math.round(((Number(d.calories) || 0) / maxCalories.value) * 100))}%`
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const raw = await fetchReport({
      mealPlanId: undefined,
      scope: scope.value === 'auto' ? undefined : scope.value
    })
    report.value = raw ? normalizeReport(raw) : null
  } catch (e) {
    error.value = e.message || '报告加载失败'
    report.value = null
  } finally {
    loading.value = false
  }
}

function switchScope(key) {
  if (scope.value === key) return
  scope.value = key
  load()
}

function onAction(a) {
  if (a.phrase === 'reload') load()
  else chat.send(a.phrase)
}

onMounted(load)
watch(() => panel.revision, load)
watch(() => panel.active, (v) => v === 'report' && load())
</script>

<style scoped>
.sk-wrap {
  padding-top: 4px;
}

.rp-micro-grid :deep(.micro-ring-wrapper) {
  width: 40px;
  height: 40px;
}

.rp-trend {
  height: 110px;
}
</style>
