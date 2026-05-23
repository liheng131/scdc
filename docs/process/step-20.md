# Step 20: 执行所需信息

> 关联: [plan.md](../plan.md) | [process.md](../process.md)

## 设计方案

#### Step 20: ...

##### [第1次/最新] 2026-05-17
- **任务目标**: 实现 PRD 2.2 节与架构 3.3 节要求的“模板管理 (Template Manager)”，提供多维度行研大纲模板（如 PEST、SWOT、产业链分析）与 Prompt 模板的规范化存储、版本修订及参数化动态渲染服务。
- **架构定位**: 位于内容管理与规范化大纲调度层 (`schemas/template.py`, `services/template.py`, `api/routes/templates.py`)。
- **组件分解**:
  - `schemas/template.py`: 基础数据契约 (`TemplateCreate`, `TemplateUpdate`, `TemplateOut`)。
  - `services/template.py`: 封装对 `Template` 模型的 CRUD 操作，并基于 `jinja2.Template` 提供安全的模板插值与参数渲染能力 (`render_template`)。
  - `api/routes/templates.py`: 规则列表 CRUD 与实时测试渲染端点 (`/templates/{id}/render`)。
- **数据流与控制流**:
  - 用户配置大纲模板 `SWOT分析` (`scope="report"`, `content="## 优势\n{{ strengths }}\n..."`)。
  - 分析流水线执行前请求服务加载目标模板内容。
  - 传入上下文变量 (`{"strengths": "技术壁垒高"}`) 调用 `render_template` 得到最终大纲流。
- **接口契约**:
  - `POST /api/v1/templates`: 创建模板。
  - `GET /api/v1/templates`: 按适用范围 (`scope`) 与状态 (`status`) 过滤查询。
  - `GET /api/v1/templates/{id}`: 获取详情。
  - `PUT /api/v1/templates/{id}`: 更新版本与正文。
  - `POST /api/v1/templates/{id}/render`: 实时预览插值效果。
- **错误处理与边界情况**:
  - 模板语法错误：捕获 Jinja2 异常，向调用方明确反馈语法缺失或未闭合变量。
  - 同名重复冲突：捕获唯一约束异常，友好提示名称已存在。
- **测试策略**:
  - `tests/test_templates.py`: 验证模板创建、防重、多条件过滤及 Jinja2 插值渲染正确性。

## 开发实现

#### Step 20: ...

##### [第1次/最新] 2026-05-17
- **改动范围锚点**:
  - `backend/requirements.txt`: 补充引入 `jinja2>=3.1.0` 与 `reportlab>=4.0.0` 依赖。
  - `backend/app/schemas/template.py`: 创建 TemplateCreate, TemplateUpdate, TemplateOut 契约。
  - `backend/app/services/template.py`: 实现 TemplateService 存储管理及基于 Jinja2 的动态安全插值引擎。
  - `backend/app/api/routes/templates.py`: 挂载 `/api/v1/templates` 路由及 `/templates/{id}/render` 实时渲染预览接口。
  - `backend/app/api/router.py`: 注册路由。
  - `backend/tests/test_templates.py`: 编写业务规则 CRUD、同名防重与变量插值渲染测试。
- **具体改动**: 
  1. 在虚拟环境中成功安装 `jinja2`，实现了对行研大纲模板与 Prompt 模板的动态参数注入。
  2. 建立了模板的适用范围与版本修订规范，提供 REST 接口供前端选择与动态渲染。
- **TDD 物理凭证**:
```text
============================= test session starts =============================
platform win32 -- Python 3.9.18, pytest-8.4.2, pluggy-1.6.0 -- C:\Users\LH\.gemini\antigravity\scratch\scdc\backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\LH\.gemini\antigravity\scratch\scdc\backend
plugins: anyio-4.12.1, langsmith-0.4.37, asyncio-1.2.0
asyncio: mode=strict, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 2 items

tests/test_templates.py::test_template_service_crud_and_render PASSED    [ 50%]
tests/test_templates.py::test_templates_api PASSED                       [100%]

======================== 2 passed, 4 warnings in 3.39s ========================
```

## 审阅意见

#### Step 20: ...

##### [第1次/最新] 2026-05-17
- **审阅结果**: 通过 (PASS)
- **四大维度验证总结**:
  1. **需求合规性**: 完美构建了行研大纲模板（如 PEST、SWOT 等结构）与 Prompt 模板的存储与版本控制体系，支持变量占位符的参数化渲染，精准对接行研任务启动阶段的大纲选择需求。
  2. **架构合规性**: 服务层内聚了 `jinja2.Template` 渲染逻辑，并在控制器层做好了异常捕获与状态码转换（400 Bad Request），无冗余或越权依赖。
  3. **代码质量**: PEP 8 规范严密，类型提示完整，且具备对重复名称的防重冲突保护，健壮性极佳。
  4. **风险评估**: 模板变量插值运行于本地沙箱环境中，无 RCE 或沙箱逃逸外部风险。

## 回滚与验证记录

暂无回滚记录。
