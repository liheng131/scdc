<script setup lang="ts">
import { reactive } from 'vue';
import { ElMessage } from 'element-plus';
import { Check } from '@element-plus/icons-vue';

const config = reactive({
  llmProvider: 'deepseek',
  apiKey: 'sk-98a7cf810b1a409f8c12a7b890123ef4',
  maxTokens: 4096,
  temperature: 0.3,
  cronSchedule: '0 8 * * *',
  notificationEmail: 'executive@market-insight.internal',
  webhookUrl: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=e0b...c31',
});

const handleSave = () => {
  ElMessage.success('系统配置与底层大模型密钥更新成功');
};
</script>

<template>
  <div class="settings-container">
    <el-card shadow="never" class="settings-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">系统底层参数与大模型环境配置</span>
          <el-button type="primary" :icon="Check" @click="handleSave">保存变更</el-button>
        </div>
      </template>

      <el-form :model="config" label-width="180px" class="settings-form">
        <el-divider content-position="left">AI 大模型推理引擎配置 (LLM Base)</el-divider>
        <el-form-item label="模型供应商 (Provider)">
          <el-select v-model="config.llmProvider" style="width: 360px">
            <el-option label="DeepSeek R1 / V3 深度推理模型" value="deepseek" />
            <el-option label="Kimi Moonshot 长文本分析引擎" value="kimi" />
            <el-option label="本地私有化部署 Llama-3 (vLLM)" value="local" />
          </el-select>
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="config.apiKey" type="password" show-password style="width: 360px" />
        </el-form-item>
        <el-form-item label="最大生成长度 (Tokens)">
          <el-input-number v-model="config.maxTokens" :min="1024" :max="32768" :step="1024" />
        </el-form-item>
        <el-form-item label="分析温度值 (Temperature)">
          <el-slider v-model="config.temperature" :min="0" :max="1" :step="0.1" style="width: 360px" />
          <span class="tip-text">当前设定: {{ config.temperature }} (数值越低逻辑推导越严谨)</span>
        </el-form-item>

        <el-divider content-position="left">自动化调度与分发通道 (Dispatch & Pipeline)</el-divider>
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
