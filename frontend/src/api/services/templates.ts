/**
 * 模板 API 服务
 *
 * 封装 Jinja2 模板的 CRUD 和沙箱渲染接口。
 *
 * renderPreview 说明：
 * - 发送模板 ID 和变量 JSON 到后端，后端用 Jinja2 渲染并返回结果
 * - 用户可在线测试模板效果后再保存，降低草稿错误率
 */
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
