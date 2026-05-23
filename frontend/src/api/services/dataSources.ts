/**
 * 数据源 API 服务
 *
 * 封装数据源的 CRUD 和手动同步接口。
 *
 * 接口说明：
 * - getDataSources: 分页查询数据源列表，支持按 source_type/status 筛选
 * - createDataSource: 创建新数据源（name/source_type/config）
 * - updateDataSource: 更新数据源配置
 * - deleteDataSource: 删除数据源
 * - syncDataSource: 手动触发数据源同步，返回收集记录数
 */
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

  syncDataSource: async (id: number): Promise<ApiResponse<{ status: string; records_collected: number; error?: string }>> => {
    const res = await apiClient.post(`/api/v1/data-sources/${id}/sync`);
    return res.data;
  },
};

export interface CollectedRecordInfo {
  id: number;
  data_source_id: number;
  title: string;
  url: string | null;
  content: string | null;
  source_type: string;
  created_at: string;
  updated_at: string;
}

export const collectedRecordsApi = {
  listRecords: async (dataSourceId: number, params?: { skip?: number; limit?: number }): Promise<ApiResponse<CollectedRecordInfo[]>> => {
    const res = await apiClient.get(`/api/v1/data-sources/${dataSourceId}/records`, { params });
    return res.data;
  },

  createRecord: async (dataSourceId: number, data: { title: string; url?: string; content?: string; source_type?: string }): Promise<ApiResponse<CollectedRecordInfo>> => {
    const res = await apiClient.post(`/api/v1/data-sources/${dataSourceId}/records`, data);
    return res.data;
  },

  updateRecord: async (dataSourceId: number, recordId: number, data: { title?: string; url?: string; content?: string; source_type?: string }): Promise<ApiResponse<CollectedRecordInfo>> => {
    const res = await apiClient.put(`/api/v1/data-sources/${dataSourceId}/records/${recordId}`, data);
    return res.data;
  },

  deleteRecord: async (dataSourceId: number, recordId: number): Promise<ApiResponse<{ success: boolean }>> => {
    const res = await apiClient.delete(`/api/v1/data-sources/${dataSourceId}/records/${recordId}`);
    return res.data;
  },

  fetchContent: async (dataSourceId: number, recordId: number): Promise<ApiResponse<CollectedRecordInfo>> => {
    const res = await apiClient.post(`/api/v1/data-sources/${dataSourceId}/records/${recordId}/fetch-content`);
    return res.data;
  },
};
