<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue';
import { DataLine, Document, RefreshRight } from '@element-plus/icons-vue';
import * as echarts from 'echarts';
import { tasksApi, reportsApi, dataSourcesApi, type ReportStatisticsItem, metricsApi, type MetricsData } from '../api';
import { ElMessage } from 'element-plus';

const stats = ref({
  dataSourcesCount: 0,
  tasksCount: 0,
  reportsCount: 0,
  health: '100%',
});

const recentReports = ref<any[]>([]);
const loading = ref(false);
const currentPeriod = ref<'month' | 'week' | 'day' | 'year'>('month');
const statisticsData = ref<ReportStatisticsItem[]>([]);
const statisticsLoading = ref(false);
const chartRef = ref<HTMLElement | null>(null);

const metricsData = ref<MetricsData | null>(null);
const metricsHistory = ref<Array<{ time: string; rps: number; latency: number }>>([]);
let metricsTimer: ReturnType<typeof setInterval> | null = null;
const trendChartRef = ref<HTMLElement | null>(null);

// ECharts instances for lifecycle management
let statisticsChart: echarts.ECharts | null = null;
let trendChart: echarts.ECharts | null = null;

const fetchSummaryData = async () => {
  loading.value = true;
  try {
    // 使用独立的 try-catch 处理每个 API 调用，避免一个失败影响其他
    const dsRes = await dataSourcesApi.getDataSources({ limit: 100 }).catch((err: any) => {
      console.warn('[HomeView] 获取数据源失败:', err);
      return null;
    });
    const tRes = await tasksApi.getTasks({ limit: 100 }).catch((err: any) => {
      console.warn('[HomeView] 获取任务列表失败:', err);
      return null;
    });
    const rRes = await reportsApi.getReports({ skip: 0, limit: 5 }).catch((err: any) => {
      console.warn('[HomeView] 获取报告列表失败:', err);
      return null;
    });

    if (dsRes) stats.value.dataSourcesCount = dsRes.data?.length || 0;
    if (tRes) stats.value.tasksCount = tRes.data?.length || 0;
    if (rRes && rRes.data) {
      stats.value.reportsCount = rRes.data.total ?? 0;
      recentReports.value = rRes.data.items || [];
    }
  } catch (err: any) {
    console.error('[HomeView] 获取统计数据异常:', err);
    // 不显示全局错误提示，避免与拦截器提示重复
  } finally {
    loading.value = false;
  }
};

const fetchStatistics = async () => {
  statisticsLoading.value = true;
  try {
    const res = await reportsApi.getStatistics({ period: currentPeriod.value });
    statisticsData.value = res.data?.items || [];
    initStatisticsChart();
  } catch (err: any) {
    ElMessage.error('获取报告统计异常');
  } finally {
    statisticsLoading.value = false;
  }
};

const initStatisticsChart = () => {
  if (!chartRef.value) return;
  if (statisticsChart) statisticsChart.dispose();

  statisticsChart = echarts.init(chartRef.value);

  const option = {
    title: {
      text: '报告产出统计',
      left: 'center',
      textStyle: { color: '#2B2419', fontSize: 18, fontWeight: 600, fontFamily: 'Fraunces, Georgia, serif' },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow',
      },
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: statisticsData.value.map(item => item.label),
      axisTick: {
        alignWithLabel: true,
      },
      axisLabel: { color: '#6B6258' },
      axisLine: { lineStyle: { color: '#EAE3D2' } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#6B6258' },
      splitLine: { lineStyle: { color: '#EAE3D2' } },
    },
    series: [
      {
        name: '报告数量',
        type: 'bar',
        barWidth: '60%',
        data: statisticsData.value.map(item => item.count),
        itemStyle: {
          color: '#B45309',
          borderRadius: [6, 6, 0, 0],
        },
      },
    ],
  };

  statisticsChart.setOption(option);
  window.addEventListener('resize', () => statisticsChart?.resize());
};

const fetchMetrics = async () => {
  try {
    const res = await metricsApi.getMetrics();
    metricsData.value = res.data;
    const now = new Date();
    const timeStr = now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0') + ':' + now.getSeconds().toString().padStart(2, '0');
    metricsHistory.value.push({
      time: timeStr,
      rps: res.data?.requests_per_second || 0,
      latency: res.data?.latency_ms_p95 || 0,
    });
    if (metricsHistory.value.length > 60) {
      metricsHistory.value.splice(0, metricsHistory.value.length - 60);
    }
    initTrendChart();
  } catch (err) {
    // silent fail for metrics
  }
};

