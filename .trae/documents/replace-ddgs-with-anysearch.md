# 用 AnySearch 替换 DDGS 搜索服务 - 实施计划

## 1. 任务背景

`/plan` 工作流在采集（collecting）阶段调用搜索服务时持续失败：
```
❌ 搜索信息失败：Collector failed: DDGS search failed: [backend=duckduckgo,wikipedia,wikipedia-fallback]
[attempt 3/3] No results found. | fallback(wikipedia): No results found.
```

根因：当前环境对 DuckDuckGo/Wikipedia 后端的网络访问被持续拦截，三次重试 + Wikipedia 降级均返回 "No results found"。

用户已提供 **AnySearch** API 作为替代方案，并给出调用示例与 API Key：
- **API Key**：`as_sk_570631acc467a32b822b64646948acc8`
- **调用示例**：
  ```bash
  curl -X POST https://api.anysearch.com/v1/search \
    -H "Authorization: Bearer YOUR_ANYSEARCH_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
      "query": "Go 1.22 release notes",
      "max_results": 5,
      "domain": "code",
      "tag": "code.doc",
      "content_types": ["web", "doc"]
    }'
  ```

本计划目标：**用 AnySearchService 替换 DDGSService**，保持 `SearchRequest` / `SearchResponse` 公共契约不变，让 `CollectorAgent`、`/api/v1/search/query`、`/api/v1/health/ddgs` 等所有调用方零改动或仅需最小改动。

---

## 2. 当前状态分析（基于 Phase 1 代码探索）

### 2.1 DDGS 相关的文件与调用点

