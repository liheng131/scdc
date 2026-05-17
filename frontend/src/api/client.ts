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
