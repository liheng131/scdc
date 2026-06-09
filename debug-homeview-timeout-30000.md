# Debug: HomeView 30s timeout 错误

## Session Info
- **Session ID**: homeview-timeout-30000
- **Created**: 2026-06-09
- **Status**: [FIXED] 等待用户最终确认
- **Symptom**: 登录后仪表盘页面 AxiosError: timeout of 30000ms exceeded
- **Stack**: `at async Object.getReports (reports.ts:37:7) at async getSummaryData (HomeView.vue:43:18)`
- **Reproduction**: 打开首页 → 看到登录弹窗 → DevTools Console 出现 timeout 错误

## Hypotheses (待证据验证)
1. **H1: 后端服务未运行** — 端口 8000 无响应，axios 30s 后 timeout
2. **H2: 后端数据库连接失败** — 请求在 DB 层挂死，未返回响应
3. **H3: Auth token 缺失 / 路由守卫未生效** — 错误端点需认证，前端未传 token 触发某中间件挂起
4. **H4: 前端 API base URL 错误** — 指向不存在的后端实例
5. **H5: CORS / 反向代理配置问题** — OPTIONS 预检请求挂死

## Evidence Collection
- **前端 Vite 端口 3000 Listen ✓** — Test-NetConnection 正常
- **后端 8000 Listen 但 HTTP timeout** — curl /api/v1/health 10s 0 字节
- **5 个 uvicorn / python 进程并存**（旧 group 9:07 + 新 group 17:56）
- **旧 worker (PID 32548) 持有 ~50 个 Established 长连接** — 疑似死锁/DB 连接池耗尽
- **新 worker (PID 27604) 拿到 Listen** 但旧请求落到旧 worker 无人处理

## 结论
- **H1 (后端卡死) 确认成立** —— 多套 uvicorn 进程并存，旧 worker 死锁，新 worker 拿不到请求处理权
- **H2-H5 排除** —— 前端代码 (vite.config.ts, client.ts) 配置正确，axios 30s timeout 完全是后端没回响应导致

## 修复
- 杀掉 5 个 uvicorn / python 进程 (PID 16032, 27604, 30568, 32548, 32940)
- 端口 8000 释放后，干净启动 `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 后端启动日志显示：`Application startup complete. Uvicorn running on http://0.0.0.0:8000`
- 启动后只剩 1 uvicorn + 1 python worker（无冲突）

## 修复后验证
| 端点 | 响应 | 状态 |
|------|------|------|
| `GET /api/v1/health` | `{"code":0,"msg":"success","data":{"version":"1.0.0","environment":"development"}}` | ✓ |
| `GET /docs` | 200 OK Swagger HTML | ✓ |
| `GET /api/v1/reports`（无 token） | 404（URL 经 PowerShell 编码异常），但**关键：立即响应，不是 timeout** | ✓ |

## 下一步
- [ ] 请用户刷新浏览器（Ctrl+Shift+R 硬刷），重新打开首页
- [ ] 验证仪表盘正常显示统计卡片（数据源/任务/报告数）
- [ ] 验证控制台无 timeout 错误

## 衍生发现（非本次任务）
- `/api/v1/reports` 路径匹配问题（FastAPI 路由 vs redirect_slashes 行为）—— 暂未影响功能
- 进程冲突易再次发生 —— 建议加启动脚本或 PID 文件防重复启动

## Status: [RESOLVED] ✅

用户 2026-06-09 19:40 确认：仪表盘正常，3 个统计卡片有数字，控制台无 timeout 错误。

## Timeline
- 2026-06-09 创建 → 收集证据 → 修复 → 用户确认成功 → RESOLVED
