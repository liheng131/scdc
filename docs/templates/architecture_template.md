# {{PROJECT_NAME}} — 架构文档

> **文档版本**: v1.0  
> **创建日期**: {{DATE}}  
> **最后更新**: {{DATE}}  
> **状态**: 草案 / 维护中  
> **关联文档**: [PRD](./prd.md) | [技术栈文档](./tech.md) | [分步计划](./plan.md)

---

## 1. 文档定位与维护边界

### 1.1 本文档回答的问题

- {{QUESTION_1}}
- {{QUESTION_2}}
- {{QUESTION_3}}

### 1.2 多 Agent 使用约定

| Agent | 使用方式 | 允许更新的内容 |
|------|------|------|
| 设计 Agent | {{USAGE_1}} | {{EDIT_SCOPE_1}} |
| 开发 Agent | {{USAGE_2}} | {{EDIT_SCOPE_2}} |
| 审阅 Agent | {{USAGE_3}} | {{EDIT_SCOPE_3}} |

### 1.3 文档边界

| 内容 | 应写在哪个文档 |
|------|------|
| {{CONTENT_1}} | `prd.md` |
| {{CONTENT_2}} | `architecture.md` |
| {{CONTENT_3}} | `tech.md` |
| {{CONTENT_4}} | `plan.md` |

---

## 2. 总体架构

### 2.1 架构原则

| 原则 | 说明 |
|------|------|
| {{PRINCIPLE_1}} | {{DESCRIPTION_1}} |
| {{PRINCIPLE_2}} | {{DESCRIPTION_2}} |
| {{PRINCIPLE_3}} | {{DESCRIPTION_3}} |

### 2.2 逻辑分层

| 层级 | 核心职责 | 主要模块 |
|------|------|------|
| {{LAYER_1}} | {{RESPONSIBILITY_1}} | {{MODULES_1}} |
| {{LAYER_2}} | {{RESPONSIBILITY_2}} | {{MODULES_2}} |
| {{LAYER_3}} | {{RESPONSIBILITY_3}} | {{MODULES_3}} |

### 2.3 模块职责边界

| 模块 | 负责 | 不负责 |
|------|------|------|
| {{MODULE_1}} | {{DO_1}} | {{NOT_DO_1}} |
| {{MODULE_2}} | {{DO_2}} | {{NOT_DO_2}} |
| {{MODULE_3}} | {{DO_3}} | {{NOT_DO_3}} |

### 2.4 运行时拓扑

| 组件 | 运行形态 | 作用 |
|------|------|------|
| {{COMPONENT_1}} | {{FORM_1}} | {{PURPOSE_1}} |
| {{COMPONENT_2}} | {{FORM_2}} | {{PURPOSE_2}} |
| {{COMPONENT_3}} | {{FORM_3}} | {{PURPOSE_3}} |

---

## 3. 数据与状态边界

### 3.1 存储职责分配

| 存储 | 存什么 | 为什么放这里 |
|------|------|------|
| {{STORE_1}} | {{DATA_1}} | {{REASON_1}} |
| {{STORE_2}} | {{DATA_2}} | {{REASON_2}} |
| {{STORE_3}} | {{DATA_3}} | {{REASON_3}} |

### 3.2 核心实体

| 实体 | 关键字段 | 说明 |
|------|------|------|
| {{ENTITY_1}} | {{FIELDS_1}} | {{DESC_1}} |
| {{ENTITY_2}} | {{FIELDS_2}} | {{DESC_2}} |
| {{ENTITY_3}} | {{FIELDS_3}} | {{DESC_3}} |

### 3.3 任务状态机

| 状态 | 含义 |
|------|------|
| {{STATE_1}} | {{MEANING_1}} |
| {{STATE_2}} | {{MEANING_2}} |
| {{STATE_3}} | {{MEANING_3}} |

### 3.4 证据追溯约束

- {{TRACE_RULE_1}}
- {{TRACE_RULE_2}}
- {{TRACE_RULE_3}}

---

## 4. 核心流程

### 4.1 {{FLOW_1}}

1. {{STEP_1}}
2. {{STEP_2}}
3. {{STEP_3}}

### 4.2 {{FLOW_2}}

1. {{STEP_1}}
2. {{STEP_2}}
3. {{STEP_3}}

### 4.3 {{FLOW_3}}

1. {{STEP_1}}
2. {{STEP_2}}
3. {{STEP_3}}

---

## 5. 接口与集成边界

### 5.1 内部接口分组

| 接口分组 | 主要职责 |
|------|------|
| {{API_GROUP_1}} | {{API_DESC_1}} |
| {{API_GROUP_2}} | {{API_DESC_2}} |
| {{API_GROUP_3}} | {{API_DESC_3}} |

### 5.2 SSE 事件契约

| 事件 | 用途 | 必带字段 |
|------|------|------|
| {{EVENT_1}} | {{PURPOSE_1}} | {{FIELDS_1}} |
| {{EVENT_2}} | {{PURPOSE_2}} | {{FIELDS_2}} |

### 5.3 外部集成边界

| 集成对象 | 方式 | 架构要求 |
|------|------|------|
| {{INTEGRATION_1}} | {{METHOD_1}} | {{RULE_1}} |
| {{INTEGRATION_2}} | {{METHOD_2}} | {{RULE_2}} |

---

## 6. 横切约束

### 6.1 安全

- {{SECURITY_RULE_1}}
- {{SECURITY_RULE_2}}

### 6.2 可观测性

- {{OBS_RULE_1}}
- {{OBS_RULE_2}}

### 6.3 可靠性

- {{RELIABILITY_RULE_1}}
- {{RELIABILITY_RULE_2}}

### 6.4 可扩展性

- {{SCALABILITY_RULE_1}}
- {{SCALABILITY_RULE_2}}

---

## 7. 架构决策记录

| 决策 | 当前选择 | 原因 | 何时需要重审 |
|------|------|------|------|
| {{DECISION_1}} | {{CHOICE_1}} | {{WHY_1}} | {{REVISIT_1}} |
| {{DECISION_2}} | {{CHOICE_2}} | {{WHY_2}} | {{REVISIT_2}} |

### 7.2 架构变更触发条件

- {{TRIGGER_1}}
- {{TRIGGER_2}}
- {{TRIGGER_3}}

---

> **文档维护者**: {{OWNER}}  
> **变更原则**: 架构文档必须先于或同步于实现偏差被修正
