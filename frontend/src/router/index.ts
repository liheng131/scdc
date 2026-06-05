/**
 * Vue Router 路由配置
 *
 * 定义前端页面路由结构。
 *
 * 路由设计：
 * - 所有路由公开访问，无登录守卫
 * - 登录态由 Pinia store（useAuthStore）持有
 * - 受限页面（如 /workflow、/settings）由各 View 内部根据 auth.isAuthenticated
 *   渲染"请登录"占位卡片，由 AuthModal 触发登录
 *
 * 为什么使用动态 import (() => import(...)):
 * - 实现路由级代码分割，Vite 自动将每个 view 打包为独立 chunk
 * - 首屏只加载当前路由所需代码，减少 bundle 体积
 *
 * 为什么使用嵌套路由 (children):
 * - / 路径下的页面共享 MainLayout 布局（顶栏 + 账户菜单）
 * - 路由切换只需替换 RouterView 内部组件，不重渲染布局
 */

import { createRouter, createWebHistory } from 'vue-router';

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      component: () => import('../components/layout/MainLayout.vue'),
      children: [
        {
          path: '',
          name: 'dashboard',
          component: () => import('../views/HomeView.vue'),
          meta: { title: '仪表盘 Dashboard' },
        },
        {
          path: 'workflow',
          name: 'workflow',
          component: () => import('../views/WorkflowView.vue'),
          meta: { title: '智能体工作流 Workflow' },
        },
        {
          path: 'data-sources',
          redirect: '/workflow',
        },
        {
          path: 'tasks',
          redirect: '/workflow',
        },
        {
          path: 'reports',
          name: 'reports',
          component: () => import('../views/ReportsView.vue'),
          meta: { title: '智能报告 Reports' },
        },
        {
          path: 'settings',
          name: 'settings',
          component: () => import('../views/SettingsView.vue'),
          meta: { title: '系统设置 Settings' },
        },
      ],
    },
  ],
});

export default router;
