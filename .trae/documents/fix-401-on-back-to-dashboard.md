# 修复登录后返回仪表盘报 401 错误

## Why
用户登录后从其他页面（如智能体工作流）点击导航回到仪表盘页面时，控制台报 401 Unauthorized，页面顶部弹出红色提示"认证服务暂时不可用（/api/v1/data-sources/），请重试或稍后再操作"。

经过排查（阅读 client.ts、data_sources.py、main.py、vite.config.ts、auth store）：
- 前端 axios 拦截器从 `localStorage.getItem('token')` 读取 token，并附带 `Authorization: Bearer <token>` 头
- 后端 FastAPI 路由定义：`@router.get("/")` 注册在 `prefix="/data-sources"`，完整路径 = `/api/v1/data-sources/`
- 前端 API 调用使用 `axios.get('/api/v1/data-sources', { params })`，URL **没有**结尾斜杠
- FastAPI 默认 `redirect_slashes=True`：当请求 `/api/v1/data-sources` 时，会 307 重定向到 `/api/v1/data-sources/`
- 浏览器/axios 在跨域重定向时会**丢失 Authorization 头**（即使在同源的 vite proxy 下，redirect 仍会丢头）
- 重定向后的请求没有 token，后端抛 401

**根因**：FastAPI 路由尾部斜杠重定向 + 前端调用路径无尾部斜杠 = 重定向丢 Authorization 头 → 401

此问题影响**所有**以 `"/"` 结尾的路由（包括 `data-sources`、`tasks`、`reports`、`metrics-json` 等列表接口）。

## What Changes
- 后端 `app/main.py`：在 `FastAPI(...)` 中显式设置 `redirect_slashes=False`，关闭 FastAPI 的自动斜杠重定向，避免请求路径不匹配时通过重定向（丢头）来"修复"
- 前端 `api/client.ts`：在请求拦截器中，如果 URL 以 `/api/v1/<resource>` 结尾（无尾部斜杠）且不是某个具体子路径，自动补全尾部斜杠，统一调用风格，避免与后端路由不匹配

## Impact
- Affected specs: api-trailing-slash-handling
- Affected code:
  - `backend/app/main.py`（FastAPI 实例化）
  - `frontend/src/api/client.ts`（请求拦截器）

## Risks
- 关闭 `redirect_slashes=False` 后，错误的 URL 会直接 404 而非重定向。但这是更可取的（更严格的 API 契约）
- 前端拦截器补全斜杠只对 `/api/v1/<resource>` 形式的列表/集合类 URL 生效，不会动 `/{id}`、`/path/to/file` 等具体路径

## 修复步骤

### 步骤 1：后端关闭自动斜杠重定向
- **文件**：[main.py](file:///c:/Users/U0015856/Documents/trae_projects/scdc/backend/app/main.py#L177-L182)
- **改动**：
  ```python
  app = FastAPI(
      title="SCDC API",
      description="Market Insight AI Agent API",
      version="1.0.0",
      lifespan=lifespan,
      redirect_slashes=False,  # 关闭自动斜杠重定向，避免重定向丢失 Authorization 头
  )
  ```

### 步骤 2：前端 axios 请求拦截器补全尾部斜杠
- **文件**：[client.ts](file:///c:/Users/U0015856/Documents/trae_projects/scdc/frontend/src/api/client.ts#L39-L50)
- **改动**：在请求拦截器中，如果 URL 形如 `/api/v1/<something>`（即后面没有 `/`、没有 `?`、没有 `&`、没有 `{`），则自动补全尾部斜杠
- **代码草图**：
  ```ts
  apiClient.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
      const token = localStorage.getItem('token');
      if (token && config.headers) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      // 规范化 URL：/api/v1/<resource> → /api/v1/<resource>/
      // 避免 FastAPI redirect_slashes=True 时的重定向丢头
      if (config.url) {
        const match = config.url.match(/^(\/api\/v[0-9]+\/[a-z][a-z0-9-]*)(\?.*)?$/i);
        if (match) {
          config.url = match[1] + '/' + (match[2] || '');
        }
      }
      return config;
    },
    ...
  );
  ```

## 验证步骤

1. **步骤 1 验证**：在浏览器中登录账号 → 进入仪表盘 → 观察 devtools network：
   - 请求 `GET /api/v1/data-sources/?limit=100` 应直接返回 200，**不再有 307 重定向**
2. **步骤 2 验证**：再次刷新仪表盘，观察 network：
   - 请求 URL 应该是 `/api/v1/data-sources/?limit=100`（原始 URL 已被拦截器改为带斜杠）
   - 状态码应为 200
3. **业务验证**：
   - 从仪表盘进入"智能体工作流"页面
   - 触发一次新分析
   - 等报告生成后，点击左侧导航"仪表盘"返回
   - 页面正常加载，无 401 错误提示
4. **其他页面回归**：
   - 进入"智能报告"页面，确认列表和分页正常
   - 进入"任务管理"页面，确认任务列表正常
   - 所有列表型接口（GET 集合资源）均应正常

## 不在本次修复范围
- 单个资源查询（`/api/v1/reports/{id}`）不受影响，不需修改
- 带子路径的端点（`/api/v1/data-sources/{id}/sync`）不受影响，不需修改
- 已存在但调用方式正确的接口（如 `/api/v1/reports/statistics`）不受影响
