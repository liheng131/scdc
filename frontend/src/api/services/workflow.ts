import apiClient, { type ApiResponse } from '../client';

export interface WorkflowStartRequest {
  topic: string;
  max_items?: number;
}

export interface ConversationMessage {
  role: string;
  content: string;
}

export interface FollowUpRequest {
  message: string;
  conversation_history?: ConversationMessage[];
}

export interface WorkflowStartResponse {
  workflow_id: string;
  topic: string;
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
};