<template>
  <div>
    <div v-if="loading" class="sk-wrap">
      <div class="skeleton sk-line" style="width: 65%"></div>
      <div class="skeleton" style="height: 90px; margin-bottom: 10px"></div>
      <div class="skeleton sk-line" style="width: 80%"></div>
    </div>

    <template v-else-if="report">
      <div class="data-timestamp">🕒 生成于 {{ generatedText }} · 报告口径：当前方案（plan）</div>

      <div class="rp-insights" style="margin-top: 0">
        <h5>{{ report.headline }}</h5>
        <div style="font-size: 12.5px; color: var(--text-sub); line-height: 1.8">
          {{ report.meta.range_text }}
          <span v-if="report.completeness.known_meal_count != null"> · 已知 {{ fmtNum(report.completeness.known_meal_count) }} 餐</span>
          <span v-if="report.completeness.meal_count != null"> · 共 {{ fmtNum(report.completeness.meal_count) }} 餐</span>
        </div>
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
                  <span class="rp-legend-name">{{ seg.name }} {{ seg.percent === null ? '—' : seg.percent + '%' }}</span>
                </div>
                <div class="rp-legend-desc">{{ seg.desc }}</div>
              </div>
            </div>
          </div>
        </div>
        <div class="rp-extra">
          <div v-for="m in report.extra_metrics" :key="m.key" class="rp-extra-item">
            <span class="rp-extra-name">{{ m.name }}</span>
            <span class="rp-extra-val">{{ m.value === null || m.value === undefined ? '—' : m.value + ' ' + m.unit }}</span>
          </div>
        </div>
      </div>

      <div class="rp-section">
        <div class="rp-section-title">🔬 {{ report.micro.title }}</div>
        <div class="rp-micro-grid">
          <div v-for="(m, i) in report.micro.items" :key="i" class="rp-micro">
            <MicroRing :item="m" :size="40" />
            <div class="rp-micro-name">{{ m.name }}</div>
            <div v-if="m.status === 'neutral'" class="rp-micro-tag">提示</div>
          </div>
        </div>
        <p class="rp-micro-note">覆盖度按方案内食材估算；显示「—」表示该项数据不足，不作为 0 处理。</p>
      </div>

      <div v-if="report.insights.length" class="rp-insights">
        <h5>关键结论</h5>
        <ul>
          <li v-for="(t, i) in report.insights" :key="i">{{ t }}</li>
        </ul>
      </div>

      <!-- 数据质量与完整度：常驻，不折叠 -->
      <div class="rp-quality">
        <div class="rp-quality-line">
          <span class="rp-quality-label">数据完整度</span>
          <span>
            共 {{ fmtNum(report.completeness.meal_count) }} 餐 · 已知
            {{ fmtNum(report.completeness.known_meal_count) }} 餐 · 缺失
            {{ fmtNum(report.completeness.missing_meal_count) }} 餐
          </span>
        </div>
        <div v-for="(n, i) in report.data_quality_notes" :key="'q' + i" class="rp-quality-line">
          <span class="rp-quality-label">数据说明</span>
          <span>{{ n }}</span>
        </div>
        <div v-if="report.reference_hints.length" class="rp-quality-line">
          <span class="rp-quality-label">参考口径</span>
          <span>{{ report.reference_hints.join('；') }}</span>
        </div>
      </div>
    </template>

    <template v-else-if="error">
      <EmptyState icon="⚠️" title="加载失败" :desc="error" :actions="[{ label: '重新加载', phrase: 'reload' }]" @action="onAction" />
    </template>

    <template v-else-if="hasPlan">
      <EmptyState
        icon="📄"
        title="这份方案还没生成报告"
        desc="报告会按当前方案复盘宏量供能比、7 项关键微量，
并列出数据完整度与口径说明。"
        :actions="[{ icon: '📊', label: '生成本方案膳食报告', desc: '基于当前方案生成 plan 级报告', phrase: '生成周膳食报告' }]"
        hint="💡 也可以在底部输入框直接对我说：<br><b>“帮我生成一份膳食报告”</b>"
        @action="onAction"
      />
    </template>

    <template v-else>
      <EmptyState
        icon="📄"
        title="暂未生成膳食报告"
        desc="膳食报告以已固定的膳食方案为口径，
先配一份方案，再生成报告。"
        :actions="[{ icon: '🥗', label: '生成一日三餐', desc: '先让智能体为你配餐', phrase: '生成一日三餐' }]"
        hint="💡 报告只支持方案级口径（report_type=plan），不再按周/月切分。"
        @action="onAction"
      />
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { fetchCurrentPlan } from '@/api/mealPlan.js'
import { fetchReport } from '@/api/nutrition.js'
import { normalizeReport } from '@/utils/schema.js'
import { fmtNum } from '@/utils/schema.js'
import { fmtDateTime } from '@/utils/format.js'
import { usePanelStore } from '@/stores/panel.js'
import { useChatStore } from '@/stores/chat.js'
import EmptyState from '@/components/common/EmptyState.vue'
import MacroDonut from '@/components/renderer/widgets/MacroDonut.vue'
import MicroRing from '@/components/renderer/widgets/MicroRing.vue'

const panel = usePanelStore()
const chat = useChatStore()

const loading = ref(false)
const error = ref('')
const report = ref(null)
const hasPlan = ref(false)

const generatedText = computed(() =>
  report.value?.meta.generated_at ? fmtDateTime(report.value.meta.generated_at) : '—'
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const current = await fetchCurrentPlan()
    hasPlan.value = Boolean(current && current.meal_plan_id != null)
    if (!hasPlan.value) {
      report.value = null
      return
    }
    const raw = await fetchReport({ mealPlanId: current.meal_plan_id })
    report.value = raw ? normalizeReport(raw) : null
  } catch (e) {
    error.value = e.message || '报告加载失败'
    report.value = null
  } finally {
    loading.value = false
  }
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

.rp-extra {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--border-soft, #e8e8e8);
}

.rp-extra-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.rp-extra-name {
  font-size: 11.5px;
  color: var(--text-sub);
}

.rp-extra-val {
  font-size: 13px;
  font-weight: 600;
}

.rp-micro-tag {
  margin-top: 2px;
  font-size: 10px;
  padding: 0 4px;
  border-radius: 4px;
  color: var(--text-sub);
  background: var(--bg-soft, #f2f3f5);
}

.rp-micro-note {
  margin-top: 10px;
  font-size: 11.5px;
  color: var(--text-sub);
  line-height: 1.6;
}

.rp-quality {
  margin-top: 12px;
  padding: 10px 12px;
  background: var(--bg-soft, #fafafa);
  border-radius: 8px;
  font-size: 11.5px;
  color: var(--text-sub);
  line-height: 1.7;
}

.rp-quality-line {
  display: flex;
  gap: 8px;
}

.rp-quality-label {
  flex: none;
  color: var(--text-main, #333);
  font-weight: 600;
}
</style>
