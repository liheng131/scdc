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
    const res = await apiClient.post('/api/v1/auth/login', params, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
    return res.data;
  },

  getCurrentUser: async (): Promise<ApiResponse<UserInfo>> => {
    const res = await apiClient.get('/api/v1/auth/me');
    return res.data;
  },
};
