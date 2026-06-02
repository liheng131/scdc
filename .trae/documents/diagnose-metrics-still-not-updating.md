# 仪表盘指标不变问题 — 根因诊断与修复计划

## 当前状态

1. ✅ 代码已修复并推送到 GitHub（提交 `aa4ed69`）
2. ❌ 但后端服务仍在运行**旧版本代码**，未重启
3. 证据：CPU/内存有值（psutil），但 QPS/P95/错误率全是 0（Prometheus 指标）

## 问题根因

后端进程自代码推送后**未重启**，加载的仍是旧版 `metrics.py`，其中的 Counter 和 Histogram 匹配 bug 导致所有 Prometheus 指标始终为 0。

### 旧代码 bug 回顾

| Bug | 旧代码 | 结果 |
|-----|-------|------|
| Counter 匹配 | `metric.name == "http_requests_total"` 遍历 metric_family 对象而非 sample | 永远返回 0 |
| Histogram 分位数 | `sample.labels.get('quantile')` 查找 `0.5`/`0.95` | Instrumentator 默认不存储 quantile label，永远返回 0 |

### 为什么 CPU/内存有值？

`psutil.cpu_percent()` 和 `psutil.virtual_memory()` 是直接系统调用，不依赖 Prometheus REGISTRY，所以不受旧代码 bug 影响。

## 诊断方案

已添加两个诊断端点到 [metrics.py](file:///c:/Users/U0015856/Documents/trae_projects/scdc/backend/app/api/routes/metrics.py)：

### 1. `/api/v1/metrics-json/ping` — 代码版本检测

```json
{"status": "ok", "timestamp": 1234567890, "version": "v2"}
```

如果返回 `v2` → 新代码在运行。如果返回其他或 404 → 仍是旧代码。

### 2. `/api/v1/metrics-json/debug` — Prometheus 原始样本查看

返回所有 HTTP 相关的 Prometheus 样本（name、labels、value），可以直接看到 `http_requests_total` 是否有非零值。

## 实施步骤

### Step 1: 用户重启后端服务

用户需要在本地重启后端服务（`uvicorn app.main:app --reload` 或对应启动命令）。

### Step 2: 验证新代码已运行

访问 `http://localhost:8000/api/v1/metrics-json/ping`，确认返回 `version: "v2"`。

### Step 3: 验证指标有变化

- 打开仪表盘页面
- 触发几个 API 请求（如点击报告列表刷新按钮）
- 观察 QPS 和 P95 延迟卡片是否有非零值
- 等待 10 秒后观察趋势图是否出现数据

### Step 4: 如果仍有问题，使用 debug 端点排查

访问 `http://localhost:8000/api/v1/metrics-json/debug`，查看：
- `http_requests_total` 样本是否存在且 value > 0
- `http_request_duration_seconds_count` 样本是否存在且 value > 0
- `http_request_duration_seconds_bucket` 样本的 le 标签和累积值

## 注意事项

- 此问题与代码逻辑无关，纯粹是服务未重启导致
- 修复代码已推送到 GitHub，重启后即可生效
- 前端代码无需修改
