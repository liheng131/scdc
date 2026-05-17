# {{PROJECT_NAME}} — 产品需求文档（PRD）

> **文档版本**: v1.0  
> **创建日期**: {{DATE}}  
> **最后更新**: {{DATE}}  
> **状态**: 草案 / 维护中  
> **关联文档**: [架构文档](./architecture.md) | [技术栈文档](./tech.md) | [分步计划](./plan.md)

---

## 1. 文档定位与使用方式

### 1.1 本文档回答的问题

- 为什么做这个系统
- 为谁服务
- MVP 必须交付什么
- 业务上如何验收

### 1.2 多 Agent 使用约定

| Agent | 必读内容 | 可更新内容 | 不应直接更新的内容 |
|------|------|------|------|
| 设计 Agent | {{SECTIONS}} | {{CAN_EDIT}} | {{SHOULD_NOT_EDIT}} |
| 开发 Agent | {{SECTIONS}} | {{CAN_EDIT}} | {{SHOULD_NOT_EDIT}} |
| 审阅 Agent | {{SECTIONS}} | {{CAN_EDIT}} | {{SHOULD_NOT_EDIT}} |

### 1.3 与其他核心文档的边界

| 文档 | 关注点 | 单一事实来源 |
|------|------|------|
| `prd.md` | 业务目标、范围、验收标准 | {{DESCRIPTION}} |
| `architecture.md` | 系统边界、模块职责、流程 | {{DESCRIPTION}} |
| `tech.md` | 技术选型、版本、工程约定 | {{DESCRIPTION}} |
| `plan.md` | 任务拆分、依赖、状态流转 | {{DESCRIPTION}} |

---

## 2. 产品背景与目标

### 2.1 产品愿景

{{ONE_PARAGRAPH_VISION}}

### 2.2 核心成功指标

| 目标 | 衡量指标 | 目标值 |
|------|------|------|
| {{GOAL_1}} | {{METRIC_1}} | {{TARGET_1}} |
| {{GOAL_2}} | {{METRIC_2}} | {{TARGET_2}} |
| {{GOAL_3}} | {{METRIC_3}} | {{TARGET_3}} |

### 2.3 非目标

- {{NON_GOAL_1}}
- {{NON_GOAL_2}}
- {{NON_GOAL_3}}

---

## 3. 用户与关键场景

### 3.1 角色定义

| 角色 | 核心职责 | 典型关注点 |
|------|------|------|
| {{ROLE_1}} | {{RESPONSIBILITY_1}} | {{FOCUS_1}} |
| {{ROLE_2}} | {{RESPONSIBILITY_2}} | {{FOCUS_2}} |
| {{ROLE_3}} | {{RESPONSIBILITY_3}} | {{FOCUS_3}} |

### 3.2 权限矩阵

| 功能 | {{ROLE_1}} | {{ROLE_2}} | {{ROLE_3}} |
|------|------|------|------|
| {{CAPABILITY_1}} | 是 | 否 | 否 |
| {{CAPABILITY_2}} | 是 | 是 | 否 |
| {{CAPABILITY_3}} | 是 | 是 | 是 |

### 3.3 核心业务场景

| 场景 | 触发方式 | 期望结果 |
|------|------|------|
| {{SCENARIO_1}} | {{TRIGGER_1}} | {{RESULT_1}} |
| {{SCENARIO_2}} | {{TRIGGER_2}} | {{RESULT_2}} |
| {{SCENARIO_3}} | {{TRIGGER_3}} | {{RESULT_3}} |

---

## 4. MVP 范围定义

### 4.1 MVP 包含内容（In Scope）

| 模块 | MVP 范围 | 业务价值 |
|------|------|------|
| {{MODULE_1}} | {{SCOPE_1}} | {{VALUE_1}} |
| {{MODULE_2}} | {{SCOPE_2}} | {{VALUE_2}} |
| {{MODULE_3}} | {{SCOPE_3}} | {{VALUE_3}} |

### 4.2 MVP 不包含内容（Out of Scope）

- {{OUT_OF_SCOPE_1}}
- {{OUT_OF_SCOPE_2}}
- {{OUT_OF_SCOPE_3}}

### 4.3 阶段路线图

| 阶段 | 重点 | 结果 |
|------|------|------|
| Phase 1 | {{FOCUS_1}} | {{RESULT_1}} |
| Phase 2 | {{FOCUS_2}} | {{RESULT_2}} |
| Phase 3 | {{FOCUS_3}} | {{RESULT_3}} |

---

## 5. 功能需求与验收标准

### 5.1 {{MODULE_NAME_1}}

| 编号 | 需求 | 验收标准 |
|------|------|------|
| {{FR_ID_1}} | {{REQ_1}} | {{ACCEPTANCE_1}} |
| {{FR_ID_2}} | {{REQ_2}} | {{ACCEPTANCE_2}} |

### 5.2 {{MODULE_NAME_2}}

| 编号 | 需求 | 验收标准 |
|------|------|------|
| {{FR_ID_3}} | {{REQ_3}} | {{ACCEPTANCE_3}} |
| {{FR_ID_4}} | {{REQ_4}} | {{ACCEPTANCE_4}} |

### 5.3 {{MODULE_NAME_3}}

| 编号 | 需求 | 验收标准 |
|------|------|------|
| {{FR_ID_5}} | {{REQ_5}} | {{ACCEPTANCE_5}} |
| {{FR_ID_6}} | {{REQ_6}} | {{ACCEPTANCE_6}} |

---

## 6. 非功能需求

| 类别 | 要求 | 目标 |
|------|------|------|
| 性能 | {{NFR_PERF}} | {{TARGET_PERF}} |
| 可用性 | {{NFR_AVAILABILITY}} | {{TARGET_AVAILABILITY}} |
| 安全 | {{NFR_SECURITY}} | {{TARGET_SECURITY}} |
| 可观测性 | {{NFR_OBSERVABILITY}} | {{TARGET_OBSERVABILITY}} |
| 可扩展性 | {{NFR_SCALABILITY}} | {{TARGET_SCALABILITY}} |

---

## 7. 风险与假设

### 7.1 关键风险

| 风险 | 影响 | 缓解思路 |
|------|------|------|
| {{RISK_1}} | {{IMPACT_1}} | {{MITIGATION_1}} |
| {{RISK_2}} | {{IMPACT_2}} | {{MITIGATION_2}} |

### 7.2 关键假设

- {{ASSUMPTION_1}}
- {{ASSUMPTION_2}}
- {{ASSUMPTION_3}}

---

## 8. 附录

### 8.1 术语

| 术语 | 定义 |
|------|------|
| {{TERM_1}} | {{DEFINITION_1}} |
| {{TERM_2}} | {{DEFINITION_2}} |

### 8.2 文档维护规则

- {{RULE_1}}
- {{RULE_2}}
- {{RULE_3}}

---

> **文档维护者**: {{OWNER}}  
> **变更原则**: 需求变更优先于实现变更
