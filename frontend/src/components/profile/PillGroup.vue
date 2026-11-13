<template>
  <div class="pill-row">
    <button
      v-for="opt in options"
      :key="opt"
      type="button"
      class="pill"
      :class="{ on: modelValue.includes(opt), off: !modelValue.includes(opt) }"
      @click="toggle(opt)"
    >
      {{ opt }}
    </button>

    <template v-if="allowCustom">
      <input
        v-if="adding"
        ref="inputEl"
        v-model="draft"
        class="pill-input"
        placeholder="回车确认"
        @keydown.enter.prevent="confirmCustom"
        @blur="confirmCustom"
      />
      <button v-else type="button" class="pill-add" @click="startAdd">＋ 自定义</button>
    </template>
  </div>
</template>

<script setup>
import { nextTick, ref } from 'vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  options: { type: Array, default: () => [] },
  allowCustom: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue'])

const adding = ref(false)
const draft = ref('')
const inputEl = ref(null)

function toggle(opt) {
  const list = [...props.modelValue]
  const NONE = '无'
  if (opt === NONE) {
    emit('update:modelValue', list.includes(NONE) ? [] : [NONE])
    return
  }
  const idx = list.indexOf(opt)
  if (idx >= 0) list.splice(idx, 1)
  else list.push(opt)
  emit('update:modelValue', list.filter((x) => x !== NONE))
}

function startAdd() {
  adding.value = true
  nextTick(() => inputEl.value && inputEl.value.focus())
}

function confirmCustom() {
  const v = draft.value.trim()
  if (v && !props.modelValue.includes(v)) emit('update:modelValue', [...props.modelValue.filter((x) => x !== '无'), v])
  draft.value = ''
  adding.value = false
}
</script>
