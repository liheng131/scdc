<script setup lang="ts">
/**
 * 数据源管理页面
 *
 * 支持数据源的增删改查和手动同步操作。
 * 点击"查看记录"可以展开该数据源下的采集资讯列表，支持查看、编辑、删除、新增。
 *
 * handleAdd / handleEdit 共用同一个 dialogVisible：
 * - 通过 form.id 是否为 undefined 区分新建和编辑模式
 * - el-dialog 的 title 动态显示"接入新数据源"或"编辑数据源配置"
 *
 * 为什么 syncLoadingMap 使用 Record<number, boolean> 而不是单一 boolean：
 * - 多个数据源可同时触发同步，每个按钮独立显示 loading 状态
 * - 避免点击某行按钮导致其他行按钮也进入 loading
 */
import { ref, reactive, onMounted, nextTick } from 'vue';
import { dataSourcesApi, collectedRecordsApi, type DataSourceInfo, type CollectedRecordInfo } from '../api';
import { Plus, Refresh, Delete, Edit, Check, View, Search, Download } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';

const dataSources = ref<DataSourceInfo[]>([]);
const loading = ref(false);
const dialogVisible = ref(false);
const syncLoadingMap = ref<Record<number, boolean>>({});
const fetchContentLoadingMap = ref<Record<number, boolean>>({});

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

// ===== 采集记录相关状态 =====
const recordsDialogVisible = ref(false);
const recordsLoading = ref(false);
const records = ref<CollectedRecordInfo[]>([]);
const currentDataSourceId = ref(0);
const currentDataSourceName = ref('');

const recordFormVisible = ref(false);
const recordForm = reactive({
  id: undefined as number | undefined,
  title: '',
  url: '',
  content: '',
});
const recordFormRef = ref();
const recordRules = {
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
};

const viewContentVisible = ref(false);
const viewContentTitle = ref('');
const viewContentBody = ref('');

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
    const { records_collected, status, error: errMsg } = res.data;
    if (status === 'crawl_failed') {
      ElMessage.warning(`抓取失败：${errMsg || '无法访问目标页面，请检查 URL 是否正确或网络是否可达'}`);
    } else if (status === 'no_url') {
      ElMessage.warning('数据源未配置 URL');
    } else {
      ElMessage.success(`触发同步成功，共抓取到 ${records_collected} 条新增资讯`);
    }
    fetchDataSources();
  } catch (err) {
    ElMessage.error('同步异常');
  } finally {
    syncLoadingMap.value[row.id] = false;
  }
};

// ===== 采集记录操作 =====

const fetchRecords = async () => {
  if (!currentDataSourceId.value) return;
  recordsLoading.value = true;
  try {
    const res = await collectedRecordsApi.listRecords(currentDataSourceId.value);
    records.value = res.data || [];
  } catch (err) {
    ElMessage.error('获取采集记录失败');
  } finally {
    recordsLoading.value = false;
  }
};

const handleViewRecords = async (row: DataSourceInfo) => {
  currentDataSourceId.value = row.id;
  currentDataSourceName.value = row.name;
  recordsDialogVisible.value = true;
  await fetchRecords();
};

const handleAddRecord = () => {
  recordForm.id = undefined;
  recordForm.title = '';
  recordForm.url = '';
  recordForm.content = '';
  recordFormVisible.value = true;
  nextTick(() => {
    recordFormRef.value?.resetFields();
  });
};

const handleEditRecord = (row: CollectedRecordInfo) => {
  recordForm.id = row.id;
  recordForm.title = row.title;
  recordForm.url = row.url || '';
  recordForm.content = row.content || '';
  recordFormVisible.value = true;
};

const handleDeleteRecord = (row: CollectedRecordInfo) => {
  ElMessageBox.confirm(`确定要删除资讯 "${row.title}" 吗？`, '警告', {
    confirmButtonText: '确定删除',
    cancelButtonText: '取消',
    type: 'warning',
  }).then(async () => {
    await collectedRecordsApi.deleteRecord(currentDataSourceId.value, row.id);
    ElMessage.success('删除成功');
    fetchRecords();
  }).catch(() => {});
};

const handleSaveRecord = async () => {
  if (!recordFormRef.value) return;
  await recordFormRef.value.validate(async (valid: boolean) => {
    if (!valid) return;
    const data = {
      title: recordForm.title,
      url: recordForm.url || undefined,
      content: recordForm.content || undefined,
    };
    if (recordForm.id) {
      await collectedRecordsApi.updateRecord(currentDataSourceId.value, recordForm.id, data);
      ElMessage.success('更新成功');
    } else {
      await collectedRecordsApi.createRecord(currentDataSourceId.value, data);
      ElMessage.success('新增成功');
    }
    recordFormVisible.value = false;
    fetchRecords();
  });
};

