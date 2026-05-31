import apiClient, { type ApiResponse } from '../client';

export interface MetricsData {
  total_requests: number;
  requests_per_second: number;
  latency_ms_p50: number;
  latency_ms_p95: number;
  error_rate: number;
  status_codes: Record<string, number>;
  endpoint_latency: Array<{ endpoint: string; avg_ms: number }>;
  cpu_percent: number;
  memory_percent: number;
  health_score: number;
}

export const metricsApi = {
  getMetrics: async (): Promise<ApiResponse<MetricsData>> => {
    const res = await apiClient.get('/api/v1/metrics-json/json');
    return res.data;
  },
};