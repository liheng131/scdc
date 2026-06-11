<script setup lang="ts">
/**
 * Spec 2 阶段内容渲染器: collecting
 *
 * 自包含 collecting 阶段 UI:
 *  - 信源列表展示
 *  - 补充 URL / 关键词输入(reject 时用)
 *  - warning 提示
 *
 * Props:
 *   stageOutput: { sources, item_count, warning, stage: 'collecting' }
 *
 * Emits:
 *   update:userEdits: { extra_urls: string[], extra_keywords: string[] }
 */
import { ref, computed, watch } from 'vue';
import { Link, Key, CircleClose } from '@element-plus/icons-vue';

interface Source {
  source_type?: string;
  source_uri?: string;
  title?: string;
  snippet?: string;
  content_length?: number;
  metadata?: Record<string, any>;
}

const props = defineProps<{
  stageOutput: any;
}>();

const emit = defineEmits<{
  (e: 'update:userEdits', value: { extra_urls?: string[]; extra_keywords?: string[] }): void;
}>();

// 本地表单状态
const extraUrls = ref<string[]>(['']);
const extraKeywords = ref<string[]>(['']);

// sources
const sources = computed<Source[]>(() => {
  const o = props.stageOutput;
  if (!o) return [];
  if (Array.isArray(o.sources)) return o.sources;
  return [];
});

const warning = computed(() => props.stageOutput?.warning || '');

const truncate = (s: string, n: number) =>
  (s || '').length > n ? (s || '').slice(0, n) + '…' : (s || '');

// reset 表单
watch(() => props.stageOutput, (v) => {
  if (v) {
    extraUrls.value = [''];
    extraKeywords.value = [''];
  }
}, { immediate: true });

// helpers
const addUrl = () => extraUrls.value.push('');
const removeUrl = (i: number) => extraUrls.value.splice(i, 1);
const addKw = () => extraKeywords.value.push('');
const removeKw = (i: number) => extraKeywords.value.splice(i, 1);

const cleanedUrls = computed(() =>
  extraUrls.value.map(s => (s || '').trim()).filter(Boolean)
);
const cleanedKeywords = computed(() =>
  extraKeywords.value.map(s => (s || '').trim()).filter(Boolean)
);

// emit
const notifyEdits = () => {
  emit('update:userEdits', {
    extra_urls: cleanedUrls.value.length ? cleanedUrls.value : undefined,
    extra_keywords: cleanedKeywords.value.length ? cleanedKeywords.value : undefined,
  });
};
watch([cleanedUrls, cleanedKeywords], notifyEdits, { immediate: false });
</script>

<template>
  <div>
    <el-alert
      v-if="warning"
      :title="warning"
      type="warning"
      :closable="false"
      show-icon
      class="warning-alert"
    />

    <el-scrollbar height="280px" class="sources-scroll">
      <div v-if="sources.length === 0" class="empty">
        <el-empty description="本阶段无信源输出" :image-size="80" />
      </div>
      <el-card
        v-for="(src, i) in sources"
        :key="i"
        shadow="hover"
        class="source-card"
        :body-style="{ padding: '12px 16px' }"
      >
        <div class="source-head">
          <el-tag size="small" :type="src.source_type === 'news' ? 'primary' : 'success'" effect="light">
            {{ src.source_type || 'unknown' }}
          </el-tag>
          <a
            v-if="src.source_uri"
            :href="src.source_uri"
            target="_blank"
            rel="noopener"
            class="source-link"
          >
            {{ src.title || truncate(src.source_uri, 60) }}
          </a>
          <span v-else class="source-title">{{ src.title || '(无标题)' }}</span>
        </div>
        <div v-if="src.snippet" class="source-snippet">{{ truncate(src.snippet, 220) }}</div>
        <div class="source-meta">
          <span>长度: {{ src.content_length || 0 }} 字符</span>
          <span v-if="src.metadata && Object.keys(src.metadata).length">
            {{ Object.entries(src.metadata).slice(0, 2).map(([k, v]) => `${k}=${v}`).join(' · ') }}
          </span>
        </div>
      </el-card>
    </el-scrollbar>

    <!-- 补充 URL -->
    <div class="form-block">
      <label class="form-label">
        <el-icon><Link /></el-icon>
        补充 URL
      </label>
      <div v-for="(_, i) in extraUrls" :key="`url-${i}`" class="form-row">
        <el-input
          v-model="extraUrls[i]"
          placeholder="https://example.com/article-1"
          clearable
          size="default"
        />
        <el-button
          v-if="extraUrls.length > 1"
          text
          :icon="CircleClose"
          @click="removeUrl(i)"
          class="row-remove"
        />
      </div>
      <el-button text size="small" @click="addUrl" :icon="Link">+ 添加 URL</el-button>
    </div>

    <!-- 补充关键词 -->
    <div class="form-block">
      <label class="form-label">
        <el-icon><Key /></el-icon>
        补充关键词
      </label>
      <div v-for="(_, i) in extraKeywords" :key="`kw-${i}`" class="form-row">
        <el-input
          v-model="extraKeywords[i]"
          placeholder="例:AI制药 · 临床试验"
          clearable
          size="default"
        />
        <el-button
          v-if="extraKeywords.length > 1"
          text
          :icon="CircleClose"
          @click="removeKw(i)"
          class="row-remove"
        />
      </div>
      <el-button text size="small" @click="addKw" :icon="Key">+ 添加关键词</el-button>
    </div>
  </div>
</template>

<style scoped>
.warning-alert {
  margin-bottom: 12px;
}

.sources-scroll {
  border: 1px solid var(--scdc-bg-sunken, #e8e3d6);
  border-radius: 8px;
  background: var(--scdc-bg-elevated, #faf7f0);
  padding: 8px 12px;
  margin-bottom: 16px;
}

.empty {
  display: flex;
  justify-content: center;
  padding: 20px 0;
}

.source-card {
  margin-bottom: 10px;
  border: 1px solid var(--scdc-bg-sunken, #e8e3d6);
}

.source-card:last-child {
  margin-bottom: 0;
}

.source-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.source-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--scdc-ink, #333);
}

.source-link {
  font-size: 14px;
  font-weight: 500;
  color: var(--scdc-accent, #b45309);
  text-decoration: none;
  word-break: break-all;
}

.source-link:hover {
  text-decoration: underline;
}

.source-snippet {
  font-size: 13px;
  line-height: 1.6;
  color: var(--scdc-ink-muted, #666);
  margin-bottom: 6px;
  padding-left: 4px;
  border-left: 2px solid var(--scdc-bg-sunken, #e8e3d6);
}

.source-meta {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--scdc-ink-soft, #999);
  font-family: var(--scdc-font-mono, monospace);
}

.form-block {
  margin-bottom: 14px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 500;
  color: var(--scdc-ink, #333);
  margin-bottom: 6px;
}

.form-row {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 6px;
}

.row-remove {
  flex-shrink: 0;
  color: var(--scdc-danger, #f56c6c);
}
</style>
