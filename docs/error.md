# 问题记录与经验总结

> **本文档仅供人类开发者参考，Agent 不读取此文件。** 
> 复盘时可将高频易错点提炼后加入 `tech.md` 工程约束或 `flow.md` 执行纪律中。

## 1. Docker 部署问题

### 1.1 镜像源无法访问

**问题描述**：
```
failed to do request: Head "https://docker.mirrors.ustc.edu.cn/v2/library/python/manifests/3.11-slim?ns=docker.io": EOF
```

**原因分析**：
- Docker Desktop 配置的镜像源 `docker.mirrors.ustc.edu.cn`（中科大镜像源）已失效或无法访问
- 导致无法拉取构建所需的基础镜像（python:3.11-slim、nginx:1.25-alpine、node:20-alpine）

**解决措施**：
修改 Docker Desktop 设置（Settings → Docker Engine），将 `registry-mirrors` 替换为可用的镜像源：
```json
{
  "registry-mirrors": [
    "https://docker.1ms.run",
    "https://docker.xuanyuan.me",
    "https://hub.rat.dev"
  ]
}
```

**经验总结**：
- 国内 Docker 镜像源经常变动，需要定期更新可用的镜像源列表
- 建议配置多个镜像源以提高拉取成功率
- 首次构建较慢是正常的，需要下载和编译所有依赖

### 1.2 端口 80 被占用

**问题描述**：
```
Bind for 0.0.0.0:80 failed: port is already allocated
```

**原因分析**：
- Windows 系统进程（PID 4）占用了 80 端口
- 可能是 IIS、World Wide Web Publishing Service 或其他系统服务

**解决措施**：
修改 `docker-compose.yml` 中前端端口映射，将 80 改为 8888：
```yaml
ports:
  - "8888:80"
```

**经验总结**：
- Windows 系统默认占用 80 端口的情况较常见
- 开发环境建议使用非标准端口（如 8888、3000）避免冲突

## 2. 登录功能问题

### 2.1 前端 API 路径不匹配

**问题描述**：
- 前端调用：`POST /api/v1/auth/login`
- 后端路由：`POST /api/v1/auth/login/access-token`
- 导致 404 Not Found

**原因分析**：
- 前端 `auth.ts` 中的 API 路径与后端实际路由不一致
- 后端使用 FastAPI 的 OAuth2PasswordRequestForm，标准路径为 `/login/access-token`

**解决措施**：
修改 `frontend/src/api/services/auth.ts`：
```typescript
// 修改前
const res = await apiClient.post('/api/v1/auth/login', params, ...)

// 修改后
const res = await apiClient.post('/api/v1/auth/login/access-token', params, ...)
```

### 2.2 后端返回数据格式不匹配

**问题描述**：
- 后端直接返回 `{ access_token, token_type, user }`
- 前端期望 `{ code, data: { access_token, ... }, msg }` 的统一包装格式
- 前端拦截器判断 `code !== 0` 时视为错误，导致登录响应被当作错误处理

**原因分析**：
- 后端其他 API 使用 `success_response()` 包装返回数据
- 登录 API 直接返回字典，未使用统一响应格式

**解决措施**：
修改 `backend/app/api/routes/auth.py`：
```python
from app.api.responses import success_response

@router.post("/login/access-token")
async def login_access_token(...):
    return success_response(data={
        "access_token": ...,
        "token_type": "bearer",
        "user": {...}
    })
```

### 2.3 数据库无初始用户

**问题描述**：
- 数据库中没有 admin 用户，登录时返回 "Incorrect email or password"

**原因分析**：
- 后端只有登录验证逻辑，没有创建初始用户的种子数据（seed data）
- 数据库迁移文件中也没有包含初始用户创建逻辑

**解决措施**：
创建种子脚本 `backend/scripts/seed_admin.py`：
```python
async def seed_admin_user():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with async_session_factory() as session:
        admin_user = User(
            username="admin",
            email="admin@scdc.local",
            password_hash=get_password_hash("password"),
            role=UserRole.admin,
            status="active",
        )
        session.add(admin_user)
        await session.commit()
```

执行方式：
```bash
docker exec scdc_backend python /app/scripts/seed_admin.py
```

**经验总结**：
- 项目应包含初始化脚本或迁移种子数据，确保首次部署即可使用
- 建议在应用启动时自动检查并创建默认管理员用户
- 种子数据脚本应放在 `scripts/` 目录并纳入版本控制

## 3. API 请求问题

### 3.1 FastAPI 尾斜杠 307 重定向

**问题描述**：
```
GET http://localhost:8888/api/v1/data-sources?limit=100 → 307 Temporary Redirect
GET http://localhost/api/v1/data-sources/?limit=100 → 404 Not Found
```
307 重定向到无端口的 URL，导致浏览器跟随到 80 端口而被 IIS 返回 404。

