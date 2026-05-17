<script setup lang="ts">
defineProps<{
  msg: string
}>();
</script>

<template>
  <div class="hello">
    <h1>{{ msg }}</h1>
    <p>单机 All-in-One 市场洞察智能体平台前端已成功初始化。</p>
  </div>
</template>

<style scoped>
h1 {
  color: #303133;
}
</style>
