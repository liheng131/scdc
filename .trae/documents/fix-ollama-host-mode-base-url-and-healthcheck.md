# Ollama Docker 部署 + Embedding 模型 + 测试连接：根因与修复

## Why

用户报告两个症状：

1. **Embedding 模型"用不了"** —— `nomic-embed-text` 一直在 DB 里配置为默认 embedding，
   但 analyzer / report 服务调用 embedding 时静默降级返回空向量
2. **系统设置 → 测试连接失败** —— UI 点击 embedding 模型的"测试连接"返回 5xx
   `Server disconnected without sending a response.` / `无法连接到服务 'http://localhost:11434'`

经端到端排查，根因不在 Docker、不在 Ollama 服务、不在模型本身，而是 **DB 中那条
embedding 配置的 `base_url` 写成了 Docker 内部网络名 `http://ollama:11434`，
但当前后端进程是用 host 上 `uvicorn` 启动的，根本解析不到 `ollama` 这个主机名**。

## Current State Analysis（基于实际探测的根因链）

| 探测项 | 结果 | 解读 |
|--------|------|------|
| `docker ps \| grep ollama` | `scdc_ollama Up 2 minutes (unhealthy)` | 容器在跑；"unhealthy" 仅因 healthcheck 命令不存在（详见下表） |
| `docker logs scdc_ollama` | `Listening on [::]:11434 (version 0.24.0)` | Ollama 进程已启动并监听 |
| `docker exec scdc_ollama ollama list` | `nomic-embed-text:latest  274 MB  8 days ago` | embedding 模型已就位 |
| `docker exec scdc_ollama sh -c 'command -v curl'` | (空) | 镜像里没装 curl/wget/nc，**这就是 healthcheck 不健康的根因** |
| `curl http://localhost:11434/api/tags` (host) | 返回 `nomic-embed-text:latest` | 容器把 11434 已映射到 host，端口可通 |
| `python httpx.post http://localhost:11434/api/embeddings` (host) | 200 + 768 维向量 | Ollama embedding 端点完全 OK |
| `GET /api/v1/settings/llm-health` | `{"status":"ok","provider":"ollama","base_url":"http://localhost:11434","models":["nomic-embed-text:latest"]}` | 后端用 `llm_base_url=http://localhost:11434` 调得到 Ollama |
| `GET /api/v1/settings/ai-models` | `id=2: provider=ollama, model_type=embedding, base_url=http://ollama:11434, is_default=true` | ⚠️ **根因**：DB 这条 embedding 配的 base_url 是 Docker 网络名 |
| `POST /api/v1/settings/ai-models/2/test` (改前) | `500 测试连接时发生未知错误: Server disconnected without sending a response.` | uvicorn 调 `http://ollama:11434`，host 解析不到 `ollama` 主机名 |
| `PUT base_url=http://localhost:11434` → 再测 | `200 {"status":"ok","dimension":768}` | 改完之后立即通 |

