/**
 * 认证 API 服务
 *
 * 封装用户登录、注册、当前用户信息查询、数学验证接口。
 *
 * 为什么 login 使用 x-www-form-urlencoded 格式：
 * - 后端 FastAPI 的 OAuth2PasswordRequestForm 要求此格式
 * - 相比 JSON 格式，表单格式兼容更多 OAuth2 客户端（如 Swagger UI 的 Authorize 面板）
 */
import apiClient, { type ApiResponse } from '../client';

export interface UserInfo {
  id: number;
  username: string;
  email: string;
  role: string;
  status: string;
  created_at: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: UserInfo;
}

export interface CaptchaResponse {
  token: string;
  question: string;
}

export interface RegisterResponse {
  id: number;
  username: string;
  email: string;
  role: string;
}

export interface RegisterPayload {
  email: string;
  username: string;
  password: string;
  confirm_password: string;
  captcha_token: string;
  captcha_answer: number;
}

export const authApi = {
  /**
   * 登录
   * @param credentials 形参键值对，通常为 { identifier: 'username or email', password: 'xxx' }
   * 后端 OAuth2PasswordRequestForm 仍接收 `username` 字段，因此这里把 identifier 作为 username 提交。
   */
  login: async (credentials: Record<string, string>): Promise<ApiResponse<LoginResponse>> => {
    const params = new URLSearchParams();
    for (const key in credentials) {
      params.append(key, credentials[key]);
    }
    const res = await apiClient.post('/api/v1/auth/login/access-token', params, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
    return res.data;
  },

  getCurrentUser: async (): Promise<ApiResponse<UserInfo>> => {
    const res = await apiClient.get('/api/v1/auth/me');
    return res.data;
  },

  /**
   * 获取数学验证（注册时使用）
   * 服务端返回 5 分钟有效期的 token + 算式
   */
  getCaptcha: async (): Promise<ApiResponse<CaptchaResponse>> => {
    const res = await apiClient.get('/api/v1/auth/captcha');
    return res.data;
  },

  /**
   * 账号注册
   * @param payload 邮箱 / 用户名 / 密码 / 确认密码 / 验证 token / 答案
   * 成功返回 201 + 精简用户信息（不含 token）
   */
  register: async (payload: RegisterPayload): Promise<ApiResponse<RegisterResponse>> => {
    const res = await apiClient.post('/api/v1/auth/register', payload);
    return res.data;
  },

  /**
   * 修改密码
   *
   * 当前为前端 stub：后端接口尚未实现时调用会 reject 一个
   * `NOT_IMPLEMENTED` 错误，调用方（ChangePasswordModal）会捕获并
   * 展示"功能开发中"的友好提示。后续接入真实后端时只需把实现替换为：
   *   const res = await apiClient.post('/api/v1/auth/change-password', payload);
   *   return res.data;
   */
  changePassword: async (
    payload: { current: string; new: string }
  ): Promise<ApiResponse<{ success: boolean; message?: string }>> => {
    return Promise.reject(new Error('NOT_IMPLEMENTED'));
  },
};
