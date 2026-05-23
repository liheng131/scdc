<script setup lang="ts">
/**
 * 仪表盘（Dashboard）页面
 *
 * 系统首页，展示核心指标概览和任务状态分布图。
 *
 * 为什么使用 ECharts 饼图展示任务分布：
 * - 饼图直观展示各状态任务的比例，管理层用户无需查看任务列表即可了解系统负载
 * - ECharts 的环形图（radius: ['40%', '70%']）视觉效果现代、空间利用率高
 *
 * 为什么使用 Promise.all 并行请求：
 * - 三个 API 互不依赖，并行请求减少总加载时间
 * - 任一请求失败不影响其他指标展示（stats 初始值为 0）
 *
 * 为什么点击报告标题跳转到报告详情：
 * - 提供从概览到详情的快速导航路径，减少用户操作步骤
 */
import { ref, onMounted } from 'vue';
import { DataLine, Document, List, Connection, RefreshRight } from '@element-plus/icons-vue';
import * as echarts from 'echarts';
import { tasksApi, reportsApi, dataSourcesApi } from '../api';
import { ElMessage } from 'element-plus';

const stats = ref({
  dataSourcesCount: 0,
  tasksCount: 0,
  reportsCount: 0,
  health: '100%',
});

const recentReports = ref<any[]>([]);
const loading = ref(false);
const chartRef = ref<HTMLElement | null>(null);

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

    initChart(tRes.data || []);
  } catch (err: any) {
    ElMessage.error('获取统计数据异常');
  } finally {
    loading.value = false;
  }
};

const initChart = (tasks: any[]) => {
  if (!chartRef.value) return;
  const myChart = echarts.init(chartRef.value);

  const statusMap: Record<string, number> = {
    pending: 0,
    running: 0,
    completed: 0,
    failed: 0,
  };
  tasks.forEach((t) => {
    const s = t.status || 'pending';
    statusMap[s] = (statusMap[s] || 0) + 1;
  });

  const option = {
    title: {
      text: '分析任务调度执行分布',
      left: 'center',
      textStyle: { color: '#2d3748', fontSize: 16, fontWeight: 600 },
    },
    tooltip: { trigger: 'item' },
    legend: { bottom: '0%', left: 'center' },
    series: [
      {
        name: '任务状态',
        type: 'pie',
        radius: ['40%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: '#fff',
          borderWidth: 2,
        },
        label: { show: false },
        data: [
          { value: statusMap.completed, name: '已完成 (Completed)', itemStyle: { color: '#67c23a' } },
          { value: statusMap.running, name: '执行中 (Running)', itemStyle: { color: '#409eff' } },
          { value: statusMap.pending, name: '等待中 (Pending)', itemStyle: { color: '#e6a23c' } },
          { value: statusMap.failed, name: '失败 (Failed)', itemStyle: { color: '#f56c6c' } },
        ],
      },
    ],
  };
  myChart.setOption(option);
};

onMounted(() => {
  fetchSummaryData();
});
</script>

<template>
  <div class="dashboard-container" v-loading="loading">
    <div class="banner">
      <div class="banner-content">
        <h2>欢迎使用市场洞察 AI 智能体决策平台</h2>
        <p>单机 All-in-One 全自动化行业资讯抓取、大模型深度洞察与智能研报组装引擎</p>
      </div>
      <el-button type="primary" :icon="RefreshRight" round @click="fetchSummaryData">刷新指标</el-button>
    </div>

    <!-- 统计指标卡 -->
    <el-row :gutter="20" class="stat-cards">
      <el-col :span="6">
        <el-card shadow="hover" class="metric-card ds-card">
          <div class="metric-icon"><el-icon><Connection /></el-icon></div>
          <div class="metric-info">
            <div class="metric-title">接入数据源</div>
            <div class="metric-val">{{ stats.dataSourcesCount }} <span class="metric-unit">个</span></div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="metric-card tasks-card">
          <div class="metric-icon"><el-icon><List /></el-icon></div>
          <div class="metric-info">
            <div class="metric-title">任务实例总数</div>
            <div class="metric-val">{{ stats.tasksCount }} <span class="metric-unit">例</span></div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="metric-card reports-card">
          <div class="metric-icon"><el-icon><Document /></el-icon></div>
          <div class="metric-info">
            <div class="metric-title">智能产出报告</div>
            <div class="metric-val">{{ stats.reportsCount }} <span class="metric-unit">份</span></div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="metric-card health-card">
          <div class="metric-icon"><el-icon><DataLine /></el-icon></div>
          <div class="metric-info">
            <div class="metric-title">系统健康度</div>
            <div class="metric-val">{{ stats.health }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表与动态列表 -->
    <el-row :gutter="20" class="charts-row">
      <el-col :span="12">
        <el-card shadow="hover" class="chart-card">
          <div ref="chartRef" class="echarts-box"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover" class="recent-reports-card">
          <template #header>
            <div class="card-header">
              <span class="card-title"><el-icon><Document /></el-icon> 最新生成的行研报告</span>
              <el-button type="primary" link router to="/reports">查看全部</el-button>
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

.ds-card .metric-icon { background: rgba(64, 158, 255, 0.1); color: #409eff; }
.tasks-card .metric-icon { background: rgba(230, 162, 60, 0.1); color: #e6a23c; }
.reports-card .metric-icon { background: rgba(103, 194, 58, 0.1); color: #67c23a; }
.health-card .metric-icon { background: rgba(245, 108, 108, 0.1); color: #f56c6c; }

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

.charts-row {
  display: flex;
}

.chart-card, .recent-reports-card {
  border-radius: 12px;
  border: none;
  height: 380px;
}

.echarts-box {
  width: 100%;
  height: 340px;
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
</style>
