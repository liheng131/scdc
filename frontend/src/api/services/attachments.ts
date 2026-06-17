/**
 * 附件 API 服务
 *
 * 封装附件的查询、批量获取和删除接口。
 */
import apiClient, { type ApiResponse } from '../client';

export interface AttachmentChunk {
  index: number;
  content: string;
  metadata?: Record<string, any>;
}

export interface Attachment {
  id: string;
  filename: string;
  file_type: string;
  file_size: number;
  file_hash: string;
  parsed_content?: string;
  parsed_chunks?: AttachmentChunk[];
  metadata?: Record<string, any>;
  created_at: string;
  updated_at?: string;
}

export const attachmentsApi = {
  list: async (limit = 50, skip = 0): Promise<ApiResponse<Attachment[]>> => {
    const res = await apiClient.get(`/api/v1/attachments?limit=${limit}&skip=${skip}`);
    return res.data;
  },

  get: async (id: string): Promise<ApiResponse<Attachment>> => {
    const res = await apiClient.get(`/api/v1/attachments/${id}`);
    return res.data;
  },

  delete: async (id: string): Promise<ApiResponse<any>> => {
    const res = await apiClient.delete(`/api/v1/attachments/${id}`);
    return res.data;
  },

  batchGet: async (ids: string[]): Promise<ApiResponse<Attachment[]>> => {
    const res = await apiClient.post('/api/v1/attachments/batch', { ids });
    return res.data;
  },
};
