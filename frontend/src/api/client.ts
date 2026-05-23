/**
 * Axios HTTP 客户端（单例）
 *
 * 封装统一的 HTTP 请求/响应处理，是整个前端 API 层的核心基础设施。
 *
 * 为什么使用拦截器：
 * - 请求拦截器：自动注入 JWT Token 到 Authorization 头，无需每个 API 手动添加
 * - 响应拦截器：统一处理业务错误码（code !== 0）和 HTTP 状态码（401/403 等），
 *   避免每个页面都写重复的错误处理
 *
 * 为什么 401 时直接 window.location.href 而不用 router.push：
 * - 需要清除所有状态并重新加载应用，router.push 无法清除内存中的 Pinia 状态
 * - 硬刷新确保 Vue 实例完全重建，不会有残留的状态污染
 *
 * 为什么超时设为 30 秒：
 * - AI 流水线任务（特别是 LLM 调用）可能耗时较长
 * - 但也不能无限等待，30 秒是 HTTP 场景的经验平衡值
 */

import axios, { AxiosError, type InternalAxiosRequestConfig, type AxiosResponse } from 'axios';
import { ElMessage } from 'element-plus';

export interface ApiResponse<T = any> {
  code: number;
  data: T;
  msg: string;
}

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('token');
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error: AxiosError) => {
    return Promise.reject(error);
  }
);

apiClient.interceptors.response.use(
  (response: AxiosResponse<ApiResponse>) => {
    const res = response.data;
    if (res && res.code !== undefined && res.code !== 0) {
      ElMessage.error(res.msg || '系统请求处理失败');
      return Promise.reject(new Error(res.msg || 'Error'));
    }
    return response;
  },
  (error: AxiosError<any>) => {
    if (error.response) {
      const status = error.response.status;
      const msg = error.response.data?.detail || error.response.data?.msg || error.message;
      if (status === 401) {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        ElMessage.error('登录凭证已过期或未授权，请重新登录');
        if (window.location.pathname !== '/login') {
          window.location.href = '/login';
        }
      } else if (status === 403) {
        ElMessage.error('没有权限执行该操作');
      } else {
        ElMessage.error(`请求失败 (${status}): ${msg}`);
      }
    } else {
      ElMessage.error('网络连接失败或服务器无响应');
    }
    return Promise.reject(error);
  }
);

export default apiClient;
