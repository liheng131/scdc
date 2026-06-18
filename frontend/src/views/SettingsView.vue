<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage, ElMessageBox } from 'element-plus';
import AiModelsView from './AiModelsView.vue';
import DispatchView from './DispatchView.vue';
import { useAuthStore } from '@/stores/auth';
import { notificationApi, type NotificationRule, type NotificationRuleCreate } from '@/api/services/notification';

const auth = useAuthStore();
const { t } = useI18n();

const activeTab = ref('llm');

// ===== Notification rules =====
const rules = ref<NotificationRule[]>([]);
const rulesLoading = ref(false);
const showCreateDialog = ref(false);
const showEditDialog = ref(false);
const editingRule = ref<NotificationRule | null>(null);

const form = ref<NotificationRuleCreate>({
  name: '',
  channel: 'email',
  trigger: 'report_ready',
  target: '',
  enabled: true,
});

const channelOptions = [
  { label: '邮件 (Email)', value: 'email' },
  { label: 'Webhook', value: 'webhook' },
];

const triggerOptions = [
  { label: '报告完成 (report_ready)', value: 'report_ready' },
  { label: '事件告警 (event_alert)', value: 'event_alert' },
];

async function fetchRules() {
  rulesLoading.value = true;
  try {
    const res = await notificationApi.listRules();
    rules.value = res.data || [];
  } catch (e) {
    ElMessage.error('获取通知规则失败');
  } finally {
    rulesLoading.value = false;
  }
}

function openCreate() {
  form.value = { name: '', channel: 'email', trigger: 'report_ready', target: '', enabled: true };
  showCreateDialog.value = true;
}

async function handleCreate() {
  if (!form.value.name || !form.value.target) {
    ElMessage.warning('请填写规则名称和目标');
    return;
  }
  try {
    await notificationApi.createRule(form.value);
    ElMessage.success('规则创建成功');
    showCreateDialog.value = false;
    await fetchRules();
  } catch (e) {
    ElMessage.error('创建规则失败');
  }
}

function openEdit(rule: NotificationRule) {
  editingRule.value = rule;
  form.value = {
    name: rule.name,
    channel: rule.channel,
    trigger: rule.trigger,
    target: rule.target,
    enabled: rule.enabled,
  };
  showEditDialog.value = true;
}

async function handleUpdate() {
  if (!editingRule.value || !form.value.name || !form.value.target) {
    ElMessage.warning('请填写规则名称和目标');
    return;
  }
  try {
    await notificationApi.updateRule(editingRule.value.id, form.value);
    ElMessage.success('规则更新成功');
    showEditDialog.value = false;
    await fetchRules();
  } catch (e) {
    ElMessage.error('更新规则失败');
  }
}

async function handleDelete(rule: NotificationRule) {
  try {
    await ElMessageBox.confirm(`确定删除规则「${rule.name}」吗？`, '确认删除', { type: 'warning' });
    await notificationApi.deleteRule(rule.id);
    ElMessage.success('规则已删除');
    await fetchRules();
  } catch {
    // cancelled
  }
}

async function toggleEnabled(rule: NotificationRule) {
  try {
    await notificationApi.updateRule(rule.id, { enabled: !rule.enabled });
    await fetchRules();
  } catch {
    ElMessage.error('切换状态失败');
  }
}

function getChannelLabel(channel: string) {
  return channelOptions.find(c => c.value === channel)?.label || channel;
}

function getTriggerLabel(trigger: string) {
  return triggerOptions.find(t => t.value === trigger)?.label || trigger;
}

onMounted(() => {
  fetchRules();
});
</script>