const initTrendChart = () => {
  if (!trendChartRef.value || metricsHistory.value.length < 2) return;
  if (trendChart) trendChart.dispose();

  trendChart = echarts.init(trendChartRef.value);
  const option = {
    title: {
      text: '系统性能趋势',
      left: 'center',
      textStyle: { color: '#2B2419', fontSize: 18, fontWeight: 600, fontFamily: 'Fraunces, Georgia, serif' },
    },
    tooltip: { trigger: 'axis' },
    legend: {
      data: ['请求速率 (req/s)', 'P95 延迟 (ms)'],
      bottom: 0,
      textStyle: { color: '#2B2419', fontWeight: 600, fontFamily: 'Fraunces, Georgia, serif' },
    },
    grid: { left: '3%', right: '4%', bottom: '12%', containLabel: true },
    xAxis: {
      type: 'category',
      data: metricsHistory.value.map(item => item.time),
      boundaryGap: false,
      axisLabel: { color: '#6B6258' },
      axisLine: { lineStyle: { color: '#EAE3D2' } },
    },
    yAxis: [
      {
        type: 'value',
        name: 'req/s',
        axisLabel: { color: '#6B6258' },
        splitLine: { lineStyle: { color: '#EAE3D2' } },
      },
      {
        type: 'value',
        name: 'ms',
        axisLabel: { color: '#6B6258' },
        splitLine: { lineStyle: { color: '#EAE3D2' } },
      },
    ],
    series: [
      {
        name: '请求速率 (req/s)',
        type: 'line',
        data: metricsHistory.value.map(item => item.rps),
        smooth: true,
        itemStyle: { color: '#B45309' },
        lineStyle: { color: '#B45309', width: 2 },
        areaStyle: { color: 'rgba(180, 83, 9, 0.08)' },
      },
      {
        name: 'P95 延迟 (ms)',
        type: 'line',
        yAxisIndex: 1,
        data: metricsHistory.value.map(item => item.latency),
        smooth: true,
        itemStyle: { color: '#92400E' },
        lineStyle: { color: '#92400E', width: 2 },
      },
    ],
  };
  trendChart.setOption(option);
  window.addEventListener('resize', () => trendChart?.resize());
};

const handlePeriodChange = (period: 'day' | 'week' | 'month' | 'year') => {
  currentPeriod.value = period;
  fetchStatistics();
};

onMounted(() => {
  fetchSummaryData();
  fetchStatistics();
  fetchMetrics();
  metricsTimer = setInterval(fetchMetrics, 10000);
});

onUnmounted(() => {
  if (metricsTimer) {
    clearInterval(metricsTimer);
    metricsTimer = null;
  }
  if (statisticsChart) {
    statisticsChart.dispose();
    statisticsChart = null;
  }
  if (trendChart) {
    trendChart.dispose();
    trendChart = null;
  }
});
</script>

