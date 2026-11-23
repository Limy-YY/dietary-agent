<template>
  <!-- Element Plus 按需引入后，中文文案（确认/取消等）由根级 ConfigProvider 统一提供 -->
  <el-config-provider :locale="zhCn">
    <router-view />
  </el-config-provider>
</template>

<script setup>
import zhCn from 'element-plus/es/locale/lang/zh-cn'
</script>
