<script setup lang="ts">
/**
 * Spec 2 阶段内容渲染器: cleaning
 *
 * 自包含 cleaning 阶段 UI:
 *  - 顶部 stats 卡片(输入/输出/移除数)
 *  - 清洗后信源列表,每条带勾选框(勾上 = 加入 removed_item_ids)
 *  - 折叠区:阈值调整 (min_content_length slider, language select)
 *
 * Props:
 *   stageOutput: { cleaned_items, stats: { total_in, total_out, removed_count }, stage: 'cleaning' }
 *
 * Emits:
 *   update:userEdits: { removed_item_ids: string[], min_content_length?: number, language?: string }
 */
import { ref, computed, watch } from 'vue';

interface CleanedItem {
  id?: string;
  source_uri?: string;
  title?: string;
  summary?: string;
  content_length?: number;
  language?: string;
  key_topics?: string[];
}

const props = defineProps<{
  stageOutput: any;
}>();

const emit = defineEmits<{
  (e: 'update:userEdits', value: { removed_item_ids?: string[]; min_content_length?: number; language?: string }): void;
}>();

// 本地状态
const removedIds = ref<Set<string>>(new Set());
const minLength = ref<number>(100);
const language = ref<string>('');

const cleanedItems = computed<CleanedItem[]>(() => {
  const o = props.stageOutput;
  if (!o) return [];
  if (Array.isArray(o.cleaned_items)) return o.cleaned_items;
  return [];
});

const stats = computed(() => props.stageOutput?.stats || { total_in: 0, total_out: 0, removed_count: 0 });

// 给每条 item 生成稳定 id(用 uri 哈希)
const getItemId = (item: CleanedItem, idx: number) => item.id || item.source_uri || `idx-${idx}`;

const toggleItem = (id: string) => {
  if (removedIds.value.has(id)) {
    removedIds.value.delete(id);
  } else {
    removedIds.value.add(id);
  }
  removedIds.value = new Set(removedIds.value);  // 触发响应式
  notifyEdits();
};

const isRemoved = (id: string) => removedIds.value.has(id);

const truncate = (s: string, n: number) =>
  (s || '').length > n ? (s || '').slice(0, n) + '…' : (s || '');

// reset
watch(() => props.stageOutput, (v) => {
  if (v) {
    removedIds.value = new Set();
    minLength.value = 100;
    language.value = '';
  }
}, { immediate: true });

// emit
const notifyEdits = () => {
  emit('update:userEdits', {
    removed_item_ids: removedIds.value.size > 0 ? Array.from(removedIds.value) : undefined,
    min_content_length: minLength.value !== 100 ? minLength.value : undefined,
    language: language.value || undefined,
  });
};
watch([minLength, language], notifyEdits, { immediate: false });
</script>

