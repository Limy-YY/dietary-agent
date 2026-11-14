<template>
  <div class="clarify">
    <div class="clarify-q">{{ question }}</div>
    <div v-if="missingFields.length" class="clarify-actions">
      <span class="clarify-label">还缺：</span>
      <span v-for="f in missingFields" :key="f" class="clarify-tag">{{ fieldLabel(f) }}</span>
      <button class="clarify-fill" @click="goFill">去补录</button>
    </div>
  </div>
</template>

<script setup>
import { useUi } from '@/composables/useUi.js'

const props = defineProps({
  question: { type: String, default: '' },
  missingFields: { type: Array, default: () => [] }
})

const ui = useUi()

/** 缺失字段键 → 中文展示名（仅 UI 文案，不承载业务映射） */
const FIELD_LABELS = {
  gender: '性别',
  age: '年龄',
  height_cm: '身高',
  weight_kg: '体重',
  goal_code: '健康目标',
  cooking_equipment: '烹饪设备',
  conditions: '疾病情况',
  allergies: '过敏原',
  religious_ethical: '宗教伦理'
}

function fieldLabel(key) {
  return FIELD_LABELS[key] || key
}

function goFill() {
  ui.profileHighlight = [...props.missingFields]
  ui.profileMode = 'edit'
  ui.profileOpen = true
}
</script>

<style scoped>
.clarify {
  padding: 12px 14px;
  border-radius: 10px;
  background: #f5f8f6;
  border: 1px solid #dfe9e2;
  max-width: 520px;
}
.clarify-q {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-main, #333);
  white-space: pre-wrap;
}
.clarify-actions {
  margin-top: 10px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.clarify-label {
  font-size: 13px;
  color: var(--text-sub, #666);
}
.clarify-tag {
  font-size: 13px;
  color: #4a7c59;
  background: #e8f0ea;
  border-radius: 999px;
  padding: 2px 10px;
}
.clarify-fill {
  margin-left: auto;
  border: none;
  background: #4a7c59;
  color: #fff;
  font-size: 13px;
  padding: 5px 14px;
  border-radius: 999px;
  cursor: pointer;
}
.clarify-fill:hover {
  background: #3d6849;
}
</style>
