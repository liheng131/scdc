<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Edit, Delete, Connection, StarFilled } from '@element-plus/icons-vue'
import { settingsApi, type AiModelConfig } from '../api/services/settings'

const MODEL_TYPE_LABELS: Record<string, string> = {
  llm: 'LLM 推理模型',
  embedding: 'Embedding 嵌入模型',
  rerank: 'Rerank 重排序模型',
}

const MODEL_TYPES = ['llm', 'embedding', 'rerank'] as const

const loading = ref(false)
const models = reactive<Record<string, AiModelConfig[]>>({
  llm: [],
  embedding: [],
  rerank: [],
})

const dialogVisible = ref(false)
const dialogTitle = ref('添加模型')
const dialogLoading = ref(false)
const editingId = ref<number | null>(null)
const currentModelType = ref('llm')

const formData = reactive({
  provider: '',
  model_name: '',
  base_url: '',
  api_key: '',
})

const testingIds = reactive<Set<number>>(new Set())

const fetchModels = async () => {
  loading.value = true
  try {
    const res = await settingsApi.listAiModels()
    const allModels = res.data || []
    models.llm = allModels.filter((m) => m.model_type === 'llm')
    models.embedding = allModels.filter((m) => m.model_type === 'embedding')
    models.rerank = allModels.filter((m) => m.model_type === 'rerank')
  } catch (e: any) {
    ElMessage.error(e?.message || '获取 AI 模型配置失败')
  } finally {
    loading.value = false
  }
}

const maskApiKey = (key: string) => {
  if (!key) return '未设置'
  return '••••••••'
}

const truncateUrl = (url: string) => {
  if (!url) return ''
  return url.length > 40 ? url.slice(0, 40) + '...' : url
}

const openAddDialog = (modelType: string) => {
  editingId.value = null
  dialogTitle.value = '添加模型'
  currentModelType.value = modelType
  formData.provider = ''
  formData.model_name = ''
  formData.base_url = ''
  formData.api_key = ''
  dialogVisible.value = true
}

const openEditDialog = (row: AiModelConfig) => {
  editingId.value = row.id
  dialogTitle.value = '编辑模型'
  currentModelType.value = row.model_type
  formData.provider = row.provider
  formData.model_name = row.model_name
  formData.base_url = row.base_url
  formData.api_key = ''
  dialogVisible.value = true
}

const handleSave = async () => {
  if (!formData.provider.trim()) {
    ElMessage.warning('请输入供应商')
    return
  }
  if (!formData.model_name.trim()) {
    ElMessage.warning('请输入模型名')
    return
  }
  if (!formData.base_url.trim()) {
    ElMessage.warning('请输入服务地址')
    return
  }

  dialogLoading.value = true
  try {
    if (editingId.value) {
      const updateData: any = {
        provider: formData.provider.trim(),
        model_name: formData.model_name.trim(),
        model_type: currentModelType.value,
        base_url: formData.base_url.trim(),
      }
      if (formData.api_key) {
        updateData.api_key = formData.api_key
      }
      await settingsApi.updateAiModel(editingId.value, updateData)
      ElMessage.success('模型配置更新成功')
    } else {
      await settingsApi.createAiModel({
        provider: formData.provider.trim(),
        model_name: formData.model_name.trim(),
        model_type: currentModelType.value,
        base_url: formData.base_url.trim(),
        api_key: formData.api_key,
      })
      ElMessage.success('模型添加成功')
    }
    dialogVisible.value = false
    fetchModels()
  } catch (e: any) {
    ElMessage.error(e?.message || '操作失败，请稍后重试')
  } finally {
    dialogLoading.value = false
  }
}

const handleDelete = async (row: AiModelConfig) => {
  try {
    await ElMessageBox.confirm(
      `确认删除模型 "${row.model_name}"？此操作不可恢复。`,
      '删除确认',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' }
    )
    await settingsApi.deleteAiModel(row.id)
    ElMessage.success('模型已删除')
    fetchModels()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.message || '删除失败，请稍后重试')
    }
  }
}

