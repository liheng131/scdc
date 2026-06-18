<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { reportsApi, apiClient, type ReportInfo } from '../api'
import { notificationApi } from '../api/services/notification'
import { Search, Refresh, View, Delete, Download, Upload, Promotion } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { marked } from 'marked'

const reports = ref<ReportInfo[]>([])
const loading = ref(false)
const searchQuery = ref('')
const total = ref(0)
const currentPage = ref(1)
const pageSize = 10

const uploadVisible = ref(false)
const uploading = ref(false)
const uploadFile = ref<File | null>(null)
const uploadTitle = ref('')

const previewVisible = ref(false)
const currentReport = ref<ReportInfo | null>(null)
const renderedMarkdown = ref('')

const editingId = ref<number | null>(null)
const editingTitle = ref('')
const editInputRef = ref<any>(null)

// 推送弹窗
const pushVisible = ref(false)
const pushReportId = ref<number | null>(null)
const pushFormat = ref('pdf')
const pushLoading = ref(false)
const pushFormatOptions = [
  { label: 'PDF 文档', value: 'pdf' },
  { label: 'Word 文档', value: 'docx' },
  { label: 'PPT 演示', value: 'pptx' },
  { label: 'Markdown', value: 'md' },
]

let debounceTimer: ReturnType<typeof setTimeout> | null = null

const skip = computed(() => (currentPage.value - 1) * pageSize)

const formatTime = (ts: string) => {
  const d = new Date(ts)
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

const fetchReports = async () => {
  loading.value = true
  try {
    const res = await reportsApi.getReports({
      q: searchQuery.value || undefined,
      skip: skip.value,
      limit: pageSize,
    })
    reports.value = res.data?.items || []
    total.value = res.data?.total ?? reports.value.length
  } catch (err) {
    ElMessage.error('获取研报列表失败')
  } finally {
    loading.value = false
  }
}

const onSearchDebounced = () => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    currentPage.value = 1
    fetchReports()
  }, 300)
}

watch(searchQuery, onSearchDebounced)

const onPageChange = (page: number) => {
  currentPage.value = page
  fetchReports()
}

const handlePreview = async (row: ReportInfo) => {
  try {
    const res = await reportsApi.getReportDetail(row.id)
    currentReport.value = res.data
    renderedMarkdown.value = marked.parse(res.data.content_markdown || '# 暂无报告正文内容') as string
    previewVisible.value = true
  } catch (err) {
    ElMessage.error('获取研报详情失败')
  }
}

const startEdit = async (row: ReportInfo) => {
  editingId.value = row.id
  editingTitle.value = row.title
  await nextTick()
  editInputRef.value?.focus?.()
}

const confirmEdit = async (row: ReportInfo) => {
  if (!editingTitle.value.trim()) {
    editingId.value = null
    return
  }
  try {
    await reportsApi.updateReport(row.id, { title: editingTitle.value.trim() })
    row.title = editingTitle.value.trim()
    editingId.value = null
    ElMessage.success('标题更新成功')
  } catch (err) {
    ElMessage.error('标题更新失败')
  }
}

const cancelEdit = () => {
  editingId.value = null
  editingTitle.value = ''
}

const handleEditKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape') {
    cancelEdit()
  }
}

const handleDelete = async (row: ReportInfo) => {
  try {
    await apiClient.delete(`/api/v1/reports/${row.id}`)
    ElMessage.success('研报已删除')
    fetchReports()
  } catch (err) {
    ElMessage.error('删除研报失败')
  }
}

const handleExport = async (row: ReportInfo, cmd: { fmt: string; template_id?: string } | string) => {
  // 兼容旧的字符串入参（直接传 fmt）
  const fmt = typeof cmd === 'string' ? cmd : cmd.fmt
  const template_id = typeof cmd === 'string' ? undefined : cmd.template_id
  try {
    const url = reportsApi.exportReportUrl(row.id, fmt, template_id)
    const response = await fetch(url, {
      headers: reportsApi.getExportHeaders(),
    })
    if (!response.ok) throw new Error('下载失败')
    const blob = await response.blob()
    const objectUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = objectUrl
    a.download = `report_${row.id}.${fmt}`
    a.click()
    URL.revokeObjectURL(objectUrl)
    ElMessage.success('导出成功，该报告已同步至智能报告列表')
  } catch {
    ElMessage.error('导出失败，请重试')
  }
}

// 加载 PPT 模板列表
const pptTemplates = ref<Array<{ id: string; name: string; description: string; file: string; layouts_count: number }>>([])
onMounted(async () => {
  try {
    const res = await reportsApi.listPptTemplates()
    pptTemplates.value = (res.data?.items || []) as any
  } catch {
    pptTemplates.value = []
  }
})

