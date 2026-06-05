<script setup lang="ts">
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import AiModelsView from './AiModelsView.vue';
import DispatchView from './DispatchView.vue';
import { useAuthStore } from '@/stores/auth';

const auth = useAuthStore();
const { t } = useI18n();

const activeTab = ref('llm');
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
    </el-tabs>
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