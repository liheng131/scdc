<script setup lang="ts">
/**
 * Spec 2 阶段内容渲染器: analyzing
 *
 * 自包含 analyzing 阶段 UI:
 *  - 顶部 summary 卡片
 *  - 维度标签条(chips)
 *  - 洞察卡片列表,每条带勾选框(勾上 = 加入 removed_insight_ids)
 *  - 折叠区:补充自定义维度
 *
 * Props:
 *   stageOutput: { insights, dimensions, summary, stage: 'analyzing' }
 *
 * Emits:
 *   update:userEdits: { removed_insight_ids: string[], custom_dimensions: string[] }
 */
import { ref, computed, watch } from 'vue';
import { Key } from '@element-plus/icons-vue';

interface Insight {
  id?: string;
  title: string;
  description: string;
  evidence?: string[];
  confidence?: number;
  dimension?: string;
}

const props = defineProps<{
  stageOutput: any;
}>();

const emit = defineEmits<{
  (e: 'update:userEdits', value: { removed_insight_ids?: string[]; custom_dimensions?: string[] }): void;
}>();

// 本地状态
const removedIds = ref<Set<string>>(new Set());
const customDimensions = ref<string[]>([]);
const newDimension = ref<string>('');

const insights = computed<Insight[]>(() => {
  const o = props.stageOutput;
  if (!o) return [];
  if (Array.isArray(o.insights)) return o.insights;
  return [];
});

const dimensions = computed<string[]>(() => {
  const o = props.stageOutput;
  if (!o) return [];
  if (Array.isArray(o.dimensions)) return o.dimensions;
  return [];
});

const summary = computed(() => props.stageOutput?.summary || '');

// 给每条 insight 生成稳定 id
const getInsightId = (ins: Insight, idx: number) => ins.id || `idx-${idx}`;

const toggleInsight = (id: string) => {
  if (removedIds.value.has(id)) {
    removedIds.value.delete(id);
  } else {
    removedIds.value.add(id);
  }
  removedIds.value = new Set(removedIds.value);
  notifyEdits();
};

const isRemoved = (id: string) => removedIds.value.has(id);

// 维度输入
const addDimension = () => {
  const v = newDimension.value.trim();
  if (v && !customDimensions.value.includes(v)) {
    customDimensions.value.push(v);
    newDimension.value = '';
    notifyEdits();
  }
};
const removeDimension = (d: string) => {
  customDimensions.value = customDimensions.value.filter(x => x !== d);
  notifyEdits();
};

// reset
watch(() => props.stageOutput, (v) => {
  if (v) {
    removedIds.value = new Set();
    customDimensions.value = [];
    newDimension.value = '';
  }
}, { immediate: true });

// emit
const notifyEdits = () => {
  emit('update:userEdits', {
    removed_insight_ids: removedIds.value.size > 0 ? Array.from(removedIds.value) : undefined,
    custom_dimensions: customDimensions.value.length > 0 ? customDimensions.value : undefined,
  });
};
</script>

