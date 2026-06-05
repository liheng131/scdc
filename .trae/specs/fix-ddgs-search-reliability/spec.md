# DDGS 搜索可靠性修复（v2）Spec

## Why

上一轮 spec `fix-ddgs-search-reliability` 的验证清单（checklist）存在**虚假勾选**问题：
- spec 第 30 行明确要求 `DDGSService.search()` SHALL 显式指定 `backend="duckduckgo,wikipedia"`
- 但实际 [ddgs.py:41](file:///d:/project/trae_projects/scdc/backend/app/services/ddgs.py#L41) 实现为 `DEFAULT_BACKEND = "auto"`
- checklist 第 4 行却把 `backend="auto"` 当作"已通过"勾上

复现证据：直接调用 `ddgs.text(query, backend="auto")` 仍抛出 `('builder error', None)`（orchestrator 实际日志，task `8a670c6b`），导致 `Collector failed: SerpAPI search failed: [attempt 3/3] BuilderError`。

实测三种后端在当前环境（`ddgs==9.14.4`）的表现：

| backend | 行为 | 结论 |
|---------|------|------|
| `auto` | 偶发成功 3 条，频繁抛 `builder error` | 不可靠 |
| `duckduckgo` | 100% 失败，ConnectError `[WinError 10054] 远程主机强迫关闭了一个现有的连接` | TCP RST，被反爬 |
| `duckduckgo,wikipedia` | 未在 v1 实现中启用 | 需重测 |

**根因**：`ddgs==9.14.4` 内部 HTTP/2 多引擎并发请求在当前网络环境被 DuckDuckGo RST；`auto` 模式下任一引擎失败即返回空结果并触发 builder error。

本轮真正修复：
1. 真正按 spec 要求把 `DEFAULT_BACKEND` 改为 `"duckduckgo,wikipedia"`
2. `ddgs.text()` 调用使用 `http_client` 参数禁用 HTTP/2（HTTP/1.1 + TLS 指纹伪装可绕过部分反爬）
3. 在 `builder error` 时**先重试**，重试失败则**降级**到纯 Wikipedia 后端
4. 在 SearchResponse.error 里明确告知前端是 `auto` 引擎问题还是 `duckduckgo` 引擎问题

## What Changes

- **修复** `DDGSService` 默认后端：把 `DEFAULT_BACKEND = "auto"` 改为 `DEFAULT_BACKEND = "duckduckgo,wikipedia"`
- **新增** `ddgs.text()` 关闭 HTTP/2（`http_client="curl_cffi"` 或显式传 `httpx.Client(http2=False)`）以规避 RST
- **新增** 降级策略：`duckduckgo` 后端失败时自动 fallback 到 `wikipedia` 单引擎
- **修复** checklist 行为：实际跑通端到端 `test_pipeline.py` 才允许勾选
- **修复** CollectorAgent 日志文案："SerpAPI search failed" 改为 "DDGS search failed"（沿用旧字符串避免破坏日志聚合，但 error 字段准确化）

## Impact

- Affected specs: `fix-ddgs-search-reliability`（v1）— 本次覆盖其未真正修复的部分
- Affected code:
  - [backend/app/services/ddgs.py](file:///d:/project/trae_projects/scdc/backend/app/services/ddgs.py) — DEFAULT_BACKEND 常量、`_do_search()` http_client 参数、新增降级逻辑
  - [backend/app/agents/collector.py](file:///d:/project/trae_projects/scdc/backend/app/agents/collector.py) — 日志文案（可选）
  - [backend/tests/e2e/test_pipeline.py](file:///d:/project/trae_projects/scdc/backend/tests/e2e/test_pipeline.py) — 真正执行该测试

## ADDED Requirements

### Requirement: 真正按 spec 锁定后端
`DDGSService.backend` SHALL 等于字符串 `"duckduckgo,wikipedia"`，不得在生产代码中出现 `"auto"`。

#### Scenario: 启动后默认后端校验
- **WHEN** `DDGSService()` 被实例化
- **THEN** `instance.backend == "duckduckgo,wikipedia"`
- **THEN** `ddgs.text(...)` 调用中 `backend` 参数等于 `instance.backend`

### Requirement: 关闭 HTTP/2 规避 RST
`DDGSService._do_search()` SHALL 在 `DDGS(proxy=..., timeout=..., verify=False, http_client=...)` 中显式传 `http_client`，使底层 httpx 客户端走 HTTP/1.1。

#### Scenario: HTTP/1.1 模式
- **WHEN** 用户环境存在 HTTP/2 多路复用被 RST 的情况
- **THEN** DDGS 走 HTTP/1.1 + curl_cffi TLS 指纹
- **THEN** 连续 3 次 builder error 概率显著降低

### Requirement: Wikipedia 降级
`DDGSService._search_with_retry()` SHALL 在 `backend="duckduckgo,wikipedia"` 三次尝试全失败时，**再尝试** `backend="wikipedia"` 一次（不计入重试预算）。

#### Scenario: 主后端失败
- **WHEN** `duckduckgo` 引擎连续失败
- **THEN** 跳过 duckduckgo，仅用 wikipedia
- **THEN** 若 wikipedia 成功，error 字段标注 `[downgraded to wikipedia]`

#### Scenario: 主后端成功
- **WHEN** `duckduckgo` 第一次就成功
- **THEN** 不触发 wikipedia 降级

### Requirement: 错误信息区分引擎
`SearchResponse.error` SHALL 包含失败时实际尝试的后端名（如 `[backend=duckduckgo,wikipedia] ...`）。

#### Scenario: 全部失败
- **WHEN** 主+降级全失败
- **THEN** error 形如 `[backend=duckduckgo,wikipedia,wikipedia-fallback] [attempt 3/3] builder error`

## MODIFIED Requirements

### Requirement: 修正 checklist 验收方式
`fix-ddgs-search-reliability` checklist 中关于"backend 已显式指定"的条目 SHALL 由 `pytest tests/e2e/test_pipeline.py -v` 真正执行通过来验证，不接受人工勾选。

### Requirement: 日志文案统一
`CollectorAgent.execute` 中 `logger.warning(f"SerpAPI search failed ...")` SHALL 改为 `logger.warning(f"DDGS search failed ...")`，error 字段保持中文可读。

## REMOVED Requirements

无。
