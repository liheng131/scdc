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
 * 401 处理防抖标志：防止多个并发 401 响应同时触发登出逻辑
 * 当第一个 401 进入后设置为 true，后续 401 直接跳过
 * 3 秒后自动重置，允许下一次独立的 401 事件正常处理
 *
 * 改进：401 不再立即清除 token 和登出，而是：
 * 1. 先检查 localStorage 中是否仍存在有效 token
 * 2. 如果 token 存在，可能是后端临时问题（如数据库连接失败）
 *    只记录错误日志，不清除 token
 * 3. 如果 token 不存在，才是真正的未认证状态
 */
let isHandling401 = false;
let handling401Timer: ReturnType<typeof setTimeout> | null = null;

function handle401(requestUrl?: string) {
  if (isHandling401) {
    return;
  }
  isHandling401 = true;
  if (handling401Timer) {
    clearTimeout(handling401Timer);
  }
  handling401Timer = setTimeout(() => {
    isHandling401 = false;
    handling401Timer = null;
  }, 3000);

  // 详细日志：记录 401 错误发生时的上下文
  const existingToken = localStorage.getItem('token');
  console.warn('[401 Auth Error]', {
    url: requestUrl,
    hasLocalToken: !!existingToken,
    timestamp: new Date().toISOString(),
  });

  // 关键改进：只有当 localStorage 中确实没有 token 时，才是真正的未认证
  // 如果有 token，说明可能是后端认证服务临时问题（如数据库连接失败），不应登出
  if (!existingToken) {
    // 真正的未认证状态：清理残留数据（如有）并提示
    localStorage.removeItem('user');
    ElMessage.error('登录凭证已过期或未授权，请重新登录');
    try {
      useAuthStore().logout();
    } catch {
      // store 尚未初始化或 pinia 不可用，静默忽略
    }
  } else {
    // 有 token 但返回 401：可能是后端认证服务问题
    // 不清除 token，只提示用户，让用户有机会重试
    ElMessage.warning(`认证服务暂时不可用（${requestUrl || 'API'}），请重试或稍后再操作`);
    // 不调用 logout()，保持登录状态
  }
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
