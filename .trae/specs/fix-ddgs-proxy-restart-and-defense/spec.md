# DDGS Proxy 空字符串 + Backend 热加载 Spec

## Why

工作流跑市场洞察时，`CollectorAgent` 调 `DDGSService.search()` 失败，错误为：

```
WARNING:app.services.ddgs:DDGS search attempt 1/3 backend=duckduckgo,wikipedia
failed (retryable=False): Unknown scheme for proxy URL URL('')
```

日常提问（`general_question`）正常工作，只有工作流提问（`market_insight`）失败——因为只有工作流会触发 `DDGS` 搜索。

**根因（已通过证据证实）**：

| 文件 | 最后修改时间 | 状态 |
|------|--------------|------|
| `backend/.env` | 2026-06-08 11:52:54 | `DDGS_PROXY=` 留空 |
| `backend/app/services/ddgs.py` | 2026-06-08 11:52:54 | 已含 `raw.strip() if raw and raw.strip() else None` 修复 |
| backend 进程 (PID 30012) | 2026-06-08 **11:49:36** 启动 | **早于代码修改 3 分钟**，加载的是旧 `ddgs.py`，没有 trim 逻辑 |

旧版 `ddgs.py` 的 `__init__` 没有处理空字符串 → `DDGS(proxy='')` → 内部 `httpx.Client(proxy=URL(''))` 抛 `Unknown scheme for proxy URL URL('')`。

**为什么日常提问没问题**：日常提问走 `is_direct_response=True` 直答通路，不调 `DDGSService`。

## What Changes

- **操作项**：用户**重启 backend** 进程（`uvicorn app.main:app --reload` 或手动 kill+restart），加载新版 `ddgs.py`
- **预防改进 1**：在 backend 启动时打印一次 `ddgs_proxy` 的最终生效值（`None` 或实际 URL），让用户立即看到是否正确
- **预防改进 2**：在 `DDGSService.__init__` 加防御——如果 `proxy == ''` 主动改为 `None`，避免任何未来代码路径（如直接传 `os.getenv('DDGS_PROXY', '')`）漏过 trim 逻辑
- **预防改进 3**：在 `/api/v1/health/ddgs` 端点返回 `effective_proxy: <null-or-url>` 字段，运维可远程确认当前生效的代理

## Impact

- Affected specs: `fix-ddgs-search-reliability` v2（覆盖其 Task 1.4 的 trim 修复，添加 3 道防线）
- Affected code:
  - [backend/app/services/ddgs.py](file:///d:/project/trae_projects/scdc/backend/app/services/ddgs.py) — `__init__` 主动改 `'' → None` + 启动日志
  - [backend/app/main.py](file:///d:/project/trae_projects/scdc/backend/app/main.py) — startup 钩子打印 `effective_proxy`
  - [backend/app/api/router.py](file:///d:/project/trae_projects/scdc/backend/app/api/router.py) — `/api/v1/health/ddgs` 返回 `effective_proxy`

## ADDED Requirements

### Requirement: DDGSService proxy 主动归一化
`DDGSService.__init__` SHALL 在赋值 `self.proxy` 前，如果传入值或 `settings.ddgs_proxy` 是 `''` / `'  '`（纯空白），统一归一化为 `None`。

#### Scenario: 显式传入空字符串
- **WHEN** `DDGSService(proxy='')` 被调用
- **THEN** `instance.proxy is None`

#### Scenario: settings.ddgs_proxy 为空字符串
- **WHEN** `DDGSService()` 被调用且 `settings.ddgs_proxy == ''`
- **THEN** `instance.proxy is None`

#### Scenario: settings.ddgs_proxy 为纯空白
- **WHEN** `DDGSService()` 被调用且 `settings.ddgs_proxy == '  '`
- **THEN** `instance.proxy is None`

### Requirement: 启动期打印 effective proxy
backend startup 阶段 SHALL 打印一行 INFO 日志，格式为 `DDGS effective_proxy=<None or URL>`，便于确认启动加载到的代理值。

#### Scenario: 启动时无代理
- **WHEN** `.env` 中 `DDGS_PROXY=` 留空
- **THEN** 日志输出 `DDGS effective_proxy=None`

#### Scenario: 启动时有代理
- **WHEN** `.env` 中 `DDGS_PROXY=socks5://1.2.3.4:1080`
- **THEN** 日志输出 `DDGS effective_proxy=socks5://1.2.3.4:1080`

### Requirement: 健康检查暴露 effective proxy
`GET /api/v1/health/ddgs` SHALL 在响应 `data` 中返回 `effective_proxy` 字段（值或 null）。

#### Scenario: 健康检查返回代理状态
- **WHEN** 运维访问 `/api/v1/health/ddgs`
- **THEN** 响应体含 `data.effective_proxy` 字段

## MODIFIED Requirements

无（`fix-ddgs-search-reliability` v2 已勾选的部分保持勾选；本 spec 是 v3 增量）

## REMOVED Requirements

无。