const handleViewContent = (row: CollectedRecordInfo) => {
  viewContentTitle.value = row.title;
  viewContentBody.value = row.content || '暂无正文内容，请点击「抓取正文」按钮获取文章全文。';
  viewContentVisible.value = true;
};

const handleFetchContent = async (row: CollectedRecordInfo) => {
  if (!row.url) {
    ElMessage.warning('该记录没有 URL，无法抓取正文');
    return;
  }
  fetchContentLoadingMap.value[row.id] = true;
  try {
    const res = await collectedRecordsApi.fetchContent(currentDataSourceId.value, row.id);
    if (res.code === 0 && res.data) {
      ElMessage.success(`正文抓取成功（${res.data.content ? res.data.content.length : 0} 字符）`);
      fetchRecords();
    } else {
      ElMessage.warning(`抓取失败：${(res.data as any)?.error || '未知错误'}`);
    }
  } catch (err) {
    ElMessage.error('抓取正文异常');
  } finally {
    fetchContentLoadingMap.value[row.id] = false;
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
        <el-table-column label="操作" width="310" fixed="right" align="center">
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
            <el-button
              type="warning"
              size="small"
              :icon="View"
              @click="handleViewRecords(row)"
            >
              查看记录
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

    <!-- 采集记录弹窗 -->
    <el-dialog
      v-model="recordsDialogVisible"
      :title="`${currentDataSourceName} - 采集资讯记录`"
      width="800px"
    >
      <div class="records-toolbar">
        <el-button type="primary" size="small" :icon="Plus" @click="handleAddRecord">新增记录</el-button>
        <el-button size="small" :icon="Refresh" @click="fetchRecords" :loading="recordsLoading">刷新</el-button>
      </div>

      <el-table v-loading="recordsLoading" :data="records" stripe style="width: 100%; margin-top: 12px;" max-height="400">
        <el-table-column type="index" label="#" width="50" />
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column prop="url" label="URL" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <a v-if="row.url" :href="row.url" target="_blank" class="record-link">{{ row.url }}</a>
            <span v-else class="muted-text">--</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="采集时间" width="170">
          <template #default="{ row }">
            {{ new Date(row.created_at).toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="info" size="small" :icon="Search" @click="handleViewContent(row)">内容</el-button>
            <el-button
              type="success"
              size="small"
              :icon="Download"
              :loading="fetchContentLoadingMap[row.id]"
              @click="handleFetchContent(row)"
            >
              抓取正文
            </el-button>
            <el-button type="primary" size="small" :icon="Edit" @click="handleEditRecord(row)" circle></el-button>
            <el-button type="danger" size="small" :icon="Delete" @click="handleDeleteRecord(row)" circle></el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!recordsLoading && records.length === 0" class="records-empty">
        暂无采集记录，请点击「手动抓取」按钮获取资讯
      </div>

      <template #footer>
        <el-button @click="recordsDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 记录新增/编辑弹窗 -->
    <el-dialog
      v-model="recordFormVisible"
      :title="recordForm.id ? '编辑资讯记录' : '新增资讯记录'"
      width="550px"
    >
      <el-form ref="recordFormRef" :model="recordForm" :rules="recordRules" label-width="80px">
        <el-form-item label="标题" prop="title">
          <el-input v-model="recordForm.title" placeholder="请输入资讯标题" />
        </el-form-item>
        <el-form-item label="URL">
          <el-input v-model="recordForm.url" placeholder="https://..." />
        </el-form-item>
        <el-form-item label="正文内容">
          <el-input
            v-model="recordForm.content"
            type="textarea"
            :rows="6"
            placeholder="请输入或粘贴资讯正文内容"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="recordFormVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSaveRecord">确认保存</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 内容查看弹窗 -->
    <el-dialog
      v-model="viewContentVisible"
      :title="viewContentTitle"
      width="600px"
    >
      <div class="content-view" v-text="viewContentBody"></div>
      <template #footer>
        <el-button @click="viewContentVisible = false">关闭</el-button>
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
}

.actions {
  display: flex;
  gap: 12px;
}

.records-toolbar {
  display: flex;
  gap: 10px;
}

.record-link {
  color: var(--scdc-accent);
  text-decoration: none;
  font-size: 13px;
}
.record-link:hover {
  text-decoration: underline;
}

.content-view {
  white-space: pre-wrap;
  line-height: 1.75;
  max-height: 400px;
  overflow-y: auto;
  color: var(--scdc-ink);
  font-size: 15px;
  padding: 8px 0;
}

.muted-text {
  color: var(--scdc-ink-soft);
}

.records-empty {
  text-align: center;
  padding: 40px;
  color: var(--scdc-ink-soft);
}
</style>