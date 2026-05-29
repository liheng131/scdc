import apiClient, { type ApiResponse } from '../client';

export interface RuntimeSettings {
  llm_provider: string;
  llm_api_key: string;
  llm_base_url: string;
  default_model: string;
  temperature: number;
  max_tokens: number;
}

export interface LlmHealthResult {
  status: string;
  provider: string;
  base_url: string;
  models?: string[];
  error?: string;
}

export interface AiModelConfig {
  id: number;
  provider: string;
  model_name: string;
  model_type: string;
  base_url: string;
  api_key: string;
  is_default: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface AiModelCreate {
  provider: string;
  model_name: string;
  model_type: string;
  base_url: string;
  api_key: string;
}

export interface AiModelUpdate {
  provider?: string;
  model_name?: string;
  model_type?: string;
  base_url?: string;
  api_key?: string;
}

export interface AiModelTestResult {
  status: string;
  models?: string[];
  error?: string;
}

export const settingsApi = {
  getSettings: async (): Promise<ApiResponse<RuntimeSettings>> => {
    const res = await apiClient.get('/api/v1/settings');
    return res.data;
  },

  updateSettings: async (data: Partial<RuntimeSettings>): Promise<ApiResponse<RuntimeSettings>> => {
    const res = await apiClient.put('/api/v1/settings', data);
    return res.data;
  },

  checkLlmHealth: async (): Promise<ApiResponse<LlmHealthResult>> => {
    const res = await apiClient.get('/api/v1/settings/llm-health');
    return res.data;
  },

  listAiModels: async (modelType?: string): Promise<ApiResponse<AiModelConfig[]>> => {
    const res = await apiClient.get('/api/v1/settings/ai-models', { params: modelType ? { model_type: modelType } : {} });
    return res.data;
  },

  createAiModel: async (data: AiModelCreate): Promise<ApiResponse<AiModelConfig>> => {
    const res = await apiClient.post('/api/v1/settings/ai-models', data);
    return res.data;
  },

  updateAiModel: async (id: number, data: AiModelUpdate): Promise<ApiResponse<AiModelConfig>> => {
    const res = await apiClient.put(`/api/v1/settings/ai-models/${id}`, data);
    return res.data;
  },

  deleteAiModel: async (id: number): Promise<ApiResponse<any>> => {
    const res = await apiClient.delete(`/api/v1/settings/ai-models/${id}`);
    return res.data;
  },

  setDefaultAiModel: async (id: number): Promise<ApiResponse<any>> => {
    const res = await apiClient.post(`/api/v1/settings/ai-models/${id}/set-default`);
    return res.data;
  },

  testAiModel: async (id: number): Promise<ApiResponse<AiModelTestResult>> => {
    const res = await apiClient.post(`/api/v1/settings/ai-models/${id}/test`);
    return res.data;
  },
};