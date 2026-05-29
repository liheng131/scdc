# 修复前端导出下载方式

## 问题诊断

### 后端完全正常
```
PDF via Nginx:   200 OK, 82119 bytes, Content-Type: application/pdf   ✅
DOCX via Nginx:  200 OK, 39635 bytes, Content-Type: application/vnd... ✅
PPTX via Docker: 200 OK, 29907 bytes                                     ✅
```

### 根因：`window.open()` 不可靠
前端两个页面都使用 `window.open(url, '_blank')` 触发文件下载：

| 页面 | md 导出 | docx/pdf/pptx 导出 |
|------|---------|---------------------|
| **WorkflowView.vue** | `Blob + <a> click` ✅ | `window.open()` ❌ |
| **ReportsView.vue** | `window.open()` | `window.open()` ❌ |

`window.open()` 在文件下载场景下有以下问题：
1. **浏览器弹窗拦截器**可能阻止新窗口
2. **Content-Disposition: attachment** 导致浏览器打开空白窗口后立即关闭，用户无感知
3. 不同浏览器行为不一致（Chrome/Firefox/Edge 处理方式各异）

### 为什么 Markdown 能正常导出
`WorkflowView.vue` 中 md 格式使用 `fetch → Blob → createObjectURL → <a> click` 模式，这是成熟可靠的文件下载模式，不受弹窗拦截器影响。

## 修复方案

将两处的 `window.open()` 替换为统一的 `fetch + Blob + <a> click` 下载模式：

```typescript
// 替换前
const handleExport = (row: ReportInfo, fmt: string) => {
  const url = reportsApi.exportReportUrl(row.id, fmt)
  window.open(url, '_blank')
}

// 替换后
const handleExport = async (row: ReportInfo, fmt: string) => {
  try {
    const url = reportsApi.exportReportUrl(row.id, fmt)
    const response = await fetch(url)
    if (!response.ok) throw new Error('下载失败')
    const blob = await response.blob()
    const objectUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = objectUrl
    a.download = `report_${row.id}.${fmt}`
    a.click()
    URL.revokeObjectURL(objectUrl)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败，请重试')
  }
}
```

## 改动范围

| 文件 | 函数 | 改动 |
|------|------|------|
| `frontend/src/views/ReportsView.vue` | `handleExport` (line 118) | `window.open` → `fetch + blob` |
| `frontend/src/views/WorkflowView.vue` | `handleExportReport` 非 md 分支 (line 274) | `window.open` → `fetch + blob` |

## 影响
- 不需要重建后端 Docker（仅前端代码改动）
- 不需要修改 API 接口
- 下载行为对用户更友好：直接弹出保存对话框，无空白窗口闪烁