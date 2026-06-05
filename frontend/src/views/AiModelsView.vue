<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Edit, Delete, Connection, StarFilled } from '@element-plus/icons-vue'
import { settingsApi, type AiModelConfig } from '../api/services/settings'

const props = defineProps<{
  modelType?: 'llm' | 'embedding' | 'rerank' | 'all'
}>()

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

const displayModels = computed(() => {
  if (props.modelType && props.modelType !== 'all') {
    return models[props.modelType]
  }
  return [...models.llm, ...models.embedding, ...models.rerank]
})

const activeTab = ref(props.modelType || 'llm')

const dialogVisible = ref(false)
const dialogTitle = ref('添加模型')
const dialogLoading = ref(false)
const editingId = ref<number | null>(null)
const currentModelType = ref(props.modelType || 'llm')

const formData = reactive({
  provider: '',
  model_name: '',
  base_url: '',
  api_key: '',
})

const testingIds = ref<Set<number>>(new Set())

const formRules = {
  base_url: (url: string): string | null => {
    if (!url.trim()) return '请输入服务地址'
    if (!/^https?:\/\//i.test(url.trim())) return '服务地址必须以 http:// 或 https:// 开头'
    return null
  },
}

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
  const urlError = formRules.base_url(formData.base_url)
  if (urlError) {
    ElMessage.warning(urlError)
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
  testingIds.value.add(row.id)
  try {
    const res = await settingsApi.testAiModel(row.id)
    if (res.data?.status === 'ok') {
      const details: string[] = []
      if (res.data.message) details.push(`模型回复: "${res.data.message}"`)
      if (res.data.dimension) details.push(`向量维度: ${res.data.dimension}`)
      if (res.data.result_count !== undefined) details.push(`返回结果: ${res.data.result_count} 条`)
      const successMsg = details.length > 0
        ? `连接成功！${details.join('，')}`
        : `连接成功！模型 "${row.model_name}" 可正常使用`
      ElMessage.success(successMsg)
    } else {
      ElMessage.warning(`连接失败: ${res.data?.error || '未知错误'}`)
    }
  } catch (e: any) {
    // axios 拦截器已显示错误消息（ElMessage.error），此处不再重复显示
    // 仅处理网络异常拦截器可能未覆盖的情况
    if (e?.response?.status) {
      const status = e.response.status
      const detail = e.response.data?.detail || e.response.data?.msg || ''
      if (status >= 400 && status < 600) {
        // 错误已由拦截器处理，不重复显示
      } else {
        ElMessage.error(`测试连接请求失败 (${status}): ${detail}`)
      }
    } else if (e?.message) {
      // 非 HTTP 错误（如 axios 自身错误），已在拦截器显示，避免重复
    }
  } finally {
    testingIds.value.delete(row.id)
  }
}

const isTesting = (id: number) => testingIds.value.has(id)

onMounted(() => {
  fetchModels()
})
</script>

<template>
  <div class="settings-container">
    <el-card shadow="never" class="settings-card" v-loading="loading">
      <template v-if="props.modelType && props.modelType !== 'all'">
        <div class="tab-header">
          <el-button type="primary" :icon="Plus" @click="openAddDialog(props.modelType)">
            添加模型
          </el-button>
        </div>
        <el-table
          v-if="displayModels.length > 0"
          :data="displayModels"
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
          :description="`暂无${MODEL_TYPE_LABELS[props.modelType]}配置`"
          :image-size="80"
        />
      </template>

      <template v-else>
        <el-tabs v-model="activeTab" class="models-tabs">
          <el-tab-pane label="LLM推理模型" name="llm">
            <div class="tab-header">
              <el-button type="primary" :icon="Plus" @click="openAddDialog('llm')">
                添加模型
              </el-button>
            </div>
            <el-table
              v-if="models.llm.length > 0"
              :data="models.llm"
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
              :description="`暂无LLM推理模型配置`"
              :image-size="80"
            />
          </el-tab-pane>

          <el-tab-pane label="Embedding嵌入模型" name="embedding">
            <div class="tab-header">
              <el-button type="primary" :icon="Plus" @click="openAddDialog('embedding')">
                添加模型
              </el-button>
            </div>
            <el-table
              v-if="models.embedding.length > 0"
              :data="models.embedding"
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
              :description="`暂无Embedding嵌入模型配置`"
              :image-size="80"
            />
          </el-tab-pane>

          <el-tab-pane label="Rerank重排序模型" name="rerank">
            <div class="tab-header">
              <el-button type="primary" :icon="Plus" @click="openAddDialog('rerank')">
                添加模型
              </el-button>
            </div>
            <el-table
              v-if="models.rerank.length > 0"
              :data="models.rerank"
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
              :description="`暂无Rerank重排序模型配置`"
              :image-size="80"
            />
          </el-tab-pane>
        </el-tabs>
      </template>
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
  border-radius: var(--scdc-radius-lg);
  border: 1px solid var(--scdc-bg-sunken);
  box-shadow: var(--scdc-shadow-soft);
}

.models-tabs {
  padding: 10px 0;
}

.tab-header {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 20px;
}

.api-key-unset {
  color: var(--scdc-ink-soft);
  font-style: italic;
}

.not-default {
  color: var(--scdc-ink-soft);
}
</style>