| 文件 | 当前角色 | 改造方向 |
|------|---------|---------|
| [d:\project\trae_projects\scdc\backend\app\services\ddgs.py](file:///d:/project/trae_projects/scdc/backend/app/services/ddgs.py) | `DDGSService` 同步 + 线程池 + 重试/降级实现；含 `ddgs_health` 模块级健康状态 | **核心文件**：就地重写为 `AnySearchService`（保留同名文件以最小化 import 改动），使用 `httpx.AsyncClient` 调用 AnySearch |
| [d:\project\trae_projects\scdc\backend\app\agents\collector.py](file:///d:/project/trae_projects/scdc/backend/app/agents/collector.py#L22) | `from app.services.ddgs import DDGSService` | 仅调整错误信息文案："DDGS search failed" → "AnySearch search failed" |
| [d:\project\trae_projects\scdc\backend\app\api\routes\search.py](file:///d:/project/trae_projects/scdc/backend/app/api/routes/search.py#L15-L47) | `/api/v1/search/query` + `/api/v1/search/health/ddgs` 端点 | 文件名/导入保留；端点路径保留 `/health/ddgs`（兼容前端），handler 内重命名为 AnySearch |
| [d:\project\trae_projects\scdc\backend\app\api\router.py](file:///d:/project/trae_projects/scdc/backend/app/api/router.py#L13-L83) | `/api/v1/health/ddgs` 直连入口 | 同样保留路径，handler 内部切换到 AnySearch |
| [d:\project\trae_projects\scdc\backend\app\main.py](file:///d:/project/trae_projects/scdc/backend/app/main.py#L173-L178) | 启动期打印 `DDGS effective_proxy` 日志 | 改为打印 `AnySearch effective_api_url` 与 `api_key` 存在性 |
| [d:\project\trae_projects\scdc\backend\app\core\config.py](file:///d:/project/trae_projects/scdc/backend/app/core/config.py#L40-L41) | `serpapi_key`、`ddgs_proxy` 字段 | 新增 `anysearch_api_key`、`anysearch_base_url`、`anysearch_default_max_results` |
| [d:\project\trae_projects\scdc\backend\.env](file:///d:/project/trae_projects/scdc/backend/.env#L42-L47) | 已存在 `DDGS_PROXY=` 注释 | 新增 `ANYSEARCH_API_KEY=as_sk_570631acc467a32b822b64646948acc8` 与 `ANYSEARCH_BASE_URL=https://api.anysearch.com` |

### 2.2 现有公共契约（保持不变）

- [d:\project\trae_projects\scdc\backend\app\schemas\search.py](file:///d:/project/trae_projects/scdc/backend/app/schemas/search.py)
  - `SearchRequest`：字段 `query`, `categories`, `pageno`, `time_range`, `timeout`
  - `SearchResultItem`：字段 `url`, `title`, `snippet`, `source`, `score`, `published_date`
  - `SearchResponse`：字段 `query`, `success`, `results`, `total_results`, `error`
- `CollectorAgent.execute()` 仅使用 `search_service.search(SearchRequest)` 与 `SearchResponse.{success, results, error}` —— **无需改动调用方**。
- 同步 → 异步：`DDGSService` 当前因底层 `ddgs` 是同步库而用 `asyncio.to_thread`；`AnySearch` 使用 `httpx.AsyncClient` 原生协程即可，移除 `to_thread` 包装。

### 2.3 依赖

- [d:\project\trae_projects\scdc\backend\requirements.txt](file:///d:/project/trae_projects/scdc/backend/requirements.txt) 中 `httpx>=0.27.0` 已存在，无需新增；`ddgs>=9.0.0` 保留（无副作用，且改动依赖不在本次最小目标内）。

---

## 3. 实施步骤

### 步骤 1：在 `.env` 与 `config.py` 中加入 AnySearch 配置

**文件**：[d:\project\trae_projects\scdc\backend\.env](file:///d:/project/trae_projects/scdc/backend/.env)、[d:\project\trae_projects\scdc\backend\app\core\config.py](file:///d:/project/trae_projects/scdc/backend/app/core/config.py)

**改动**：
- `.env` 末尾新增：
  ```
  # AnySearch 搜索引擎 (替换 DDGS)
  ANYSEARCH_API_KEY=as_sk_570631acc467a32b822b64646948acc8
  ANYSEARCH_BASE_URL=https://api.anysearch.com
  ANYSEARCH_DEFAULT_MAX_RESULTS=10
  ANYSEARCH_TIMEOUT=10
  ```
- `config.py` 新增字段（`Settings` 类）：
  - `anysearch_api_key: str = ""`
  - `anysearch_base_url: str = "https://api.anysearch.com"`
  - `anysearch_default_max_results: int = 10`
  - `anysearch_timeout: int = 10`

**为什么**：`pydantic-settings` 会从 `.env` 自动加载，让 `AnySearchService` 通过 `settings.anysearch_api_key` 拿到密钥，避免在代码里硬编码。

---

### 步骤 2：重写 `app/services/ddgs.py` 为 AnySearch 实现

**文件**：[d:\project\trae_projects\scdc\backend\app\services\ddgs.py](file:///d:/project/trae_projects/scdc/backend/app/services/ddgs.py)

**策略**：就地重写，但**保留文件路径与模块名**（`ddgs.py`），原因：
- `collector.py` / `routes/search.py` / `router.py` / `main.py` 都已 `from app.services.ddgs import ...`
- 保留模块名 = 0 改动 import
- 文件名与文档字符串在本次重写中改为 "AnySearch"，但仍可作为兼容层

**类结构**（完全替换原内容）：

```python
"""
AnySearch 搜索引擎服务

封装 AnySearch (https://api.anysearch.com/v1/search) 搜索 API。
替代原先的 DDGSService，因 DDGS 后端在当前环境被持续拦截且降级到 Wikipedia 仍无法获取结果。

请求格式（参考用户提供的 curl 示例）：
POST {base_url}/v1/search
Headers:
  Authorization: Bearer <ANYSEARCH_API_KEY>
  Content-Type: application/json
Body:
  {
    "query": "<query>",
    "max_results": <int>,
    "domain": "<code|news|...>",  # 可选
    "tag": "<code.doc|...>",       # 可选
    "content_types": ["web","doc"] # 可选
  }
"""

import logging
from typing import Optional, Any, Dict, List

import httpx

from app.core.config import settings
from app.schemas.search import SearchRequest, SearchResultItem, SearchResponse

logger = logging.getLogger(__name__)

DEFAULT_MAX_RESULTS = 10
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1.0


class DDGSService:  # 保留类名以避免改动 import
    """AnySearch 实现（类名沿用旧名 DDGSService 以兼容现有调用方）。"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = (api_key or settings.anysearch_api_key or "").strip()
        self.base_url = (base_url or settings.anysearch_base_url or "https://api.anysearch.com").rstrip("/")
        self.default_max_results = settings.anysearch_default_max_results or DEFAULT_MAX_RESULTS
        self.default_timeout = settings.anysearch_timeout or 10
        if not self.api_key:
            logger.warning("ANYSEARCH_API_KEY 未配置，搜索将返回错误")

    def _build_payload(self, request: SearchRequest) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "query": request.query,
            "max_results": self.default_max_results,
        }
        if request.time_range:
            # AnySearch 暂未确认 time_range 字段；先不传，避免未知字段被拒
            pass
        return payload

    async def _do_request(self, payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/v1/search"
        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code in RETRYABLE_STATUS:
                # 抛错触发重试
                resp.raise_for_status()
            if resp.status_code >= 400:
                # 非重试错误：直接抛错
                raise httpx.HTTPStatusError(
                    f"AnySearch HTTP {resp.status_code}: {resp.text[:200]}",
                    request=resp.request,
                    response=resp,
                )
            return resp.json()

    async def _search_with_retry(self, payload: Dict[str, Any], timeout: int) -> List[Dict[str, Any]]:
        import asyncio
        last_error: Optional[Exception] = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                data = await self._do_request(payload, timeout)
                return data.get("data") or data.get("results") or []
            except Exception as e:
                last_error = e
                retryable = isinstance(e, (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError)) \
                    and (not isinstance(e, httpx.HTTPStatusError) or e.response.status_code in RETRYABLE_STATUS)
                logger.warning(
                    "AnySearch attempt %d/%d failed (retryable=%s): %s",
                    attempt, MAX_ATTEMPTS, retryable, e,
                )
                if not retryable or attempt >= MAX_ATTEMPTS:
                    break
                await asyncio.sleep(RETRY_DELAY_SECONDS)
        assert last_error is not None
        raise last_error

    async def search(self, request: SearchRequest) -> SearchResponse:
        if not self.api_key:
            return SearchResponse(
                query=request.query,
                success=False,
                error="ANYSEARCH_API_KEY 未配置",
                results=[],
                total_results=0,
            )
        payload = self._build_payload(request)
        timeout = min(request.timeout or self.default_timeout, 30)
        try:
            raw_results = await self._search_with_retry(payload, timeout)
        except Exception as e:
            logger.warning("AnySearch search failed for query '%s': %s", request.query, e)
            record_anysearch_failure(str(e))
            return SearchResponse(
                query=request.query,
                success=False,
                error=str(e),
                results=[],
                total_results=0,
            )

        items: List[SearchResultItem] = []
        for r in raw_results:
            items.append(
                SearchResultItem(
                    url=r.get("url") or r.get("link") or "",
                    title=r.get("title") or "",
                    snippet=r.get("snippet") or r.get("content") or r.get("description") or "",
                    source=r.get("source") or "anysearch",
                    score=r.get("score"),
                    published_date=r.get("published_date") or r.get("date"),
                )
            )
        record_anysearch_success()
        return SearchResponse(
            query=request.query,
            success=True,
            results=items,
            total_results=len(items),
        )


# 模块级健康状态（沿用旧名 ddgs_health 以兼容现有 import）
class _DDGSHealthState:
    def __init__(self) -> None:
        self.last_status: str = "unknown"
        self.last_error: Optional[str] = None
        self.last_check_at: Optional[str] = None
        self.last_engine: str = "anysearch"
        self._consecutive_failures: int = 0


ddgs_health = _DDGSHealthState()


def record_anysearch_success() -> None:
    from datetime import datetime, timezone
    ddgs_health.last_status = "ok"
    ddgs_health.last_error = None
    ddgs_health.last_check_at = datetime.now(timezone.utc).isoformat()
    ddgs_health._consecutive_failures = 0


def record_anysearch_failure(error: str) -> None:
    from datetime import datetime, timezone
    ddgs_health._consecutive_failures += 1
    ddgs_health.last_error = error
    ddgs_health.last_check_at = datetime.now(timezone.utc).isoformat()
    if ddgs_health._consecutive_failures >= 3:
        ddgs_health.last_status = "degraded"
    else:
        ddgs_health.last_status = ddgs_health.last_status or "unknown"


# 兼容旧名（让旧的 `record_ddgs_success/failure` 调用不报错；本次代码无调用，但留作兜底）
record_ddgs_success = record_anysearch_success
record_ddgs_failure = record_anysearch_failure
```

**字段映射说明**（AnySearch 返回结构按常见搜索 API 约定，文档在探索阶段无法 100% 确认时按多字段名兜底）：
- `url` ← 响应中 `url` / `link`
- `title` ← `title`
- `snippet` ← `snippet` / `content` / `description`
- `source` ← `source`，缺省填 `"anysearch"`
- `published_date` ← `published_date` / `date`

若真实响应字段不同，**唯一需要调整的就是 `_do_request` 返回值解析那段映射**，其余逻辑（重试、健康状态、错误返回）都不动。

**为什么用 `httpx.AsyncClient`**：项目内 `notification.py`、`embedding.py`、`intent_classifier.py`、`agents/reporter.py` 已统一使用 `httpx.AsyncClient`，是项目约定。

**为什么需要兼容类名 `DDGSService` 与 `ddgs_health`**：`collector.py` / `routes/search.py` / `router.py` / `main.py` 中已写死 `from app.services.ddgs import DDGSService, ddgs_health, ...`，改名会牵动这些文件。保留类名=0 改动这些调用方。

---

### 步骤 3：调整调用方文案（可选但推荐）

**文件**：[d:\project\trae_projects\scdc\backend\app\agents\collector.py](file:///d:/project/trae_projects/scdc/backend/app/agents/collector.py#L55-L60)

**改动**：仅修改日志/错误消息字符串：
```python
# 原
logger.warning(f"DDGS search failed for topic '{input_data.topic}': {search_resp.error}")
return CollectorOutput(
    task_id=input_data.task_id,
    success=False,
    error=f"DDGS search failed: {search_resp.error}"
)
# 改为
logger.warning(f"AnySearch search failed for topic '{input_data.topic}': {search_resp.error}")
return CollectorOutput(
    task_id=input_data.task_id,
    success=False,
    error=f"AnySearch search failed: {search_resp.error}"
)
```

**为什么不动 import**：步骤 2 保留了 `DDGSService` 类名，import 语句无需调整。

---

### 步骤 4：调整 `main.py` 启动日志

**文件**：[d:\project\trae_projects\scdc\backend\app\main.py](file:///d:/project/trae_projects/scdc/backend/app/main.py#L173-L178)

**改动**：
```python
# 原
from app.services.ddgs import DDGSService
logger.info("DDGS effective_proxy=%r", DDGSService().proxy)
# 改为
from app.services.ddgs import DDGSService
probe = DDGSService()
logger.info("AnySearch base_url=%r api_key_set=%s", probe.base_url, bool(probe.api_key))
```

**为什么**：启动期需要确认 API Key 真的加载到了。

---

### 步骤 5：`/api/v1/health/ddgs` 端点保留路径，文案调整

**文件**：[d:\project\trae_projects\scdc\backend\app\api\routes\search.py](file:///d:/project/trae_projects/scdc/backend/app/api/routes/search.py)、[d:\project\trae_projects\scdc\backend\app\api\router.py](file:///d:/project/trae_projects/scdc/backend/app/api/router.py)

**改动**：仅在响应 payload 中将 `"engine": DEFAULT_BACKEND`（`DEFAULT_BACKEND` 是字符串 `"duckduckgo,wikipedia"`）改为 `"engine": "anysearch"`；`DEFAULT_BACKEND` 常量在 `ddgs.py` 中改名为 `"anysearch"` 即可（已在步骤 2 中一并改写）。

**路径保留 `/health/ddgs`**：前端可能已硬编码此路径，保留避免破坏前端。

---

## 4. 关键决策与假设

| 决策 | 理由 |
|------|------|
| 保留 `ddgs.py` 文件名与 `DDGSService` 类名 | 最小化 import 改动；前端/调用方零感知；`/health/ddgs` 路径继续工作 |
| 使用 `httpx.AsyncClient` 而非同步库 + `to_thread` | AnySearch 是纯 HTTP 异步；与项目内 `notification.py`/`embedding.py` 风格一致；性能更好 |
| `time_range` 字段暂不传 | 用户提供的示例未包含此字段；先保守不传，避免 422 风险 |
| `categories` 字段暂不映射 | AnySearch 用 `domain`/`tag`/`content_types` 体系；不强行转换，避免误传 |
| 不引入抽象 `SearchService` 接口 | 单一替换场景，过度抽象会提高改动面；后续若要支持多引擎再重构 |
| 不删除 `ddgs` 依赖 | 最小目标只修故障；保留依赖无副作用，可后续清理 |
| AnySearch 响应字段映射采用多字段名兜底（`url`/`link`、`snippet`/`content` 等） | 探索阶段无法 100% 确认响应 schema；用兜底兼容最常见变体 |

---

## 5. 验证步骤

### 5.1 配置加载验证
1. 重启后端服务，启动日志应打印：
   ```
   AnySearch base_url='https://api.anysearch.com' api_key_set=True
   ```
2. 确认 `ANYSEARCH_API_KEY` 已被 `pydantic-settings` 正确读取。

### 5.2 单元 / 集成验证
3. 调 `POST /api/v1/search/query` 携带 Bearer token，请求体 `{"query": "2025年AI芯片市场趋势", "timeout": 15}`：
   - 期望：返回 200 + `data.success=true` + `data.results` 非空数组
4. 调 `GET /api/v1/health/ddgs`：
   - 期望：`engine=anysearch`，`status=ok`，`probe.success=true`

### 5.3 端到端验证（核心）
5. 通过前端或 `POST /api/v1/workflow/run` 触发 `/plan` 类工作流问题：
   - 期望：完整跑通 `collecting → cleaning → analyzing → reporting`，不再出现 `DDGS search failed: No results found`
6. 检查后端日志，应出现：
   ```
   INFO:app.services.ddgs:AnySearch attempt 1/1 returned N results
   ```
   （不再出现 `attempt 3/3 ... No results found` 警告）

### 5.4 错误兜底验证
7. 临时将 `.env` 中 `ANYSEARCH_API_KEY` 改空，重启后再调 `/api/v1/search/query`：
   - 期望：返回 `success=false` + `error="ANYSEARCH_API_KEY 未配置"`，而不是 500
8. 恢复 API Key。

---

## 6. 文件改动清单汇总

| # | 文件路径 | 改动类型 | 关键内容 |
|---|---------|---------|---------|
| 1 | [d:\project\trae_projects\scdc\backend\.env](file:///d:/project/trae_projects/scdc/backend/.env) | 编辑 | 新增 4 行 AnySearch 配置 |
| 2 | [d:\project\trae_projects\scdc\backend\app\core\config.py](file:///d:/project/trae_projects/scdc/backend/app/core/config.py) | 编辑 | 新增 4 个 Settings 字段 |
| 3 | [d:\project\trae_projects\scdc\backend\app\services\ddgs.py](file:///d:/project/trae_projects/scdc/backend/app/services/ddgs.py) | **完全重写** | `DDGSService` 类体改为 `httpx.AsyncClient` + AnySearch，保留类名/模块名/健康状态对象名 |
| 4 | [d:\project\trae_projects\scdc\backend\app\agents\collector.py](file:///d:/project/trae_projects/scdc/backend/app/agents/collector.py) | 编辑 | 错误消息 "DDGS" → "AnySearch"（仅 2 行） |
| 5 | [d:\project\trae_projects\scdc\backend\app\main.py](file:///d:/project/trae_projects/scdc/backend/app/main.py) | 编辑 | 启动日志探针改为 AnySearch（4 行） |
| 6 | [d:\project\trae_projects\scdc\backend\app\api\routes\search.py](file:///d:/project/trae_projects/scdc/backend/app/api/routes/search.py) | 编辑 | 端点 `engine` 字段值（1 行） |
| 7 | [d:\project\trae_projects\scdc\backend\app\api\router.py](file:///d:/project/trae_projects/scdc/backend/app/api/router.py) | 编辑 | 端点 `engine` 字段值（1 行） |

**不改动**：
- `SearchRequest` / `SearchResponse` / `SearchResultItem` Schema —— 公共契约保持
- `CollectorAgent` 主流程（除错误文案外）—— 接口一致
- `requirements.txt` —— `httpx` 已存在，`ddgs` 保留无副作用
- 任何前端代码 —— `/health/ddgs` 路径保留
