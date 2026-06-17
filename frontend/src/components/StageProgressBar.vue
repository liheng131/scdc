<template>
  <div class="stage-progress-bar">
    <div
      v-for="(stage, index) in stages"
      :key="stage.key"
      class="stage-node-wrapper"
    >
      <!-- 节点 -->
      <div
        class="stage-node"
        :class="getNodeClass(stage.key)"
        @click="handleNodeClick(stage.key)"
      >
        <div class="node-icon">
          <template v-if="getStageStatus(stage.key) === 'completed'">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M9 16.2L4.8 12L3.4 13.4L9 19L21 7L19.6 5.6L9 16.2Z" fill="currentColor"/>
            </svg>
          </template>
          <template v-else-if="getStageStatus(stage.key) === 'active'">
            <div class="loading-spinner"></div>
          </template>
          <template v-else>
            <span class="node-number">{{ index + 1 }}</span>
          </template>
        </div>
        <div class="node-label">{{ stage.label }}</div>
      </div>

      <!-- 连接线 -->
      <div
        v-if="index < stages.length - 1"
        class="stage-connector"
        :class="getConnectorClass(stage.key, stages[index + 1].key)"
      ></div>

      <!-- Hover Tooltip -->
      <div
        v-if="getStageStatus(stage.key) === 'completed' && stageSummaries[stage.key]"
        class="stage-tooltip"
      >
        {{ stageSummaries[stage.key].text }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Stage {
  key: string;
  label: string;
  icon: string;
}

interface StageSummary {
  text: string;
}

const props = defineProps<{
  stages: Stage[];
  currentStage: string;
  stageStatuses: Record<string, 'pending' | 'active' | 'completed'>;
  stageSummaries: Record<string, StageSummary>;
}>();

const emit = defineEmits<{
  detail: [stageKey: string];
}>();

const getStageStatus = (stageKey: string): 'pending' | 'active' | 'completed' => {
  return props.stageStatuses[stageKey] || 'pending';
};

const getNodeClass = (stageKey: string) => {
  const status = getStageStatus(stageKey);
  return {
    'node-pending': status === 'pending',
    'node-active': status === 'active',
    'node-completed': status === 'completed',
  };
};

const getConnectorClass = (currentKey: string, nextKey: string) => {
  const currentStatus = getStageStatus(currentKey);
  return {
    'connector-completed': currentStatus === 'completed',
    'connector-active': currentStatus === 'active',
  };
};

const handleNodeClick = (stageKey: string) => {
  if (getStageStatus(stageKey) === 'completed') {
    emit('detail', stageKey);
  }
};
</script>

<style scoped>
.stage-progress-bar {
  display: flex;
  align-items: center;
  padding: 16px 8px;
  gap: 0;
}

.stage-node-wrapper {
  display: flex;
  align-items: center;
  position: relative;
  flex: 1;
}

.stage-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  cursor: default;
  position: relative;
  z-index: 2;
}

.stage-node.node-completed {
  cursor: pointer;
}

.stage-node.node-completed:hover .stage-tooltip {
  opacity: 1;
  visibility: visible;
  transform: translateY(0);
}

.node-icon {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  transition: all 0.3s ease;
}

.node-pending .node-icon {
  background: #d1d5db;
  color: white;
}

.node-active .node-icon {
  background: #f59e0b;
  color: white;
  animation: pulse 2s ease-in-out infinite;
}

.node-completed .node-icon {
  background: #10b981;
  color: white;
}

.node-label {
  font-size: 12px;
  color: #6b7280;
  white-space: nowrap;
}

.node-active .node-label {
  color: #f59e0b;
  font-weight: 500;
}

.node-completed .node-label {
  color: #10b981;
  font-weight: 500;
}

.node-number {
  line-height: 1;
}

.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.stage-connector {
  flex: 1;
  height: 2px;
  background: #d1d5db;
  margin: 0 8px;
  margin-bottom: 20px;
  transition: background 0.3s ease;
}

.connector-completed {
  background: #10b981;
}

.connector-active {
  background: linear-gradient(90deg, #10b981 0%, #f59e0b 100%);
}

.stage-tooltip {
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%) translateY(8px);
  background: #1f2937;
  color: white;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
  white-space: nowrap;
  opacity: 0;
  visibility: hidden;
  transition: all 0.2s ease;
  pointer-events: none;
  z-index: 10;
  margin-bottom: 8px;
}

.stage-tooltip::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 4px solid transparent;
  border-top-color: #1f2937;
}

@keyframes pulse {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.4);
  }
  50% {
    box-shadow: 0 0 0 8px rgba(245, 158, 11, 0);
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
