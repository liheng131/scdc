<script setup lang="ts">
/**
 * 根组件
 *
 * 为什么使用 el-container 布局：
 * - Element Plus 的 Container 组件自带 flex 布局语义，header/main/footer 层级清晰
 * - 高度自动占满视口，无需手动计算 CSS 高度
 *
 * 为什么 RouterView 不加条件渲染：
 * - 路由守卫（router.beforeEach）在路由层统一处理登录态判断
 * - 根组件保持简洁，不干预业务逻辑
 */
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
