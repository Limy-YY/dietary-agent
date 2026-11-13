<template>
  <div class="welcome-screen">
    <div class="ws-logo"><img :src="logo" alt="膳宝" /></div>
    <div class="ws-title">今天想吃点什么？</div>
    <div class="ws-sub">说说你的想法，或者直接选一个下面的事开始。</div>
    <div class="ws-chips">
      <button class="ws-chip" @click="$emit('pick', '生成一日三餐')">安排今天三餐</button>
      <button class="ws-chip" @click="$emit('pick', '生成一周食谱')">排一周食谱</button>
      <button class="ws-chip" @click="$emit('pick', '推荐一餐搭配')">推荐一餐</button>
      <button class="ws-chip" @click="$emit('pick', '生成周膳食报告')">看本周报告</button>
    </div>
  </div>
</template>

<script setup>
import logo from '@/assets/logo.jpg'

defineEmits(['pick'])
</script>