const handleFileChange = (file: File) => {
  uploadFile.value = file
  if (!uploadTitle.value) {
    uploadTitle.value = file.name.replace(/\.[^/.]+$/, '')
  }
}

const handleUpload = async () => {
  if (!uploadFile.value) {
    ElMessage.warning('请选择文件')
    return
  }
  uploading.value = true
  try {
    await reportsApi.uploadReport(uploadFile.value, uploadTitle.value || undefined)
    ElMessage.success('上传成功')
    uploadVisible.value = false
    uploadFile.value = null
    uploadTitle.value = ''
    fetchReports()
  } catch {
    ElMessage.error('上传失败，请重试')
  } finally {
    uploading.value = false
  }
}

const openPushDialog = (row: ReportInfo) => {
  pushReportId.value = row.id
  pushFormat.value = 'pdf'
  pushVisible.value = true
}

const handlePushAll = () => {
  if (reports.value.length === 0) {
    ElMessage.warning('没有可推送的报告')
    return
  }
  // 默认推送最新一条报告
  openPushDialog(reports.value[0])
}

const handlePushReport = async () => {
  if (!pushReportId.value) return
  pushLoading.value = true
  try {
    const res = await notificationApi.pushReport({
      report_id: pushReportId.value,
      format: pushFormat.value,
    })
    const data = res.data
    const total = data?.total ?? 0
    const results = data?.results ?? {}
    const successCount = Object.values(results).filter((v: any) => v).length
    const failCount = total - successCount
    if (failCount === 0) {
      ElMessage.success(`报告已成功推送到 ${total} 个邮箱`)
    } else {
      ElMessage.warning(`推送完成：${successCount} 成功，${failCount} 失败`)
    }
    pushVisible.value = false
  } catch (err: any) {
    const msg = err?.response?.data?.detail || '推送失败，请检查是否已配置通知规则'
    ElMessage.error(msg)
  } finally {
    pushLoading.value = false
  }
}

onMounted(() => {
  fetchReports()
})
</script>