**根因（最关键的一条）**：
DB 里早就有一条 `provider=ollama / model_type=embedding / base_url=http://ollama:11434` 的
默认配置（创建于 2026-05-28）。当初为了在 Docker 中跑 backend，docker-compose.yml 里把
`backend.environment.OLLAMA_BASE_URL` 写成了 `http://ollama:11434`，并通过 main.py 的
`ai_model_configs` 启动初始化把 LLM 配置塞进 DB（[main.py:113-129](file:///d:/project/trae_projects/scdc/backend/app/main.py#L113)）。
但那条 embedding 配置很可能是在 backend 容器化模式下被同步上去的。**当下后端切换回
host uvicorn 模式后，那条配置的 host 部分就再也无法解析 `ollama` 这个 Docker 网络名了**。

**连锁影响**：
- [EmbeddingService._ensure_db_config](file:///d:/project/trae_projects/scdc/backend/app/services/embedding.py#L17) 优先用 DB 的 base_url，DB 那条坏了 → 永远拿不到 embedding → 降级空向量
- [test_ai_model](file:///d:/project/trae_projects/scdc/backend/app/api/routes/settings.py#L322) 把"连接被拒"包成 `Server disconnected` → 500

**附带问题**：
1. **Ollama 容器 healthcheck 永远 unhealthy** —— 镜像没 `curl/wget/nc`，`curl -fsS ...` 必失败；但 Ollama 进程其实正常跑（仅 docker ps 显示状态不绿，**不影响业务**）
2. **UI 缺提示** —— 用户在"添加模型"表单里看到 placeholder `http://localhost:11434`，但 DB 旧配置是 `http://ollama:11434`，两者混着，新人不知道该用哪个
3. **错误信息不友好** —— 500 `Server disconnected` 完全没有可操作提示
4. **自动迁移逻辑隐患** —— [main.py:113-129](file:///d:/project/trae_projects/scdc/backend/app/main.py#L113) 启动时如果 `llm_base_url` 在 .env 中是 `http://ollama:11434`（即 Docker 模式），迁移出来的配置**在 host 模式下永远连不上**

## Proposed Changes

### 变更 1：修正 DB 中错误的 embedding 配置（最小修复，让系统立刻可用）

**操作**（一条 SQL 或通过已有 API 都可）：

把 `ai_model_configs` 表中 `id=2`（provider=ollama, model_type=embedding）的 `base_url` 字段
从 `http://ollama:11434` 改为 `http://localhost:11434`。

**为什么是 localhost**：
- 当前 ollama 容器已把 11434 端口映射到 host（`ports: 11434:11434`）
- 后端是 host uvicorn 进程，访问 host 的 11434 即访问 ollama 容器
- 改后测试连接 → 已验证返回 200 + 768 维

**为什么不动 model_name / provider / api_key**：
- `nomic-embed-text` 在 ollama 容器里已下载并就位
- `provider=ollama` 是正确的，会走 [settings.py:396-403](file:///d:/project/trae_projects/scdc/backend/app/api/routes/settings.py#L396) 的 Ollama 原生端点
- `api_key` 字段是 ollama 端无意义（后续 [settings.py:337](file:///d:/project/trae_projects/scdc/backend/app/api/routes/settings.py#L337) 把它当 Bearer 加也会被忽略）

**通过 API 的等价操作**（SQL 路径也允许）：
```http
PUT /api/v1/settings/ai-models/2
Content-Type: application/json
Authorization: Bearer <admin_token>
{"base_url": "http://localhost:11434", "api_key": ""}
```
（`api_key=""` 触发 [settings.py:233-237](file:///d:/project/trae_projects/scdc/backend/app/api/routes/settings.py#L233) 的"清空 api_key"分支，把误存的 gpustack key 也清掉）

### 变更 2：修 Ollama 容器 healthcheck（让 docker ps 状态变绿）

**文件**：[docker-compose.yml](file:///d:/project/trae_projects/scdc/docker-compose.yml) 第 185-190 行 + [docker-compose.infra.yml](file:///d:/project/trae_projects/scdc/docker-compose.infra.yml) 第 176-181 行

**当前**：
```yaml
healthcheck:
  test: ["CMD-SHELL", "curl -fsS http://localhost:11434/api/tags || exit 1"]
  interval: 10s
  timeout: 5s
  retries: 10
  start_period: 30s
```

**改为**：
```yaml
healthcheck:
  test: ["CMD-SHELL", "pgrep -f 'ollama serve' >/dev/null || exit 1"]
  interval: 10s
  timeout: 5s
  retries: 10
  start_period: 30s
```

**为什么**：刚刚已确认 ollama 镜像里有 `pgrep`；用 `pgrep -f 'ollama serve'` 比端口检测更准确（端口监听但模型没拉完也算不健康——但 `ollama list` 调用在镜像里需要交互，简化用进程检测即可）。

**为什么不用 ollama 自带 CLI 检测**：`ollama list` 在镜像里能用但会输出大量日志且退出码总为 0；`pgrep` 简单直接。

### 变更 3：让 test_ai_model 错误信息更友好

**文件**：[backend/app/api/routes/settings.py](file:///d:/project/trae_projects/scdc/backend/app/api/routes/settings.py)

在 [settings.py:532-535](file:///d:/project/trae_projects/scdc/backend/app/api/routes/settings.py#L532) 的兜底 `except Exception` 块里，把 `httpx` 抛的 `RemoteProtocolError` / `ServerDisconnected` / `ConnectError` 区分出来，给出"是不是填了 Docker 网络名"这种可操作提示：

```python
except httpx.RemoteProtocolError as e:
    raise HTTPException(
        status_code=502,
        detail=(
            f"连接被对端关闭：'{base_url}' 看起来不通。"
            f"如果是 Docker 部署的 backend 容器，base_url 应填 Docker 网络名（如 'http://ollama:11434'）；"
            f"如果是 host 上跑的 uvicorn，应填 'http://localhost:11434'。"
        ),
    )
```

**为什么**：当前 500 "Server disconnected" 让用户完全没法判断是 URL 错、模型错还是网络错。

### 变更 4：UI 加"部署模式说明"提示

**文件**：[frontend/src/views/AiModelsView.vue](file:///d:/project/trae_projects/scdc/frontend/src/views/AiModelsView.vue)

在"添加模型"对话框的 `base_url` 输入框下方加一行 helper text：

```html
<el-form-item label="服务地址" required>
  <el-input v-model="formData.base_url" placeholder="例如: http://localhost:11434" />
  <div class="form-hint">
    后端以 host uvicorn 启动时填 <code>http://localhost:11434</code>；
    后端在 Docker 容器内启动时填 <code>http://ollama:11434</code>（Docker 网络名）
  </div>
</el-form-item>
```

并在 `<style scoped>` 加：
```css
.form-hint { font-size: 12px; color: var(--scdc-ink-soft); margin-top: 4px; line-height: 1.5; }
.form-hint code { background: var(--scdc-bg-sunken); padding: 1px 4px; border-radius: 3px; font-family: monospace; }
```

**为什么**：用户已经踩过这个坑（之前的 .env / DB 配置混着 `ollama` 和 `localhost`），避免下次再踩。

### 变更 5：.env 加注释 + 调整 OLLAMA_BASE_URL（已部分就位）

**文件**：[backend/.env](file:///d:/project/trae_projects/scdc/backend/.env)

当前已经写好注释（line 31-34）说明 host / docker / 混部三种模式。当前值 `OLLAMA_BASE_URL=http://localhost:11434` 与当前 host uvicorn 模式匹配，**保持不变**。仅追加一行强提示：

```ini
# ⚠️ 启动 backend 模式决定此处值：
#   1) uvicorn app.main:app --reload (host)   → http://localhost:11434
#   2) docker compose up -d backend (容器内)   → http://ollama:11434
# ⚠️ 同步检查 DB 中 ai_model_configs (id=2 embedding) 的 base_url 必须与模式一致！
OLLAMA_BASE_URL=http://localhost:11434
```

**为什么**：这个值是 llm-health、EmbeddingService 兜底、main.py 启动时迁移 LLM 配置到 DB 时的来源；写错会被同步污染 DB。

### 变更 6：启动迁移逻辑加固（防御性，避免下次再出同样问题）

**文件**：[backend/app/main.py](file:///d:/project/trae_projects/scdc/backend/app/main.py) 第 113-129 行

**当前逻辑**：
```python
if count == 0:
    rumtime_config._ensure_loaded()
    provider = rumtime_config.get("llm_provider", "")
    base_url = rumtime_config.get("llm_base_url", "")  # 可能是 ollama:11434
    ...
    INSERT INTO ai_model_configs (provider, model_name, model_type, base_url, api_key, is_default)
    VALUES (:provider, :model_name, 'llm', :base_url, :api_key, TRUE)
```

**问题**：迁移时把 `.env` 中的 `llm_base_url` 原样塞进 DB；如果该值是 `http://ollama:11434`，以后在 host 模式启动时这条配置就用不了。

**修复**：在 `INSERT` 之前做一次连通性探测——用 `httpx.AsyncClient` 试 `GET {base_url}/api/tags`，5 秒超时；不通则跳过迁移（让用户后续在 UI 里手动加）。同时加日志说明。

```python
import httpx as _httpx
try:
    async with _httpx.AsyncClient(timeout=5) as _client:
        _probe = await _client.get(f"{base_url.rstrip('/')}/api/tags")
        if _probe.status_code != 200:
            logger.warning("llm_base_url '%s' 不通 (HTTP %d)，跳过自动迁移到 ai_model_configs", base_url, _probe.status_code)
            return
except Exception as _e:
    logger.warning("llm_base_url '%s' 连通性探测失败: %s；跳过自动迁移到 ai_model_configs", base_url, _e)
    return
# 再 INSERT
```

**为什么**：当前 count=0 时才迁移；DB 中已有 4 条 LLM/embedding/rerank 配置（id=1,2,4,5），count 早已非 0，**本轮不会触发**；但重启 backend 时 count 会变化（被清空 → 触发），避免再次把错误 URL 塞进去。

**为什么不在 settings 端做兼容**：base_url 错误的根本责任在配置，不应在服务侧做 DNS 重写（那会掩盖更多问题）。

## Impact

- **Affected files**：
  - `docker-compose.yml`（line 185-190）—— healthcheck
  - `docker-compose.infra.yml`（line 176-181）—— healthcheck
  - `backend/app/api/routes/settings.py`（line 532-535 区域）—— 错误信息分类
  - `backend/app/main.py`（line 113-129）—— 启动迁移连通性探测
  - `backend/.env`（line 31-37）—— 注释强化
  - `frontend/src/views/AiModelsView.vue`（line 567-572）—— helper text
- **DB**：通过 API / SQL 修改 id=2 的 base_url
- **影响范围**：仅影响"embedding 模型连接"和"Ollama docker 状态显示"两处业务
- **不影响**：其他 LLM (gpustack)、rerank、其他 ai-models 配置

## Assumptions & Decisions

1. **不切换部署模式** —— 用户当前是 host uvicorn + docker 跑 ollama 的混部模式（[.env:34](file:///d:/project/trae_projects/scdc/backend/.env#L34) 第三种）；保持该模式，不切回纯 docker compose（避免引入更多变更）
2. **改 DB 配置优先于改代码** —— DB 里有错配就先修 DB；本计划的变更 3-6 都是预防性加固，不依赖它们也能让系统立即可用
3. **不删旧配置重建** —— 直接改 id=2 保留 created_at/updated_at 历史；后续若用户切回 docker backend 可手工改回
4. **不改 provider 字段** —— `provider=ollama` 正确；只改 base_url
5. **不引入新依赖** —— pgrep / httpx / FastAPI 已都有
6. **不修 ollama_data 卷** —— `nomic-embed-text` 274MB 已下载，卷正常工作

## Verification

### 第一步：变更 1 立即验证（已完成于排错阶段）

```bash
PUT /api/v1/settings/ai-models/2  body={"base_url":"http://localhost:11434","api_key":""}
→ 200 OK
POST /api/v1/settings/ai-models/2/test
→ 200 {"status":"ok","dimension":768}      ← 通过
```

### 第二步：变更 2 验证（docker compose 重启后）

```bash
docker compose restart ollama
# 等待 start_period 30s
docker ps --filter name=scdc_ollama --format "{{.Names}}\t{{.Status}}"
# 期望：scdc_ollama   Up X minutes (healthy)
```

### 第三步：变更 3 验证（错误信息更友好）

临时把 id=2 的 base_url 改回 `http://ollama:11434`（触发错误），点测试：
```bash
POST /api/v1/settings/ai-models/2/test
→ 502 {"detail":"连接被对端关闭：'http://ollama:11434' 看起来不通。如果是 Docker 部署的 backend 容器，base_url 应填 Docker 网络名（如 'http://ollama:11434'）；如果是 host 上跑的 uvicorn，应填 'http://localhost:11434'。"}
```
再改回 `http://localhost:11434` 验证仍 OK。

### 第四步：变更 4 验证（UI 提示）

打开 http://localhost:8888 → 系统设置 → AI 模型配置 → Embedding 标签 → 添加模型，
看到 base_url 下方出现两行 helper text。

### 第五步：变更 5 验证

打开 `backend/.env` 看到 OLLAMA_BASE_URL 上方加粗的 ⚠️ 注释。

### 第六步：端到端 workflow 验证（最重要）

1. 打开前端 → 创建工作流，topic="2025年AI芯片市场趋势"
2. 触发工作流，等完成
3. 查 backend 日志：
   ```
   grep "Retrieved.*vector hits" backend/startup.log
   ```
   **期望**：出现 `Retrieved N vector hits, reranked to 3 context snippets`（不再 silently 失败）
4. 打开报告详情 → 看到基于历史 context 的高质量摘要

## Implementation Order

1. **变更 1**（最关键，立即可执行）：通过 API 改 id=2 base_url
2. **变更 2**：改 docker-compose 两个文件的 healthcheck → `docker compose restart ollama`
3. **变更 3**：settings.py 加 RemoteProtocolError 分类
4. **变更 4**：AiModelsView.vue 加 helper text
5. **变更 5**：.env 注释强化
6. **变更 6**：main.py 启动迁移连通性探测
7. 端到端 workflow 验证

## Risk & Rollback

- 变更 1 是 DB 修改，回滚只需把 base_url 改回 `http://ollama:11434`
- 变更 2 只影响 healthcheck，Ollama 容器重启失败也只影响"docker ps 状态"，业务不受影响
- 变更 3-6 都是加性变更，回滚即删除对应代码块
