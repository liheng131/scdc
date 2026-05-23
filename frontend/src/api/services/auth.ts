/**
 * 认证 API 服务
 *
 * 封装用户登录和当前用户信息查询接口。
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

export const authApi = {
  login: async (data: Record<string, string>): Promise<ApiResponse<LoginResponse>> => {
    const params = new URLSearchParams();
    for (const key in data) {
      params.append(key, data[key]);
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
};
