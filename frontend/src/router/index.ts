/**
 * Vue Router 路由配置
 *
 * 定义前端页面路由结构和导航守卫逻辑。
 *
 * 路由设计：
 * - /login: 公开路由，不校验登录态
 * - / 及其子路由（dashboard/data-sources/tasks/reports/templates/settings）: 需要登录
 *
 * 为什么使用动态 import (() => import(...)):
 * - 实现路由级代码分割，Vite 自动将每个 view 打包为独立 chunk
 * - 首屏只加载当前路由所需代码，减少 bundle 体积
 *
 * 为什么使用嵌套路由 (children):
 * - / 路径下的页面共享 MainLayout 布局（侧边栏 + 顶栏）
 * - 路由切换只需替换 RouterView 内部组件，不重渲染布局
 *
 * beforeEach 导航守卫作用：
 * - 未登录访问受保护路由 → 重定向到 /login 并携带 redirect 参数
 * - 已登录访问 /login → 重定向到 Dashboard
 */

import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '../stores/auth';

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { title: '系统登录', requiresAuth: false },
    },
    {
      path: '/',
      component: () => import('../components/layout/MainLayout.vue'),
      meta: { requiresAuth: true },
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
          path: 'templates',
          name: 'templates',
          component: () => import('../views/TemplatesView.vue'),
          meta: { title: '大纲模板管理 Templates' },
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

router.beforeEach((to, _from, next) => {
  const authStore = useAuthStore();
  if (to.meta.requiresAuth !== false && !authStore.isAuthenticated) {
    next({ name: 'login', query: { redirect: to.fullPath } });
  } else if (to.name === 'login' && authStore.isAuthenticated) {
    next({ name: 'dashboard' });
  } else {
    next();
  }
});

export default router;