const handleSetDefault = async (row: AiModelConfig) => {
  try {
    await settingsApi.setDefaultAiModel(row.id)
    ElMessage.success(`已将 "${row.model_name}" 设为默认模型`)
    fetchModels()
  } catch (e: any) {
    ElMessage.error(e?.message || '设置默认模型失败')
  }
}

const handleTestConnection = async (row: AiModelConfig) => {
  testingIds.add(row.id)
  try {
    const res = await settingsApi.testAiModel(row.id)
    if (res.data?.status === 'ok') {
      ElMessage.success(`连接成功！模型 "${row.model_name}" 可正常使用`)
    } else {
      ElMessage.warning(`连接失败: ${res.data?.error || '未知错误'}`)
    }
  } catch (e: any) {
    ElMessage.error('测试连接请求失败，请检查后端服务')
  } finally {
    testingIds.delete(row.id)
  }
}

const isTesting = (id: number) => testingIds.has(id)

onMounted(() => {
  fetchModels()
})
</script>

<template>
  <div class="settings-container">
    <el-card
      v-for="modelType in MODEL_TYPES"
      :key="modelType"
      shadow="never"
      class="settings-card"
      v-loading="loading"
    >
      <template #header>
        <div class="card-header">
          <span class="card-title">{{ MODEL_TYPE_LABELS[modelType] }}</span>
          <el-button type="primary" :icon="Plus" @click="openAddDialog(modelType)">
            添加模型
          </el-button>
        </div>
      </template>

      <el-table
        v-if="models[modelType].length > 0"
        :data="models[modelType]"
        stripe
        style="width: 100%"
      >
        <el-table-column prop="provider" label="供应商" width="120" />
        <el-table-column prop="model_name" label="模型名" width="160" />
        <el-table-column label="服务地址" min-width="200">
          <template #default="{ row }">
            <el-tooltip :content="row.base_url" placement="top" :disabled="!row.base_url || row.base_url.length <= 40">
              <span>{{ truncateUrl(row.base_url) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="API Key" width="100" align="center">
          <template #default="{ row }">
            <span :class="{ 'api-key-unset': !row.api_key }">
              {{ maskApiKey(row.api_key) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="默认标记" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" type="warning" size="small">
              <el-icon style="margin-right: 2px"><StarFilled /></el-icon>
              默认
            </el-tag>
            <span v-else class="not-default">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="320" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="primary" size="small" :icon="Edit" @click="openEditDialog(row)">
              编辑
            </el-button>
            <el-popconfirm
              title="确认删除该模型？"
              confirm-button-text="确认删除"
              cancel-button-text="取消"
              @confirm="handleDelete(row)"
            >
              <template #reference>
                <el-button type="danger" size="small" :icon="Delete">
                  删除
                </el-button>
              </template>
            </el-popconfirm>
            <el-button
              type="warning"
              size="small"
              :disabled="row.is_default"
              @click="handleSetDefault(row)"
            >
              设为默认
            </el-button>
            <el-button
              type="success"
              size="small"
              :icon="Connection"
              :loading="isTesting(row.id)"
              @click="handleTestConnection(row)"
            >
              测试连接
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty
        v-else
        :description="`暂无${MODEL_TYPE_LABELS[modelType]}配置`"
        :image-size="80"
      />
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="520px"
      :close-on-click-modal="false"
    >
      <el-form label-width="100px" @submit.prevent="handleSave">
        <el-form-item label="供应商" required>
          <el-input v-model="formData.provider" placeholder="例如: deepseek / kimi / ollama" />
        </el-form-item>
        <el-form-item label="模型名" required>
          <el-input v-model="formData.model_name" placeholder="例如: deepseek-chat" />
        </el-form-item>
        <el-form-item label="服务地址" required>
          <el-input
            v-model="formData.base_url"
            placeholder="例如: http://localhost:11434"
          />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="formData.api_key"
            type="password"
            show-password
            placeholder="输入 API Key（可选）"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="dialogLoading" @click="handleSave">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.settings-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 1200px;
}

.settings-card {
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

.api-key-unset {
  color: #c0c4cc;
  font-style: italic;
}

.not-default {
  color: #c0c4cc;
}
</style>