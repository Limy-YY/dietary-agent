<template>
  <el-dialog
    v-model="visible"
    :title="title"
    width="800px"
    append-to-body
    class="report-detail-modal"
  >
    <ReportBlock v-if="report" :block="report" />
    <div v-else class="rm-tip">这份报告找不到了，重新生成一份吧。</div>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'
import { useUi } from '@/composables/useUi.js'
import { normalizeReport } from '@/utils/schema.js'
import ReportBlock from '@/components/renderer/blocks/ReportBlock.vue'

const ui = useUi()

const visible = computed({
  get: () => ui.reportOpen,
  set: (v) => (ui.reportOpen = v)
})

// 报告存档详情：复用 ReportBlock，默认展开
const report = computed(() => {
  const raw = ui.reportPayload
  if (!raw) return null
  return { ...normalizeReport(raw), expanded: true }
})

const title = computed(() => report.value?.headline || '膳食报告')
</script>

<style scoped>
.report-detail-modal :deep(.el-dialog__body) {
  padding-top: 8px;
}

.rm-tip {
  padding: 20px 0;
  color: var(--text-sub);
  font-size: 13px;
  text-align: center;
}
</style>
