# 在 Docker 中添加 Ollama 服务并修复 Embedding 模型管理

## Why

用户报告：① 以为 `docker-compose.yml` 里已经部署了 Ollama，可以用作 embedding 模型；
② 在系统设置 → AI 模型配置页添加 embedding 模型后，点"测试连接"返回
`请求失败 (502): 无法连接到服务 'http://localhost:11434'，请检查服务地址和网络`。

经代码审计发现 docker-compose 中实际**没有任何 ollama 服务**，后端默认走 GPUStack
远程服务（`http://120.79.96.231:6003`）。"Ollama 在 Docker 中"是用户的误解，需要
在 docker-compose 中真正添加一个 ollama 服务，并修复几个连带 bug。

## Current State Analysis（基于代码审计的关键发现）

| 问题 | 位置 | 影响 |
|------|------|------|
| 1. **docker-compose 无 ollama 服务** | [docker-compose.yml](file:///d:/project/trae_projects/scdc/docker-compose.yml) (整文件) | 用户期望的"Ollama in Docker"不存在；后端无 Ollama 容器可连 |
| 2. **测试连接端点不对 Ollama 区分** | [settings.py:393-435](file:///d:/project/trae_projects/scdc/backend/app/api/routes/settings.py#L393) `test_ai_model` 的 `elif config.model_type == "embedding"` 分支 | 不论 `provider` 是 ollama 还是 gpustack，**总是** POST `/v1/embeddings`（OpenAI 格式）。Ollama < 0.1.32 不支持该端点；且当 `provider=ollama` 时还应走 `/api/embeddings`（Ollama 原生格式） |
| 3. **测试连接端点 502 ConnectError** | [settings.py:485-489](file:///d:/project/trae_projects/scdc/backend/app/api/routes/settings.py#L485) | 抛出 `httpx.ConnectError` 时返回 502 + 通用文案，未说明 "Docker 内未启动 ollama" 或 "base_url 错" 的具体原因 |
| 4. **EmbeddingService 兜底用错 provider** | [embedding.py:14](file:///d:/project/trae_projects/scdc/backend/app/services/embedding.py#L14) `self.provider = (provider or settings.llm_provider).lower()` | 当用户在 DB 中存了 `provider=ollama` 的 embedding 配置但**没有 is_default=true** 时，`_ensure_db_config()` 走 DB 路径正常；但若 DB 无该类型默认配置，则回退到 `settings.llm_provider="gpustack"`，而 `ollama_base_url` 也被当成通用 base_url 复用，命名误导 |
| 5. **OLLAMA_BASE_URL 命名误导** | [config.py:35](file:///d:/project/trae_projects/scdc/backend/app/core/config.py#L35) | 变量名暗示只能指向 Ollama，实际 GPUStack 也在用。`runtime_config.py:17` 直接用 `settings.ollama_base_url` 兜底，含义错位 |
| 6. **Ollama 模型未预下载** | 镜像用 `ollama/ollama:latest` 时不会自动下载模型 | 容器起来了但 `nomic-embed-text` 等模型不在，第一次调用会失败 |
| 7. **测试端点不验证 model 存在** | [settings.py:393-435](file:///d:/project/trae_projects/scdc/backend/app/api/routes/settings.py#L393) | 调用 `/v1/embeddings` 时若模型名拼写错，Ollama 会 200 + 空 data 数组，校验通过但实际不可用 |
| 8. **.env 中 OLLAMA_BASE_URL=localhost:11434** | [backend/.env:31](file:///d:/project/trae_projects/scdc/backend/.env#L31) | 在 Docker backend 容器内，`localhost` = 容器自身，**不是宿主**；必须用 `http://ollama:11434` 或宿主 IP |

## Proposed Changes

### 变更 1：docker-compose.yml 添加 ollama 服务

**文件**：[docker-compose.yml](file:///d:/project/trae_projects/scdc/docker-compose.yml)

在 `services:` 内（建议放在 `minio` 之后、`opensearch` 之前）新增：

```yaml
  # Ollama：本地 LLM 推理 + Embedding 服务
  ollama:
    image: ollama/ollama:latest
    container_name: scdc_ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama       # 持久化已下载的模型
    networks:
      - scdc_net
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://localhost:11434/api/tags || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s
    restart: unless-stopped
```

在 `volumes:` 段加入：
```yaml
  ollama_data:        # Ollama 镜像持久化（避免每次重建下载模型）
```

在 `backend.environment:` 中修改：
- `OLLAMA_BASE_URL: "http://localhost:11434"` → `OLLAMA_BASE_URL: "http://ollama:11434"`
- 新增 `EMBEDDING_MODEL: "nomic-embed-text"`
- 移除 docker-compose.yml:184 的 SerpAPI key（已用 DDGS 替代）；可选

在 `backend.depends_on:` 块加入：
```yaml
      ollama:
        condition: service_healthy
```

**为什么这样设计**：
- `ollama_data` 卷：避免重建容器时重新下载 1GB+ 的模型
- healthcheck 用 `/api/tags`（Ollama 列出本地模型）：容器起来后 Ollama 进程 ready 才算健康
- backend env 用 `http://ollama:11434`（Docker 网络名）：从 backend 容器到 ollama 容器的内部 DNS

### 变更 2：docker-compose.infra.yml 同步添加 ollama 服务

**文件**：[docker-compose.infra.yml](file:///d:/project/trae_projects/scdc/docker-compose.infra.yml)

在文件中重复变更 1 的 ollama service 定义，使本地基础设施 compose 也能起 Ollama。

### 变更 3：后端 .env 调整 OLLAMA_BASE_URL

**文件**：[backend/.env](file:///d:/project/trae_projects/scdc/backend/.env)

```diff
- OLLAMA_BASE_URL=http://localhost:11434
+ OLLAMA_BASE_URL=http://ollama:11434   # Docker 内部网络名
```

**为什么**：本地用 `uvicorn app.main:app --reload` 时，backend 跑在 host；`localhost` 指向 host。
此时本机需要 `ollama serve` 监听 11434，或改 `http://host.docker.internal:11434`（Docker Desktop 特性）。
**但** 既然用户是 Docker compose 起后端，所以默认改成 `http://ollama:11434`；如果是 host 模式启动后端，再覆盖为 `localhost` 即可。

### 变更 4：修复 test_ai_model 端点对 ollama 的兼容

**文件**：[backend/app/api/routes/settings.py](file:///d:/project/trae_projects/scdc/backend/app/api/routes/settings.py)

修改 `test_ai_model` 函数 [settings.py:322-435](file:///d:/project/trae_projects/scdc/backend/app/api/routes/settings.py#L322) 的 `elif config.model_type == "embedding"` 分支：

- 根据 `config.provider` 路由到不同端点：
  - `provider == "ollama"` → POST `{base_url}/api/embeddings`，payload `{"model": ..., "prompt": "test"}`（Ollama 原生）
  - `provider == "gpustack"` (或 OpenAI 兼容) → 保持 `/v1/embeddings` + `{"input": [...], "model": ...}`
- 增加响应体校验：必须 `data["embedding"]` 或 `data["data"][0]["embedding"]` 存在且长度 > 0；为空则 502 + 明确提示
- 增加预先 `GET {base_url}/api/tags`（Ollama）或 `GET {base_url}/v1/models`（OpenAI）校验模型是否存在；不存在则 404 + 模型列表建议

**伪代码**：
```python
elif config.model_type == "embedding":
    provider = (config.provider or "ollama").lower()
    if provider == "ollama":
        # 1) 校验模型存在
        await _check_model_exists_ollama(client, base_url, config.model_name)
        # 2) 原生调用
        resp = await client.post(
            f"{base_url}/api/embeddings",
            json={"model": config.model_name, "prompt": "test"},
            headers=headers,
        )
        data = resp.json()
        embedding = data.get("embedding", [])
    else:  # gpustack / openai
        # 1) 校验模型存在
        await _check_model_exists_openai(client, base_url, headers, config.model_name)
        # 2) OpenAI 调用
        resp = await client.post(
            f"{base_url}/v1/embeddings",
            json={"input": ["test"], "model": config.model_name},
            headers=headers,
        )
        data = resp.json()
        embedding = data["data"][0].get("embedding", [])

    if not embedding:
        raise HTTPException(502, f"Embedding 返回空向量，模型 '{config.model_name}' 可能未拉取或损坏")
    return success_response(data={"status": "ok", "dimension": len(embedding)})
```

### 变更 5：修复 EmbeddingService 兜底 provider 逻辑

**文件**：[backend/app/services/embedding.py](file:///d:/project/trae_projects/scdc/backend/app/services/embedding.py)

问题在第 14 行 `self.provider = (provider or settings.llm_provider).lower()` 与第 35-38 行的 `_embed_*` 分发不一致：
- `llm_provider` 默认为 `"ollama"` → 当 DB 无默认 embedding 配置时，service 自认是 ollama
- 但 `llm_base_url` 实际指向 GPUStack 端点 → 调用 Ollama 端点失败

修改：
- 第 11-12 行：`self.base_url = (base_url or settings.ollama_base_url).rstrip('/')` → 改为更明确的 `self.base_url = ...`
- 第 14 行：增加注释说明 `llm_provider` 兜底行为
- 第 35 行：把分发从"if ollama, else gpustack"改为"if gpustack, else 假定是 ollama 兼容端点"（向后兼容）

**为什么**：`auto` 路径走 Ollama 原生 `/api/embeddings`（包括 Ollama < 0.1.32）；新版本 Ollama 同时支持 `/v1/embeddings`，但若用户配置 `provider=ollama` + `base_url=http://ollama:11434`，应走原生端点避免协议版本探测。

### 变更 6：明确 OLLAMA_BASE_URL 的语义（命名调整）

**文件**：[backend/app/core/config.py](file:///d:/project/trae_projects/scdc/backend/app/core/config.py)

把变量名从 `ollama_base_url` 改为 `model_base_url` 或加 alias 兼容：

```python
ollama_base_url: str = "http://localhost:11434"  # 向后兼容（deprecated，建议改用 model_base_url）
model_base_url: str = "http://localhost:11434"    # 通用 LLM/embedding 服务地址
```

并在 `runtime_config.py:17` 同时支持新旧名字。

**或者更简单**：只改注释说明，变量名保持（避免破坏太多点引用）。

### 变更 7：编写初始化 Ollama 模型的脚本

**文件**：`docker/ollama/init-models.sh`（新建）

```bash
#!/bin/sh
# 在 ollama 容器启动后，自动拉取项目所需模型
set -e
echo "Pulling embedding model: nomic-embed-text"
ollama pull nomic-embed-text
echo "Pulling LLM model: qwen2.5:7b (optional)"
# ollama pull qwen2.5:7b
echo "All models pulled."
```

在 `docker-compose.yml` 的 `ollama` service 加：
```yaml
    entrypoint: ["/bin/sh", "-c"]
    command: >
      "ollama serve &
       sleep 5 &&
       ollama pull nomic-embed-text &&
       wait"
```

**为什么**：避免用户第一次跑 pipeline 时才下载模型（首调用 60s+ 卡顿）。

## Impact

- **Affected specs**：与 `ai-model-config-management`、`fix-intent-integration-and-report-save` 关联
- **Affected code**：
  - [docker-compose.yml](file:///d:/project/trae_projects/scdc/docker-compose.yml) — +ollama service / +volume
  - [docker-compose.infra.yml](file:///d:/project/trae_projects/scdc/docker-compose.infra.yml) — +ollama service
  - [backend/.env](file:///d:/project/trae_projects/scdc/backend/.env) — OLLAMA_BASE_URL
  - [backend/app/api/routes/settings.py](file:///d:/project/trae_projects/scdc/backend/app/api/routes/settings.py) — test_ai_model
  - [backend/app/services/embedding.py](file:///d:/project/trae_projects/scdc/backend/app/services/embedding.py) — provider 分发
  - [backend/app/core/config.py](file:///d:/project/trae_projects/scdc/backend/app/core/config.py) — 命名注释
  - `docker/ollama/init-models.sh`（新文件）— 预拉模型

## Assumptions & Decisions

1. **不重新部署 GPUStack** — 用户已选 Docker 中加 Ollama；GPUStack 保留为 LLM 后端（性能更好），Ollama 仅用于本地 embedding（避免 API 配额）
2. **Ollama 镜像用 `:latest`** — 用户后续可通过 `ollama pull` 拉其他模型；`:latest` 跟随官方更新
3. **不破坏 GPUStack 路径** — 现有 `provider=gpustack` 的 LLM/embedding 配置保持兼容
4. **测试端点改造** — 仅 `test_ai_model` 改 `provider` 路由；不引入新公共接口

## Verification

1. **docker compose up -d** 后 `docker ps | grep ollama` 看到 scdc_ollama 健康
2. **curl http://localhost:11434/api/tags** 返回 200 + models 数组
3. **curl http://localhost:11434/api/embeddings -d '{"model":"nomic-embed-text","prompt":"test"}'** 返回 embedding 向量
4. **打开 AI 模型配置页 → 添加 embedding 模型**（provider=ollama, base_url=http://ollama:11434, model=nomic-embed-text, api_key 留空）→ 点"测试连接" → 看到 "连接成功！向量维度: 768"
5. **点"设为默认"** → 触发一次 workflow（topic="2025年AI芯片市场趋势"）→ analyzer.py 调 EmbeddingService 不再降级返回空
6. **健康检查端点**：`GET /api/v1/settings/llm-health` → `provider=ollama, base_url=http://ollama:11434, models=[..., nomic-embed-text]`

## Implementation Order

1. 先改 [docker-compose.yml](file:///d:/project/trae_projects/scdc/docker-compose.yml) + [docker-compose.infra.yml](file:///d:/project/trae_projects/scdc/docker-compose.infra.yml) + [backend/.env](file:///d:/project/trae_projects/scdc/backend/.env) — 起 Ollama 容器
2. 重启 backend 容器 `docker compose up -d --force-recreate backend`
3. 改 [settings.py](file:///d:/project/trae_projects/scdc/backend/app/api/routes/settings.py) test_ai_model 端点 — 让测试连接支持 ollama
4. 改 [embedding.py](file:///d:/project/trae_projects/scdc/backend/app/services/embedding.py) — provider 分发修正
5. 真实端到端验证：UI 添加配置 → 测试连接 → 触发 workflow
