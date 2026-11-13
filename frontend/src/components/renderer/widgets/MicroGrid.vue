<template>
  <div class="micro-grid">
    <div v-for="(item, i) in items" :key="item.name + i" class="micro-item">
      <MicroRing :item="item" :size="44" />
      <div class="micro-name">{{ item.name }}</div>
      <div class="micro-note">{{ item.note }}</div>
    </div>
    <div v-if="!items.length" class="micro-empty">本方案暂未提供微量元素明细</div>
  </div>
</template>

<script setup>
import MicroRing from './MicroRing.vue'

defineProps({ items: { type: Array, default: () => [] } })
</script>

<style scoped>
.micro-empty {
  grid-column: 1 / -1;
  font-size: 12px;
  color: var(--text-sub);
  text-align: center;
  padding: 12px 0;
}
</style>
