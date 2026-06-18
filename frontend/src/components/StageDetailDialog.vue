<template>
  <el-dialog
    :model-value="visible"
    :title="stageName"
    width="80%"
    min-width="600px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <!-- 耗时显示 -->
    <div v-if="stageDetail?.summary?.duration_seconds" class="duration-badge">
      <el-tag type="info" size="small">耗时 {{ stageDetail.summary.duration_seconds }} 秒</el-tag>
    </div>

    <!-- 数据采集 -->
    <div v-if="stageKey === 'collecting'" class="stage-detail-content">
      <div v-if="stageDetail?.detail?.keywords?.length" class="detail-section">
        <h4>搜索关键词 ({{ stageDetail.detail.keywords.length }})</h4>
        <div class="keyword-tags">
          <el-tag
            v-for="keyword in stageDetail.detail.keywords"
            :key="keyword"
            type="success"
            size="small"
          >
            {{ keyword }}
          </el-tag>
        </div>
      </div>

      <div v-if="stageDetail?.detail?.items?.length" class="detail-section">
        <h4>资讯网站列表 ({{ stageDetail.detail.items.length }})</h4>
        <div class="source-cards">
          <div
            v-for="(item, index) in stageDetail.detail.items"
            :key="index"
            class="source-card"
          >
            <div class="source-title">{{ item.title || '无标题' }}</div>
            <div class="source-snippet">{{ item.snippet || '无摘要' }}</div>
            <div v-if="item.source_uri" class="source-uri">
              <a :href="item.source_uri" target="_blank">{{ item.source_uri }}</a>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 数据清洗 -->
    <div v-else-if="stageKey === 'cleaning'" class="stage-detail-content">
      <div v-if="stageDetail?.detail?.cleaning_summary" class="detail-section">
        <h4>清洗摘要</h4>
        <p class="cleaning-summary-text">{{ stageDetail.detail.cleaning_summary }}</p>
      </div>

      <div v-if="stageDetail?.detail?.stats" class="detail-section">
        <h4>清洗前后对比</h4>
        <el-table :data="cleaningTableData" border style="width: 100%">
          <el-table-column prop="metric" label="指标" width="150" />
          <el-table-column prop="before" label="清洗前" width="120" />
          <el-table-column prop="after" label="清洗后" width="120" />
          <el-table-column prop="change" label="变化" />
        </el-table>
      </div>

      <div v-if="stageDetail?.detail?.cleaning_operations" class="detail-section">
        <h4>具体清洗操作</h4>
        <div class="operation-stats">
          <div v-if="stageDetail.detail.cleaning_operations.duplicates_removed" class="stat-item">
            <span class="stat-label">移除重复数据：</span>
            <span class="stat-value">{{ stageDetail.detail.cleaning_operations.duplicates_removed }} 条</span>
          </div>
          <div v-if="stageDetail.detail.cleaning_operations.low_quality_filtered" class="stat-item">
            <span class="stat-label">过滤低质量内容：</span>
            <span class="stat-value">{{ stageDetail.detail.cleaning_operations.low_quality_filtered }} 条</span>
          </div>
          <div v-if="stageDetail.detail.cleaning_operations.format_standardized" class="stat-item">
            <span class="stat-label">标准化格式：</span>
            <span class="stat-value">{{ stageDetail.detail.cleaning_operations.format_standardized }} 条</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 数据分析 -->
    <div v-else-if="stageKey === 'analyzing'" class="stage-detail-content">
      <div v-if="stageDetail?.detail?.rag_results_count" class="detail-section">
        <h4>RAG 检索情况</h4>
        <p>命中 {{ stageDetail.detail.rag_results_count }} 条相关文档</p>
      </div>

      <div v-if="stageDetail?.detail?.rag_results?.length" class="detail-section">
        <h4>RAG 检索内容</h4>
        <div class="rag-cards">
          <div
            v-for="(rag, index) in stageDetail.detail.rag_results"
            :key="index"
            class="rag-card"
          >
            <div class="rag-header">
              <span class="rag-title">{{ rag.title || '文档 ' + (index + 1) }}</span>
              <el-tag v-if="rag.relevance_score" type="warning" size="small">相关度 {{ (rag.relevance_score * 100).toFixed(0) }}%</el-tag>
            </div>
            <div class="rag-content">{{ rag.content_snippet || '无内容' }}</div>
          </div>
        </div>
      </div>

      <div v-if="stageDetail?.detail?.dimensions?.length" class="detail-section">
        <h4>分析维度</h4>
        <div class="keyword-tags">
          <el-tag
            v-for="dim in stageDetail.detail.dimensions"
            :key="dim"
            type="primary"
            size="small"
          >
            {{ dim }}
          </el-tag>
        </div>
      </div>

      <div v-if="stageDetail?.detail?.insights?.length" class="detail-section">
        <h4>分析洞察 ({{ stageDetail.detail.insights.length }})</h4>
        <div class="insight-cards">
          <div
            v-for="(insight, index) in stageDetail.detail.insights"
            :key="index"
            class="insight-card"
          >
            <div v-if="insight.dimension" class="insight-dimension">
              <el-tag type="primary" size="small">{{ insight.dimension }}</el-tag>
            </div>
            <div v-if="insight.title" class="insight-title">{{ insight.title }}</div>
            <div class="insight-content">{{ insight.content || '无内容' }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 报告生成 -->
    <div v-else-if="stageKey === 'reporting'" class="stage-detail-content">
      <div v-if="stageDetail?.detail?.chart_count !== undefined" class="detail-section">
        <h4>报告统计</h4>
        <div class="report-stats">
          <div class="stat-item">
            <span class="stat-label">报告字数：</span>
            <span class="stat-value">{{ stageDetail.detail.report_markdown?.length || 0 }} 字</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">图表数量：</span>
            <span class="stat-value">{{ stageDetail.detail.chart_count }} 张</span>
          </div>
        </div>
      </div>

      <div v-if="stageDetail?.detail?.report_markdown" class="detail-section">
        <h4>报告正文</h4>
        <div class="report-content" v-html="stageDetail.detail.report_markdown"></div>
      </div>
    </div>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  visible: boolean;
  stageName: string;
  stageKey: string;
  stageDetail: any;
}>();

