<script setup lang="ts">
/**
 * 示例组件
 *
 * Vue 3 + Vite 脚手架自带的基础展示组件，
 * 用于验证前端项目初始化成功，不承载业务功能。
 *
 * 可安全删除或在基础上扩展为其他业务组件。
 */
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
