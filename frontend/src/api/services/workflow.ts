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
  // Phase 2: 阶段状态机
  stage_state?: 'running' | 'awaiting_confirmation' | 'completed' | 'failed';
  stage_output?: any | null;
  stage_history?: any[] | null;
}

// Phase 2: Human-in-the-Loop 阶段确认
export interface StageConfirmRequest {
  decision: 'accept' | 'reject';
  user_edits?: {
    extra_urls?: string[];
    extra_keywords?: string[];
  } | null;
  user_feedback?: string | null;
}

export interface StageConfirmResponse {
  workflow_id: string;
  stage: string;
  stage_state: string;
  next_stage: string | null;
  sse_url: string | null;
  stage_history_length: number;
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

  // Phase 2: 数据采集阶段单独 SSE 流 URL
  getCollectingStreamUrl: (workflowId: string): string => {
    const token = localStorage.getItem('token') || '';
    return `/api/v1/workflow/${workflowId}/stream-collecting?token=${encodeURIComponent(token)}`;
  },

  // Phase 2: 阶段确认
  confirmStage: async (
    workflowId: string,
    body: StageConfirmRequest
  ): Promise<ApiResponse<StageConfirmResponse>> => {
    const res = await apiClient.post(`/api/v1/workflow/${workflowId}/confirm`, body);
    return res.data;
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

  reentryStream: async (workflowId: string, target_stage: string, user_feedback: string): Promise<Response> => {
    const token = localStorage.getItem('token') || '';
    const url = `/api/v1/workflow/${workflowId}/reentry?token=${encodeURIComponent(token)}`;
    return fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({ target_stage, user_feedback }),
    });
  },
};