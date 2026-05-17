import apiClient, { type ApiResponse } from '../client';

export interface TaskInfo {
  id: number;
  name: string;
  type: string;
  trigger_mode: string;
  status: string;
  input_data: Record<string, any>;
  created_by: number;
  created_at: string;
}

export const tasksApi = {
  getTasks: async (params?: { type?: string; status?: string; skip?: number; limit?: number }): Promise<ApiResponse<TaskInfo[]>> => {
    const res = await apiClient.get('/api/v1/tasks', { params });
    return res.data;
  },

  createTask: async (data: { name: string; type: string; trigger_mode?: string; input_data?: Record<string, any> }): Promise<ApiResponse<TaskInfo>> => {
    const res = await apiClient.post('/api/v1/tasks', data);
    return res.data;
  },

  getTaskDetail: async (id: number): Promise<ApiResponse<TaskInfo>> => {
    const res = await apiClient.get(`/api/v1/tasks/${id}`);
    return res.data;
  },

  triggerTask: async (id: number): Promise<ApiResponse<{ run_id: number; status: string }>> => {
    const res = await apiClient.post(`/api/v1/tasks/${id}/run`);
    return res.data;
  },
};
