<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { reportsApi, apiClient, type ReportInfo } from '../api'
import { Search, Refresh, View, Delete, Download, Upload } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
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
    reports.value = res.data || []
    total.value = (res as any).total ?? reports.value.length
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
    ElMessage.success('导出成功，该报告已同步至智能报告列表')
  } catch {
    ElMessage.error('导出失败，请重试')
  }
}

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
        <el-table-column label="操作" width="280" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="primary" size="small" :icon="View" @click="handlePreview(row)">
              预览
            </el-button>
            <el-dropdown trigger="click" @command="(fmt: string) => handleExport(row, fmt)">
              <el-button type="success" size="small" :icon="Download">
                导出
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="md">Markdown (.md)</el-dropdown-item>
                  <el-dropdown-item command="docx">Word 文档 (.docx)</el-dropdown-item>
                  <el-dropdown-item command="pdf">PDF 文档 (.pdf)</el-dropdown-item>
                  <el-dropdown-item command="pptx">PPT 演示 (.pptx)</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
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
  </div>
</template>

<style scoped>
.reports-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.table-card {
  border-radius: 12px;
  border: none;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-weight: 600;
  font-size: 18px;
  color: #1e222d;
}

.actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.report-title {
  cursor: pointer;
  color: #1e222d;
  font-weight: 500;
}

.report-title:hover {
  color: #409eff;
}

.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

.preview-dialog .markdown-body {
  font-size: 15px;
  line-height: 1.8;
  color: #2d3748;
  padding: 0 16px 32px 16px;
  max-height: 60vh;
  overflow-y: auto;
}

.preview-meta {
  color: #718096;
  font-size: 14px;
}

.markdown-body h1,
.markdown-body h2,
.markdown-body h3 {
  color: #1a202c;
  margin-top: 24px;
  margin-bottom: 12px;
  font-weight: 700;
}

.markdown-body p {
  margin-bottom: 16px;
}

.markdown-body ul,
.markdown-body ol {
  padding-left: 24px;
  margin-bottom: 16px;
}

.markdown-body img {
  max-width: 100%;
  height: auto;
  border-radius: 8px;
  margin: 12px 0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}
</style>