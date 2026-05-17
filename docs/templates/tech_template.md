# {{PROJECT_NAME}} — 技术栈文档

> **文档版本**: v1.0  
> **创建日期**: {{DATE}}  
> **最后更新**: {{DATE}}  
> **状态**: 草案 / 维护中  
> **关联文档**: [PRD](./prd.md) | [架构文档](./architecture.md) | [分步计划](./plan.md)

---

## 1. 文档定位与更新规则

### 1.1 本文档回答的问题

- {{QUESTION_1}}
- {{QUESTION_2}}
- {{QUESTION_3}}

### 1.2 多 Agent 更新规则

| Agent | 关注点 | 可更新内容 |
|------|------|------|
| 设计 Agent | {{FOCUS_1}} | {{EDIT_SCOPE_1}} |
| 开发 Agent | {{FOCUS_2}} | {{EDIT_SCOPE_2}} |
| 审阅 Agent | {{FOCUS_3}} | {{EDIT_SCOPE_3}} |

### 1.3 与架构文档的区别

- `architecture.md`：{{ARCH_SCOPE}}
- `tech.md`：{{TECH_SCOPE}}

---

## 2. 技术栈总览

| 层级 | 技术 | 版本基线 | 用途 | 备注 |
|------|------|------|------|------|
| {{LAYER_1}} | {{TECH_1}} | {{VERSION_1}} | {{PURPOSE_1}} | {{NOTE_1}} |
| {{LAYER_2}} | {{TECH_2}} | {{VERSION_2}} | {{PURPOSE_2}} | {{NOTE_2}} |
| {{LAYER_3}} | {{TECH_3}} | {{VERSION_3}} | {{PURPOSE_3}} | {{NOTE_3}} |

---

## 3. 仓库结构与工程约定

### 3.1 Monorepo 目录约定

```text
{{REPO_TREE}}
```

### 3.2 后端目录约定

| 目录 | 职责 |
|------|------|
| {{DIR_1}} | {{RESP_1}} |
| {{DIR_2}} | {{RESP_2}} |
| {{DIR_3}} | {{RESP_3}} |

### 3.3 前端目录约定

| 目录 | 职责 |
|------|------|
| {{DIR_4}} | {{RESP_4}} |
| {{DIR_5}} | {{RESP_5}} |
| {{DIR_6}} | {{RESP_6}} |

### 3.4 Prompt 与模板约定

- {{RULE_1}}
- {{RULE_2}}
- {{RULE_3}}

---

## 4. 开发环境与工具链

### 4.1 本地环境基线

| 项目 | 要求 |
|------|------|
| {{ITEM_1}} | {{REQ_1}} |
| {{ITEM_2}} | {{REQ_2}} |
| {{ITEM_3}} | {{REQ_3}} |

### 4.2 常用开发动作

| 场景 | 建议命令基线 |
|------|------|
| {{SCENE_1}} | {{COMMAND_1}} |
| {{SCENE_2}} | {{COMMAND_2}} |
| {{SCENE_3}} | {{COMMAND_3}} |

### 4.3 环境变量分类

| 类别 | 示例 |
|------|------|
| {{ENV_GROUP_1}} | {{ENV_EXAMPLE_1}} |
| {{ENV_GROUP_2}} | {{ENV_EXAMPLE_2}} |
| {{ENV_GROUP_3}} | {{ENV_EXAMPLE_3}} |

---

## 5. 后端技术栈细化

| 技术 | 用途 | 说明 |
|------|------|------|
| {{BACKEND_TECH_1}} | {{USE_1}} | {{DESC_1}} |
| {{BACKEND_TECH_2}} | {{USE_2}} | {{DESC_2}} |
| {{BACKEND_TECH_3}} | {{USE_3}} | {{DESC_3}} |

### 5.2 后端工程约束

- {{BACKEND_RULE_1}}
- {{BACKEND_RULE_2}}
- {{BACKEND_RULE_3}}

---

## 6. 前端技术栈细化

| 技术 | 用途 | 说明 |
|------|------|------|
| {{FRONTEND_TECH_1}} | {{USE_1}} | {{DESC_1}} |
| {{FRONTEND_TECH_2}} | {{USE_2}} | {{DESC_2}} |
| {{FRONTEND_TECH_3}} | {{USE_3}} | {{DESC_3}} |

### 6.2 前端工程约束

- {{FRONTEND_RULE_1}}
- {{FRONTEND_RULE_2}}
- {{FRONTEND_RULE_3}}

---

## 7. AI、采集与数据技术栈

### 7.1 Agent 与模型

| 技术 | 用途 |
|------|------|
| {{AI_TECH_1}} | {{AI_USE_1}} |
| {{AI_TECH_2}} | {{AI_USE_2}} |

### 7.2 采集

| 技术 | 用途 |
|------|------|
| {{COLLECT_TECH_1}} | {{COLLECT_USE_1}} |
| {{COLLECT_TECH_2}} | {{COLLECT_USE_2}} |

### 7.3 数据与检索

| 技术 | 用途 |
|------|------|
| {{DATA_TECH_1}} | {{DATA_USE_1}} |
| {{DATA_TECH_2}} | {{DATA_USE_2}} |

---

## 8. 质量、测试与可观测性基线

### 8.1 测试层次

| 层次 | 目标 |
|------|------|
| {{TEST_LAYER_1}} | {{TEST_GOAL_1}} |
| {{TEST_LAYER_2}} | {{TEST_GOAL_2}} |
| {{TEST_LAYER_3}} | {{TEST_GOAL_3}} |

### 8.2 最低质量门槛

- {{QUALITY_RULE_1}}
- {{QUALITY_RULE_2}}
- {{QUALITY_RULE_3}}

### 8.3 可观测性工具

| 技术 | 用途 |
|------|------|
| {{OBS_TECH_1}} | {{OBS_USE_1}} |
| {{OBS_TECH_2}} | {{OBS_USE_2}} |

---

## 9. 许可证与外部依赖约束

### 9.1 许可证分层策略

| 类型 | 处理原则 |
|------|------|
| {{LICENSE_TYPE_1}} | {{LICENSE_RULE_1}} |
| {{LICENSE_TYPE_2}} | {{LICENSE_RULE_2}} |

### 9.2 当前需重点关注的组件

| 组件 | 风险点 | 处理方式 |
|------|------|------|
| {{RISK_COMPONENT_1}} | {{RISK_1}} | {{ACTION_1}} |
| {{RISK_COMPONENT_2}} | {{RISK_2}} | {{ACTION_2}} |

### 9.3 技术栈变更触发条件

- {{TRIGGER_1}}
- {{TRIGGER_2}}
- {{TRIGGER_3}}

---

## 10. 选型决策摘要

| 主题 | 当前选择 | 摘要理由 |
|------|------|------|
| {{TOPIC_1}} | {{CHOICE_1}} | {{WHY_1}} |
| {{TOPIC_2}} | {{CHOICE_2}} | {{WHY_2}} |
| {{TOPIC_3}} | {{CHOICE_3}} | {{WHY_3}} |

---

> **文档维护者**: {{OWNER}}  
> **变更原则**: 技术文档必须反映真实实现
