# {{PROJECT_NAME}} — 多 Agent 分步计划

> **文档版本**: v1.0  
> **创建日期**: {{DATE}}  
> **最后更新**: {{DATE}}  
> **状态**: 待执行 / 执行中  
> **关联文档**: [PRD](./prd.md) | [架构文档](./architecture.md) | [技术栈文档](./tech.md)

---

## 1. 文档定位与协作规则

### 1.1 本文档的职责

- {{RESPONSIBILITY_1}}
- {{RESPONSIBILITY_2}}
- {{RESPONSIBILITY_MODULE_CONTEXT}}
- {{RESPONSIBILITY_3}}

### 1.2 标准工作流

1. **设计阶段**  
   {{DESIGN_STAGE_RULE}}
2. **开发阶段**  
   {{DEVELOP_STAGE_RULE}}
3. **审阅阶段**  
   {{REVIEW_STAGE_RULE}}

### 1.3 审阅失败后的回流规则

| 审阅结论 | 回流目标 | 处理方式 |
|------|------|------|
| 设计问题 | 设计 Agent | {{DESIGN_FEEDBACK_LOOP}} |
| 开发问题 | 开发 Agent | {{DEV_FEEDBACK_LOOP}} |
| 需求问题 | 设计 Agent + PRD | {{REQ_FEEDBACK_LOOP}} |

### 1.4 完成定义

- {{DONE_RULE_1}}
- {{DONE_RULE_2}}
- {{DONE_RULE_3}}

---

## 2. 状态枚举与更新规则

### 2.1 任务状态

| 状态 | 含义 |
|------|------|
| `backlog` | 尚未开始 |
| `designing` | 设计中 |
| `design_done` | 设计完成，待开发 |
| `developing` | 开发中 |
| `reviewing` | 审阅中 |
| `review_failed_design` | 审阅判定为设计问题 |
| `review_failed_dev` | 审阅判定为开发问题 |
| `done` | 已通过审阅 |
| `blocked` | 被阻塞 |

### 2.2 文档更新责任

| 阶段 | 必须更新 |
|------|------|
| 设计完成 | {{UPDATE_RULE_1}} |
| 开发完成 | {{UPDATE_RULE_2}} |
| 审阅完成 | {{UPDATE_RULE_3}} |

### 2.3 当前总体策略

- {{STRATEGY_1}}
- {{STRATEGY_2}}
- {{STRATEGY_MODULE_CONTEXT}}
- {{STRATEGY_3}}

---

## 3. 里程碑与依赖总览

### 3.1 里程碑

| 里程碑 | 目标 | 任务范围 |
|------|------|------|
| {{MILESTONE_1}} | {{GOAL_1}} | {{TASK_RANGE_1}} |
| {{MILESTONE_2}} | {{GOAL_2}} | {{TASK_RANGE_2}} |
| {{MILESTONE_3}} | {{GOAL_3}} | {{TASK_RANGE_3}} |

### 3.2 依赖关系

| 模块 | 依赖 |
|------|------|
| {{MODULE_1}} | {{DEP_1}} |
| {{MODULE_2}} | {{DEP_2}} |
| {{MODULE_3}} | {{DEP_3}} |

---

## 4. 任务执行清单

### {{MILESTONE_NAME_1}}

#### 模块技术方案（简略版）

- {{MODULE_SCHEME_1}}
- {{MODULE_SCHEME_2}}

#### 任务项关联关系

- {{TASK_RELATION_1}}
- {{TASK_RELATION_2}}

| ID | 任务项 | 前置依赖 | 设计产出 | 开发产出 | 审阅重点 | 状态 |
|------|------|------|------|------|------|------|
| {{STEP_ID_1}} | {{TASK_1}} | {{PRE_1}} | {{DESIGN_OUT_1}} | {{DEV_OUT_1}} | {{REVIEW_1}} | `backlog` |
| {{STEP_ID_2}} | {{TASK_2}} | {{PRE_2}} | {{DESIGN_OUT_2}} | {{DEV_OUT_2}} | {{REVIEW_2}} | `backlog` |

### {{MILESTONE_NAME_2}}

#### 模块技术方案（简略版）

- {{MODULE_SCHEME_3}}
- {{MODULE_SCHEME_4}}

#### 任务项关联关系

- {{TASK_RELATION_3}}
- {{TASK_RELATION_4}}

| ID | 任务项 | 前置依赖 | 设计产出 | 开发产出 | 审阅重点 | 状态 |
|------|------|------|------|------|------|------|
| {{STEP_ID_3}} | {{TASK_3}} | {{PRE_3}} | {{DESIGN_OUT_3}} | {{DEV_OUT_3}} | {{REVIEW_3}} | `backlog` |
| {{STEP_ID_4}} | {{TASK_4}} | {{PRE_4}} | {{DESIGN_OUT_4}} | {{DEV_OUT_4}} | {{REVIEW_4}} | `backlog` |

### {{MILESTONE_NAME_3}}

#### 模块技术方案（简略版）

- {{MODULE_SCHEME_5}}
- {{MODULE_SCHEME_6}}

#### 任务项关联关系

- {{TASK_RELATION_5}}
- {{TASK_RELATION_6}}

| ID | 任务项 | 前置依赖 | 设计产出 | 开发产出 | 审阅重点 | 状态 |
|------|------|------|------|------|------|------|
| {{STEP_ID_5}} | {{TASK_5}} | {{PRE_5}} | {{DESIGN_OUT_5}} | {{DEV_OUT_5}} | {{REVIEW_5}} | `backlog` |
| {{STEP_ID_6}} | {{TASK_6}} | {{PRE_6}} | {{DESIGN_OUT_6}} | {{DEV_OUT_6}} | {{REVIEW_6}} | `backlog` |

---

## 5. 单任务执行记录模板

```md
## {Step X} 执行记录

- 当前状态: backlog / designing / design_done / developing / reviewing / review_failed_design / review_failed_dev / done / blocked
- 关联里程碑: {{MILESTONE}}
- 关联需求: {{PRD_SECTION}}
- 关联架构: {{ARCH_SECTION}}
- 关联技术约束: {{TECH_SECTION}}

### 设计结论
- 

### 开发说明
- 

### 审阅结论
- 结果:
- 问题归类: design / development / requirement / none
- 需要回流:

### 变更同步
- [ ] 已更新 plan.md
- [ ] 已更新 architecture.md（如需要）
- [ ] 已更新 tech.md（如需要）
- [ ] 已更新 prd.md（如需要）
```

---

## 6. 执行纪律

- {{DISCIPLINE_1}}
- {{DISCIPLINE_2}}
- {{DISCIPLINE_3}}
- {{DISCIPLINE_4}}

---

> **文档维护者**: {{OWNER}}  
> **当前默认推进策略**: 从第一个未完成任务开始，逐项通过审阅后再进入下一项
