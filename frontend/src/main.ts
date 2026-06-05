/**
 * Vue 应用入口文件
 *
 * 负责初始化 Vue 实例并挂载全局插件：
 * - Pinia（状态管理，替代 Vuex）
 * - Vue Router（路由管理）
 * - Element Plus（UI 组件库）
 *
 * 为什么选择 Pinia 而不是 Vuex：
 * - Pinia 是 Vue 3 官方推荐的状态管理方案，TypeScript 支持更好
 * - 组合式 API 风格与 Vue 3 Composition API 一致，降低心智负担
 *
 * 为什么选择 Element Plus：
 * - 国内使用广泛的 Vue 3 UI 框架，企业级组件丰富
 * - 与 Element UI（Vue 2 版）API 兼容，迁移成本低
 */

import { createApp } from 'vue';
import { createPinia } from 'pinia';
import ElementPlus from 'element-plus';
import 'element-plus/dist/index.css';
import './styles/variables.css';
import App from './App.vue';
import router from './router';
import i18n from './i18n';
import { usePreferencesStore } from './stores/preferences';
import { useAuthStore } from './stores/auth';

const app = createApp(App);

app.use(createPinia());
app.use(router);
app.use(ElementPlus);
app.use(i18n);

// 应用挂载前初始化用户偏好（语言 / 主题），避免首屏闪回 fallback
const preferencesStore = usePreferencesStore();
preferencesStore.init();

// 应用初始化时验证本地存储的token是否有效
// 只在localStorage中存在token时才调用，避免不必要的请求
if (localStorage.getItem('token')) {
  const authStore = useAuthStore();
  // 异步验证，不阻断应用启动
  authStore.fetchCurrentUser().catch(() => {
    // fetchCurrentUser 内部已处理失败情况（清除无效token）
    // 这里静默捕获，避免未处理的 Promise rejection
  });
}

app.mount('#app');