<template>
  <div class="reports-container">
    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">智能研报中心</span>
          <div class="actions">
            <el-input
              v-model="searchQuery"
              placeholder="搜索报告标题或摘要..."
              :prefix-icon="Search"
              style="width: 320px"
              clearable
            />
            <el-button type="warning" :icon="Promotion" @click="handlePushAll">报告推送</el-button>
            <el-button type="primary" :icon="Upload" @click="uploadVisible = true">上传报告</el-button>
            <el-button :icon="Refresh" @click="fetchReports" circle title="刷新列表"></el-button>
          </div>
        </div>
      </template>

      <el-table v-loading="loading" :data="reports" stripe style="width: 100%">
        <el-table-column label="标题" min-width="260">
          <template #default="{ row }">
            <template v-if="editingId === row.id">
              <el-input
                v-model="editingTitle"
                size="small"
                ref="editInputRef"
                @keyup.enter="confirmEdit(row)"
                @keydown="handleEditKeydown($event)"
                @blur="cancelEdit"
              />
            </template>
            <template v-else>
              <span class="report-title" @click="startEdit(row)">{{ row.title }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'completed' ? 'success' : 'warning'">
              {{ row.status === 'completed' ? '已完成' : row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="360" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="primary" size="small" :icon="View" @click="handlePreview(row)">
              预览
            </el-button>
            <el-dropdown trigger="click" @command="(cmd: {fmt: string; template_id?: string}) => handleExport(row, cmd)">
              <el-button type="success" size="small" :icon="Download">
                导出
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item :command="{fmt: 'md'}">Markdown (.md)</el-dropdown-item>
                  <el-dropdown-item :command="{fmt: 'docx'}">Word 文档 (.docx)</el-dropdown-item>
                  <el-dropdown-item :command="{fmt: 'pdf'}">PDF 文档 (.pdf)</el-dropdown-item>
                  <el-sub-menu v-if="pptTemplates.length > 0" teleported>
                    <template #title>PPT 演示 (.pptx)</template>
                    <el-dropdown-item
                      v-for="t in pptTemplates"
                      :key="t.id"
                      :command="{fmt: 'pptx', template_id: t.id}"
                    >
                      {{ t.name }}
                    </el-dropdown-item>
                  </el-sub-menu>
                  <el-dropdown-item v-else :command="{fmt: 'pptx'}">PPT 演示 (.pptx)</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button type="warning" size="small" :icon="Promotion" @click="openPushDialog(row)">
              推送
            </el-button>
            <el-popconfirm
              title="确认删除该研报？"
              confirm-button-text="确认删除"
              cancel-button-text="取消"
              @confirm="handleDelete(row)"
            >
              <template #reference>
                <el-button type="danger" size="small" :icon="Delete" style="margin-left: 8px">
                  删除
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper" v-if="total > pageSize">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="onPageChange"
        />
      </div>
    </el-card>

    <el-empty v-if="!loading && reports.length === 0" description="暂无生成的智能研报成果" />

    <el-dialog
      v-model="uploadVisible"
      title="上传报告"
      width="500px"
      :close-on-click-modal="false"
    >
      <el-form label-width="80px">
        <el-form-item label="报告标题">
          <el-input v-model="uploadTitle" placeholder="输入标题（可选，默认使用文件名）" />
        </el-form-item>
        <el-form-item label="文件上传">
          <el-upload
            :auto-upload="false"
            :on-change="(f: any) => handleFileChange(f.raw as File)"
            :limit="1"
            accept=".md,.pdf,.docx,.pptx,.txt"
            drag
          >
            <el-icon class="el-icon--upload"><upload-filled /></el-icon>
            <div class="el-upload__text">
              拖拽文件到此处，或 <em>点击上传</em>
            </div>
            <template #tip>
              <div class="el-upload__tip">
                支持 .md / .pdf / .docx / .pptx / .txt 格式
              </div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="handleUpload">确认上传</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="previewVisible"
      :title="currentReport?.title"
      width="65%"
      class="preview-dialog"
    >
      <div class="preview-meta" v-if="currentReport">
        <span class="meta-time">创建时间：{{ formatTime(currentReport.created_at) }}</span>
      </div>
      <el-divider />
      <div class="markdown-body" v-html="renderedMarkdown"></div>
    </el-dialog>

    <!-- 报告推送弹窗 -->
    <el-dialog
      v-model="pushVisible"
      title="推送报告到邮箱"
      width="450px"
      :close-on-click-modal="false"
    >
      <el-form label-width="100px">
        <el-form-item label="导出格式">
          <el-select v-model="pushFormat" style="width: 100%">
            <el-option
              v-for="opt in pushFormatOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="推送目标">
          <div style="color: var(--scdc-ink-light); font-size: 13px;">
            将推送到所有已启用的邮件通知规则邮箱
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pushVisible = false">取消</el-button>
        <el-button type="warning" :loading="pushLoading" @click="handlePushReport">确认推送</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.reports-container {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.table-card {
  border-radius: var(--scdc-radius-lg);
  border: 1px solid var(--scdc-bg-sunken);
  box-shadow: var(--scdc-shadow-soft);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-family: var(--scdc-font-display);
  font-weight: 600;
  font-size: 18px;
  color: var(--scdc-ink-strong);
  letter-spacing: -0.01em;
}

.actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.actions :deep(.el-input__wrapper) {
  border-radius: var(--scdc-radius-md);
}

.report-title {
  cursor: pointer;
  color: var(--scdc-ink);
  font-weight: 500;
  transition: color var(--scdc-transition-fast);
}

.report-title:hover {
  color: var(--scdc-accent);
}

.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 24px;
  padding: 8px 0;
}

.preview-dialog :deep(.el-dialog__header) {
  padding-bottom: 0;
}

.preview-dialog .markdown-body {
  font-size: 15px;
  line-height: 1.8;
  color: var(--scdc-ink);
  padding: 0 8px 32px 8px;
  max-height: 65vh;
  overflow-y: auto;
}

.preview-meta {
  color: var(--scdc-ink-muted);
  font-size: 13px;
  padding: 8px 0;
}

.markdown-body h1,
.markdown-body h2,
.markdown-body h3 {
  color: var(--scdc-ink-strong);
  font-family: var(--scdc-font-display);
  margin-top: 28px;
  margin-bottom: 14px;
  font-weight: 700;
  line-height: 1.3;
}

.markdown-body h1 { font-size: 24px; }
.markdown-body h2 { font-size: 20px; }
.markdown-body h3 { font-size: 17px; }

.markdown-body p {
  margin-bottom: 16px;
}

.markdown-body ul,
.markdown-body ol {
  padding-left: 24px;
  margin-bottom: 16px;
}

.markdown-body th {
  background: var(--scdc-bg-elevated);
  font-weight: 600;
}

.markdown-body img {
  max-width: 100%;
  height: auto;
  border-radius: var(--scdc-radius-md);
  margin: 16px 0;
  box-shadow: var(--scdc-shadow-soft);
}

/* 响应式优化 */
@media (max-width: 1200px) {
  .actions { flex-wrap: wrap; }
  .actions :deep(.el-input) { width: 240px !important; }
}

@media (max-width: 900px) {
  .card-header { flex-direction: column; gap: 12px; align-items: flex-start; }
  .actions { width: 100%; }
  .actions :deep(.el-input) { flex: 1; min-width: 0; }
}
</style>