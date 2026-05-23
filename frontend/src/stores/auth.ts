/**
 * 认证状态管理（Pinia Store）
 *
 * 管理用户登录态、Token 持久化、用户信息缓存。
 *
 * 为什么 Token 存储在 localStorage：
 * - 页面刷新后 Token 不会丢失，避免每次刷新都需重新登录
 * - localStorage 数据在各标签页间共享，适合单用户场景
 * - 注意：Token 不应存储 secret/敏感业务数据，仅存放认证凭证
 *
 * 为什么使用 Pinia 的 Composition API 风格（defineStore + setup）：
 * - 与 Vue 3 Composition API 语法一致，方便组件中直接使用 ref/reactive
 * - 相比 Options API 风格更灵活，可自由组合逻辑
 *
 * login() 流程：
 * 1. 调用 authApi.login() 获取 access_token 和 user 信息
 * 2. 更新 Store 状态并持久化到 localStorage
 *
 * fetchCurrentUser()：
 * - 应用初始化时调用，验证 Token 有效性并获取最新用户信息
 * - Token 失效时自动登出
 */

import { defineStore } from 'pinia';
import { ref } from 'vue';
import { authApi, type UserInfo } from '../api';

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(localStorage.getItem('token') || '');
  const user = ref<UserInfo | null>(
    localStorage.getItem('user') ? JSON.parse(localStorage.getItem('user')!) : null
  );
  const isAuthenticated = ref<boolean>(!!token.value);

  const login = async (credentials: Record<string, string>) => {
    const data = await authApi.login(credentials);
    if (data.data && data.data.access_token) {
      token.value = data.data.access_token;
      user.value = data.data.user;
      isAuthenticated.value = true;
      localStorage.setItem('token', token.value);
      localStorage.setItem('user', JSON.stringify(user.value));
    }
  };

  const logout = () => {
    token.value = '';
    user.value = null;
    isAuthenticated.value = false;
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    if (window.location.pathname !== '/login') {
      window.location.href = '/login';
    }
  };

  const fetchCurrentUser = async () => {
    if (!token.value) return;
    try {
      const res = await authApi.getCurrentUser();
      user.value = res.data;
      localStorage.setItem('user', JSON.stringify(user.value));
    } catch {
      logout();
    }
  };

  return { token, user, isAuthenticated, login, logout, fetchCurrentUser };
});
