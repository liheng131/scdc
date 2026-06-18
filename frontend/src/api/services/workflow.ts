import apiClient, { type ApiResponse } from '../client';

export interface WorkflowStartRequest {
  topic: string;
  max_items?: number;
  attachment_ids?: string[];
}

export interface ConversationMessage {
  role: string;
  content: string;
}

export interface FollowUpRequest {
  message: string;
  conversation_history?: ConversationMessage[];
  // 历史追问聚合 spec: 追问时携带父工作流 ID,用于在 DB 中建立父子关联
  parent_workflow_id?: string;
}

export interface WorkflowStartResponse {
  workflow_id: string;
  topic: string;
  intent_type?: string;
  target_stage?: string;
  user_feedback?: string;
}

export interface FollowUpResponse {
  workflow_id: string;
}

export interface WorkflowStatusResponse {
  workflow_id: string;
  topic: string;
  status: string;
  current_stage: string;
  stages: Record<string, any>;
  result: any;
  error?: string;
}

export const workflowApi = {
  start: async (data: WorkflowStartRequest): Promise<ApiResponse<WorkflowStartResponse>> => {
    const res = await apiClient.post('/api/v1/workflow/start', data);
    return res.data;
  },

  getStreamUrl: (workflowId: string): string => {
    const token = localStorage.getItem('token') || '';
    return `/api/v1/workflow/${workflowId}/stream?token=${encodeURIComponent(token)}`;
  },

  followUp: async (data: FollowUpRequest): Promise<ApiResponse<FollowUpResponse>> => {
    const res = await apiClient.post('/api/v1/workflow/follow-up', data);
    return res.data;
  },

  getFollowUpStreamUrl: (workflowId: string): string => {
    const token = localStorage.getItem('token') || '';
    return `/api/v1/workflow/${workflowId}/stream?token=${encodeURIComponent(token)}`;
  },

  getStatus: async (workflowId: string): Promise<ApiResponse<WorkflowStatusResponse>> => {
    const res = await apiClient.get(`/api/v1/workflow/${workflowId}`);
    return res.data;
  },

  getHistory: async (): Promise<ApiResponse<any[]>> => {
    const res = await apiClient.get('/api/v1/workflow/history/list');
    return res.data;
  },

  updateWorkflowStatus: async (workflowId: string, status: string): Promise<ApiResponse<any>> => {
    const res = await apiClient.patch(`/api/v1/workflow/${workflowId}/status`, { status });
    return res.data;
  },

  deleteWorkflow: async (workflowId: string): Promise<ApiResponse<any>> => {
    const res = await apiClient.delete(`/api/v1/workflow/${workflowId}`);
    return res.data;
  },

  stopWorkflow: async (workflowId: string): Promise<ApiResponse<any>> => {
    // 防止发送 pending_ 占位符 ID 到后端
    if (workflowId.startsWith('pending_')) {
      console.warn('[stopWorkflow] Skipping stop API call for pending workflow ID:', workflowId);
      return { code: 200, data: { workflow_id: workflowId }, message: 'Skipped pending workflow' };
    }
    const res = await apiClient.post(`/api/v1/workflow/${workflowId}/stop`);
    return res.data;
  },
};