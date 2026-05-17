<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue';
import { dataSourcesApi, type DataSourceInfo } from '../api';
import { Plus, Refresh, Delete, Edit, Check } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';

const dataSources = ref<DataSourceInfo[]>([]);
const loading = ref(false);
const dialogVisible = ref(false);
const syncLoadingMap = ref<Record<number, boolean>>({});

const form = reactive({
  id: undefined as number | undefined,
  name: '',
  source_type: 'rss',
  configUrl: '',
});

const rules = {
  name: [{ required: true, message: '请输入数据源名称', trigger: 'blur' }],
  configUrl: [{ required: true, message: '请输入数据源目标连接或 RSS URL', trigger: 'blur' }],
};

const formRef = ref();

const fetchDataSources = async () => {
  loading.value = true;
  try {
    const res = await dataSourcesApi.getDataSources();
    dataSources.value = res.data || [];
  } catch (err) {
    ElMessage.error('获取数据源列表失败');
  } finally {
    loading.value = false;
  }
};

const handleAdd = () => {
  form.id = undefined;
  form.name = '';
  form.source_type = 'rss';
  form.configUrl = '';
  dialogVisible.value = true;
};

const handleEdit = (row: DataSourceInfo) => {
  form.id = row.id;
  form.name = row.name;
  form.source_type = row.source_type;
  form.configUrl = row.config?.url || '';
  dialogVisible.value = true;
};

const handleDelete = (row: DataSourceInfo) => {
  ElMessageBox.confirm(`确定要删除数据源 "${row.name}" 吗？`, '警告', {
    confirmButtonText: '确定删除',
    cancelButtonText: '取消',
    type: 'warning',
  }).then(async () => {
    await dataSourcesApi.deleteDataSource(row.id);
    ElMessage.success('删除成功');
    fetchDataSources();
  }).catch(() => {});
};

const handleSave = async () => {
  if (!formRef.value) return;
  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) return;
    const configData = { url: form.configUrl };
    if (form.id) {
      await dataSourcesApi.updateDataSource(form.id, {
        name: form.name,
        source_type: form.source_type,
        config: configData,
      });
      ElMessage.success('更新成功');
    } else {
      await dataSourcesApi.createDataSource({
        name: form.name,
        source_type: form.source_type,
        config: configData,
      });
      ElMessage.success('创建成功');
    }
    dialogVisible.value = false;
    fetchDataSources();
  });
};

const handleSync = async (row: DataSourceInfo) => {
  syncLoadingMap.value[row.id] = true;
  try {
    const res = await dataSourcesApi.syncDataSource(row.id);
    ElMessage.success(`触发同步成功，共抓取到 ${res.data.records_collected} 条新增资讯`);
    fetchDataSources();
  } catch (err) {
    ElMessage.error('同步异常');
  } finally {
    syncLoadingMap.value[row.id] = false;
  }
};

onMounted(() => {
  fetchDataSources();
});
</script>

<template>
  <div class="ds-container">
    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">数据源监控与采集配置</span>
          <div class="actions">
            <el-button :icon="Refresh" @click="fetchDataSources" circle title="刷新列表"></el-button>
            <el-button type="primary" :icon="Plus" @click="handleAdd">接入新数据源</el-button>
          </div>
        </div>
      </template>

      <el-table v-loading="loading" :data="dataSources" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="数据源名称" min-width="180" />
        <el-table-column prop="source_type" label="采集类型" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="row.source_type === 'rss' ? 'success' : 'primary'">
              {{ row.source_type.toUpperCase() }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="目标连接配置 (Config URL)" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">
            <code>{{ row.config?.url || '--' }}</code>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'">
              {{ row.status === 'active' ? '活跃' : row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ new Date(row.created_at).toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right" align="center">
          <template #default="{ row }">
            <el-button
              type="success"
              size="small"
              :icon="Check"
              :loading="syncLoadingMap[row.id]"
              @click="handleSync(row)"
            >
              手动抓取
            </el-button>
            <el-button type="primary" size="small" :icon="Edit" @click="handleEdit(row)" circle></el-button>
            <el-button type="danger" size="small" :icon="Delete" @click="handleDelete(row)" circle></el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 增改弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="form.id ? '编辑数据源配置' : '接入新数据源'"
      width="500px"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-form-item label="数据源名称" prop="name">
          <el-input v-model="form.name" placeholder="例如: 36氪创投圈 RSS" />
        </el-form-item>
        <el-form-item label="数据源类型" prop="source_type">
          <el-select v-model="form.source_type" style="width: 100%">
            <el-option label="RSS 订阅流 (RSS)" value="rss" />
            <el-option label="网页动态抓取 (Web)" value="web" />
            <el-option label="开放接口 (API)" value="api" />
          </el-select>
        </el-form-item>
        <el-form-item label="抓取目标 URL" prop="configUrl">
          <el-input v-model="form.configUrl" placeholder="https://..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSave">确认保存</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.ds-container {
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
</style>
