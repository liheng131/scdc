from fastapi import APIRouter
from prometheus_client import REGISTRY, Counter, Histogram
from app.api.responses import success_response, ResponseModel
import psutil
import os
import threading
import time

router = APIRouter()

_last_sample: dict = {"time": time.time(), "count": 0}

def _get_metric_value(name: str, labels: dict = None) -> float:
    for metric in REGISTRY.collect():
        if metric.name == name:
            for sample in metric.samples:
                if labels is None or all(sample.labels.get(k) == v for k, v in (labels or {}).items()):
                    return sample.value
    return 0

def _get_histogram_quantile(name: str, quantile: float, labels: dict = None) -> float:
    for metric in REGISTRY.collect():
        if metric.name == name:
            for sample in metric.samples:
                if sample.labels.get('quantile', '') == str(quantile):
                    if labels is None or all(sample.labels.get(k) == v for k, v in (labels or {}).items() if k != 'quantile'):
                        return sample.value
    return 0

@router.get("/json", response_model=ResponseModel)
async def get_metrics_json():
    global _last_sample

    total_count = _get_metric_value("http_requests_total", {"method": "GET"}) + \
                  _get_metric_value("http_requests_total", {"method": "POST"}) + \
                  _get_metric_value("http_requests_total", {"method": "PUT"}) + \
                  _get_metric_value("http_requests_total", {"method": "DELETE"})

    now = time.time()
    elapsed = now - _last_sample["time"]
    rps = (total_count - _last_sample["count"]) / elapsed if elapsed > 0 else 0
    _last_sample = {"time": now, "count": total_count}

    latency_p50 = _get_histogram_quantile("http_request_duration_seconds", 0.5) * 1000
    latency_p95 = _get_histogram_quantile("http_request_duration_seconds", 0.95) * 1000

    status_codes = {}
    error_count_5xx = 0
    for metric in REGISTRY.collect():
        if metric.name == "http_requests_total":
            for sample in metric.samples:
                code = sample.labels.get("status", "")
                if code:
                    status_codes[code] = status_codes.get(code, 0) + int(sample.value)
                    if code.startswith("5"):
                        error_count_5xx += int(sample.value)

    error_rate = (error_count_5xx / total_count * 100) if total_count > 0 else 0

    endpoint_latency = []
    for metric in REGISTRY.collect():
        if metric.name == "http_request_duration_seconds_sum":
            for sample in metric.samples:
                handler = sample.labels.get("handler", "")
                method = sample.labels.get("method", "")
                if handler and handler != "/metrics" and handler != "/api/v1/metrics":
                    count_val = _get_metric_value("http_request_duration_seconds_count",
                        {"handler": handler, "method": method})
                    if count_val > 0:
                        avg_ms = (sample.value / count_val) * 1000
                        endpoint_latency.append({
                            "endpoint": f"{method} {handler}",
                            "avg_ms": round(avg_ms, 2)
                        })

    endpoint_latency.sort(key=lambda x: x["avg_ms"], reverse=True)
    endpoint_latency = endpoint_latency[:10]

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
        "health_score": round(100 - error_count_5xx - (latency_p95 / 100), 1) if total_count > 0 else 100,
    })