<template>
  <div class="dashboard-container" v-loading="loading">
    <div class="banner">
      <div class="banner-content">
        <h2>欢迎使用市场洞察 AI 智能体决策平台</h2>
        <p>单机 All-in-One 全自动化行业资讯抓取、大模型深度洞察与智能研报组装引擎</p>
      </div>
      <el-button type="primary" :icon="RefreshRight" round @click="fetchSummaryData; fetchStatistics();">刷新指标</el-button>
    </div>

    <el-row :gutter="20" class="metrics-row">
      <el-col :span="4">
        <el-card shadow="hover" class="metric-card-small">
          <div class="metric-card-small-content">
            <span class="metric-card-small-label">每秒请求</span>
            <span class="metric-card-small-val" style="color: var(--scdc-accent)">{{ metricsData?.requests_per_second?.toFixed(1) || '--' }} req/s</span>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="metric-card-small">
          <div class="metric-card-small-content">
            <span class="metric-card-small-label">P95 延迟</span>
            <span class="metric-card-small-val" style="color: var(--scdc-warning)">{{ metricsData?.latency_ms_p95?.toFixed(1) || '--' }} ms</span>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="metric-card-small">
          <div class="metric-card-small-content">
            <span class="metric-card-small-label">错误率</span>
            <span class="metric-card-small-val" :style="{ color: (metricsData?.error_rate ?? 0) > 5 ? 'var(--scdc-danger)' : 'var(--scdc-success)' }">{{ metricsData?.error_rate?.toFixed(2) || '--' }} %</span>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="metric-card-small">
          <div class="metric-card-small-content">
            <span class="metric-card-small-label">CPU</span>
            <span class="metric-card-small-val" :style="{ color: (metricsData?.cpu_percent ?? 0) > 80 ? 'var(--scdc-danger)' : 'var(--scdc-accent)' }">{{ metricsData?.cpu_percent?.toFixed(1) || '--' }} %</span>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="metric-card-small">
          <div class="metric-card-small-content">
            <span class="metric-card-small-label">内存</span>
            <span class="metric-card-small-val" :style="{ color: (metricsData?.memory_percent ?? 0) > 80 ? 'var(--scdc-danger)' : 'var(--scdc-accent)' }">{{ metricsData?.memory_percent?.toFixed(1) || '--' }} %</span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 主内容区域 -->
    <el-row :gutter="20" class="main-content">
      <!-- 左侧：统计图表 -->
      <el-col :span="12">
        <el-card shadow="hover" class="trend-chart-card" v-if="metricsHistory.length > 0">
          <div ref="trendChartRef" class="echarts-box"></div>
        </el-card>
        <el-card shadow="hover" class="statistics-card">
          <template #header>
            <div class="card-header">
              <span class="card-title">报告产出统计</span>
              <div class="period-buttons">
                <el-button
                  v-for="p in ['day', 'week', 'month', 'year']"
                  :key="p"
                  :type="currentPeriod === p ? 'primary' : 'default'"
                  size="small"
                  @click="handlePeriodChange(p as any)"
                >
                  {{ p === 'day' ? '日' : p === 'week' ? '周' : p === 'month' ? '月' : '年' }}
                </el-button>
              </div>
            </div>
          </template>
          <div ref="chartRef" class="echarts-box" v-loading="statisticsLoading"></div>
        </el-card>
      </el-col>

      <!-- 右侧：两个卡片+报告列表 -->
      <el-col :span="12" class="right-column">
        <!-- 右上：两个统计卡片 -->
        <el-row :gutter="20" class="stat-cards-top">
          <el-col :span="12">
            <el-card shadow="hover" class="metric-card reports-card">
              <div class="metric-icon"><el-icon><Document /></el-icon></div>
              <div class="metric-info">
                <div class="metric-title">智能产出报告</div>
                <div class="metric-val">{{ stats.reportsCount }} <span class="metric-unit">份</span></div>
              </div>
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card shadow="hover" class="metric-card health-card">
              <div class="metric-icon"><el-icon><DataLine /></el-icon></div>
              <div class="metric-info">
                <div class="metric-title">系统健康度</div>
                <div class="metric-val">{{ stats.health }}</div>
              </div>
            </el-card>
          </el-col>
        </el-row>

        <!-- 右下：最新报告列表 -->
        <el-card shadow="hover" class="recent-reports-card">
          <template #header>
            <div class="card-header">
              <span class="card-title"><el-icon><Document /></el-icon> 最新生成的行研报告</span>
              <router-link to="/reports" class="view-all-link">查看全部</router-link>
            </div>
          </template>
          <el-table :data="recentReports" style="width: 100%" stripe>
            <el-table-column prop="title" label="报告标题" min-width="180" show-overflow-tooltip />
            <el-table-column prop="version" label="版本号" width="100">
              <template #default="{ row }">
                <el-tag size="small">{{ row.version || 'v1.0' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="生成状态" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="row.status === 'completed' ? 'success' : 'warning'">
                  {{ row.status === 'completed' ? '完成' : row.status }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.dashboard-container {
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.banner {
  background: var(--scdc-bg-surface);
  border: 1px solid var(--scdc-bg-sunken);
  border-radius: var(--scdc-radius-lg);
  padding: 40px 48px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: var(--scdc-shadow-soft);
  position: relative;
  overflow: hidden;
}

.banner::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse at top right, rgba(180, 83, 9, 0.06), transparent 60%);
  pointer-events: none;
}

.banner-content {
  position: relative;
  z-index: 1;
}

.banner h2 {
  font-family: var(--scdc-font-display);
  color: var(--scdc-ink-strong);
  font-size: 28px;
  font-weight: 600;
  letter-spacing: -0.015em;
  margin: 0 0 10px 0;
  line-height: 1.2;
}

.banner p {
  margin: 0;
  color: var(--scdc-ink-muted);
  font-size: 14px;
  line-height: 1.5;
}

.main-content {
  display: flex;
}

.right-column {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.stat-cards-top {
  display: flex;
}

.metric-card {
  border-radius: var(--scdc-radius-lg);
  border: 1px solid var(--scdc-bg-sunken);
  display: flex;
  align-items: center;
  padding: 20px;
  box-shadow: var(--scdc-shadow-soft);
  transition: transform var(--scdc-transition-base), box-shadow var(--scdc-transition-base);
}

.metric-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--scdc-shadow-lift);
}

.metric-icon {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26px;
  margin-right: 16px;
  flex-shrink: 0;
}

.reports-card .metric-icon { background: var(--scdc-accent-soft); color: var(--scdc-accent); }

.health-card .metric-icon { background: var(--scdc-success-soft); color: var(--scdc-success); }

.metric-title {
  font-size: 13px;
  color: var(--scdc-ink-muted);
  margin-bottom: 6px;
  font-weight: 500;
}

.metric-val {
  font-family: var(--scdc-font-display);
  font-size: 28px;
  font-weight: 600;
  color: var(--scdc-ink-strong);
  line-height: 1;
}

.metric-unit {
  font-size: 14px;
  font-weight: 400;
  color: var(--scdc-ink-soft);
  margin-left: 2px;
}

.statistics-card {
  border-radius: var(--scdc-radius-lg);
  border: 1px solid var(--scdc-bg-sunken);
  height: 480px;
  box-shadow: var(--scdc-shadow-soft);
}

.recent-reports-card {
  border-radius: var(--scdc-radius-lg);
  border: 1px solid var(--scdc-bg-sunken);
  flex: 1;
  min-height: 280px;
  box-shadow: var(--scdc-shadow-soft);
}

.echarts-box {
  width: 100%;
  height: 400px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-family: var(--scdc-font-display);
  font-size: 17px;
  color: var(--scdc-ink-strong);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.period-buttons {
  display: flex;
  gap: 6px;
}

.period-buttons :deep(.el-button) {
  font-weight: 500;
  min-width: 40px;
}

.view-all-link {
  color: var(--scdc-accent);
  font-size: 13px;
  text-decoration: none;
  cursor: pointer;
  transition: color var(--scdc-transition-fast);
  font-weight: 500;
}

.view-all-link:hover {
  color: var(--scdc-accent-hover);
  text-decoration: none;
}

.metrics-row {
  margin-bottom: 4px;
}

.metric-card-small {
  border-radius: var(--scdc-radius-lg);
  border: 1px solid var(--scdc-bg-sunken);
  box-shadow: var(--scdc-shadow-soft);
  transition: transform var(--scdc-transition-base), box-shadow var(--scdc-transition-base);
}

.metric-card-small:hover {
  transform: translateY(-2px);
  box-shadow: var(--scdc-shadow-lift);
}

.metric-card-small-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px 8px;
}

.metric-card-small-label {
  font-size: 12px;
  color: var(--scdc-ink-muted);
  font-weight: 500;
  letter-spacing: 0.02em;
}

.metric-card-small-val {
  font-family: var(--scdc-font-display);
  font-size: 22px;
  font-weight: 600;
  color: var(--scdc-ink-strong);
  line-height: 1;
}

.trend-chart-card {
  border-radius: var(--scdc-radius-lg);
  border: 1px solid var(--scdc-bg-sunken);
  margin-bottom: 20px;
  box-shadow: var(--scdc-shadow-soft);
}

/* 响应式优化 */
@media (max-width: 1200px) {
  .banner { padding: 32px 36px; }
  .banner h2 { font-size: 24px; }
  .metric-val { font-size: 26px; }
  .metric-icon { width: 48px; height: 48px; font-size: 24px; }
  .metric-card-small-val { font-size: 20px; }
  .echarts-box { height: 360px; }
}

@media (max-width: 900px) {
  .banner { 
    padding: 24px; 
    flex-direction: column;
    gap: 16px;
    align-items: flex-start;
  }
  .banner h2 { font-size: 22px; }
  .metric-card-small-content { padding: 12px 4px; }
  .metric-card-small-val { font-size: 18px; }
  .main-content { flex-direction: column; }
  .stat-cards-top { flex-direction: column; }
  .echarts-box { height: 320px; }
}
</style>
