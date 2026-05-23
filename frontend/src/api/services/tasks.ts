/**
 * 任务 API 服务
 *
 * 封装分析任务的 CRUD 和执行接口。
 *
 * 接口说明：
 * - getTasks: 分页查询任务列表，支持按 type/status 筛选
 * - createTask: 创建新任务（name/type/trigger_mode/input_data）
 * - getTaskDetail: 查询任务详情（含 runs 关联数据）
 * - triggerTask: 手动触发任务执行，调用后端 OrchestratorAgent 流水线
 */
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
