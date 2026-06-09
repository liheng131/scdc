# 彻底清理 DDGS 痕迹 - 实施计划

## 1. 任务背景

确认 `/plan` 工作流**已在使用 AnySearch**（上次实施已切换，搜索 `2025年AI芯片市场趋势` 实测返回 10 条结果），但**代码中 DDGS 痕迹尚未清理干净**。本次按用户决策执行彻底重命名 + 旧资产全部清理。

## 2. 范围确认（用户已决策）

| 决策项 | 选择 |
|--------|------|
| 重命名范围 | **彻底重命名**：`ddgs.py` → `anysearch.py`、`DDGSService` → `AnySearchService`、端点 `/health/ddgs` → `/health/anysearch`，4 处 import 同步更新 |
| 旧资产处理 | **全部清理**：`requirements.txt` 移除 ddgs、`config.py` 移除 `ddgs_proxy` 与 `serpapi_key`、`.env` 移除 `DDGS_PROXY` 与 `SERPAPI_KEY`、删除 4 个 `test_ddgs_*.py`、更新 `tests/e2e/test_pipeline.py` 注释 |

## 3. 当前 DDGS 痕迹清单（基于 Phase 1 探索）

| # | 路径 | 现状 | 处理 |
|---|------|------|------|
| 1 | [d:\project\trae_projects\scdc\backend\app\services\ddgs.py](file:///d:/project/trae_projects/scdc/backend/app/services/ddgs.py) | 文件名+类名仍叫 ddgs/DDGSService | **重命名为 anysearch.py / AnySearchService** |
| 2 | [d:\project\trae_projects\scdc\backend\app\agents\collector.py](file:///d:/project/trae_projects/scdc/backend/app/agents/collector.py) | 文档字符串"使用 DDGS"、import ddgs、`proxy` 形参 | 更新 import + docstring + 移除 proxy 形参 |
| 3 | [d:\project\trae_projects\scdc\backend\app\api\router.py](file:///d:/project/trae_projects/scdc/backend/app/api/router.py) | import ddgs、`_ddgs_probe` 变量、端点 `/health/ddgs`、`ddgs_health_check` 函数、payload `effective_proxy` 字段 | 全部改名为 anysearch + `effective_api_url` |
| 4 | [d:\project\trae_projects\scdc\backend\app\api\routes\search.py](file:///d:/project/trae_projects/scdc/backend/app/api/routes/search.py) | 文档字符串、import、端点路径、函数名 | 全部改名为 anysearch |
| 5 | [d:\project\trae_projects\scdc\backend\app\main.py](file:///d:/project/trae_projects/scdc/backend/app/main.py#L175) | `from app.services.ddgs import DDGSService` | 改 import |
| 6 | [d:\project\trae_projects\scdc\backend\app\core\config.py](file:///d:/project/trae_projects/scdc/backend/app/core/config.py) | `serpapi_key`、`ddgs_proxy` 字段 | 删除两字段 |
| 7 | [d:\project\trae_projects\scdc\backend\.env](file:///d:/project/trae_projects/scdc/backend/.env) | `# SERPAPI_KEY=` 与 `DDGS_PROXY=` 注释行 | 删除两行 |
| 8 | [d:\project\trae_projects\scdc\backend\requirements.txt](file:///d:/project/trae_projects/scdc/backend/requirements.txt#L13) | `ddgs>=9.0.0` | 删除该行 |
| 9 | `d:\project\trae_projects\scdc\backend\test_ddgs_full.py` | 旧 DDGS 库测试脚本 | **删除** |
| 10 | `d:\project\trae_projects\scdc\backend\test_ddgs_queries.py` | 旧 DDGS 库测试脚本 | **删除** |
| 11 | `d:\project\trae_projects\scdc\backend\test_ddgs_inspect.py` | 旧 DDGS 库测试脚本 | **删除** |
| 12 | `d:\project\trae_projects\scdc\backend\test_ddgs_behavior.py` | 旧 DDGS 库测试脚本 | **删除** |
| 13 | [d:\project\trae_projects\scdc\backend\tests\e2e\test_pipeline.py](file:///d:/project/trae_projects/scdc/backend/tests/e2e/test_pipeline.py#L11) | 注释 "DDGS 始终可用" | 改为 "AnySearch 始终可用" |

**不清理（历史记录，不属于代码痕迹）**：
- `d:\project\trae_projects\scdc\backend\startup.log`（历史日志）
- `d:\project\trae_projects\scdc\.trae\documents\replace-ddgs-with-anysearch.md`（上次实施的计划文档）
- `d:\project\trae_projects\scdc\.trae\specs\fix-ddgs-*`（历史 spec）
- `d:\project\trae_projects\scdc\docs\error.md`（历史错误文档）
- `d:\project\trae_projects\scdc\backend\app\agents\collector.py` 第 41 行 `1. 调用 SerpAPI 搜索主题关键词`（docstring 内的步骤描述，本计划不修改，纯属历史背景描述）

---

## 4. 实施步骤

### 步骤 1：创建 `app/services/anysearch.py`（重命名后的新文件）

**动作**：将 `app/services/ddgs.py` 内容写入 `app/services/anysearch.py`，并做以下调整：
- 类名 `DDGSService` → `AnySearchService`
- 模块级对象 `ddgs_health` → `anysearch_health`
- 函数 `record_anysearch_success/failure` 保持（名称已正确）
- **删除** 旧名别名 `record_ddgs_success/failure = record_anysearch_success/failure`（不再需要兼容）
- **删除** `__init__` 中的 `proxy: Optional[str] = None` 形参与 `del proxy`（无调用方再传）
- 文档字符串中的"类名沿用旧名 DDGSService"段落改为"AnySearch 实现"，删除"保留旧名以兼容"说明
- `_DDGSHealthState` 类名 → `_AnySearchHealthState`
- `DEFAULT_BACKEND` 保持 `"anysearch"`

**完成后**：`app/services/ddgs.py` 删除。

### 步骤 2：更新 `app/agents/collector.py`

**改动**：
- 顶部 docstring "使用 DDGS (DuckDuckGo Search) 搜索引擎" → "使用 AnySearch 搜索引擎"
- 顶部 docstring "为什么使用 DDGS" 段落删除或改为 "为什么使用 AnySearch"
- `from app.services.ddgs import DDGSService` → `from app.services.anysearch import AnySearchService`
- `__init__(self, proxy: Optional[str] = None)` → `__init__(self)`（移除 proxy 形参）
- `self.search_service = DDGSService(proxy=proxy)` → `self.search_service = AnySearchService()`
- 文档字符串 `:param proxy: 可选 DDGS 代理...` 整段删除

### 步骤 3：更新 `app/api/router.py`

**改动**：
- `from app.services.ddgs import ...` → `from app.services.anysearch import AnySearchService, anysearch_health, DEFAULT_BACKEND`
- `# 共享一个 DDGSService 实例给健康检查用` → `# 共享一个 AnySearchService 实例给健康检查用`
- `_ddgs_probe = DDGSService()` → `_anysearch_probe = AnySearchService()`
- `@api_router.get("/health/ddgs", ...)` → `@api_router.get("/health/anysearch", ...)`
- `async def ddgs_health_check(...)` → `async def anysearch_health_check(...)`
- 函数 docstring 中的 "DDGS 搜索服务健康检查端点" → "AnySearch 搜索服务健康检查端点（路径：/api/v1/health/anysearch）"
- docstring 中 "主动执行一次轻量搜索...探测 DDGS 可用性" → "探测 AnySearch 可用性"
- `probe = await _ddgs_probe.search(...)` → `probe = await _anysearch_probe.search(...)`
- payload 字段 `"effective_proxy": _ddgs_probe.proxy` → 删除（AnySearch 无代理概念），改为 `"effective_api_url": _anysearch_probe.base_url, "api_key_set": bool(_anysearch_probe.api_key)`
- payload `"consecutive_failures": ddgs_health._consecutive_failures` → `"consecutive_failures": anysearch_health._consecutive_failures`
- payload `"last_check_at": ddgs_health.last_check_at` → `"last_check_at": anysearch_health.last_check_at`
- payload `"last_error": ddgs_health.last_error` → `"last_error": anysearch_health.last_error`

### 步骤 4：更新 `app/api/routes/search.py`

**改动**：
- docstring "提供 DDGS (DuckDuckGo Search) 搜索引擎的 HTTP 查询接口" → "提供 AnySearch 搜索引擎的 HTTP 查询接口"
- docstring "CollectorAgent 内部复用同一个 DDGSService 实例" → "CollectorAgent 内部复用同一个 AnySearchService 实例"
- `from app.services.ddgs import ...` → `from app.services.anysearch import AnySearchService, anysearch_health, DEFAULT_BACKEND`
- `search_service = DDGSService()` → `search_service = AnySearchService()`（变量名可保留，因其作用域是模块内）
- `@router.get("/health/ddgs", ...)` → `@router.get("/health/anysearch", ...)`
- `async def ddgs_health_check(...)` → `async def anysearch_health_check(...)`
- docstring "DDGS 健康检查端点（路径：/api/v1/search/health/ddgs）" → "AnySearch 健康检查端点（路径：/api/v1/search/health/anysearch）"
- docstring "兼容通过 /api/v1/health/ddgs 直接访问的实现见 api_router 的转发" → "兼容通过 /api/v1/health/anysearch 直接访问的实现见 api_router 的转发"
- payload `"last_check_at": ddgs_health.last_check_at` → `"last_check_at": anysearch_health.last_check_at`
- payload `"last_error": ddgs_health.last_error` → `"last_error": anysearch_health.last_error`
- payload `"consecutive_failures": ddgs_health._consecutive_failures` → `"consecutive_failures": anysearch_health._consecutive_failures`

### 步骤 5：更新 `app/main.py`

**改动**：
- `from app.services.ddgs import DDGSService` → `from app.services.anysearch import AnySearchService`
- `_probe = DDGSService()` → `_probe = AnySearchService()`
- 注释 "启动期打印 AnySearch 实际生效的配置" 保留（日志文案已正确）
- 注释 "Failed to probe AnySearch config at startup" 保留

### 步骤 6：清理 `app/core/config.py`

**改动**：删除两个废弃字段：
```python
serpapi_key: str = ""                                # SerpAPI 搜索引擎 API Key (已废弃，保留为空以兼容旧配置)
ddgs_proxy: str = ""                                # DDGS (DuckDuckGo) 可选代理，形如 socks5://user:pass@host:port (已废弃，保留字段以兼容旧配置)
```

**为什么可以删除**：
- 探索阶段确认 `serpapi_key` / `ddgs_proxy` 仅在 `app/services/ddgs.py` 的旧版中使用，AnySearch 实现不再读取
- `grep "settings.serpapi_key\|settings.ddgs_proxy"` 在生产代码中无任何命中
- 删除可减少配置噪音

### 步骤 7：清理 `.env`

**改动**：删除 4 行：
```
# SerpAPI 搜索引擎密钥 (已废弃，搜索已切换为免费的 DDGS / DuckDuckGo)
# SERPAPI_KEY=

# DDGS (DuckDuckGo Search) 可选代理 (留空 = 直连)
# 仅在地区受限 / 网络不可达时填写，形如 socks5://user:pass@host:port
DDGS_PROXY=
```

### 步骤 8：清理 `requirements.txt`

**改动**：删除一行：
```
ddgs>=9.0.0
```

### 步骤 9：删除 4 个旧 DDGS 测试脚本

**动作**：删除以下文件：
- `d:\project\trae_projects\scdc\backend\test_ddgs_full.py`
- `d:\project\trae_projects\scdc\backend\test_ddgs_queries.py`
- `d:\project\trae_projects\scdc\backend\test_ddgs_inspect.py`
- `d:\project\trae_projects\scdc\backend\test_ddgs_behavior.py`

**为什么**：
- 这 4 个文件直接 `from ddgs import DDGS`，是早期诊断 DDGS 行为的脚本
- 任何搜索现在通过 `test_search.py` 覆盖（已存在）
- 与生产代码无任何引用关系

### 步骤 10：更新 `tests/e2e/test_pipeline.py`

**改动**：`# DDGS 始终可用，无需 skip 条件` → `# AnySearch 始终可用，无需 skip 条件`

---

## 5. 关键决策

| 决策 | 理由 |
|------|------|
| 文件 ddgs.py 物理删除（不是保留作为空壳） | 用户选"彻底重命名"；保留空文件无意义且仍会误导后续开发者 |
| 删除 `proxy` 形参 | `CollectorAgent` 是唯一调用方，本次同步更新；新 `AnySearchService.__init__()` 不需要 proxy |
| 删除 `serpapi_key` 配置 | 探索确认无任何代码读取 `settings.serpapi_key`，是死代码 |
| 删除 `ddgs_proxy` 配置 | 探索确认无任何代码读取 `settings.ddgs_proxy`（旧版 ddgs.py 用的，新版不再用） |
| 端点路径 `/health/ddgs` → `/health/anysearch` | 用户选"彻底重命名"；前端探索未发现引用此路径（无 matches），前端无破坏风险 |
| 函数 `ddgs_health_check` → `anysearch_health_check` | 与类名/对象名/端点保持一致命名空间 |
| `effective_proxy` 字段改为 `effective_api_url` + `api_key_set` | AnySearch 无代理概念；新字段更能反映实际状态 |
| 不清理 `startup.log` / 历史 spec / docs | 属于历史档案，不是代码痕迹；清理反而丢失故障排查记录 |
| 不清理 `collector.py` docstring 中残留的"调用 SerpAPI 搜索主题关键词"（第 41 行步骤描述） | 这是历史步骤的文本残留，含义上不再准确；但本计划聚焦在"DDGS"字面痕迹，不扩大改动面 |

---

## 6. 验证步骤

### 6.1 字面验证（确保 DDGS 字面无残留）
1. 在 `d:\project\trae_projects\scdc\backend` 下执行：
   ```bash
   grep -r "DDGS\|ddgs\|duckduckgo\|DuckDuckGo" app/ tests/ requirements.txt .env
   ```
   **期望**：仅 `tests/e2e/test_pipeline.py` 第 11 行的注释命中（已改为 "AnySearch"——应无命中），其它 0 命中
2. `grep -r "DDGSService\|ddgs_health\|ddgs_proxy\|serpapi_key" app/` 期望 0 命中

### 6.2 配置加载验证
3. `python -c "from app.core.config import settings; print(settings.anysearch_api_key[:10] if settings.anysearch_api_key else 'MISSING')"` 期望输出前 10 字符 `as_sk_57063`（即 .env 中的 key 前缀）
4. `python -c "from app.core.config import settings; print(hasattr(settings, 'ddgs_proxy'), hasattr(settings, 'serpapi_key'))"` 期望输出 `False False`

### 6.3 模块导入验证
5. `python -c "from app.services.anysearch import AnySearchService, anysearch_health, DEFAULT_BACKEND; print(DEFAULT_BACKEND)"` 期望输出 `anysearch`
6. `python -c "from app.agents.collector import CollectorAgent; from app.api.routes.search import router; from app.api.router import api_router; print('OK')"` 期望输出 `OK`
7. `python -c "from app.main import app; print(len(app.routes))"` 期望 83（与重命名前数量一致，证明端点未丢失）

### 6.4 端点路径验证
8. 启动后端，`curl http://localhost:8000/api/v1/health/anysearch`（带 Bearer token）期望 200 + `engine: anysearch`
9. `curl http://localhost:8000/api/v1/health/ddgs` 期望 **404**（端点已移除）

### 6.5 功能回归
10. `POST /api/v1/search/query` 调任意 query，期望 `success=true` 且 `results` 非空
11. 在 `/plan` 工作流中提问"2025年AI芯片市场趋势"，期望完整跑通 collecting → cleaning → analyzing → reporting

---

## 7. 文件改动清单汇总

| # | 文件路径 | 动作 |
|---|---------|------|
| 1 | `d:\project\trae_projects\scdc\backend\app\services\ddgs.py` | **删除** |
| 2 | `d:\project\trae_projects\scdc\backend\app\services\anysearch.py` | **新建**（重命名 + 类/对象改名 + 删除 proxy 形参） |
| 3 | `d:\project\trae_projects\scdc\backend\app\agents\collector.py` | 编辑：import + docstring + 移除 proxy 形参 |
| 4 | `d:\project\trae_projects\scdc\backend\app\api\router.py` | 编辑：import + 变量名 + 端点路径 + 函数名 + payload 字段 |
| 5 | `d:\project\trae_projects\scdc\backend\app\api\routes\search.py` | 编辑：import + 端点路径 + 函数名 + docstring |
| 6 | `d:\project\trae_projects\scdc\backend\app\main.py` | 编辑：import（仅 2 行） |
| 7 | `d:\project\trae_projects\scdc\backend\app\core\config.py` | 编辑：删除 `serpapi_key` + `ddgs_proxy` 2 个字段 |
| 8 | `d:\project\trae_projects\scdc\backend\.env` | 编辑：删除 4 行 SerpAPI/DDGS 注释 |
| 9 | `d:\project\trae_projects\scdc\backend\requirements.txt` | 编辑：删除 `ddgs>=9.0.0` 1 行 |
| 10 | `d:\project\trae_projects\scdc\backend\test_ddgs_full.py` | **删除** |
| 11 | `d:\project\trae_projects\scdc\backend\test_ddgs_queries.py` | **删除** |
| 12 | `d:\project\trae_projects\scdc\backend\test_ddgs_inspect.py` | **删除** |
| 13 | `d:\project\trae_projects\scdc\backend\test_ddgs_behavior.py` | **删除** |
| 14 | `d:\project\trae_projects\scdc\backend\tests\e2e\test_pipeline.py` | 编辑：1 行注释 |

**共 14 个文件**：1 新建 + 8 编辑 + 5 删除。
