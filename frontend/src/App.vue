<script setup lang="ts">
import { RouterView } from 'vue-router';
</script>

<template>
  <div class="app-container">
    <el-container>
      <el-header class="app-header">
        <h2>市场洞察 AI 智能体系统 (SCDC)</h2>
      </el-header>
      <el-main>
        <RouterView />
      </el-main>
    </el-container>
  </div>
</template>

<style>
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
}
.app-header {
  background-color: #409eff;
  color: white;
  display: flex;
  align-items: center;
}
</style>
