from fastapi import APIRouter
from prometheus_client import REGISTRY
from app.api.responses import success_response, ResponseModel
import psutil
import time
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

_last_sample: dict = {"time": 0.0, "count": 0.0, "initialized": False}

def _get_counter_total(name: str, extra_labels: dict = None) -> float:
    full_name = f"{name}_total" if not name.endswith("_total") else name
    for metric_family in REGISTRY.collect():
        for s in metric_family.samples:
            if s.name == full_name:
                if extra_labels is None or all(
                    s.labels.get(k) == v for k, v in extra_labels.items()
                ):
                    return s.value
    return 0.0

def _get_histogram_quantile_approx(name: str, quantile: float) -> float:
    count_name = f"{name}_count"
    count_val = 0.0
    buckets = []

    for metric_family in REGISTRY.collect():
        for s in metric_family.samples:
            if s.name == count_name:
                count_val = s.value
            elif s.name == f"{name}_bucket":
                le = s.labels.get("le")
                if le is not None and le != "+Inf":
                    buckets.append((float(le), s.value))

    if count_val <= 0 or not buckets:
        return 0.0

    target = count_val * quantile
    buckets.sort()
    for le, cumulative in buckets:
        if cumulative >= target:
            return le

    if buckets:
        return buckets[-1][0]
    return 0.0

def _collect_endpoint_latency() -> list:
    sums = {}
    counts = {}
    for metric_family in REGISTRY.collect():
        for s in metric_family.samples:
            if s.name == "http_request_duration_seconds_sum":
                handler = s.labels.get("handler", "")
                method = s.labels.get("method", "")
                if handler and handler not in ("/metrics", "/api/v1/metrics", "/api/v1/metrics-json/json"):
                    key = f"{method} {handler}"
                    sums[key] = s.value
            elif s.name == "http_request_duration_seconds_count":
                handler = s.labels.get("handler", "")
                method = s.labels.get("method", "")
                if handler and handler not in ("/metrics", "/api/v1/metrics", "/api/v1/metrics-json/json"):
                    key = f"{method} {handler}"
                    counts[key] = s.value

    endpoint_latency = []
    for key in sums:
        if key in counts and counts[key] > 0:
            avg_ms = (sums[key] / counts[key]) * 1000
            endpoint_latency.append({"endpoint": key, "avg_ms": round(avg_ms, 2)})

    endpoint_latency.sort(key=lambda x: x["avg_ms"], reverse=True)
    return endpoint_latency[:10]

@router.get("/json", response_model=ResponseModel)
async def get_metrics_json():
    global _last_sample

    if not _last_sample["initialized"]:
        initial_count = sum(
            _get_counter_total("http_requests_total", {"method": m})
            for m in ["GET", "POST", "PUT", "DELETE"]
        )
        _last_sample = {"time": time.time(), "count": initial_count, "initialized": True}

    total_count = sum(
        _get_counter_total("http_requests_total", {"method": m})
        for m in ["GET", "POST", "PUT", "DELETE"]
    )

    now = time.time()
    elapsed = now - _last_sample["time"]
    delta = total_count - _last_sample["count"]
    rps = delta / elapsed if elapsed > 0 else 0
    _last_sample["time"] = now
    _last_sample["count"] = total_count

    latency_p50 = _get_histogram_quantile_approx("http_request_duration_seconds", 0.5) * 1000
    latency_p95 = _get_histogram_quantile_approx("http_request_duration_seconds", 0.95) * 1000

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
    endpoint_latency = _collect_endpoint_latency()

    cpu_percent = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory()
    memory_percent = memory.percent

    health_score = max(0, min(100, round(100 - error_rate * 10 - latency_p95 / 10, 1)))

    logger.info(
        "Metrics snapshot: total=%d rps=%.2f p50=%.1fms p95=%.1fms err_rate=%.2f%% cpu=%.1f%% mem=%.1f%%",
        int(total_count), rps, latency_p50, latency_p95, error_rate, cpu_percent, memory_percent,
    )

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
        "health_score": health_score,
    })

@router.get("/debug")
async def debug_metrics():
    """调试端点：返回 REGISTRY 中的所有 HTTP 相关样本"""
    result = []
    for metric_family in REGISTRY.collect():
        for s in metric_family.samples:
            if "http" in s.name.lower() or "request" in s.name.lower():
                result.append({
                    "name": s.name,
                    "labels": s.labels,
                    "value": s.value,
                })
    return {"samples": result}

@router.get("/ping")
async def ping():
    import time
    return {"status": "ok", "timestamp": time.time(), "version": "v2"}
