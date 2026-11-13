<template>
  <div class="block-wrap">
    <component v-if="comp" :is="comp" :block="block" @phrase="(p) => $emit('phrase', p)" />
    <FallbackBlock v-else :block="block" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import MealCardBlock from './blocks/MealCardBlock.vue'
import MealPlanBlock from './blocks/MealPlanBlock.vue'
import NutritionBlock from './blocks/NutritionBlock.vue'
import ReportBlock from './blocks/ReportBlock.vue'
import SourcesBlock from './blocks/SourcesBlock.vue'
import MedicalHintBlock from './blocks/MedicalHintBlock.vue'
import AnchorBlock from './blocks/AnchorBlock.vue'
import RecipeDetailBlock from './blocks/RecipeDetailBlock.vue'
import ShoppingBlock from './blocks/ShoppingBlock.vue'
import FallbackBlock from './blocks/FallbackBlock.vue'

const props = defineProps({ block: { type: Object, required: true } })
defineEmits(['phrase'])

/**
 * 前端渲染注册表：Agent 只会下发 type，前端自己决定长什么样。
 * 未知 type 一律交给 FallbackBlock，原样展示不崩。
 */
const REGISTRY = {
  meal_card: MealCardBlock,
  meal_plan: MealPlanBlock,
  recipe_detail: RecipeDetailBlock,
  shopping_list: ShoppingBlock,
  nutrition: NutritionBlock,
  report: ReportBlock,
  sources: SourcesBlock,
  medical_hint: MedicalHintBlock,
  anchor: AnchorBlock
}

const comp = computed(() => REGISTRY[props.block.type] || null)
</script>
