# 修复导出接口认证失败

## Why
导出报告的 API 端点 `/api/v1/reports/{report_id}/export` 使用 `get_current_active_user` 作为认证依赖，该依赖仅从 `Authorization: Bearer <token>` 请求头中提取 token。但前端通过 `window.open()` 在新标签页中打开下载链接，只能将 token 附加到 URL 查询参数中（如 `?token=xxx`），无法设置请求头，导致导出接口返回 401 Unauthorized。

## What Changes
- **修改** `backend/app/api/routes/reports.py` 的 `export_report` 端点，将认证依赖从 `get_current_active_user` 改为 `get_current_active_user_sse`（支持从查询参数 `?token=xxx` 读取令牌）

## Impact
- 受影响代码：`backend/app/api/routes/reports.py`
- 受影响能力：报告导出 API 认证方式（从仅 Header 改为 Header + Query 参数双兼容）

## MODIFIED Requirements
### Requirement: 报告导出认证
导出报告端点 `GET /api/v1/reports/{report_id}/export` 的认证方式 SHALL 同时支持：
- `Authorization: Bearer <token>` 请求头（传统方式）
- `?token=<token>` 查询参数（用于浏览器新标签页直接下载）

#### Scenario: 前端通过 URL 参数导出
- **WHEN** 前端在新标签页打开 `GET /api/v1/reports/2/export?fmt=pdf&token=xxx`
- **THEN** 服务端从查询参数解析 token，认证成功，返回文件流（不再返回 401）

#### Scenario: 通过请求头导出
- **WHEN** 客户端通过 `Authorization: Bearer <token>` 请求头调用导出接口
- **THEN** 服务端正常解析 token 并返回文件流
