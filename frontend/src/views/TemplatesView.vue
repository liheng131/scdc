<script setup lang="ts">
/**
 * 大纲与 Prompt 模板管理页面
 *
 * 管理 Jinja2 模板的创建和在线插值预览。
 *
 * 为什么使用 Jinja2 模板引擎：
 * - 支持双大括号语法 {{ variable }} 进行参数占位，业界标准、语法简单
 * - 后端沙箱渲染确保模板安全，避免服务端代码注入
 *
 * openPreview 流程：
 * 1. 记录当前模板 ID
 * 2. 弹出插值预览弹窗（previewVisible）
 * 3. 用户在弹窗中输入 JSON 变量 → 点击渲染按钮 → 后端 Jinja2 编译 → 返回结果
 *
 * 为什么自定义 rules 校验 content 字段：
 * - 模板内容不能为空，直接影响后续 ReporterAgent 的模板渲染质量
 */
import { ref, reactive, onMounted } from 'vue';
import { templatesApi, type TemplateInfo } from '../api';
import { Plus, Refresh, VideoPlay } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';

const templates = ref<TemplateInfo[]>([]);
const loading = ref(false);
const dialogVisible = ref(false);
const previewVisible = ref(false);

const form = reactive({
  name: '',
  scope: 'report',
  version: '1.0',
  content: '',
});

const previewForm = reactive({
  id: 0,
  variablesJson: '{\n  "industry_name": "人工智能",\n  "competitors": "OpenAI, Google, Anthropic"\n}',
  renderedOutput: '',
});

const rules = {
  name: [{ required: true, message: '请输入模板名称', trigger: 'blur' }],
  content: [{ required: true, message: '请输入 Jinja2 模板结构内容', trigger: 'blur' }],
};

const formRef = ref();

const fetchTemplates = async () => {
  loading.value = true;
  try {
    const res = await templatesApi.getTemplates();
    templates.value = res.data || [];
  } catch (err) {
    ElMessage.error('获取模板列表失败');
  } finally {
    loading.value = false;
  }
};

const handleCreate = () => {
  form.name = '';
  form.scope = 'report';
  form.version = '1.0';
  form.content = '# {{ industry_name }} 行业分析研报大纲\n\n## 1. 竞争态势\n涉及标的: {{ competitors }}\n';
  dialogVisible.value = true;
};

const handleSave = async () => {
  if (!formRef.value) return;
  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) return;
    await templatesApi.createTemplate({
      name: form.name,
      scope: form.scope,
      version: form.version,
      content: form.content,
      status: 'active',
    });
    ElMessage.success('创建模板成功');
    dialogVisible.value = false;
    fetchTemplates();
  });
};

const openPreview = (row: TemplateInfo) => {
  previewForm.id = row.id;
  previewForm.renderedOutput = '';
  previewVisible.value = true;
};

const handleRenderPreview = async () => {
  let vars = {};
  try {
    vars = JSON.parse(previewForm.variablesJson);
  } catch (err) {
    ElMessage.warning('变量参数格式不符合 JSON 规范，请检查');
    return;
  }
  try {
    const res = await templatesApi.renderPreview(previewForm.id, vars);
    previewForm.renderedOutput = res.data;
    ElMessage.success('Jinja2 参数动态渲染成功');
  } catch (err: any) {
    previewForm.renderedOutput = '渲染失败: ' + err.message;
  }
};

onMounted(() => {
  fetchTemplates();
});
</script>

<template>
  <div class="templates-container">
    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">行研大纲与 Prompt 提示词模板中心</span>
          <div class="actions">
            <el-button :icon="Refresh" @click="fetchTemplates" circle title="刷新列表"></el-button>
            <el-button type="primary" :icon="Plus" @click="handleCreate">创建新模板</el-button>
          </div>
        </div>
      </template>

      <el-table v-loading="loading" :data="templates" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="模板名称" min-width="200" />
        <el-table-column prop="scope" label="适用范围" width="140">
          <template #default="{ row }">
            <el-tag size="small" :type="row.scope === 'report' ? 'success' : 'warning'">
              {{ row.scope === 'report' ? '行研大纲 (Report)' : '提示词模板 (Prompt)' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="100">
          <template #default="{ row }">
            <el-tag size="small">v{{ row.version }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" type="success">{{ row.status === 'active' ? '生效中' : row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="success" size="small" :icon="VideoPlay" @click="openPreview(row)">
              在线插值预览
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新建模板 -->
    <el-dialog v-model="dialogVisible" title="创建大纲与提示词规范模板" width="650px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-form-item label="模板名称" prop="name">
          <el-input v-model="form.name" placeholder="例如: 2026 科技赛道 SWOT 标准模版" />
        </el-form-item>
        <el-form-item label="模板分类" prop="scope">
          <el-select v-model="form.scope" style="width: 100%">
            <el-option label="行业研报大纲结构 (Report)" value="report" />
            <el-option label="AI 推导提示词 (Prompt)" value="prompt" />
          </el-select>
        </el-form-item>
        <el-form-item label="版本编号" prop="version">
          <el-input v-model="form.version" placeholder="1.0" />
        </el-form-item>
        <el-form-item label="Jinja2 内容" prop="content">
          <el-input
            v-model="form.content"
            type="textarea"
            :rows="8"
            placeholder="使用双大括号语法进行参数占位..."
            style="font-family: monospace"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSave">确认保存</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 沙箱插值渲染预览弹窗 -->
    <el-dialog v-model="previewVisible" title="Jinja2 在线动态插值渲染沙箱" width="700px">
      <div class="sandbox-container">
        <div class="input-section">
          <h4>输入测试变量参数 (JSON)</h4>
          <el-input
            v-model="previewForm.variablesJson"
            type="textarea"
            :rows="5"
            style="font-family: monospace"
          />
          <el-button type="primary" style="margin-top: 12px; width: 100%" @click="handleRenderPreview">
            运行沙箱编译插值
          </el-button>
        </div>
        <div class="output-section" style="margin-top: 20px">
          <h4>沙箱渲染结果预览</h4>
          <div class="preview-result-box">
            <pre v-if="previewForm.renderedOutput">{{ previewForm.renderedOutput }}</pre>
            <span v-else class="placeholder">点击上方按钮查看插值后的大纲/提示词最终形态</span>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.templates-container {
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

.preview-result-box {
  background-color: #1e222d;
  color: #67c23a;
  padding: 16px;
  border-radius: 8px;
  min-height: 120px;
  font-family: monospace;
  white-space: pre-wrap;
  overflow-y: auto;
}

.placeholder {
  color: #718096;
}
</style>