<template>
  <div>
    <!-- summary 卡片 -->
    <el-alert
      v-if="summary"
      :title="summary"
      type="info"
      :closable="false"
      show-icon
      class="summary-alert"
    />

    <!-- 维度标签条 -->
    <div v-if="dimensions.length > 0 || customDimensions.length > 0" class="dimensions-row">
      <span class="dim-label">分析维度:</span>
      <el-tag
        v-for="d in dimensions"
        :key="`d-${d}`"
        size="default"
        effect="plain"
        class="dim-tag"
      >
        {{ d }}
      </el-tag>
      <el-tag
        v-for="d in customDimensions"
        :key="`cd-${d}`"
        size="default"
        type="success"
        effect="light"
        class="dim-tag"
        closable
        @close="removeDimension(d)"
      >
        + {{ d }}
      </el-tag>
    </div>

    <div v-if="insights.length === 0" class="empty">
      <el-empty description="本阶段无洞察输出" :image-size="80" />
    </div>

    <!-- 洞察列表 -->
    <el-scrollbar :height="insights.length > 3 ? '320px' : 'auto'" class="insights-scroll">
      <div
        v-for="(ins, i) in insights"
        :key="getInsightId(ins, i)"
        class="insight-card"
        :class="{ 'insight-removed': isRemoved(getInsightId(ins, i)) }"
      >
        <el-checkbox
          :model-value="isRemoved(getInsightId(ins, i))"
          @change="toggleInsight(getInsightId(ins, i))"
          class="insight-checkbox"
        />
        <div class="insight-content">
          <div class="insight-head">
            <span class="insight-num">#{{ i + 1 }}</span>
            <span class="insight-title">{{ ins.title }}</span>
            <el-tag v-if="ins.dimension" size="small" type="warning" effect="light">
              {{ ins.dimension }}
            </el-tag>
            <el-tag v-if="ins.confidence != null" size="small" type="info" effect="plain">
              置信度 {{ Math.round(ins.confidence * 100) }}%
            </el-tag>
          </div>
          <div class="insight-desc">{{ ins.description }}</div>
          <div v-if="ins.evidence && ins.evidence.length" class="insight-evidence">
            <div class="evidence-label">证据:</div>
            <ul class="evidence-list">
              <li v-for="(ev, j) in ins.evidence.slice(0, 3)" :key="`e-${i}-${j}`">
                {{ ev.length > 200 ? ev.slice(0, 200) + '…' : ev }}
              </li>
            </ul>
          </div>
        </div>
      </div>
    </el-scrollbar>

    <!-- 自定义维度 -->
    <el-collapse class="dimensions-collapse">
      <el-collapse-item name="dimensions" title="➕ 补充自定义分析维度(可选)">
        <div class="form-block">
          <div class="form-row">
            <el-input
              v-model="newDimension"
              placeholder="例:监管政策 · 投融资动态"
              clearable
              @keyup.enter="addDimension"
            />
            <el-button type="primary" :icon="Key" @click="addDimension" :disabled="!newDimension.trim()">
              添加
            </el-button>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<style scoped>
.summary-alert {
  margin-bottom: 12px;
}

.dimensions-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
  flex-wrap: wrap;
  padding: 8px 12px;
  background: var(--scdc-bg-elevated, #faf7f0);
  border: 1px solid var(--scdc-bg-sunken, #e8e3d6);
  border-radius: 6px;
}

.dim-label {
  font-size: 12px;
  color: var(--scdc-ink-soft, #999);
  margin-right: 4px;
}

.dim-tag {
  margin: 0;
}

.empty {
  display: flex;
  justify-content: center;
  padding: 20px 0;
}

.insights-scroll {
  border: 1px solid var(--scdc-bg-sunken, #e8e3d6);
  border-radius: 8px;
  background: var(--scdc-bg-elevated, #faf7f0);
  padding: 8px 12px;
  margin-bottom: 16px;
}

.insight-card {
  display: flex;
  gap: 10px;
  padding: 12px 8px;
  margin-bottom: 10px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: #fff;
  transition: all 0.2s;
}

.insight-card.insight-removed {
  border-color: var(--scdc-danger, #f56c6c);
  background: #fef0f0;
  opacity: 0.7;
}

.insight-checkbox {
  margin-top: 4px;
  flex-shrink: 0;
}

.insight-content {
  flex: 1;
  min-width: 0;
}

.insight-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.insight-num {
  font-size: 12px;
  font-weight: 700;
  color: var(--scdc-accent, #b45309);
  font-family: var(--scdc-font-mono, monospace);
}

.insight-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--scdc-ink, #333);
  flex: 1;
  min-width: 0;
}

.insight-desc {
  font-size: 13px;
  line-height: 1.6;
  color: var(--scdc-ink-muted, #666);
  margin-bottom: 6px;
  padding-left: 4px;
  border-left: 2px solid var(--scdc-bg-sunken, #e8e3d6);
}

.insight-evidence {
  margin-top: 6px;
  padding: 6px 8px;
  background: var(--scdc-bg-sunken, #e8e3d6);
  border-radius: 4px;
}

.evidence-label {
  font-size: 11px;
  color: var(--scdc-ink-soft, #999);
  margin-bottom: 2px;
}

.evidence-list {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--scdc-ink-muted, #666);
}

.dimensions-collapse {
  margin-bottom: 4px;
}

.dimensions-collapse :deep(.el-collapse-item__header) {
  font-size: 13px;
  font-weight: 500;
  color: var(--scdc-ink, #333);
}

.form-block {
  margin-bottom: 14px;
}

.form-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
