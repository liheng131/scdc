# 仪表盘指标不变问题修复计划

## 问题根因

后端 `metrics.py` 中的 Prometheus 指标采集存在多个 bug，导致仪表盘指标始终显示 0 或固定值：

### Bug 1：Counter 采样名匹配错误

`prometheus_fastapi_instrumentator` 的 Counter 指标在 `REGISTRY` 中的 sample 名称格式为 `metric_name_total`（例如 `http_requests_total_total`），而代码直接用 `metric.name == "http_requests_total"` 去匹配 `metric` 对象，忽略了样本名后缀。

### Bug 2：Histogram 分位数标签格式不匹配

Instrumentator 的 Histogram 默认不使用 quantile label 存储分位数，而是通过 `bucket` 标签 + `_bucket` 后缀存储累积计数。代码用 `sample.labels.get('quantile')` 去找 `0.5` 和 `0.95`，永远匹配不到。

### Bug 3：RPS 计算首次永远为 0

`_last_sample` 初始 count 为 0，首次请求时 `total_count - 0` 的差值除以 `elapsed` 时间，但如果首次 `total_count` 也为 0（Prometheus 指标未初始化），则 RPS 永远是 0。

### Bug 4：端点延迟过滤条件过严

过滤条件 `handler != "/metrics"` 和 `handler != "/api/v1/metrics"` 可能漏掉实际的 API 路由 handler 名称。

## 修复方案

### 1. 使用 `prometheus_client` 原生 API 替代手动遍历 REGISTRY

改用 `prometheus_client.REGISTRY` 的标准遍历方式，直接解析 `Sample` 对象的 `name` 字段（包含 `_total`, `_bucket` 等后缀），而非通过 `metric.name`。

### 2. Histogram 分位数改用 bucket 近似计算

由于 `prometheus_fastapi_instrumentator` 默认不使用 summary quantiles，改为从 bucket 中计算 P50/P95：
- 找到 `count` 样本值
- 找到包含 count/2 和 count×0.95 的 bucket，取对应的 `le` 上界作为分位数

### 3. RPS 初始化修复

首次采样时 `count` 初始化为当前 `total_count` 而非 0，避免第一次请求差值为 0。

### 4. 调试日志辅助验证

添加 `logger.info` 输出调试信息，方便后续排查。

## 实施步骤

### Step 1：重写 metrics.py 指标采集逻辑

将 `metrics.py` 中的指标采集从手动遍历 `metric.name` 改为直接遍历 `sample.name`：

```python
from prometheus_client import REGISTRY
# ...

def _collect_metric_samples(name_prefix: str):
    """收集指定前缀的所有样本"""
    results = []
    for metric_family in REGISTRY.collect():
        for sample in metric_family.samples:
            if sample.name.startswith(name_prefix):
                results.append(sample)
    return results

def _get_counter_total(name: str, extra_labels: dict = None) -> float:
    """获取 Counter 的 _total 样本值"""
    full_name = f"{name}_total" if not name.endswith("_total") else name
    for sample in REGISTRY.collect():
        for s in sample.samples:
            if s.name == full_name:
                if extra_labels is None or all(
                    s.labels.get(k) == v for k, v in extra_labels.items()
                ):
                    return s.value
    return 0.0

def _get_histogram_quantile_approx(name: str, quantile: float) -> float:
    """从 Histogram bucket 近似计算分位数"""
    count_name = f"{name}_count"
    count_val = 0
    buckets = []
    
    for metric_family in REGISTRY.collect():
        for s in metric_family.samples:
            if s.name == count_name:
                count_val = s.value
            elif s.name == f"{name}_bucket":
                le = s.labels.get("le")
                if le is not None:
                    buckets.append((float(le), s.value))
    
    if count_val <= 0 or not buckets:
        return 0.0
    
    target = count_val * quantile
    buckets.sort()
    for le, cumulative in buckets:
        if cumulative >= target:
            return le
    
    return buckets[-1][0] if buckets else 0.0
```

### Step 2：更新 `get_metrics_json()` 函数

使用新的辅助函数重写端点：

```python
@router.get("/json", response_model=ResponseModel)
async def get_metrics_json():
    global _last_sample
    
    # 确保首次初始化
    if _last_sample["count"] == 0 and _last_sample["time"] == 0:
        # 初始化时记录当前 count，避免首次 RPS 为 0
        initial_count = sum(
            _get_counter_total("http_requests_total", {"method": m})
            for m in ["GET", "POST", "PUT", "DELETE"]
        )
        _last_sample = {"time": time.time(), "count": initial_count}
    
    total_count = sum(
        _get_counter_total("http_requests_total", {"method": m})
        for m in ["GET", "POST", "PUT", "DELETE"]
    )
    
    now = time.time()
    elapsed = now - _last_sample["time"]
    delta = total_count - _last_sample["count"]
    rps = delta / elapsed if elapsed > 0 else 0
    _last_sample = {"time": now, "count": total_count}
    
    # 使用 bucket 近似计算分位数
    latency_p50 = _get_histogram_quantile_approx("http_request_duration_seconds", 0.5) * 1000
    latency_p95 = _get_histogram_quantile_approx("http_request_duration_seconds", 0.95) * 1000
    
    # 统计状态码分布
    status_codes = {}
    error_count_5xx = 0
    for metric_family in REGISTRY.collect():
        for s in metric_family.samples:
            if s.name == "http_requests_total":
                code = s.labels.get("status", "")
                if code:
                    status_codes[code] = status_codes.get(code, 0) + int(s.value)
                    if code.startswith("5"):
                        error_count_5xx += int(s.value)
    
    error_rate = (error_count_5xx / total_count * 100) if total_count > 0 else 0
    
    # 端点延迟
    endpoint_latency = _collect_endpoint_latency()
    
    # 系统资源
    cpu_percent = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory()
    memory_percent = memory.percent
    
    return success_response(data={
        "total_requests": int(total_count),
        "requests_per_second": round(rps, 3),
        "latency_ms_p50": round(latency_p50, 2),
        "latency_ms_p95": round(latency_p95, 2),
        "error_rate": round(error_rate, 3),
        "status_codes": status_codes,
        "endpoint_latency": endpoint_latency,
        "cpu_percent": cpu_percent,
        "memory_percent": memory_percent,
        "health_score": max(0, min(100, round(100 - error_rate * 10 - latency_p95 / 10, 1))),
    })
```

### Step 3：测试验证

1. 重启后端服务
2. 打开仪表盘页面，观察 5 个指标卡片是否有变化
3. 手动触发几个 API 请求（如刷新报告列表），观察 RPS 和延迟是否有变化
4. 等待 10 秒后观察指标是否自动刷新

## 注意事项

- 修改期间不改变前端代码（前端轮询逻辑正确）
- 不删除已有的 `/api/v1/metrics` 原始 Prometheus 端点
- CPU 和内存指标由 `psutil` 提供，不受此 bug 影响，但 RPS、延迟、错误率均受影响
