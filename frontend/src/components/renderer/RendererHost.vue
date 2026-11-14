<template>
  <div class="block-wrap">
    <component v-if="comp" :is="comp" :block="block" @phrase="(p) => $emit('phrase', p)" />
    <FallbackBlock v-else :block="block" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import MealCardBlock from './blocks/MealCardBlock.vue'
import ReportBlock from './blocks/ReportBlock.vue'
import ShoppingBlock from './blocks/ShoppingBlock.vue'
import CurrentPlanBlock from './blocks/CurrentPlanBlock.vue'
import FallbackBlock from './blocks/FallbackBlock.vue'

const props = defineProps({ block: { type: Object, required: true } })
defineEmits(['phrase'])

/**
 * 前端渲染注册表：Agent 只会下发 type，前端自己决定长什么样。
 * 未知 type 一律交给 FallbackBlock，原样展示不崩。
 */
const REGISTRY = {
  meal_card: MealCardBlock,
  shopping_list: ShoppingBlock,
  current_plan: CurrentPlanBlock,
  nutrition_report: ReportBlock
}

const comp = computed(() => REGISTRY[props.block.type] || null)
</script>
