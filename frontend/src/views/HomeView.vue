<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
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

const fetchSummaryData = async () => {
  loading.value = true;
  try {
    const [dsRes, tRes, rRes] = await Promise.all([
      dataSourcesApi.getDataSources({ limit: 100 }),
      tasksApi.getTasks({ limit: 100 }),
      reportsApi.getReports({ limit: 5 }),
    ]);
    stats.value.dataSourcesCount = dsRes.data?.length || 0;
    stats.value.tasksCount = tRes.data?.length || 0;
    stats.value.reportsCount = rRes.data?.length || 0;
    recentReports.value = rRes.data || [];
  } catch (err: any) {
    ElMessage.error('获取统计数据异常');
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
  const myChart = echarts.init(chartRef.value);

  const option = {
    title: {
      text: '报告产出统计',
      left: 'center',
      textStyle: { color: '#2d3748', fontSize: 16, fontWeight: 600 },
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
    },
    yAxis: {
      type: 'value',
    },
    series: [
      {
        name: '报告数量',
        type: 'bar',
        barWidth: '60%',
        data: statisticsData.value.map(item => item.count),
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#409eff' },
            { offset: 1, color: '#67c23a' },
          ]),
          borderRadius: [4, 4, 0, 0],
        },
      },
    ],
  };

  myChart.setOption(option);
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
  const myChart = echarts.init(trendChartRef.value);
  const option = {
    title: {
      text: '系统性能趋势',
      left: 'center',
      textStyle: { color: '#2d3748', fontSize: 16, fontWeight: 600 },
    },
    tooltip: { trigger: 'axis' },
    legend: { data: ['请求速率 (req/s)', 'P95 延迟 (ms)'], bottom: 0 },
    grid: { left: '3%', right: '4%', bottom: '12%', containLabel: true },
    xAxis: {
      type: 'category',
      data: metricsHistory.value.map(item => item.time),
      boundaryGap: false,
    },
    yAxis: [
      {
        type: 'value',
        name: 'req/s',
      },
      {
        type: 'value',
        name: 'ms',
      },
    ],
    series: [
      {
        name: '请求速率 (req/s)',
        type: 'line',
        data: metricsHistory.value.map(item => item.rps),
        smooth: true,
        itemStyle: { color: '#409eff' },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(64,158,255,0.3)' }, { offset: 1, color: 'rgba(64,158,255,0.05)' }]) },
      },
      {
        name: 'P95 延迟 (ms)',
        type: 'line',
        yAxisIndex: 1,
        data: metricsHistory.value.map(item => item.latency),
        smooth: true,
        itemStyle: { color: '#e6a23c' },
      },
    ],
  };
  myChart.setOption(option);
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
            <span class="metric-card-small-val" style="color: #409eff">{{ metricsData?.requests_per_second?.toFixed(1) || '--' }} req/s</span>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="metric-card-small">
          <div class="metric-card-small-content">
            <span class="metric-card-small-label">P95 延迟</span>
            <span class="metric-card-small-val" style="color: #e6a23c">{{ metricsData?.latency_ms_p95?.toFixed(1) || '--' }} ms</span>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="metric-card-small">
          <div class="metric-card-small-content">
            <span class="metric-card-small-label">错误率</span>
            <span class="metric-card-small-val" :style="{ color: (metricsData?.error_rate ?? 0) > 5 ? '#f56c6c' : '#67c23a' }">{{ metricsData?.error_rate?.toFixed(2) || '--' }} %</span>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="metric-card-small">
          <div class="metric-card-small-content">
            <span class="metric-card-small-label">CPU</span>
            <span class="metric-card-small-val" :style="{ color: (metricsData?.cpu_percent ?? 0) > 80 ? '#f56c6c' : '#409eff' }">{{ metricsData?.cpu_percent?.toFixed(1) || '--' }} %</span>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="metric-card-small">
          <div class="metric-card-small-content">
            <span class="metric-card-small-label">内存</span>
            <span class="metric-card-small-val" :style="{ color: (metricsData?.memory_percent ?? 0) > 80 ? '#f56c6c' : '#409eff' }">{{ metricsData?.memory_percent?.toFixed(1) || '--' }} %</span>
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
  gap: 24px;
}

.banner {
  background: linear-gradient(135deg, #2b3040 0%, #161922 100%);
  color: white;
  padding: 32px 40px;
  border-radius: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.15);
}

.banner h2 {
  margin: 0 0 10px 0;
  font-size: 26px;
  font-weight: 700;
  background: linear-gradient(135deg, #409eff, #67c23a);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.banner p {
  margin: 0;
  color: #a0aec0;
  font-size: 15px;
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
  border-radius: 12px;
  border: none;
  display: flex;
  align-items: center;
  padding: 10px;
}

.metric-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  margin-right: 16px;
}

.reports-card .metric-icon { background: rgba(103, 194, 58, 0.1); color: #67c23a; }

.health-card .metric-icon { background: rgba(64, 158, 255, 0.1); color: #409eff; }

.metric-title {
  font-size: 14px;
  color: #718096;
  margin-bottom: 4px;
}

.metric-val {
  font-size: 26px;
  font-weight: 700;
  color: #2d3748;
}

.metric-unit {
  font-size: 14px;
  font-weight: normal;
  color: #a0aec0;
}

.statistics-card {
  border-radius: 12px;
  border: none;
  height: 500px;
}

.recent-reports-card {
  border-radius: 12px;
  border: none;
  flex: 1;
  min-height: 300px;
}

.echarts-box {
  width: 100%;
  height: 420px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-weight: 600;
  font-size: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.period-buttons {
  display: flex;
  gap: 8px;
}

.view-all-link {
  color: #409eff;
  font-size: 14px;
  text-decoration: none;
  cursor: pointer;
  transition: opacity 0.2s;
}

.view-all-link:hover {
  opacity: 0.8;
  text-decoration: underline;
}

.metrics-row {
  margin-bottom: 24px;
}

.metric-card-small {
  border-radius: 12px;
  border: none;
}

.metric-card-small-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}

.metric-card-small-label {
  font-size: 13px;
  color: #718096;
}

.metric-card-small-val {
  font-size: 22px;
  font-weight: 700;
}

.trend-chart-card {
  border-radius: 12px;
  border: none;
  margin-bottom: 20px;
}
</style>
