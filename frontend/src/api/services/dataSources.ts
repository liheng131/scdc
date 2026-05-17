import apiClient, { type ApiResponse } from '../client';

export interface DataSourceInfo {
  id: number;
  name: string;
  source_type: string;
  config: Record<string, any>;
  status: string;
  created_at: string;
}

export const dataSourcesApi = {
  getDataSources: async (params?: { source_type?: string; status?: string; skip?: number; limit?: number }): Promise<ApiResponse<DataSourceInfo[]>> => {
    const res = await apiClient.get('/api/v1/data-sources', { params });
    return res.data;
  },

  createDataSource: async (data: { name: string; source_type: string; config: Record<string, any> }): Promise<ApiResponse<DataSourceInfo>> => {
    const res = await apiClient.post('/api/v1/data-sources', data);
    return res.data;
  },

  updateDataSource: async (id: number, data: Partial<DataSourceInfo>): Promise<ApiResponse<DataSourceInfo>> => {
    const res = await apiClient.put(`/api/v1/data-sources/${id}`, data);
    return res.data;
  },

  deleteDataSource: async (id: number): Promise<ApiResponse<{ success: boolean }>> => {
    const res = await apiClient.delete(`/api/v1/data-sources/${id}`);
    return res.data;
  },

  syncDataSource: async (id: number): Promise<ApiResponse<{ status: string; records_collected: number }>> => {
    const res = await apiClient.post(`/api/v1/data-sources/${id}/sync`);
    return res.data;
  },
};
