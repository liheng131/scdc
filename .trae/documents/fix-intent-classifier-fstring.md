# 修复 intent_classifier.py f-string 语法错误

## 问题诊断

Docker 容器内 Python 3.11 启动时报语法错误：

```
File "/app/app/services/intent_classifier.py", line 107
    }}"""
    ^
SyntaxError: f-string expression part cannot include a backslash
```

**根因**：`intent_classifier.py` 第 80-107 行的 `_build_classification_prompt()` 方法使用了一个超长 f-string 构建 prompt。Python 3.11 严格禁止 f-string 表达式部分（`{...}` 内部）包含反斜杠。虽然代码中表达式部分肉眼看不到反斜杠，但文件可能因编码问题存在不可见字符，或 f-string 内部的换行符 `\n` 被 Python 3.11 解析器误判。

**修复方案**：将 prompt 构建方式从 f-string 改为先构建模板字符串再 `.format()`，消除所有 Python 版本兼容性问题。

## 实施步骤

### 步骤 1：修改 `_build_classification_prompt` 方法

文件：`backend/app/services/intent_classifier.py`，行 63-108

将当前 f-string 构建方式：

```python
prompt = f"""你是一个意图分类器..."""
```

改为先定义模板字符串，再用 `.format()` 填充：

```python
template = """你是一个意图分类器。请将以下用户消息分类为三种意图之一。

对话历史：
{history_text}

{report_context}

用户最新消息：
"{message}"

意图类型定义：
1. **market_insight**（市场洞察）：...
2. ...
3. ...

请严格按以下JSON格式输出，不要包含任何其他内容：
{{
  "intent_type": "...",
  ...
}}"""
prompt = template.format(
    history_text=history_text if history_text else "（无历史记录）",
    report_context=report_context,
    message=message,
)
```

### 步骤 2：验证修复

- 重新构建 Docker 镜像
- 检查容器启动日志无 SyntaxError

## 涉及文件
- 仅修改 `backend/app/services/intent_classifier.py` 第 63-108 行