**原因分析**：
- FastAPI 路由 `@router.get("/")` 定义的实际路径为 `/api/v1/data-sources/`（带尾斜杠），无尾斜杠请求返回 307 重定向
- Nginx 配置 `proxy_set_header Host $host;` 中 `$host` 不包含端口号（仅 `localhost`）
- FastAPI 用 Host 头构造重定向 URL → `http://localhost/api/...`（默认 80 端口）
- Windows 80 端口被 IIS 占用，返回 404

**解决措施**：
1. 将 `proxy_set_header Host $host;` 改为 `proxy_set_header Host $http_host;`（含端口）
2. 添加 `proxy_redirect http://backend:8000/ /;` 处理 Docker 内部地址重定向

**经验总结**：
- Nginx 反向代理时，务必配置 `proxy_redirect` 处理源站返回的重定向
- `proxy_set_header Host $host` 有助于源站生成正确的外部 URL
- 开发环境建议统一请求路径格式（全部带或不带尾斜杠），避免 Starlette 的自动重定向

### 3.2 前端 API 请求使用错误端口

**问题描述**：
```
GET http://localhost/api/v1/data-sources/?limit=100 → 404 Not Found
```
请求发到了默认 80 端口，该端口被 Windows IIS 占用，返回 IIS 的 404 页面。

**原因分析**：
- 端口 80 被改到 8888 后，用户仍使用 `http://localhost`（默认 80 端口）访问 API
- 浏览器可能缓存了旧的端口地址

**解决措施**：
确保始终使用 `http://localhost:8888` 访问应用。必要时清理浏览器缓存。

**经验总结**：
- 浏览器缓存可能导致旧的端口地址仍然被使用
- 端口变更后建议使用隐私模式或无痕窗口测试

### 3.3 API 端点需要认证

**问题描述**：
直接访问 `http://localhost:8888/api/v1/data-sources/` 返回 401 Unauthorized。

**原因分析**：
- 数据源相关 API 端点依赖 `get_current_active_user`，必须携带有效的 JWT token
- 直接通过浏览器地址栏访问 API 不会携带认证头

**解决措施**：
先通过前端登录页面登录，前端会自动存储 token 并在后续请求中携带 Authorization 头。

**经验总结**：
- 业务 API 需要登录认证是正常的安全设计
- 测试 API 时应通过前端正常流程或使用 curl 携带 token

## 4. SearXNG 搜索 API 403 Forbidden 问题

### 4.1 JSON 格式未启用

**问题描述**：
```
Client error '403 Forbidden' for url 'http://searxng:8080/search?q=AI+chip+market&format=json&pageno=1'
```
后端调用 SearXNG 搜索 API 时持续返回 403 Forbidden。

**原因分析**：
- SearXNG 默认只启用 `html` 输出格式
- 请求 `format=json` 时，如果 json 格式未在 `search.formats` 中启用，SearXNG 会返回 403
- 这是 SearXNG 的安全设计，防止未配置的格式被滥用

**解决措施**：
在 `docker/searxng/settings.yml` 中添加 json 格式支持：
```yaml
search:
  safe_search: 0
  autocomplete: "google"
  default_lang: "zh-CN"
  max_page: 3
  formats:
    - html
    - json  # 必须启用 json 格式，否则 API 返回 403
```

**经验总结**：
- SearXNG 的 API 格式需要在配置中显式启用
- 很多公共 SearXNG 实例禁用了 json 格式，自建时必须手动启用
- 403 错误不一定来自 bot detection，可能是格式未启用

### 4.2 botdetection 配置问题

**问题描述**：
尝试通过 `botdetection: enabled: false` 禁用 bot 检测无效。

**原因分析**：
- `botdetection` 不是 settings.yml 的有效顶层配置项
- bot 检测配置应通过 `limiter.toml` 文件管理
- 当 `server.limiter: false` 时，bot 检测应该自动关闭

**解决措施**：
1. 确保 `settings.yml` 中 `server.limiter: false`
2. 如需自定义 bot 检测规则，创建 `limiter.toml` 并挂载到容器
3. 在 `limiter.toml` 中添加 Docker 网络段到 `trusted_proxies`：
```toml
[botdetection]
trusted_proxies = [
  '127.0.0.0/8',
  '::1',
  '172.16.0.0/12',  # Docker bridge 网络
  '192.168.0.0/16',
  '10.0.0.0/8',
]

[botdetection.ip_lists]
pass_ip = [
  '172.16.0.0/12',
  '192.168.0.0/16',
  '10.0.0.0/8',
]
```

**经验总结**：
- SearXNG 的配置项有严格的 schema 验证，不能随意添加
- 参考官方文档：https://docs.searxng.org/admin/searx.limiter.html
- Windows Docker 环境下 `bind_address` 必须设置为 `0.0.0.0` 而非 `127.0.0.1`

## 5. AI 模型服务配置问题

### 5.1 Ollama 服务连接配置

**问题描述**：
- 后端配置 `OLLAMA_BASE_URL=http://localhost:11434` 无法连接到模型服务
- Docker 容器内无法通过 `localhost` 访问宿主机服务

