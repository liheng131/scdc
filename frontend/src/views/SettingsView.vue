<script setup lang="ts">
import { ref } from 'vue';
import AiModelsView from './AiModelsView.vue';
import DispatchView from './DispatchView.vue';

const activeTab = ref('llm');
</script>

<template>
  <div class="settings-container">
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
    </el-tabs>
  </div>
</template>

<style scoped>
.settings-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
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