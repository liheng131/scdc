import apiClient, { type ApiResponse } from '../client';

export interface ReportInfo {
  id: number;
  task_id: number;
  title: string;
  version: string;
  status: string;
  summary?: string;
  content_markdown?: string;
  created_at: string;
  updated_at: string;
}

export const reportsApi = {
  getReports: async (params?: { task_id?: number; q?: string; skip?: number; limit?: number }): Promise<ApiResponse<ReportInfo[]>> => {
    const res = await apiClient.get('/api/v1/reports', { params });
    return res.data;
  },

  getReportDetail: async (id: number): Promise<ApiResponse<ReportInfo>> => {
    const res = await apiClient.get(`/api/v1/reports/${id}`);
    return res.data;
  },

  updateReport: async (id: number, data: Partial<ReportInfo>): Promise<ApiResponse<ReportInfo>> => {
    const res = await apiClient.put(`/api/v1/reports/${id}`, data);
    return res.data;
  },

  exportReportUrl: (id: number, fmt: string = 'docx'): string => {
    const token = localStorage.getItem('token') || '';
    const base = import.meta.env.VITE_API_BASE_URL || '';
    return `${base}/api/v1/reports/${id}/export?fmt=${fmt}&token=${token}`;
  },
};
