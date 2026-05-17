<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { reportsApi, type ReportInfo } from '../api';
import { Refresh, Download, View, Printer, Search } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import { marked } from 'marked';

const reports = ref<ReportInfo[]>([]);
const loading = ref(false);
const searchQuery = ref('');
const drawerVisible = ref(false);
const currentReport = ref<ReportInfo | null>(null);
const renderedMarkdown = ref('');

const fetchReports = async () => {
  loading.value = true;
  try {
    const res = await reportsApi.getReports(searchQuery.value ? { q: searchQuery.value } : undefined);
    reports.value = res.data || [];
  } catch (err) {
    ElMessage.error('获取研报列表失败');
  } finally {
    loading.value = false;
  }
};

const handleView = (row: ReportInfo) => {
  currentReport.value = row;
  const rawMd = row.content_markdown || '# 暂无报告正文内容';
  renderedMarkdown.value = marked.parse(rawMd) as string;
  drawerVisible.value = true;
};

const exportDoc = (row: ReportInfo, fmt: string) => {
  const url = reportsApi.exportReportUrl(row.id, fmt);
  window.open(url, '_blank');
};

const handleExportCommand = (command: { fmt: string; item: ReportInfo }) => {
  exportDoc(command.item, command.fmt);
};

onMounted(() => {
  fetchReports();
});
</script>

<template>
  <div class="reports-container">
    <div class="filter-bar">
      <el-input
        v-model="searchQuery"
        placeholder="搜索报告标题或摘要..."
        :prefix-icon="Search"
        style="width: 320px"
        clearable
        @clear="fetchReports"
        @keyup.enter="fetchReports"
      />
      <el-button type="primary" :icon="Search" @click="fetchReports">快速过滤</el-button>
      <el-button :icon="Refresh" @click="fetchReports" circle style="margin-left: auto"></el-button>
    </div>

    <!-- 研报卡片网格 -->
    <el-row :gutter="24" v-loading="loading">
      <el-col :span="8" v-for="item in reports" :key="item.id" style="margin-bottom: 24px">
        <el-card shadow="hover" class="report-card">
          <div class="card-top">
            <el-tag size="small" type="success" effect="dark">研报 v{{ item.version }}</el-tag>
            <span class="date">{{ new Date(item.created_at).toLocaleDateString() }}</span>
          </div>
          <h3 class="title" @click="handleView(item)">{{ item.title }}</h3>
          <p class="summary">{{ item.summary || 'AI 智能体正在基于多源行业快讯进行多步骤推导汇编，提炼核心战略洞察...' }}</p>
          <div class="card-footer">
            <el-button type="primary" link :icon="View" @click="handleView(item)">深度阅读</el-button>
            <el-dropdown trigger="click" @command="handleExportCommand">
              <el-button type="success" size="small" :icon="Download" round>
                多模态导出 <el-icon class="el-icon--right"><Printer /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item :command="{ fmt: 'docx', item }">导出 Word 文档 (.docx)</el-dropdown-item>
                  <el-dropdown-item :command="{ fmt: 'pdf', item }">导出 PDF 文档 (.pdf)</el-dropdown-item>
                  <el-dropdown-item :command="{ fmt: 'md', item }">导出纯 Markdown 正文 (.md)</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-empty v-if="!loading && reports.length === 0" description="暂无生成的智能研报成果" />

    <!-- 深度阅读抽屉 -->
    <el-drawer
      v-model="drawerVisible"
      :title="currentReport?.title"
      size="65%"
      class="report-drawer"
    >
      <div class="drawer-header-meta" v-if="currentReport">
        <el-tag size="small">版本: v{{ currentReport.version }}</el-tag>
        <span class="meta-time">更新于: {{ new Date(currentReport.updated_at).toLocaleString() }}</span>
      </div>
      <el-divider />
      <div class="markdown-body" v-html="renderedMarkdown"></div>
    </el-drawer>
  </div>
</template>

<style scoped>
.reports-container {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  background-color: white;
  padding: 16px 24px;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
}

.report-card {
  border-radius: 16px;
  border: none;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.06);
  transition: transform 0.3s ease, box-shadow 0.3s ease;
  display: flex;
  flex-direction: column;
  height: 260px;
}

.report-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 15px 35px rgba(0, 0, 0, 0.12);
}

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.date {
  font-size: 13px;
  color: #a0aec0;
}

.title {
  margin: 0 0 10px 0;
  font-size: 18px;
  font-weight: 700;
  color: #1e222d;
  cursor: pointer;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.title:hover {
  color: #409eff;
}

.summary {
  font-size: 14px;
  color: #718096;
  line-height: 1.6;
  flex: 1;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin: 0;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #edf2f7;
}

.drawer-header-meta {
  display: flex;
  gap: 16px;
  align-items: center;
  color: #718096;
  font-size: 14px;
}

.markdown-body {
  font-size: 15px;
  line-height: 1.8;
  color: #2d3748;
  padding: 0 16px 32px 16px;
}

/* 简单的 Markdown 样式优化 */
.markdown-body h1, .markdown-body h2, .markdown-body h3 {
  color: #1a202c;
  margin-top: 24px;
  margin-bottom: 12px;
  font-weight: 700;
}
.markdown-body p {
  margin-bottom: 16px;
}
.markdown-body ul, .markdown-body ol {
  padding-left: 24px;
  margin-bottom: 16px;
}
</style>
