import apiClient, { type ApiResponse } from '../client';

export interface TemplateInfo {
  id: number;
  name: string;
  scope: string;
  version: string;
  content: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export const templatesApi = {
  getTemplates: async (params?: { scope?: string; status?: string; skip?: number; limit?: number }): Promise<ApiResponse<TemplateInfo[]>> => {
    const res = await apiClient.get('/api/v1/templates', { params });
    return res.data;
  },

  createTemplate: async (data: Omit<TemplateInfo, 'id' | 'created_at' | 'updated_at'>): Promise<ApiResponse<TemplateInfo>> => {
    const res = await apiClient.post('/api/v1/templates', data);
    return res.data;
  },

  getTemplateDetail: async (id: number): Promise<ApiResponse<TemplateInfo>> => {
    const res = await apiClient.get(`/api/v1/templates/${id}`);
    return res.data;
  },

  renderPreview: async (id: number, variables: Record<string, any>): Promise<ApiResponse<string>> => {
    const res = await apiClient.post(`/api/v1/templates/${id}/render`, variables);
    return res.data;
  },
};
