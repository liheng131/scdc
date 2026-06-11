/**
 * API 层统一导出入口
 *
 * 集中导出所有 API 模块，其他模块只需 import from '../api' 即可使用全部接口。
 *
 * 为什么使用 barrel export：
 * - 减少 import 语句数量，提高可读性
 * - 统一管理 API 的公开接口（changeset 审查）
 */
export { default as apiClient, type ApiResponse } from './client';
export * from './services/auth';
export * from './services/tasks';
export * from './services/reports';
export * from './services/templates';
export * from './services/dataSources';
export { collectedRecordsApi, type CollectedRecordInfo } from './services/dataSources';
export { workflowApi, type WorkflowStartRequest, type WorkflowStartResponse, type WorkflowStatusResponse, type StageConfirmRequest, type StageConfirmResponse, type WorkflowStatusLightweightResponse, type StageName } from './services/workflow';
export { metricsApi, type MetricsData } from './services/metrics';
