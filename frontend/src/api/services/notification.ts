import apiClient, { type ApiResponse } from '../client';

export interface NotificationRule {
  id: number;
  name: string;
  channel: string;
  trigger: string;
  target: string;
  enabled: boolean;
}

export interface NotificationRuleCreate {
  name: string;
  channel: string;
  trigger: string;
  target: string;
  enabled?: boolean;
}

export interface NotificationRuleUpdate {
  name?: string;
  channel?: string;
  trigger?: string;
  target?: string;
  enabled?: boolean;
}

export interface ReportPushRequest {
  report_id: number;
  target_email?: string;
  format?: string;
}

export const notificationApi = {
  listRules: async (enabled_only?: boolean): Promise<ApiResponse<NotificationRule[]>> => {
    const params = enabled_only !== undefined ? { enabled_only } : {};
    const res = await apiClient.get('/api/v1/notifications/rules', { params });
    return res.data;
  },

  createRule: async (rule: NotificationRuleCreate): Promise<ApiResponse<NotificationRule>> => {
    const res = await apiClient.post('/api/v1/notifications/rules', rule);
    return res.data;
  },

  updateRule: async (rule_id: number, rule: NotificationRuleUpdate): Promise<ApiResponse<NotificationRule>> => {
    const res = await apiClient.put(`/api/v1/notifications/rules/${rule_id}`, rule);
    return res.data;
  },

  deleteRule: async (rule_id: number): Promise<ApiResponse<any>> => {
    const res = await apiClient.delete(`/api/v1/notifications/rules/${rule_id}`);
    return res.data;
  },

  pushReport: async (req: ReportPushRequest): Promise<ApiResponse<any>> => {
    const endpoint = req.target_email ? '/api/v1/notifications/push' : '/api/v1/notifications/push-all';
    const res = await apiClient.post(endpoint, req);
    return res.data;
  },

  pushReportToAll: async (report_id: number, format?: string): Promise<ApiResponse<any>> => {
    const body: ReportPushRequest = { report_id };
    if (format !== undefined) {
      body.format = format;
    }
    const res = await apiClient.post('/api/v1/notifications/push-all', body);
    return res.data;
  },

  testNotification: async (trigger: string, title: string, content: string): Promise<ApiResponse<any>> => {
    const res = await apiClient.post('/api/v1/notifications/test', { trigger, title, content });
    return res.data;
  },
};