const emit = defineEmits<{
  'update:visible': [value: boolean];
}>();

const cleaningTableData = computed(() => {
  if (!props.stageDetail?.detail?.stats) return [];
  const stats = props.stageDetail.detail.stats;
  return [
    {
      metric: '数据总量',
      before: stats.total_in || 0,
      after: stats.total_out || 0,
      change: `${(stats.total_in || 0) - (stats.total_out || 0)} 条`,
    },
    {
      metric: '有效数据',
      before: stats.total_in || 0,
      after: stats.total_out || 0,
      change: '-',
    },
    {
      metric: '移除数据',
      before: 0,
      after: stats.removed_count || 0,
      change: `${stats.removed_count || 0} 条`,
    },
  ];
});
</script>

<style scoped>
.duration-badge {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e5e7eb;
}

.stage-detail-content {
  max-height: 60vh;
  overflow-y: auto;
}

.detail-section {
  margin-bottom: 24px;
}

.detail-section h4 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 12px;
  color: #1f2937;
}

.cleaning-summary-text {
  line-height: 1.6;
  color: #4b5563;
  padding: 12px;
  background: #f9fafb;
  border-radius: 6px;
  border-left: 3px solid #10b981;
}

.operation-stats {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stat-item {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  background: #f9fafb;
  border-radius: 6px;
}

.stat-label {
  color: #6b7280;
  font-size: 14px;
}

.stat-value {
  color: #1f2937;
  font-weight: 600;
  font-size: 14px;
  margin-left: 8px;
}

.keyword-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.source-cards,
.rag-cards,
.insight-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.source-card,
.rag-card,
.insight-card {
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #f9fafb;
}

.source-title,
.insight-title {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 6px;
  color: #1f2937;
}

.source-snippet,
.insight-content {
  font-size: 13px;
  color: #6b7280;
  margin-bottom: 6px;
  line-height: 1.5;
}

.source-uri {
  font-size: 12px;
}

.source-uri a {
  color: #3b82f6;
  text-decoration: none;
}

.source-uri a:hover {
  text-decoration: underline;
}

.rag-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.rag-title {
  font-weight: 600;
  font-size: 14px;
  color: #1f2937;
}

.rag-content {
  font-size: 13px;
  color: #6b7280;
  line-height: 1.5;
}

.insight-dimension {
  margin-bottom: 8px;
}

.report-stats {
  display: flex;
  gap: 24px;
}

.report-content {
  padding: 16px;
  background: #f9fafb;
  border-radius: 8px;
  line-height: 1.8;
}

.report-content :deep(h1),
.report-content :deep(h2),
.report-content :deep(h3) {
  margin-top: 16px;
  margin-bottom: 8px;
}

.report-content :deep(p) {
  margin-bottom: 12px;
}
</style>