<template>
  <div>
    <!-- stats 卡片 -->
    <div class="stats-row">
      <div class="stat-card stat-in">
        <div class="stat-num">{{ stats.total_in }}</div>
        <div class="stat-label">输入信源</div>
      </div>
      <div class="stat-arrow">→</div>
      <div class="stat-card stat-out">
        <div class="stat-num">{{ stats.total_out }}</div>
        <div class="stat-label">输出信源</div>
      </div>
      <div class="stat-arrow">·</div>
      <div class="stat-card stat-removed">
        <div class="stat-num">{{ stats.removed_count }}</div>
        <div class="stat-label">已移除</div>
      </div>
      <div class="stat-arrow">·</div>
      <div class="stat-card stat-marked" :class="{ 'stat-active': removedIds.size > 0 }">
        <div class="stat-num">{{ removedIds.size }}</div>
        <div class="stat-label">您将移除</div>
      </div>
    </div>

    <div v-if="cleanedItems.length === 0" class="empty">
      <el-empty description="本阶段无清洗后信源" :image-size="80" />
    </div>

    <!-- 清洗后信源列表 -->
    <el-scrollbar :height="cleanedItems.length > 5 ? '280px' : 'auto'" class="cleaned-scroll">
      <div
        v-for="(item, i) in cleanedItems"
        :key="getItemId(item, i)"
        class="item-card"
        :class="{ 'item-removed': isRemoved(getItemId(item, i)) }"
      >
        <el-checkbox
          :model-value="isRemoved(getItemId(item, i))"
          @change="toggleItem(getItemId(item, i))"
          class="item-checkbox"
        />
        <div class="item-content">
          <div class="item-head">
            <a
              v-if="item.source_uri"
              :href="item.source_uri"
              target="_blank"
              rel="noopener"
              class="item-link"
            >
              {{ item.title || truncate(item.source_uri, 50) }}
            </a>
            <span v-else class="item-title">{{ item.title || '(无标题)' }}</span>
            <el-tag v-if="item.language" size="small" effect="plain">{{ item.language }}</el-tag>
          </div>
          <div v-if="item.summary" class="item-summary">{{ truncate(item.summary, 180) }}</div>
          <div class="item-meta">
            <span>长度: {{ item.content_length || 0 }} 字符</span>
            <span v-if="item.key_topics && item.key_topics.length">
              话题: {{ item.key_topics.slice(0, 3).join(' · ') }}
            </span>
          </div>
        </div>
      </div>
    </el-scrollbar>

    <!-- 阈值调整 -->
    <el-collapse class="thresholds-collapse">
      <el-collapse-item name="thresholds" title="⚙️ 调整清洗阈值(可选)">
        <div class="form-block">
          <label class="form-label">
            最小内容长度: <strong>{{ minLength }}</strong> 字符
          </label>
          <el-slider
            v-model="minLength"
            :min="0"
            :max="1000"
            :step="50"
            show-stops
          />
        </div>
        <div class="form-block">
          <label class="form-label">目标语言过滤(留空 = 不过滤)</label>
          <el-select v-model="language" clearable placeholder="全部语言" size="default">
            <el-option label="中文" value="zh" />
            <el-option label="英文" value="en" />
            <el-option label="日文" value="ja" />
          </el-select>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<style scoped>
.stats-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.stat-card {
  flex: 1;
  min-width: 80px;
  padding: 10px 12px;
  border: 1px solid var(--scdc-bg-sunken, #e8e3d6);
  border-radius: 8px;
  background: var(--scdc-bg-elevated, #faf7f0);
  text-align: center;
}

.stat-card.stat-active {
  border-color: var(--scdc-accent, #b45309);
  background: var(--scdc-accent-bg, #fef3c7);
}

.stat-num {
  font-size: 22px;
  font-weight: 700;
  color: var(--scdc-ink, #333);
}

.stat-label {
  font-size: 11px;
  color: var(--scdc-ink-soft, #999);
  margin-top: 2px;
}

.stat-arrow {
  color: var(--scdc-ink-soft, #999);
  font-size: 16px;
}

.empty {
  display: flex;
  justify-content: center;
  padding: 20px 0;
}

.cleaned-scroll {
  border: 1px solid var(--scdc-bg-sunken, #e8e3d6);
  border-radius: 8px;
  background: var(--scdc-bg-elevated, #faf7f0);
  padding: 8px 12px;
  margin-bottom: 16px;
}

.item-card {
  display: flex;
  gap: 10px;
  padding: 10px 8px;
  margin-bottom: 8px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: #fff;
  transition: all 0.2s;
}

.item-card.item-removed {
  border-color: var(--scdc-danger, #f56c6c);
  background: #fef0f0;
  opacity: 0.7;
}

.item-checkbox {
  margin-top: 4px;
  flex-shrink: 0;
}

.item-content {
  flex: 1;
  min-width: 0;
}

.item-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}

.item-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--scdc-ink, #333);
}

.item-link {
  font-size: 14px;
  font-weight: 500;
  color: var(--scdc-accent, #b45309);
  text-decoration: none;
  word-break: break-all;
}

.item-link:hover {
  text-decoration: underline;
}

.item-summary {
  font-size: 13px;
  line-height: 1.5;
  color: var(--scdc-ink-muted, #666);
  margin-bottom: 4px;
  padding-left: 4px;
  border-left: 2px solid var(--scdc-bg-sunken, #e8e3d6);
}

.item-meta {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--scdc-ink-soft, #999);
  font-family: var(--scdc-font-mono, monospace);
}

.thresholds-collapse {
  margin-bottom: 4px;
}

.thresholds-collapse :deep(.el-collapse-item__header) {
  font-size: 13px;
  font-weight: 500;
  color: var(--scdc-ink, #333);
}

.form-block {
  margin-bottom: 14px;
}

.form-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--scdc-ink, #333);
  margin-bottom: 6px;
}
</style>
