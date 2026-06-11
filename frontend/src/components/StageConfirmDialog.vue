<script setup lang="ts">
/**
 * 阶段确认弹窗 (Spec 2: 4 阶段通用)
 *
 * 动态内容区: 按 ctx.stage 选 4 个 renderer 之一
 *   - collecting → CollectingContentRenderer (信源列表)
 *   - cleaning   → CleaningContentRenderer   (清洗后信源 + 勾选 + 阈值)
 *   - analyzing  → AnalyzingContentRenderer  (洞察 + 勾选 + 维度)
 *   - reporting  → ReportingContentRenderer  (报告 markdown + 富文本编辑)
 *
 * 通用: 重试折叠区（URL/关键词/反馈）+ 底部按钮 + 关闭二次确认 + 本次跳过勾选
 */
import { ref, computed, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Check, Refresh, ChatLineSquare, Loading } from '@element-plus/icons-vue';
import { useWorkflowStore, type ConfirmContext } from '../stores/workflow';
import type { StageConfirmRequest, StageConfirmResponse } from '../api';
import CollectingContentRenderer from './stage-renderers/CollectingContentRenderer.vue';
import CleaningContentRenderer from './stage-renderers/CleaningContentRenderer.vue';
import AnalyzingContentRenderer from './stage-renderers/AnalyzingContentRenderer.vue';
import ReportingContentRenderer from './stage-renderers/ReportingContentRenderer.vue';

const store = useWorkflowStore();

// 表单状态（重试输入 + renderer 共享）
const userFeedback = ref('');
const extraUrls = ref<string[]>(['']);
const extraKeywords = ref<string[]>(['']);
const skipRemaining = ref(false);  // Spec 2: 本次剩余阶段自动接受

// renderer 共享的 userEdits（重试时拼到 body）
const rendererUserEdits = ref<Record<string, any>>({});

// 弹窗可见性
const visible = computed({
  get: () => store.confirmDialogVisible,
  set: (v: boolean) => {
    if (!v) handleCloseAttempt();
  },
});

const ctx = computed<ConfirmContext | null>(() => store.confirmContext);
const submitting = computed(() => store.confirmSubmitting);

// Spec 2: 4 阶段 renderer 映射
const rendererMap: Record<string, any> = {
  collecting: CollectingContentRenderer,
  cleaning: CleaningContentRenderer,
  analyzing: AnalyzingContentRenderer,
  reporting: ReportingContentRenderer,
};
const activeRenderer = computed(() => {
  const stage = ctx.value?.stage;
  return stage && rendererMap[stage] ? rendererMap[stage] : null;
});

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

const warning = computed(() => ctx.value?.stageOutput?.warning || '');

