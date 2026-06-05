# 工作流 RAG 使用分析

## Why
用户提问"crm系统是什么"后，发现系统没有从向量数据库检索内容，直接调用了 LLM 回答。用户质疑工作流是否在使用向量数据库进行 RAG。

## 分析结论

**当前系统中 RAG 已被使用，但仅在工作流分析阶段（AnalyzerAgent），不在一般问答（DirectResponseService）中。**

### RAG 链路（当前实现）

```
工作流执行 → Orchestrator → AnalyzerAgent.execute()
    ↓
VectorStoreService.search()  ← 用 Milvus 向量库检索历史报告
    ↓
RerankService.rerank()       ← 对检索结果重排序
    ↓
context_snippets 注入 AnalyzerAgent 的 LLM prompt
    ↓
LLM 生成分析结果（结合历史报告背景 + 新采集数据）
```

关键代码位置：[analyzer.py](file:///c%3A/Users/U0015856/Documents/trae_projects/scdc/backend/app/agents/analyzer.py#L238-L256)

```python
# AnalyzerAgent.execute() 中的 RAG 逻辑：
vectorstore = VectorStoreService()
if vectorstore.collection_exists():
    embedding_service = EmbeddingService()
    embeddings = await embedding_service.embed_texts_or_empty([input_data.topic])
    if embeddings and embeddings[0]:
        hits = vectorstore.search(embeddings[0], top_k=20)
        if hits:
            documents = [hit.get("text", "") for hit in hits]
            rerank_service = RerankService()
            reranked = await rerank_service.rerank(input_data.topic, documents)
            top_indices = [r["index"] for r in reranked[:3]]
            context_snippets = [documents[i] for i in top_indices]
```

### 一般问答（DirectResponseService）

当前直接调用 LLM，**不使用 RAG**：
1. 构造 system prompt + conversation history
2. 直接请求 GPUStack/Ollama LLM API
3. 流式返回结果

关键代码位置：[direct_response.py](file:///c%3A/Users/U0015856/Documents/trae_projects/scdc/backend/app/services/direct_response.py#L95-L115)

### 向量库写入

向量库数据来自工作流生成的报告：[workflow.py](file:///c%3A/Users/U0015856/Documents/trae_projects/scdc/backend/app/services/workflow.py#L244-L266)

报告生成后，report markdown 被切块（chunk）后写入 Milvus 向量库，供后续工作流分析的 RAG 检索使用。

## 用户提问 "crm系统是什么" 的实际流程

```
用户输入: "crm系统是什么"
    ↓
IntentClassifier 分类 → general_question (confidence=0.95)
    ↓
DirectResponseService.generate_response_stream()
    ↓  (不使用 RAG，直接调 LLM)
GPUStack LLM API → 流式返回
    ↓
前端显示
```

**日志印证**：
- ✅ `Intent classification result: general_question, confidence=0.95`
- ✅ `DirectResponseService generating response for: 'crm系统是什么...'`
- ❌ 无任何向量检索相关日志（search、rerank、embedding）

## What Changes

当前实现符合架构设计意图：
- **工作流分析阶段**：使用 RAG 检索历史报告，为市场洞察提供背景参考
- **一般问答**：直接调用 LLM，不需要 RAG（属于通用知识问答，不依赖内部报告数据）

**建议的优化方向**（可选）：
- 如果希望一般问答也能参考内部知识库（如产品文档、术语定义等），需要在 DirectResponseService 中增加向量检索步骤
- 但当前向量库只存储工作流报告（scdc_reports），不含产品说明/术语库，因此即使加 RAG 也无数据可检索

## Impact
- 受影响的代码：direct_response.py（如选择增加 RAG）
- 受影响的组件：一般问答流程
