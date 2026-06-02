<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import { Check } from '@element-plus/icons-vue';
import { settingsApi, type DispatchConfig } from '../api/services/settings';

const config = reactive({
  cronSchedule: '0 8 * * *',
  notificationEmail: '',
  webhookUrl: '',
});

const loading = ref(false);
const fetchError = ref('');

onMounted(async () => {
  loading.value = true;
  fetchError.value = '';
  try {
    const res = await settingsApi.getDispatchConfig();
    if (res.data) {
      config.cronSchedule = res.data.cron_schedule || '0 8 * * *';
      config.notificationEmail = res.data.notification_email || '';
      config.webhookUrl = res.data.webhook_url || '';
    }
  } catch (e: any) {
    fetchError.value = e?.message || '加载调度配置失败';
    ElMessage.error(fetchError.value);
  } finally {
    loading.value = false;
  }
});

const handleSave = async () => {
  loading.value = true;
  try {
    await settingsApi.saveDispatchConfig({
      cron_schedule: config.cronSchedule,
      notification_email: config.notificationEmail,
      webhook_url: config.webhookUrl,
    });
    ElMessage.success('自动化调度与分发通道配置已保存');
  } catch {
    ElMessage.error('配置保存失败，请稍后重试');
  } finally {
    loading.value = false;
  }
};
</script>

<template>
  <div class="settings-container">
    <el-card shadow="never" class="settings-card" v-loading="loading">
      <template #header>
        <div class="card-header">
          <span class="card-title">自动化调度与分发通道</span>
          <el-button type="primary" :icon="Check" :loading="loading" @click="handleSave">保存变更</el-button>
        </div>
      </template>

      <el-alert
        v-if="fetchError"
        title="配置加载失败"
        :description="fetchError"
        type="error"
        show-icon
        closable
        style="margin-bottom: 16px"
      />
      <el-form :model="config" label-width="180px" class="settings-form">
        <el-form-item label="默认全局轮询表达式">
          <el-input v-model="config.cronSchedule" style="width: 360px" />
          <span class="tip-text" style="margin-left: 12px">每天上午 8:00 执行全网数据源汇编</span>
        </el-form-item>
        <el-form-item label="高管团队接收邮箱">
          <el-input v-model="config.notificationEmail" style="width: 360px" />
        </el-form-item>
        <el-form-item label="企业微信 Webhook 机器人">
          <el-input v-model="config.webhookUrl" style="width: 480px" />
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.settings-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 1000px;
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

.tip-text {
  font-size: 13px;
  color: #718096;
  margin-left: 16px;
}
</style>