// reset 表单
watch(() => ctx.value, (v) => {
  if (v) {
    userFeedback.value = '';
    extraUrls.value = [''];
    extraKeywords.value = [''];
    rendererUserEdits.value = {};
    skipRemaining.value = false;
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
      || cleanedKeywords.value.length > 0
      || Object.keys(rendererUserEdits.value || {}).length > 0)
);

const emit = defineEmits<{
  (e: 'confirmed', data: { ctx: ConfirmContext; response: StageConfirmResponse; decision: 'accept' | 'reject' }): void;
  (e: 'cancelled'): void;
}>();

// 构造重试 body（合并通用 + renderer userEdits）
const buildRejectBody = (): StageConfirmRequest => {
  return {
    decision: 'reject',
    user_edits: {
      extra_urls: cleanedUrls.value.length ? cleanedUrls.value : undefined,
      extra_keywords: cleanedKeywords.value.length ? cleanedKeywords.value : undefined,
      ...(rendererUserEdits.value || {}),  // 各 renderer 扩展字段
    },
    user_feedback: userFeedback.value.trim() || undefined,
  };
};

const handleAccept = async () => {
  if (!ctx.value) return;
  const body: StageConfirmRequest = { decision: 'accept' };
  try {
    // Spec 2: 本次剩余阶段跳过模式
    if (skipRemaining.value && ctx.value.workflowId) {
      store.setSkipRemaining(ctx.value.workflowId, true);
    }
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
    ElMessage.warning('请至少补充一项内容再重试');
    return;
  }
  try {
    const resp = await store.confirmStage(ctx.value.workflowId, buildRejectBody());
    ElMessage.info('已重试，AI 正在重新执行...');
    emit('confirmed', { ctx: ctx.value, response: resp, decision: 'reject' });
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '操作失败';
    ElMessage.error(`重试失败: ${msg}`);
  }
};

// Spec 2: 关闭二次确认（Q3 决定）
// 关闭等价于接受当前结果
const handleCloseAttempt = () => {
  if (submitting.value) return;  // 提交中不允许关闭
  if (!ctx.value) {
    store.hideConfirmDialog();
    emit('cancelled');
    return;
  }
  ElMessageBox.confirm(
    '关闭此弹窗将接受当前结果并进入下一阶段。确定要关闭吗？',
    '确认关闭',
    {
      confirmButtonText: '确定关闭（接受）',
      cancelButtonText: '继续查看',
      type: 'warning',
    }
  )
    .then(async () => {
      // 等价 accept
      if (ctx.value) {
        if (skipRemaining.value && ctx.value.workflowId) {
          store.setSkipRemaining(ctx.value.workflowId, true);
        }
        try {
          const resp = await store.confirmStage(ctx.value.workflowId, { decision: 'accept' });
          ElMessage.success('已接受，进入下一阶段');
          emit('confirmed', { ctx: ctx.value, response: resp, decision: 'accept' });
        } catch (e: any) {
          const msg = e?.response?.data?.detail || e?.message || '操作失败';
          ElMessage.error(`接受失败: ${msg}`);
        }
      } else {
        store.hideConfirmDialog();
        emit('cancelled');
      }
    })
    .catch(() => {
      // 用户选"继续查看" - 留在弹窗
    });
};

const handleCancel = () => {
  store.hideConfirmDialog();
  emit('cancelled');
};
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="`确认${stageLabel}结果`"
    width="840px"
    :close-on-click-modal="false"
    :close-on-press-escape="!submitting"
    :show-close="!submitting"
    :before-close="handleCloseAttempt"
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
          <strong>{{ stageLabel }}</strong> 已完成，请审阅
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

      <!-- Spec 2: 动态内容区（4 renderer 之一） -->
      <component
        :is="activeRenderer"
        v-if="activeRenderer"
        :stage-output="ctx.stageOutput"
        v-model:user-edits="rendererUserEdits"
        class="content-renderer"
      />

      <!-- 重试输入区(默认折叠) - 跨阶段通用 -->
      <el-collapse class="retry-collapse">
        <el-collapse-item name="retry" title="🔁 重试此阶段（添加补充材料 / 反馈）">
          <!-- 通用：补充 URL -->
          <div class="form-block">
            <label class="form-label">补充 URL</label>
            <div v-for="(_, i) in extraUrls" :key="`url-${i}`" class="form-row">
              <el-input
                v-model="extraUrls[i]"
                placeholder="https://example.com/article-1"
                clearable
              />
              <el-button
                v-if="extraUrls.length > 1"
                text
                @click="removeUrl(i)"
                class="row-remove"
              >×</el-button>
            </div>
            <el-button text size="small" @click="addUrl">+ 添加 URL</el-button>
          </div>

          <!-- 通用：补充关键词 -->
          <div class="form-block">
            <label class="form-label">补充关键词</label>
            <div v-for="(_, i) in extraKeywords" :key="`kw-${i}`" class="form-row">
              <el-input
                v-model="extraKeywords[i]"
                placeholder="例:AI制药 · 临床试验"
                clearable
              />
              <el-button
                v-if="extraKeywords.length > 1"
                text
                @click="removeKw(i)"
                class="row-remove"
              >×</el-button>
            </div>
            <el-button text size="small" @click="addKw">+ 添加关键词</el-button>
          </div>

          <!-- 通用：文字反馈 -->
          <div class="form-block">
            <label class="form-label">
              <el-icon><ChatLineSquare /></el-icon>
              文字反馈（可选，AI 会自动解析并调整策略）
            </label>
            <el-input
              v-model="userFeedback"
              type="textarea"
              :rows="3"
              :maxlength="2000"
              show-word-limit
              placeholder="例:上次没采到国内信源，请补采中国 2025 年 AI 制药新闻"
            />
          </div>
        </el-collapse-item>
      </el-collapse>
    </template>

    <template #footer>
      <div class="dialog-footer">
        <el-checkbox v-model="skipRemaining" :disabled="submitting" class="skip-checkbox">
          本次剩余阶段自动接受
        </el-checkbox>
        <div class="footer-buttons">
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
            接受，继续
          </el-button>
        </div>
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

.content-renderer {
  margin-bottom: 16px;
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
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.footer-buttons {
  display: flex;
  gap: 8px;
}

.skip-checkbox {
  font-size: 13px;
  color: var(--scdc-ink-muted, #666);
}

.rotating {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
