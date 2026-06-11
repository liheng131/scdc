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
 * 为什么 401 时不直接跳转 /login：
 * - 应用已取消独立登录页（见路由重构），登录入口改为顶部"登录/注册"按钮触发的模态
 * - 401 时只清理 store + localStorage，停留在当前页面，由各受限视图自己渲染"请登录"占位
 *   或交由 AuthModal 处理；避免硬刷新导致用户丢失当前工作上下文
 *
 * 为什么超时设为 30 秒：
 * - AI 流水线任务（特别是 LLM 调用）可能耗时较长
 * - 但也不能无限等待，30 秒是 HTTP 场景的经验平衡值
 */

import axios, { AxiosError, type InternalAxiosRequestConfig, type AxiosResponse } from 'axios';
import { ElMessage } from 'element-plus';
import { useAuthStore } from '@/stores/auth';

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
    // 规范化 URL：/api/v1/<resource> → /api/v1/<resource>/
    // 避免 FastAPI redirect_slashes=True 时的重定向丢头
    if (config.url) {
      const match = config.url.match(/^(\/api\/v[0-9]+\/[a-z][a-z0-9-]*)(\?.*)?$/i);
      if (match) {
        config.url = match[1] + '/' + (match[2] || '');
      }
    }
    return config;
  },
  (error: AxiosError) => {
    return Promise.reject(error);
  }
);

/**
 * 401 处理:统一在 401 时清掉 token + logout + 提示。
 *
 * 旧版"保留 token 仅警告"逻辑会导致 stale token 一直挂在 localStorage,
 * 后续每次 API 调用都 401,UI 看到 avatar 仍在但实际啥也干不了。
 *
 * 改进:任何业务 401 一律当作 token 失效处理,让 AuthModal 自然浮现让用户重登。
 */
let last401HandledAt = 0;
function handle401(requestUrl?: string) {
  // 简易防抖:3 秒内多次 401 只处理一次
  const now = Date.now();
  if (now - last401HandledAt < 3000) {
    return;
  }
  last401HandledAt = now;

  console.warn('[401 Auth Error] clearing stale token', {
    url: requestUrl,
    timestamp: new Date().toISOString(),
  });

  // 主动清 token + user
  localStorage.removeItem('token');
  localStorage.removeItem('user');
  try {
    useAuthStore().logout();
  } catch {
    // store 尚未初始化或 pinia 不可用,静默忽略
  }
  ElMessage.error('登录凭证已过期,请重新登录');
}

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
        handle401(error.config?.url);
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
