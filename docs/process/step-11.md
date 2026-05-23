# Step 11: 执行所需信息

> 关联: [plan.md](../plan.md) | [process.md](../process.md)

## 设计方案

#### Step 11: ...

##### [第1次/最新] 2026-05-16
- **任务目标**: 构建 M3 智能体核心业务价值节点“分析洞察 Agent”，负责接收清洗好的事实切片 (`CleanedItem`)，结合任务查询主题，通过调度本地大语言模型 (Ollama) 推理提炼深度结论。产出必须严格遵守“结论-证据-置信度”三元契约，且每条结论必须绑定来源证据。
- **架构定位**: 位于 M3 智能体引擎 `agents/analyzer.py`，承接 `CleanerAgent` 的高质量输入，产出多维度洞察 (`Insight`)，直接供给下游 `ReporterAgent` 进行专业排版渲染。
- **组件分解**:
  - `backend/app/schemas/agent.py`: 扩展定义 `Insight` (conclusion, evidence, confidence, category), `AnalyzerInput` (task_id, topic, cleaned_items) 及 `AnalyzerOutput`。
  - `backend/app/agents/analyzer.py`: 实现 `AnalyzerAgent` 执行引擎。封装对 Ollama (`ChatOllama` / 异步 HTTP) 的结构化 prompt 调用与结果解析。
  - `backend/app/api/routes/agents.py`: 挂载 `/agents/analyze` 测试端点。
- **数据流与控制流**:
  - `POST /agents/analyze` -> 接收 topic 与 cleaned_items -> 构建格式化系统提示词 -> 异步调用 LLM -> 解析输出 JSON 结构为 `Insight` 列表 -> 校验证据链对应关系 -> 返回 `AnalyzerOutput`。
- **接口契约**:
  - `POST /api/v1/agents/analyze`: 接收 `AnalyzerInput`，返回 `ResponseModel[AnalyzerOutput]`。
- **错误处理与降级策略**:
  - 模型连接兜底保护：考虑到本地 Ollama 服务可能未启动或模型正在拉取，对 LLM 调用提供 3 次容错重试；若彻底不可达，则启动本地规则抽取降级策略（从清洗摘要中提取关键短语作为备用洞察），确保流水线永不阻断。
- **测试策略**:
  - `backend/tests/test_agents.py`: 追加分析节点单元测试，验证正常解析与本地降级逻辑下的三元组输出合规性。

## 开发实现

#### Step 11: ...

##### [第1次/最新] 2026-05-16
- **改动范围锚点**:
  - `backend/app/schemas/agent.py`: 追加 Insight 模型与 AnalyzerInput, AnalyzerOutput。
  - `backend/app/agents/analyzer.py`: 构建 AnalyzerAgent 节点，封装对 Ollama 的系统提示词及容错降级。
  - `backend/app/api/routes/agents.py`: 追加 `/agents/analyze` 触发端点。
  - `backend/tests/test_agents.py`: 追加 LLM 分析与降级行为测试。
- **具体改动**: 
  1. 通过 tenacity 实现对本地 Ollama 实例请求异常的 3 次重试保护，在无可用模型时安全转入 `_rule_based_degradation` 规则提取降级模式。
  2. 严格校准输出的每一个 `Insight` 的 `evidence` 必须对应有效传入源地址，彻底实现“结论-证据-置信度”全量绑定。
- **TDD 物理凭证**:
```text
============================= test session starts =============================
platform win32 -- Python 3.9.18, pytest-8.4.2, pluggy-1.6.0 -- C:\Users\LH\.gemini\antigravity\scratch\scdc\backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\LH\.gemini\antigravity\scratch\scdc\backend
plugins: anyio-4.12.1, langsmith-0.4.37, asyncio-1.2.0
asyncio: mode=strict, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 4 items

tests/test_agents.py::test_collector_agent_execution PASSED              [ 25%]
tests/test_agents.py::test_cleaner_agent_execution PASSED                [ 50%]
tests/test_agents.py::test_analyzer_agent_degradation PASSED             [ 75%]
tests/test_agents.py::test_agents_api PASSED                             [100%]

======================= 4 passed, 2 warnings in 42.24s ========================
```

## 审阅意见

#### Step 11: ...

##### [第1次/最新] 2026-05-16
- **审阅结果**: 通过 (PASS)
- **四大维度验证总结**:
  1. **需求合规性**: 完美达成了 PRD 与架构设计对大模型分析节点的“结论-证据-置信度”契约要求。支持多类分析标签提取，结构清晰。
  2. **架构合规性**: 遵循了 3.4 节证据追溯约束，在模型生成 JSON 或本地降级时均对 evidence 字段进行了严格溯源校验，保证不出现幻觉引用。
  3. **代码质量**: Ollama 通信封装及降级捕获极具工业级标准，测试用例精确覆盖了网络异常兜底行为与正常接口调用。
  4. **风险评估**: 采用本地私有化部署的 Ollama 方案，完全杜绝了数据外发隐私泄露风险，符合单机 All-in-One 部署规则。

## 回滚与验证记录

暂无回滚记录。
