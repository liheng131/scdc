<script setup lang="ts">
/**
 * 阶段确认弹窗 (Spec 1)
 *
 * 当后端 SSE 推送 stage_state='awaiting_confirmation' 时展示。
 * 用户可:
 *  - 接受 (accept) → 进入下一阶段
 *  - 重试 (reject) → 重跑当前阶段
 *      - 可选:补充 URL / 关键词(与原 topic 合并)
 *      - 可选:文字反馈(AI 解析后调整策略)
 */
import { ref, computed, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { Check, Refresh, Link, Key, ChatLineSquare, CircleClose, Loading } from '@element-plus/icons-vue';
import { useWorkflowStore, type ConfirmContext } from '../stores/workflow';
import type { StageConfirmRequest, StageConfirmResponse } from '../api';

const store = useWorkflowStore();

// 双向绑定的本地表单状态
const userFeedback = ref('');
const extraUrls = ref<string[]>(['']);
const extraKeywords = ref<string[]>(['']);

// 弹窗可见性
const visible = computed({
  get: () => store.confirmDialogVisible,
  set: (v: boolean) => {
    if (!v) store.hideConfirmDialog();
  },
});

const ctx = computed<ConfirmContext | null>(() => store.confirmContext);
const submitting = computed(() => store.confirmSubmitting);

// sources 列表
const sources = computed<any[]>(() => {
  const o = ctx.value?.stageOutput;
  if (!o) return [];
  if (Array.isArray(o.sources)) return o.sources;
  return [];
});

const itemCount = computed(() => sources.value.length);
const warning = computed(() => ctx.value?.stageOutput?.warning || '');

const stageLabel = computed(() => {
  const m: Record<string, string> = {
    collecting: '数据采集',
    cleaning: '数据清洗',
    analyzing: '分析洞察',
    reporting: '生成报告',
  };
  return m[ctx.value?.stage || ''] || ctx.value?.stage || '当前阶段';
});

const retryCount = computed(() => ctx.value?.stageHistoryLength ?? 0);

// reset 表单
watch(() => ctx.value, (v) => {
  if (v) {
    userFeedback.value = '';
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

const canSubmit = computed(() => !submitting.value && !!ctx.value);
const canReject = computed(() =>
  !submitting.value
  && !!ctx.value
  && (userFeedback.value.trim().length > 0
      || cleanedUrls.value.length > 0
      || cleanedKeywords.value.length > 0)
);

const emit = defineEmits<{
  (e: 'confirmed', data: { ctx: ConfirmContext; response: StageConfirmResponse; decision: 'accept' | 'reject' }): void;
  (e: 'cancelled'): void;
}>();

const handleAccept = async () => {
  if (!ctx.value) return;
  const body: StageConfirmRequest = { decision: 'accept' };
  try {
    const resp = await store.confirmStage(ctx.value.workflowId, body);
    ElMessage.success('已接受，进入下一阶段');
    emit('confirmed', { ctx: ctx.value, response: resp, decision: 'accept' });
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '操作失败';
    ElMessage.error(`接受失败: ${msg}`);
  }
};

const handleReject = async () => {
  if (!ctx.value) return;
  if (!canReject.value) {
    ElMessage.warning('请至少补充一项内容(URL、关键词或文字反馈)再重试');
    return;
  }
  const body: StageConfirmRequest = {
    decision: 'reject',
    user_edits: {
      extra_urls: cleanedUrls.value.length ? cleanedUrls.value : undefined,
      extra_keywords: cleanedKeywords.value.length ? cleanedKeywords.value : undefined,
    },
    user_feedback: userFeedback.value.trim() || undefined,
  };
  try {
    const resp = await store.confirmStage(ctx.value.workflowId, body);
    ElMessage.info('已重试，AI 正在重新采集...');
    emit('confirmed', { ctx: ctx.value, response: resp, decision: 'reject' });
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '操作失败';
    ElMessage.error(`重试失败: ${msg}`);
  }
};

const handleCancel = () => {
  store.hideConfirmDialog();
  emit('cancelled');
};

const truncate = (s: string, n: number) =>
  (s || '').length > n ? (s || '').slice(0, n) + '…' : (s || '');
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="`确认${stageLabel}结果`"
    width="760px"
    :close-on-click-modal="false"
    :close-on-press-escape="!submitting"
    :show-close="!submitting"
    align-center
    class="stage-confirm-dialog"
  >
    <template v-if="ctx">
      <!-- 头部状态提示 -->
      <div class="status-bar">
        <el-tag type="warning" size="large" effect="light">
          <el-icon class="rotating" v-if="submitting"><Loading /></el-icon>
          {{ submitting ? '处理中…' : '等待您的确认' }}
        </el-tag>
        <span class="stage-summary">
          <strong>{{ stageLabel }}</strong> 已完成 · 共采集 <strong>{{ itemCount }}</strong> 条信源
        </span>
        <el-tag v-if="retryCount > 0" type="info" size="small" effect="plain">
          第 {{ retryCount + 1 }} 次确认
        </el-tag>
      </div>

      <el-alert
        v-if="warning"
        :title="warning"
        type="warning"
        :closable="false"
        show-icon
        class="warning-alert"
      />

      <!-- 信源列表 -->
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

      <!-- 重试输入区(默认折叠) -->
      <el-collapse class="retry-collapse">
        <el-collapse-item name="retry" title="🔁 重试此阶段(添加补充材料 / 反馈)">
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

          <!-- 文字反馈 -->
          <div class="form-block">
            <label class="form-label">
              <el-icon><ChatLineSquare /></el-icon>
              文字反馈(可选,AI 会自动解析并调整策略)
            </label>
            <el-input
              v-model="userFeedback"
              type="textarea"
              :rows="3"
              :maxlength="2000"
              show-word-limit
              placeholder="例:上次没采到国内信源,请补采中国 2025 年 AI 制药新闻,并重点关注临床试验数据"
            />
          </div>
        </el-collapse-item>
      </el-collapse>
    </template>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleCancel" :disabled="submitting">取消</el-button>
        <el-button
          type="warning"
          :icon="Refresh"
          :loading="submitting"
          :disabled="!canReject"
          @click="handleReject"
        >
          重试此阶段
        </el-button>
        <el-button
          type="primary"
          :icon="Check"
          :loading="submitting"
          :disabled="!canSubmit"
          @click="handleAccept"
        >
          接受,继续
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.stage-confirm-dialog :deep(.el-dialog__body) {
  padding: 16px 24px 8px;
}

.status-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.stage-summary {
  font-size: 14px;
  color: var(--scdc-ink, #333);
}

.stage-summary strong {
  color: var(--scdc-accent, #b45309);
  font-weight: 700;
}

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

.retry-collapse {
  margin-bottom: 4px;
}

.retry-collapse :deep(.el-collapse-item__header) {
  font-size: 13px;
  font-weight: 500;
  color: var(--scdc-ink, #333);
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

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.rotating {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
