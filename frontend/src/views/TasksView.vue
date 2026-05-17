<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue';
import { tasksApi, type TaskInfo } from '../api';
import { Plus, Refresh, VideoPlay, Tickets } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';

const tasks = ref<TaskInfo[]>([]);
const loading = ref(false);
const dialogVisible = ref(false);
const detailVisible = ref(false);
const currentTask = ref<TaskInfo | null>(null);
const runLoadingMap = ref<Record<number, boolean>>({});

const form = reactive({
  name: '',
  type: 'market_analysis',
  trigger_mode: 'manual',
  prompt_template: 'PEST 深度行业洞察模版',
});

const rules = {
  name: [{ required: true, message: '请输入分析任务名称', trigger: 'blur' }],
};

const formRef = ref();

const fetchTasks = async () => {
  loading.value = true;
  try {
    const res = await tasksApi.getTasks();
    tasks.value = res.data || [];
  } catch (err) {
    ElMessage.error('获取任务列表失败');
  } finally {
    loading.value = false;
  }
};

const handleCreate = () => {
  form.name = '';
  form.type = 'market_analysis';
  form.trigger_mode = 'manual';
  form.prompt_template = 'PEST 深度行业洞察模版';
  dialogVisible.value = true;
};

const handleSave = async () => {
  if (!formRef.value) return;
  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) return;
    await tasksApi.createTask({
      name: form.name,
      type: form.type,
      trigger_mode: form.trigger_mode,
      input_data: { prompt_template: form.prompt_template },
    });
    ElMessage.success('创建分析任务实例成功');
    dialogVisible.value = false;
    fetchTasks();
  });
};

const handleRun = async (row: TaskInfo) => {
  runLoadingMap.value[row.id] = true;
  try {
    const res = await tasksApi.triggerTask(row.id);
    ElMessage.success(`分析任务调度成功 (Run ID: ${res.data.run_id})，正在后台生成多模态研报`);
    fetchTasks();
  } catch (err) {
    ElMessage.error('调度失败');
  } finally {
    runLoadingMap.value[row.id] = false;
  }
};

const showDetail = (row: TaskInfo) => {
  currentTask.value = row;
  detailVisible.value = true;
};

onMounted(() => {
  fetchTasks();
});
</script>

<template>
  <div class="tasks-container">
    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">市场洞察分析流水线任务监控</span>
          <div class="actions">
            <el-button :icon="Refresh" @click="fetchTasks" circle title="刷新列表"></el-button>
            <el-button type="primary" :icon="Plus" @click="handleCreate">新建分析任务</el-button>
          </div>
        </div>
      </template>

      <el-table v-loading="loading" :data="tasks" stripe style="width: 100%">
        <el-table-column prop="id" label="任务编号" width="100" />
        <el-table-column prop="name" label="任务实例名称" min-width="200" />
        <el-table-column prop="type" label="分析模式" width="160">
          <template #default="{ row }">
            <el-tag size="small" type="warning">
              {{ row.type === 'market_analysis' ? '行业洞察智能流' : row.type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="trigger_mode" label="触发模式" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="row.trigger_mode === 'cron' ? 'primary' : 'info'">
              {{ row.trigger_mode.toUpperCase() }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="运行状态" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'completed' ? 'success' : row.status === 'running' ? 'primary' : 'warning'">
              {{ row.status === 'completed' ? '已完成' : row.status === 'running' ? '执行中' : row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ new Date(row.created_at).toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right" align="center">
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              :icon="VideoPlay"
              :loading="runLoadingMap[row.id]"
              @click="handleRun(row)"
            >
              启动调度
            </el-button>
            <el-button size="small" :icon="Tickets" @click="showDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新建弹窗 -->
    <el-dialog v-model="dialogVisible" title="创建市场洞察分析流水线" width="520px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-form-item label="任务名称" prop="name">
          <el-input v-model="form.name" placeholder="例如: 2026年Q2 AI 硬件赛道深度分析" />
        </el-form-item>
        <el-form-item label="分析引擎" prop="type">
          <el-select v-model="form.type" style="width: 100%" disabled>
            <el-option label="行业洞察大模型多步推导流" value="market_analysis" />
          </el-select>
        </el-form-item>
        <el-form-item label="调度方式" prop="trigger_mode">
          <el-radio-group v-model="form.trigger_mode">
            <el-radio label="manual">手动单次触发 (Manual)</el-radio>
            <el-radio label="cron">定时轮询监控 (Cron)</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="关联研报大纲" prop="prompt_template">
          <el-select v-model="form.prompt_template" style="width: 100%">
            <el-option label="PEST 宏观与微观赛道深度分析" value="PEST 深度行业洞察模版" />
            <el-option label="SWOT 竞品对比与商业机会洞察" value="SWOT 商业模型洞察模版" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSave">确认拉起</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" title="分析任务配置详情" width="600px">
      <div v-if="currentTask" class="detail-box">
        <p><strong>任务实例 ID:</strong> {{ currentTask.id }}</p>
        <p><strong>任务名称:</strong> {{ currentTask.name }}</p>
        <p><strong>调度模式:</strong> <el-tag size="small">{{ currentTask.trigger_mode }}</el-tag></p>
        <p><strong>状态:</strong> <el-tag size="small" type="success">{{ currentTask.status }}</el-tag></p>
        <p><strong>大纲参数配置:</strong></p>
        <pre class="json-code">{{ JSON.stringify(currentTask.input_data, null, 2) }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.tasks-container {
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
  gap: 12px;
}

.detail-box {
  font-size: 14px;
  line-height: 1.8;
}

.json-code {
  background-color: #2b3040;
  color: #a0aec0;
  padding: 16px;
  border-radius: 8px;
  overflow-x: auto;
}
</style>
