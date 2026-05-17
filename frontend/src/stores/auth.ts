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