**原因分析**：
- Docker 容器内的 `localhost` 指向容器自身，而非宿主机
- 需要通过 `host.docker.internal` 访问宿主机服务
- 或使用 Docker 网络内的服务名（如 `http://ollama:11434`）

**解决措施**：
根据部署方式选择正确的 URL：
1. **本地 Ollama 服务**：`http://host.docker.internal:11434`
2. **Docker 容器内 Ollama**：`http://ollama:11434`（需在 docker-compose.yml 中定义 ollama 服务）
3. **远程 GPUStack 服务**：`http://<IP>:<PORT>`（如 `http://120.79.96.231:6003`）

**经验总结**：
- Docker 容器网络与宿主机网络是隔离的
- 使用远程模型服务时，确保网络可达（防火墙、安全组等）
- 模型名称必须与服务器上部署的模型名称完全一致

### 5.2 GPUStack 远程模型服务配置

**问题描述**：
- 配置 GPUStack 远程服务后，Docker 容器内无法通过 `host.docker.internal` 访问
- 后端 AnalyzerAgent 触发降级策略，未使用 LLM 分析

**原因分析**：
- `host.docker.internal` 在 Windows Docker Desktop 中解析到 `192.168.65.254`（Docker 网关）
- GPUStack 服务部署在公网服务器（`120.79.96.231`），需要通过公网 IP 访问
- 容器内通过 `host.docker.internal` 无法路由到公网服务器

**解决措施**：
在 `docker-compose.yml` 中直接使用 GPUStack 的公网 IP：
```yaml
OLLAMA_BASE_URL: "http://120.79.96.231:6003"  # GPUStack 远程模型服务（公网 IP）
DEFAULT_MODEL: "qwen3-vl-32b-instruct-gguf"
LLM_API_KEY: "gpustack_xxx"
LLM_PROVIDER: "gpustack"
```

**经验总结**：
- `host.docker.internal` 仅适用于访问宿主机本地服务
- 远程公网服务应直接使用公网 IP 或域名
- GPUStack 使用 OpenAI 兼容 API 格式（`/v1/chat/completions`），与 Ollama 的 `/api/generate` 不同
- 需要在代码中根据 `LLM_PROVIDER` 区分不同的 API 格式和认证方式

### 5.3 SerpAPI 替换 SearXNG 搜索引擎

**问题描述**：
- SearXNG 自部署搜索引擎无法访问外部搜索引擎（Google、DuckDuckGo 等），所有搜索结果超时
- Docker 容器内网络限制导致 SearXNG 无法正常工作

**解决措施**：
使用 SerpAPI 替代 SearXNG，直接调用 Google 搜索 API：

1. **创建 SerpAPI 服务**（`backend/app/services/serpapi.py`）：
```python
class SerpAPIService:
    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or settings.serpapi_key
        self.base_url = (base_url or "https://serpapi.com").rstrip('/')
    
    async def search(self, request: SearchRequest) -> SearchResponse:
        params = {
            "q": request.query,
            "num": 10,
            "start": (request.pageno - 1) * 10,
        }
        # 调用 SerpAPI 并解析 organic_results
```

2. **更新 CollectorAgent**（`backend/app/agents/collector.py`）：
```python
from app.services.serpapi import SerpAPIService

class CollectorAgent:
    def __init__(self):
        self.search_service = SerpAPIService()  # 替换 SearXNGService
```

3. **更新环境变量**：
```env
SERPAPI_KEY=26d6525a9b1c53ee9f08fc2c744e9e096991e4a27828693b58e404d8028a9e6a
```

4. **移除 docker-compose.yml 中的 SearXNG 服务**：
```yaml
# 移除 searxng 服务定义
# SerpAPI 无需 Docker 容器，直接通过 API 调用
```

**经验总结**：
- SerpAPI 每月有 250 次免费额度，适合测试和开发环境
- SerpAPI 返回 Google 搜索结果，质量高于 SearXNG 聚合结果
- 自部署搜索引擎（如 SearXNG）需要确保容器有外网访问权限
- API Key 必须完整，末尾不能有 `*****` 等占位符

## 6. 通用经验总结

1. **前后端接口契约**：前后端应严格约定 API 路径、请求格式、响应格式，避免不一致
2. **统一响应格式**：所有 API 应使用统一的响应包装器（如 `success_response` / `error_response`）
3. **初始化数据**：项目首次部署需要种子数据时，应提供自动化脚本
4. **Docker 镜像源**：国内环境需配置可用的 Docker 镜像源，并准备多个备选源
5. **端口规划**：开发环境避免使用系统常用端口（80、443），减少冲突概率
6. **Nginx 反向代理**：必须使用 `$http_host`（含端口）而非 `$host`（不含端口），确保后端构造的 URL 包含正确端口号；同时配置 `proxy_redirect` 处理内部地址重定向
7. **API 路径设计**：后端路由定义应保持尾斜杠一致性，或在前端统一处理路径格式
8. **SearXNG 配置**：json 格式必须显式启用，bot 检测配置需遵循官方 schema
9. **模型服务连接**：根据部署方式选择正确的 URL，注意 Docker 网络隔离
