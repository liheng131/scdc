<script setup lang="ts">
import { ref } from 'vue';
import AiModelsView from './AiModelsView.vue';
import DispatchView from './DispatchView.vue';

const activeTab = ref('ai-models');
</script>

<template>
  <div class="settings-container">
    <el-tabs v-model="activeTab" type="border-card">
      <el-tab-pane label="AI 模型配置" name="ai-models">
        <AiModelsView />
      </el-tab-pane>
      <el-tab-pane label="自动化调度与分发通道" name="dispatch">
        <DispatchView />
      </el-tab-pane>
    </el-tabs>
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