<template>
  <div v-if="auth.isAuthenticated" class="settings-container">
    <el-tabs v-model="activeTab" type="border-card">
      <el-tab-pane label="LLM推理模型" name="llm">
        <AiModelsView modelType="llm" />
      </el-tab-pane>
      <el-tab-pane label="Embedding嵌入模型" name="embedding">
        <AiModelsView modelType="embedding" />
      </el-tab-pane>
      <el-tab-pane label="Rerank重排序模型" name="rerank">
        <AiModelsView modelType="rerank" />
      </el-tab-pane>
      <el-tab-pane label="自动化调度与分发通道" name="dispatch">
        <DispatchView />
      </el-tab-pane>
      <el-tab-pane label="通知规则" name="notification">
        <div class="notification-panel">
          <div class="panel-header">
            <span class="panel-title">邮件通知规则</span>
            <el-button type="primary" size="small" @click="openCreate">新建规则</el-button>
          </div>
          <el-table :data="rules" v-loading="rulesLoading" stripe style="width: 100%">
            <el-table-column prop="name" label="规则名称" min-width="120" />
            <el-table-column prop="channel" label="渠道" width="120">
              <template #default="{ row }">{{ getChannelLabel(row.channel) }}</template>
            </el-table-column>
            <el-table-column prop="trigger" label="触发条件" width="160">
              <template #default="{ row }">{{ getTriggerLabel(row.trigger) }}</template>
            </el-table-column>
            <el-table-column prop="target" label="目标" min-width="180" show-overflow-tooltip />
            <el-table-column label="状态" width="80" align="center">
              <template #default="{ row }">
                <el-switch
                  :model-value="row.enabled"
                  @change="toggleEnabled(row)"
                  size="small"
                />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="140" align="center">
              <template #default="{ row }">
                <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
                <el-button size="small" text type="danger" @click="handleDelete(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!rulesLoading && rules.length === 0" class="empty-rules">
            暂无通知规则，点击「新建规则」开始配置
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- Create Dialog -->
    <el-dialog v-model="showCreateDialog" title="新建通知规则" width="480px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="规则名称">
          <el-input v-model="form.name" placeholder="例如：高管报告推送" />
        </el-form-item>
        <el-form-item label="通知渠道">
          <el-select v-model="form.channel" style="width: 100%">
            <el-option v-for="opt in channelOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="触发条件">
          <el-select v-model="form.trigger" style="width: 100%">
            <el-option v-for="opt in triggerOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标">
          <el-input v-model="form.target" :placeholder="form.channel === 'email' ? '邮箱地址' : 'Webhook URL'" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- Edit Dialog -->
    <el-dialog v-model="showEditDialog" title="编辑通知规则" width="480px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="规则名称">
          <el-input v-model="form.name" placeholder="例如：高管报告推送" />
        </el-form-item>
        <el-form-item label="通知渠道">
          <el-select v-model="form.channel" style="width: 100%">
            <el-option v-for="opt in channelOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="触发条件">
          <el-select v-model="form.trigger" style="width: 100%">
            <el-option v-for="opt in triggerOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标">
          <el-input v-model="form.target" :placeholder="form.channel === 'email' ? '邮箱地址' : 'Webhook URL'" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="handleUpdate">保存</el-button>
      </template>
    </el-dialog>
  </div>
  <div v-else class="auth-placeholder">
    <div class="placeholder-inner">
      <div class="placeholder-icon">U</div>
      <h2 class="placeholder-title">{{ t('placeholder.needLogin') }}</h2>
      <p class="placeholder-desc">{{ t('placeholder.needLoginDesc') }}</p>
      <p class="placeholder-brand">{{ t('brand.name') }} · {{ t('brand.company') }}</p>
    </div>
  </div>
</template>

<style scoped>
.settings-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.notification-panel {
  padding: 20px 0;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--scdc-ink-strong);
}

.empty-rules {
  text-align: center;
  padding: 40px 20px;
  color: var(--scdc-ink-muted);
  font-size: 14px;
}

.settings-card {
  font-family: var(--scdc-font-display);
  font-weight: 600;
  border-radius: var(--scdc-radius-lg);
  border: 1px solid var(--scdc-bg-sunken);
  box-shadow: var(--scdc-shadow-soft);
  color: var(--scdc-ink-strong);
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

.tip-text {
  font-size: 13px;
  color: var(--scdc-ink-muted);
  margin-left: 16px;
}

.auth-placeholder {
  min-height: 60vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
}
.placeholder-inner {
  text-align: center;
  max-width: 420px;
}
.placeholder-icon {
  font-family: var(--scdc-font-display);
  font-size: 36px;
  font-weight: 600;
  color: var(--scdc-accent);
  width: 80px;
  height: 80px;
  margin: 0 auto 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--scdc-accent-soft);
  letter-spacing: -0.02em;
}
.placeholder-title {
  font-family: var(--scdc-font-display);
  font-size: 26px;
  font-weight: 600;
  color: var(--scdc-ink-strong);
  margin: 0 0 12px 0;
  letter-spacing: -0.01em;
}
.placeholder-desc {
  font-family: var(--scdc-font-body);
  font-size: 15px;
  color: var(--scdc-ink-muted);
  margin: 0 0 24px 0;
  line-height: 1.7;
}
.placeholder-brand {
  font-family: var(--scdc-font-body);
  font-size: 12px;
  color: var(--scdc-ink-soft);
  letter-spacing: 0.18em;
  margin: 32px 0 0 0;
  text-transform: none;
}
</style>