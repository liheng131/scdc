# 修复 AI 模型连接测试功能

## 问题分析

### 根本原因
当前"测试连接"功能存在以下致命缺陷，导致**即使填入编造的数据也会显示成功**：

### 后端问题

1. **test_ai_model 端点（第322-387行）**：
   - **问题 1**：使用 `success_response()` 包装所有结果，包括错误。即使连接失败，返回的 `status` 也是 `"unavailable"`，但 HTTP 状态码是 **200**（而非 4xx/5xx）
   - **问题 2**：前端代码 `handleTestConnection` 中只检查 `res.data?.status === 'ok'`，但由于后端返回的是 `success_response` 包装的数据，前端收到的是 `{ code: 0, data: { status: "unavailable", error: "..." } }`，而 `res.data` 在 axios 拦截器中已经被解包，所以实际检查的是 `{ status: "unavailable" }`，不等于 `"ok"`
   - **问题 3**：timeout 只有 10 秒，对于某些慢响应可能不够，或者反过来某些服务端返回 200 空响应也会被 `raise_for_status()` 通过
   - **问题 4**：**没有验证响应体内容** — `raise_for_status()` 只检查 HTTP 状态码，不检查 API 是否真正返回了有效的推理结果。例如某些代理/网关即使模型不存在也会返回 200

2. **缺少模型存在性验证**：
   - 测试 LLM 时只发送了 `max_tokens: 1` 的请求，但没有验证返回内容是否包含有效响应
   - 没有检查返回的 `choices` 数组是否非空
   - 没有检查返回的模型名称是否与配置一致

3. **前端错误处理问题**：
   - `handleTestConnection` 中 `testingIds.add(row.id)` 是同步操作但 `testingIds` 是 `Set` 的 reactive 包装，修改方式不正确（应该用 `testingIds.value.add()` 如果 testingIds 是 ref，或者直接用普通 Set + 触发响应式更新）

### 前端问题

4. **testingIds 响应式不正确**：
   - `const testingIds = reactive<Set<number>>(new Set())` — Vue 的 `reactive` 对 Set 的代理不完全可靠
   - `testingIds.add(row.id)` 和 `testingIds.delete(row.id)` 可能不会触发响应式更新

5. **错误提示误导用户**：
   - 当后端返回 `status: "unavailable"` 时，前端显示的是 `res.data?.error`，但由于 `success_response` 的包装方式，前端可能无法正确获取错误信息

## 修改计划

### 第一阶段：修复后端测试连接逻辑

**文件：`backend/app/api/routes/settings.py`**

1. **修改 `test_ai_model` 端点**：
   - 对 LLM 测试：不仅检查 HTTP 状态码，还要验证响应体中 `choices` 数组非空、`finish_reason` 字段存在
   - 对 Embedding 测试：验证返回的 `data` 数组非空、`embedding` 字段存在且长度 > 0
   - 对 Rerank 测试：验证返回的 `results` 数组非空
   - 区分 HTTP 错误（连接失败/超时/认证失败）和业务错误（模型不存在）
   - 失败时返回 HTTP 400/502（而非 200 + status: "unavailable"），让前端正确识别

2. **增加响应验证逻辑**：
   ```python
   # LLM 验证示例
   resp.raise_for_status()
   data = resp.json()
   if not data.get("choices"):
       raise ValueError(f"模型 '{config.model_name}' 未返回任何推理结果，可能不存在")
   if not data["choices"][0].get("message"):
       raise ValueError("推理响应格式异常")
   ```

### 第二阶段：修复前端测试逻辑

**文件：`frontend/src/views/AiModelsView.vue`**

3. **修复 `testingIds` 响应式**：
   - 改用 `ref<Set<number>>(new Set())`，修改时用 `testingIds.value.add()` / `testingIds.value.delete()`
   - 或使用普通 Set + 独立的 `ref<boolean>` 数组跟踪每个模型的测试状态

4. **修复 `handleTestConnection` 错误处理**：
   - 正确处理后端返回的 HTTP 错误（400/502）
   - 正确解析错误信息并显示给用户
   - 区分不同类型的错误（网络错误、认证错误、模型不存在、超时等）

### 第三阶段：增强用户体验

5. **前端表单增加 URL 格式校验**：
   - 添加 base_url 必须以 `http://` 或 `https://` 开头的校验
   - 添加端口号存在性提示

6. **测试结果展示优化**：
   - 测试成功时显示实际返回的模型信息
   - 测试失败时显示详细的错误诊断信息

## Impact
- Affected specs: ai-model-config-management
- Affected code:
  - `backend/app/api/routes/settings.py` — test_ai_model 端点
  - `frontend/src/views/AiModelsView.vue` — handleTestConnection + testingIds
  - `frontend/src/api/services/settings.ts` — AiModelTestResult 类型定义

## ADDED Requirements

### Requirement: 模型存在性验证
系统 SHALL 在测试连接时验证模型实际存在并可正常推理，而非仅检查 HTTP 状态码。

#### Scenario: 模型不存在
- **WHEN** 用户测试一个不存在的模型
- **THEN** 返回明确的错误提示 "模型 'xxx' 不存在"

#### Scenario: 模型存在但 API Key 无效
- **WHEN** 用户测试一个存在但 API Key 无效的模型
- **THEN** 返回明确的错误提示 "认证失败" 或 "API Key 无效"

#### Scenario: 连接超时
- **WHEN** 用户测试一个无法连接的服务地址
- **THEN** 返回明确的错误提示 "连接超时，请检查服务地址"

### Requirement: 响应体验证
系统 SHALL 验证各类模型的响应格式是否符合预期：
- LLM：验证 `choices` 数组非空
- Embedding：验证 `data` 数组非空且 embedding 向量长度 > 0
- Rerank：验证 `results` 数组非空
