# Step 10: 执行所需信息

> 关联: [plan.md](../plan.md) | [process.md](../process.md)

## 设计方案

#### Step 10: ...

##### [第1次/最新] 2026-05-16
- **任务目标**: 构建 M3 流水线的第二个关键智能体“数据清洗 Agent”，负责接收前置采集节点输出的未经深度加工的原始多模态素材集合，执行去重（基于 URL/内容指纹）、过滤低质短文本及噪声，同时保留完整的证据追溯链 (`source_uri`, `source_type`)。
- **架构定位**: 位于 M3 智能体引擎 `agents/cleaner.py`，承接 `CollectorAgent` 输出，为 `AnalyzerAgent` 提供高信噪比、完全结构化的有效证据事实。
- **组件分解**:
  - `backend/app/schemas/agent.py`: 扩展定义 `CleanerInput` (task_id, raw_items), `CleanedItem` (uuid, title, source_uri, summary, content_chunks, relevance_score) 及 `CleanerOutput`。
  - `backend/app/agents/cleaner.py`: 实现 `CleanerAgent` 执行引擎。包含基于文本哈希/相似度的精准去重逻辑与正文段落规范切分。
  - `backend/app/api/routes/agents.py`: 追加 `/agents/clean` 独立触发端点。
- **数据流与控制流**:
  - `POST /agents/clean` -> 传入 raw_items -> `CleanerAgent.execute` 遍历条目 -> 过滤字数极少或报错文本 -> 按 URL/内容指纹去重 -> 对长文本分段包装为 `CleanedItem` -> 返回 `CleanerOutput`。
- **接口契约**:
  - `POST /api/v1/agents/clean`: 接收 `CleanerInput`，返回 `ResponseModel[CleanerOutput]`。
- **错误处理与降级策略**:
  - 极端入参容错：当输入的 raw_items 为空或数据损坏时，安全捕获并返回包含提示信息的成功对象 (`success=True`, `cleaned_items=[]`)，保障无缝衔接。
- **测试策略**:
  - `backend/tests/test_agents.py`: 追加数据清洗测试，注入故意重复和过短的冗余数据，校验去重和追溯字段保留是否完全达标。

## 开发实现

#### Step 10: ...

##### [第1次/最新] 2026-05-16
- **改动范围锚点**:
  - `backend/app/schemas/agent.py`: 追加 CleanerInput, CleanedItem, CleanerOutput。
  - `backend/app/agents/cleaner.py`: 实现 CleanerAgent 核心节点类，执行文本指纹去重与规范分块。
  - `backend/app/api/routes/agents.py`: 追加 `/agents/clean` 触发接口。
  - `backend/tests/test_agents.py`: 编写数据清洗单元测试。
- **具体改动**: 
  1. 通过 md5 文本内容指纹和 URI 双重检验，实现了精准、快速的重复噪音过滤。
  2. 实现了文本智能分块 (`_chunk_text`)，且对所有产出的 `CleanedItem` 严格绑定 `source_uri` 与 `source_type`，保证 100% 满足架构级证据追溯约束。
- **TDD 物理凭证**:
```text
============================= test session starts =============================
platform win32 -- Python 3.9.18, pytest-8.4.2, pluggy-1.6.0 -- C:\Users\LH\.gemini\antigravity\scratch\scdc\backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\LH\.gemini\antigravity\scratch\scdc\backend
plugins: anyio-4.12.1, langsmith-0.4.37, asyncio-1.2.0
asyncio: mode=strict, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 3 items

tests/test_agents.py::test_collector_agent_execution PASSED              [ 33%]
tests/test_agents.py::test_cleaner_agent_execution PASSED                [ 66%]
tests/test_agents.py::test_agents_api PASSED                             [100%]

======================= 3 passed, 2 warnings in 27.25s ========================
```

## 审阅意见

#### Step 10: ...

##### [第1次/最新] 2026-05-16
- **审阅结果**: 通过 (PASS)
- **四大维度验证总结**:
  1. **需求合规性**: 完美构建了数据清洗过滤与文本分段管道，有效剔除了爬虫及搜索产生的重复噪声文本，并保留了优质信息。
  2. **架构合规性**: 严格遵循了架构约定的 3.4 节证据追溯约束，对所有清洗后的分块都不可磨灭地绑定了 `source_uri` 与 `source_type`，为上层可解释性分析提供了绝对的证据支撑。
  3. **代码质量**: 实现了纯 Python 哈希比对与智能换行分块计算，算法精炼高效，测试用例精确验证了去重计数与分块提取的正确性。
  4. **风险评估**: 逻辑自洽无外部高危调用，内存开销可控。

## 回滚与验证记录

暂无回滚记录。
