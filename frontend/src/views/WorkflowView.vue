<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { Promotion, Download, CopyDocument, Delete, Refresh, Plus, Close } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import * as echarts from 'echarts';
import { workflowApi, reportsApi } from '../api';
import { useWorkflowStore, type ConfirmContext } from '../stores/workflow';
import { useAuthStore } from '@/stores/auth';
import StageConfirmDialog from '../components/StageConfirmDialog.vue';

const auth = useAuthStore();
const { t } = useI18n();

interface StageHint {
  icon: string;
  label: string;
}

const workflowStore = useWorkflowStore();
const inputTopic = ref('');
const loading = ref(false);
const showSlowHint = ref(false);
let slowHintTimer: ReturnType<typeof setTimeout> | null = null;
const currentStageHint = ref<StageHint | null>(null);
const chatContainer = ref<HTMLElement | null>(null);
const chartRefs = ref<Map<number, HTMLElement>>(new Map());
const showSidebar = ref(false);
const currentWorkflowId = ref<string | null>(null);
const reportIdCache = ref<Record<string, number>>({});

const messages = computed(() => {
  return workflowStore.activeConversation?.messages || [];
});

const suggestions = [
  '2025年AI芯片市场趋势',
  '新能源汽车产业链竞争格局',
  '全球云计算市场份额分析',
  '中国SaaS行业投资机会',
];

onMounted(() => {
  workflowStore.loadHistoryFromServer();
});

onUnmounted(() => {
  if (slowHintTimer) {
    clearTimeout(slowHintTimer);
    slowHintTimer = null;
  }
  showSlowHint.value = false;
  chartRefs.value.forEach((el) => {
    const instance = echarts.getInstanceByDom(el);
    if (instance) instance.dispose();
  });
});

watch(() => workflowStore.activeConversationId, () => {
  showSidebar.value = false;
  nextTick(() => {
    chartRefs.value.forEach((el) => {
      const instance = echarts.getInstanceByDom(el);
      if (instance) instance.dispose();
    });
    chartRefs.value.clear();
    scrollToBottom();
    nextTick(() => {
      const conv = workflowStore.activeConversation;
      if (conv) renderChartsForMessages(conv.messages);
    });
  });
});

const scrollToBottom = () => {
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight;
    }
  });
};

const isFollowUpMode = computed(() => {
  const activeConv = workflowStore.activeConversation;
  return activeConv && activeConv.messages.length > 0 && activeConv.status === 'completed';
});

const inputPlaceholder = computed(() => {
  return isFollowUpMode.value ? '输入追问...' : '输入你想分析的市场主题...';
});

const buttonText = computed(() => {
  return isFollowUpMode.value ? '发送' : '开始分析';
});

const quickAsk = (topic: string) => {
  inputTopic.value = topic;
  sendMessage();
};

const handleStop = () => {
  workflowStore.stopWorkflow();
  loading.value = false;
  if (slowHintTimer) {
    clearTimeout(slowHintTimer);
    slowHintTimer = null;
  }
  showSlowHint.value = false;
  currentStageHint.value = null;
};

// Phase 2: 阶段确认后续流转
// accept → next_stage='cleaning' → 启动完整流(走 cleaning→analyzing→reporting)
// reject → next_stage='collecting' → 启动 collecting-only 流
const startNextStageStream = (
  convId: string,
  assistantIdx: number,
  workflowId: string,
  nextStage: string | null,
) => {
  if (!nextStage) {
    // completed
    return;
  }
  // 阶段提示图标映射
  const stageIcon: Record<string, string> = {
    collecting: '🔍',
    cleaning: '🧹',
    analyzing: '🧠',
    reporting: '📝',
  };
  // 启动阶段流(这里使用空 callbacks,因为我们走的是新一轮流,
  // 实际项目里可以把现在 buildStreamCallbacks 抽到顶层共用)
  // 简化:仅做最小实现,后续 Phase 3.5 再抽象
  const minimalCallbacks = {
    onStageStart: (data: any) => {
      currentStageHint.value = { icon: data.icon, label: data.label };
      scrollToBottom();
    },
    onStageError: (data: any) => {
      loading.value = false;
      currentStageHint.value = null;
      ElMessage.error(`${data.label}失败`);
    },
    onCompleted: (data: any) => {
      currentWorkflowId.value = data.workflow_id || null;
      loading.value = false;
      currentStageHint.value = null;
      scrollToBottom();
      nextTick(() => {
        const updatedConv = workflowStore.activeConversation;
        if (updatedConv) renderChartsForMessages(updatedConv.messages);
      });
    },
    onError: (data: any) => {
      loading.value = false;
      currentStageHint.value = null;
      ElMessage.error(`工作流异常: ${data.error}`);
    },
  };
  // 这里 onAwaitingConfirmation 暂以极简方式重新挂回去
  const cbWithConfirm = {
    ...minimalCallbacks,
    onAwaitingConfirmation: (data: any) => {
      loading.value = false;
      currentStageHint.value = null;
      const ctx: ConfirmContext = {
        workflowId: workflowStore.runningWorkflowId || workflowId,
        convId,
        assistantIdx,
        stage: data.stage,
        stageOutput: data.stage_output || {},
        stageHistoryLength: data.stage_history_length || 0,
      };
      workflowStore.showConfirmDialog(ctx);
    },
  };
  void stageIcon; // 占位保留
  if (nextStage === 'collecting') {
    workflowStore.startCollectingStream(convId, assistantIdx, workflowId, cbWithConfirm);
  } else {
    // cleaning/analyzing/reporting → 走完整流
    workflowStore.startWorkflowStream(convId, assistantIdx, workflowId, cbWithConfirm);
  }
};

const handleConfirmDialogConfirmed = (data: { ctx: ConfirmContext; response: any; decision: 'accept' | 'reject' }) => {
  const { ctx, response } = data;
  const nextStage = response?.next_stage as string | null | undefined;
  // 重新进入 loading 状态
  loading.value = true;
  showSlowHint.value = false;
  if (slowHintTimer) {
    clearTimeout(slowHintTimer);
    slowHintTimer = null;
  }
  startNextStageStream(ctx.convId, ctx.assistantIdx, ctx.workflowId, nextStage || null);
};

const handleConfirmDialogCancelled = () => {
  loading.value = false;
  currentStageHint.value = null;
  showSlowHint.value = false;
  if (slowHintTimer) {
    clearTimeout(slowHintTimer);
    slowHintTimer = null;
  }
};

const sendMessage = () => {
  const topic = inputTopic.value.trim();
  if (!topic || loading.value) return;

  workflowStore.clearEventSource();
  currentStageHint.value = null;
  if (slowHintTimer) {
    clearTimeout(slowHintTimer);
    slowHintTimer = null;
  }
  showSlowHint.value = false;

  const activeConv = workflowStore.activeConversation;
  const isFollowUp = activeConv && activeConv.messages.length > 0 && activeConv.status === 'completed';

  // Phase 2: 阶段确认处理
  // 当 SSE 推送 stage_state='awaiting_confirmation' 时触发,弹出确认弹窗
  // 注:handleConfirmDialogConfirmed/cancelled 已在顶层定义,弹窗 emit 后自动处理
  const onAwaitingConfirmation = (data: any) => {
    loading.value = false;
    showSlowHint.value = false;
    if (slowHintTimer) {
      clearTimeout(slowHintTimer);
      slowHintTimer = null;
    }
    currentStageHint.value = null;
    const conv = workflowStore.activeConversation;
    const ctxAssistantIdx = isFollowUp
      ? (conv ? conv.messages.length - 1 : 1)
      : 1;
    const ctx: ConfirmContext = {
      workflowId: workflowStore.runningWorkflowId || '',
      convId: conv ? conv.id : '',
      assistantIdx: ctxAssistantIdx,
      stage: data.stage,
      stageOutput: data.stage_output || {},
      stageHistoryLength: data.stage_history_length || 0,
    };
    workflowStore.showConfirmDialog(ctx);
  };

  // SSE 回调(精简版,顶层共享 startNextStageStream 处理后续)
  const streamCallbacks = {
    onStageStart: (data: any) => {
      showSlowHint.value = false;
      if (slowHintTimer) clearTimeout(slowHintTimer);
      slowHintTimer = setTimeout(() => { showSlowHint.value = true; }, 60000);
      currentStageHint.value = { icon: data.icon, label: data.label };
      scrollToBottom();
    },
    onStageComplete: (_data: any) => {
      showSlowHint.value = false;
      if (slowHintTimer) clearTimeout(slowHintTimer);
      slowHintTimer = setTimeout(() => { showSlowHint.value = true; }, 60000);
    },
    onStageError: (data: any) => {
      if (slowHintTimer) { clearTimeout(slowHintTimer); slowHintTimer = null; }
      showSlowHint.value = false;
      loading.value = false;
      currentStageHint.value = null;
      ElMessage.error(`${data.label}失败`);
    },
    onCompleted: (data: any) => {
      if (slowHintTimer) { clearTimeout(slowHintTimer); slowHintTimer = null; }
      showSlowHint.value = false;
      currentWorkflowId.value = data.workflow_id || null;
      loading.value = false;
      currentStageHint.value = null;
      scrollToBottom();
      nextTick(() => {
        const updatedConv = workflowStore.activeConversation;
        if (updatedConv) renderChartsForMessages(updatedConv.messages);
      });
    },
    onError: (data: any) => {
      if (slowHintTimer) { clearTimeout(slowHintTimer); slowHintTimer = null; }
      showSlowHint.value = false;
      loading.value = false;
      currentStageHint.value = null;
      ElMessage.error(`工作流异常: ${data.error}`);
    },
    onAwaitingConfirmation,
  };

  if (isFollowUp) {
    // 追问模式：在当前对话中追加消息
    activeConv.messages.push({ role: 'user', content: topic });
    activeConv.messages.push({
      role: 'assistant',
      content: '',
      reportMarkdown: '',
      chartOptions: [],
    });
    const assistantIdx = activeConv.messages.length - 1;

    // 构建对话历史
    const conversationHistory = activeConv.messages
      .slice(0, -2)
      .map(m => ({ role: m.role, content: m.content || m.reportMarkdown || '' }));

    inputTopic.value = '';
    loading.value = true;
    scrollToBottom();

    workflowApi.followUp({ message: topic, conversation_history: conversationHistory })
      .then((res) => {
        workflowStore.startWorkflowStream(
          activeConv.id,
          assistantIdx,
          res.data.workflow_id,
          streamCallbacks,
        );
      })
      .catch(() => {
        activeConv.messages.pop();
        if (slowHintTimer) {
          clearTimeout(slowHintTimer);
          slowHintTimer = null;
        }
        showSlowHint.value = false;
        ElMessage.error('追问失败，请重试');
        loading.value = false;
      });
  } else {
    // 首次分析模式：创建新对话
    const conv = workflowStore.createConversation(topic);

    conv.messages.push({ role: 'user', content: topic });
    conv.messages.push({
      role: 'assistant',
      content: '',
      reportMarkdown: '',
      chartOptions: [],
    });

    inputTopic.value = '';
    loading.value = true;
    scrollToBottom();

    const assistantIdx = 1;

    workflowApi.start({ topic, max_items: 5 })
      .then((res) => {
        workflowStore.startWorkflowStream(
          conv.id,
          assistantIdx,
          res.data.workflow_id,
          streamCallbacks,
        );

        showSlowHint.value = false;
        if (slowHintTimer) clearTimeout(slowHintTimer);
        slowHintTimer = setTimeout(() => {
          showSlowHint.value = true;
        }, 60000);
      })
      .catch(() => {
        conv.messages.pop();
        if (slowHintTimer) {
          clearTimeout(slowHintTimer);
          slowHintTimer = null;
        }
        showSlowHint.value = false;
        ElMessage.error('启动分析失败，请检查后端服务');
        loading.value = false;
      });
  }
};

const handleNewConversation = async () => {
  if (loading.value) {
    try {
      await ElMessageBox.confirm(
        '当前分析正在进行，切换将丢失当前进度，确定新建对话吗？',
        '提示',
        { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
      );
    } catch {
      return;
    }
    workflowStore.clearEventSource();
    loading.value = false;
    currentStageHint.value = null;
    if (slowHintTimer) {
      clearTimeout(slowHintTimer);
      slowHintTimer = null;
    }
    showSlowHint.value = false;
  }
  workflowStore.resetActiveConversation();
};

const selectConversation = (id: string) => {
  workflowStore.setActiveConversation(id);
};

const handleDeleteConversation = async (id: string) => {
  try {
    await ElMessageBox.confirm('确定删除这条对话记录吗？', '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    });
    workflowStore.deleteConversation(id);
    ElMessage.success('已删除');
  } catch {
    // cancelled
  }
};

const handleExportReport = async (markdown: string, fmt: string) => {
  if (fmt === 'md') {
    if (!markdown) return;
    const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `market-insight-${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);
    ElMessage.success('报告已导出');
    return;
  }

  const wfId = currentWorkflowId.value
    || (workflowStore.activeConversation?.id?.startsWith('server_')
        ? workflowStore.activeConversation.id.slice(7)
        : workflowStore.activeConversation?.id);
  if (!wfId) {
    ElMessage.warning('报告尚未完全生成，请稍后重试');
    return;
  }

  let reportId = reportIdCache.value[wfId];
  if (!reportId) {
    try {
      const res = await reportsApi.getReports({ task_id: wfId });
      if (res.data && res.data.length > 0) {
        reportId = res.data[0].id;
        reportIdCache.value[wfId] = reportId;
      }
    } catch {
      // ignore, will try to create below
    }
  }

  if (!reportId) {
    try {
      const res = await reportsApi.createFromWorkflow({
        task_id: wfId,
        title: workflowStore.activeConversation?.topic || 'Untitled',
        content_markdown: markdown,
        summary: markdown?.substring(0, 200),
      });
      reportId = res.data.id;
      reportIdCache.value[wfId] = reportId;
    } catch {
      ElMessage.error('创建报告失败，请重试');
      return;
    }
  }

  const exportUrl = reportsApi.exportReportUrl(reportId, fmt);
  try {
    const response = await fetch(exportUrl, {
      headers: reportsApi.getExportHeaders(),
    });
    if (!response.ok) throw new Error('下载失败');
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = objectUrl;
    a.download = `report_${reportId}.${fmt}`;
    a.click();
    URL.revokeObjectURL(objectUrl);
    ElMessage.success('报告已导出');
  } catch {
    ElMessage.error('导出失败，请重试');
  }
};

const handleCopyReport = (markdown: string) => {
  if (!markdown) return;
  navigator.clipboard.writeText(markdown).then(() => {
    ElMessage.success('报告已复制到剪贴板');
  }).catch(() => {
    ElMessage.error('复制失败');
  });
};

const renderChartsForMessages = (msgs: any[]) => {
  msgs.forEach((msg, msgIdx) => {
    if (!msg?.chartOptions) return;
    msg.chartOptions.forEach((opt: any, chartIdx: number) => {
      const domId = `chart-${msgIdx}-${chartIdx}`;
      nextTick(() => {
        const dom = document.getElementById(domId);
        if (!dom) return;
        const existing = echarts.getInstanceByDom(dom);
        if (existing) existing.dispose();
        const chart = echarts.init(dom);
        chart.setOption(opt);
        chartRefs.value.set(msgIdx * 100 + chartIdx, dom);
        const ro = new ResizeObserver(() => chart.resize());
        ro.observe(dom);
      });
    });
  });
};

const formatTime = (ts: number) => {
  const d = new Date(ts);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  if (diff < 60000) return '刚刚';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
  return d.toLocaleDateString('zh-CN');
};

const getStatusBadge = (status: string) => {
  switch (status) {
    case 'running': return { text: '执行中', class: 'status-running' };
    case 'completed': return { text: '已完成', class: 'status-completed' };
    case 'failed': return { text: '失败', class: 'status-failed' };
    default: return { text: '待开始', class: 'status-idle' };
  }
};
</script>

<template>
  <div v-if="auth.isAuthenticated" class="workflow-layout">
    <!-- Mobile overlay -->
    <div v-if="showSidebar" class="sidebar-overlay" @click="showSidebar = false"></div>

    <!-- Left sidebar -->
    <aside class="sidebar" :class="{ 'sidebar-open': showSidebar }">
      <div class="sidebar-header">
        <el-button type="primary" :icon="Plus" @click="handleNewConversation" class="new-chat-btn">
          新建对话
        </el-button>
      </div>
      <div class="sidebar-divider">
        <span>历史记录</span>
        <el-button text size="small" :icon="Refresh" @click="workflowStore.loadHistoryFromServer()" />
      </div>
      <div class="history-list">
        <div v-if="workflowStore.conversations.length === 0" class="history-empty">
          <p>暂无历史对话</p>
        </div>
        <div
          v-for="conv in workflowStore.conversations"
          :key="conv.id"
          :class="['history-item', { active: conv.id === workflowStore.activeConversationId }]"
          @click="selectConversation(conv.id)"
        >
          <div class="history-item-content">
            <div class="history-item-title">{{ conv.topic }}</div>
            <div class="history-item-meta">
              <span :class="['status-badge', getStatusBadge(conv.status).class]">
                {{ getStatusBadge(conv.status).text }}
              </span>
              <span class="history-item-time">{{ formatTime(conv.updatedAt) }}</span>
            </div>
          </div>
          <el-button
            text
            size="small"
            :icon="Delete"
            class="history-item-delete"
            @click.stop="handleDeleteConversation(conv.id)"
          />
        </div>
      </div>
    </aside>

    <!-- Right chat area -->
    <main class="chat-area">
      <div class="chat-header">
        <button class="hamburger-btn" @click="showSidebar = !showSidebar">
          <span></span><span></span><span></span>
        </button>
        <div class="current-topic" v-if="workflowStore.activeConversation">
          {{ workflowStore.activeConversation.topic }}
        </div>
      </div>

      <div class="chat-messages" ref="chatContainer">
        <el-alert
          v-if="showSlowHint"
          type="info"
          :closable="false"
          show-icon
          class="slow-hint"
        >
          <template #title>当前阶段可能耗时较久，请耐心等待...</template>
        </el-alert>

        <div v-if="messages.length === 0" class="empty-state">
          <div class="empty-icon">🤖</div>
          <h2>AI 市场洞察助手</h2>
          <p>请输入你关注的市场主题，AI 将自动搜索最新信息、深度分析并生成结构化报告</p>
          <div class="suggestions-row">
            <span
              v-for="s in suggestions"
              :key="s"
              class="suggestion-tag"
              @click="quickAsk(s)"
            >{{ s }}</span>
          </div>
        </div>

        <template v-for="(msg, idx) in messages" :key="idx">
          <div v-if="msg.role === 'user'" class="message-row user-row">
            <div class="message-avatar user-avatar">👤</div>
            <div class="message-bubble user-bubble">{{ msg.content }}</div>
          </div>

          <div v-else class="message-row assistant-row">
            <div class="message-avatar assistant-avatar">🤖</div>
            <div class="message-body">
              <div v-if="msg.stageHint" class="stage-hint-banner">
                <span class="stage-pulse"></span>
                <span>{{ msg.stageHint }}</span>
              </div>
              <div v-if="msg.stageStats && msg.stageStats.length" class="stage-stats">
                <div v-for="(stat, si) in msg.stageStats" :key="si" class="stage-stat-item">
                  <span class="stat-icon">{{ stat.icon }}</span>
                  <span class="stat-label">{{ stat.label }}</span>
                  <span class="stat-count">
                    <template v-if="stat.after !== undefined">{{ stat.before }} → {{ stat.after }}</template>
                    <template v-else>{{ stat.before }}</template>
                  </span>
                </div>
              </div>
              <el-alert
                v-if="msg.degraded"
                type="warning"
                :closable="false"
                show-icon
                class="degraded-warning"
              >
                <template #title>⚠️ AI 分析服务暂不可用，当前展示基于规则/模板生成的结果，报告质量可能受限。</template>
              </el-alert>
              <div v-if="msg.partialStats && msg.partialStats.length" class="partial-stats">
                <div class="partial-stats-title">报告中段生成失败，但已完成以下阶段：</div>
                <div v-for="(stat, si) in msg.partialStats" :key="si" class="partial-stat-item">
                  <span class="partial-stat-icon">{{ stat.icon }}</span>
                  <span class="partial-stat-text">{{ stat.label }}：{{ stat.count }}</span>
                </div>
              </div>
              <div
                v-if="msg.content"
                class="message-bubble assistant-bubble report-body"
                v-html="msg.content"
              ></div>
              <div v-if="msg.chartOptions && msg.chartOptions.length" class="charts-section">
                <div
                  v-for="(_opt, ci) in msg.chartOptions"
                  :key="ci"
                  :id="`chart-${idx}-${ci}`"
                  class="chart-container"
                ></div>
              </div>
              <div v-if="msg.reportMarkdown && !(loading && idx === messages.length - 1)" class="message-actions">
                <el-button size="small" text :icon="CopyDocument" @click="handleCopyReport(msg.reportMarkdown!)">
                  复制
                </el-button>
                <el-dropdown trigger="click" @command="(fmt: string) => handleExportReport(msg.reportMarkdown!, fmt)">
                  <el-button size="small" text :icon="Download">
                    导出报告
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="md">Markdown (.md)</el-dropdown-item>
                      <el-dropdown-item command="docx">Word (.docx)</el-dropdown-item>
                      <el-dropdown-item command="pdf">PDF (.pdf)</el-dropdown-item>
                      <el-dropdown-item command="pptx">PowerPoint (.pptx)</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </div>
          </div>
        </template>

        <div v-if="loading && messages.length > 0" class="typing-row">
          <div class="typing-dots">
            <span></span><span></span><span></span>
          </div>
        </div>
      </div>

      <div class="chat-input-bar">
        <el-input
          v-model="inputTopic"
          :placeholder="inputPlaceholder"
          :disabled="loading"
          size="large"
          clearable
          @keyup.enter="sendMessage"
          class="topic-input"
        >
          <template #prefix>
            <el-icon><Promotion /></el-icon>
          </template>
        </el-input>
        <el-button
          v-if="loading"
          type="danger"
          size="large"
          :icon="Close"
          @click="handleStop"
          class="stop-btn"
        >
          停止
        </el-button>
        <el-button
          v-else
          type="primary"
          size="large"
          :icon="Promotion"
          :disabled="!inputTopic.trim()"
          @click="sendMessage"
          class="send-btn"
        >
          {{ buttonText }}
        </el-button>
      </div>
    </main>

    <!-- Phase 2: 阶段确认弹窗 -->
    <StageConfirmDialog
      @confirmed="handleConfirmDialogConfirmed"
      @cancelled="handleConfirmDialogCancelled"
    />
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
/* ===== Layout ===== */
.workflow-layout {
  display: flex;
  height: calc(100vh - 120px);
  position: relative;
  overflow: hidden;
  border-radius: var(--scdc-radius-lg);
  border: 1px solid var(--scdc-bg-sunken);
  box-shadow: var(--scdc-shadow-soft);
}

/* ===== Sidebar ===== */
.sidebar {
  width: 280px;
  background: var(--scdc-bg-elevated);
  border-right: 1px solid var(--scdc-bg-sunken);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  z-index: 100;
  transition: transform 0.3s ease;
}

.sidebar-header {
  padding: 20px;
}

.new-chat-btn {
  width: 100%;
  font-weight: 600;
  border-radius: 12px;
  height: 44px;
  font-size: 14px;
}

.sidebar-divider {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 20px 10px;
  font-size: 11px;
  font-weight: 600;
  color: var(--scdc-ink-soft);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.history-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 12px 12px;
}

.history-empty {
  padding: 40px 16px;
  text-align: center;
  color: var(--scdc-ink-soft);
  font-size: 13px;
}

.history-item {
  display: flex;
  align-items: center;
  padding: 12px 14px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
  margin-bottom: 4px;
  border-left: 3px solid transparent;
}

.history-item:hover {
  background: var(--scdc-bg-hover);
}

.history-item.active {
  background: var(--scdc-accent-soft);
  border-left-color: var(--scdc-accent);
}

.history-item-content {
  flex: 1;
  min-width: 0;
}

.history-item-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--scdc-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 6px;
}

.history-item-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
}

.status-badge {
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 500;
}

.status-running {
  background: var(--scdc-warning-soft);
  color: var(--scdc-warning);
}

.status-completed {
  background: var(--scdc-success-soft);
  color: var(--scdc-success);
}

.status-failed {
  background: var(--scdc-danger-soft);
  color: var(--scdc-danger);
}

.status-idle {
  background: var(--scdc-bg-elevated);
  color: var(--scdc-ink-muted);
}

.history-item-time {
  color: var(--scdc-ink-soft);
}

.history-item-delete {
  opacity: 0;
  transition: opacity 0.2s;
  color: var(--scdc-danger);
}

.history-item:hover .history-item-delete {
  opacity: 1;
}

/* ===== Sidebar overlay (mobile) ===== */
.sidebar-overlay {
  display: none;
}

/* ===== Chat area ===== */
.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--scdc-bg-canvas);
}

.chat-header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 24px;
  border-bottom: 1px solid var(--scdc-bg-sunken);
  min-height: 56px;
  background: var(--scdc-bg-surface);
}

.hamburger-btn {
  display: none;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  border-radius: 8px;
  transition: background 0.2s;
}

.hamburger-btn:hover {
  background: var(--scdc-bg-hover);
}

.hamburger-btn span {
  width: 20px;
  height: 2px;
  background: var(--scdc-ink);
  border-radius: 1px;
  transition: all 0.2s;
}

.current-topic {
  font-size: 16px;
  font-weight: 600;
  color: var(--scdc-ink-strong);
  font-family: var(--scdc-font-display);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ===== Messages ===== */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 28px 0;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.slow-hint {
  margin: 0 24px 14px;
}

/* ===== Empty state ===== */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 80px 40px;
  animation: fadeInUp 0.5s ease-out;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.empty-icon {
  font-size: 72px;
  margin-bottom: 24px;
  opacity: 0.9;
}

.empty-state h2 {
  font-family: var(--scdc-font-display);
  font-size: 26px;
  font-weight: 600;
  color: var(--scdc-ink-strong);
  margin: 0 0 10px;
  letter-spacing: -0.01em;
}

.empty-state p {
  font-size: 14px;
  color: var(--scdc-ink-muted);
  max-width: 500px;
  line-height: 1.7;
  margin: 0 0 32px;
}

.suggestions-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
}

.suggestion-tag {
  padding: 10px 20px;
  background: var(--scdc-bg-surface);
  color: var(--scdc-ink);
  border-radius: var(--scdc-radius-md);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid var(--scdc-bg-sunken);
  font-weight: 500;
}

.suggestion-tag:hover {
  background: var(--scdc-accent-soft);
  border-color: var(--scdc-accent);
  color: var(--scdc-accent);
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(180, 83, 9, 0.1);
}

/* ===== Message rows ===== */
.message-row {
  display: flex;
  gap: 14px;
  padding: 0 24px;
  max-width: 850px;
  width: 100%;
  margin: 0 auto;
}

.user-row {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}

.user-avatar {
  background: var(--scdc-accent-soft);
}

.assistant-avatar {
  background: var(--scdc-success-soft);
}

.message-bubble {
  padding: 14px 20px;
  font-size: 14px;
  line-height: 1.7;
  max-width: 80%;
}

.user-bubble {
  background: var(--scdc-accent);
  color: white;
  border-radius: 18px 18px 4px 18px;
  box-shadow: 0 2px 6px rgba(180, 83, 9, 0.15);
}

.assistant-bubble {
  background: var(--scdc-bg-surface);
  color: var(--scdc-ink);
  border-radius: 18px 18px 18px 4px;
  border: 1px solid var(--scdc-bg-sunken);
  box-shadow: 0 1px 4px rgba(60, 40, 20, 0.04);
}

.message-body {
  flex: 1;
  min-width: 0;
}

/* ===== Stage hints & stats ===== */
.stage-hint-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
  color: var(--scdc-ink-muted);
  margin-bottom: 4px;
}

.stage-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 8px 14px;
  margin-bottom: 12px;
  background: var(--scdc-bg-elevated);
  border-radius: var(--scdc-radius-md);
  border: 1px solid var(--scdc-bg-sunken);
}

.stage-stat-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.stat-icon {
  font-size: 14px;
}

.stat-label {
  color: var(--scdc-ink);
  font-weight: 500;
}

.stat-count {
  color: var(--scdc-accent-hover);
  font-weight: 700;
  background: var(--scdc-accent-soft);
  padding: 2px 8px;
  border-radius: var(--scdc-radius-md);
  font-size: 12px;
  font-family: var(--scdc-font-mono);
  font-variant-numeric: tabular-nums;
}

.degraded-warning {
  margin-bottom: 12px;
}

.partial-stats {
  padding: 14px 16px;
  margin-bottom: 12px;
  background: var(--scdc-warning-soft);
  border-radius: var(--scdc-radius-md);
  border: 1px solid var(--scdc-bg-sunken);
}

.partial-stats-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--scdc-accent-hover);
  margin-bottom: 10px;
}

.partial-stat-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 0;
  font-size: 13px;
  color: var(--scdc-ink);
}

.partial-stat-icon {
  font-size: 14px;
}

.partial-stat-text {
  line-height: 1.5;
}

.stage-pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--scdc-accent);
  animation: pulse 1.4s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.2); }
}

/* ===== Typing dots ===== */
.typing-row {
  display: flex;
  padding: 0 20px 0 52px;
  max-width: 800px;
  width: 100%;
  margin: 0 auto;
}

.typing-dots {
  display: flex;
  gap: 4px;
  padding: 10px 16px;
  background: var(--scdc-bg-surface);
  border-radius: 16px 16px 16px 4px;
  border: 1px solid var(--scdc-bg-sunken);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.typing-dots span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--scdc-ink-soft);
  animation: dot-bounce 1.4s ease-in-out infinite;
}

.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes dot-bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

/* ===== Report body ===== */
.report-body {
  max-width: 100% !important;
}

.report-body :deep(h1) {
  font-size: 20px;
  font-weight: 700;
  color: var(--scdc-ink-strong);
  font-family: var(--scdc-font-display);
  margin: 0 0 12px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--scdc-bg-sunken);
}

.report-body :deep(h2) {
  font-size: 17px;
  font-weight: 700;
  color: var(--scdc-ink-strong);
  font-family: var(--scdc-font-display);
  margin: 20px 0 10px;
}

.report-body :deep(h3) {
  font-size: 15px;
  font-weight: 600;
  color: var(--scdc-ink-strong);
  font-family: var(--scdc-font-display);
  margin: 16px 0 8px;
}

.report-body :deep(p) {
  margin: 6px 0;
  line-height: 1.75;
}

.report-body :deep(blockquote) {
  margin: 10px 0;
  padding: 8px 16px;
  background: var(--scdc-accent-soft);
  border-left: 3px solid var(--scdc-accent);
  color: var(--scdc-ink-muted);
  border-radius: 0 6px 6px 0;
}

.report-body :deep(ul), .report-body :deep(ol) {
  margin: 8px 0;
  padding-left: 20px;
}

.report-body :deep(li) {
  margin: 4px 0;
  line-height: 1.6;
}

.report-body :deep(a) {
  color: var(--scdc-accent);
  text-decoration: none;
}

.report-body :deep(a:hover) {
  text-decoration: underline;
}

.report-body :deep(code) {
  background: var(--scdc-bg-elevated);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
  color: var(--scdc-danger);
  font-family: var(--scdc-font-mono);
}

.report-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--scdc-bg-sunken);
  margin: 16px 0;
}

.report-body :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: 8px;
  margin: 12px 0;
  box-shadow: var(--scdc-shadow-soft);
}

.report-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  font-size: 13px;
}

.report-body :deep(th), .report-body :deep(td) {
  padding: 8px 12px;
  border: 1px solid var(--scdc-bg-sunken);
  text-align: left;
}

.report-body :deep(th) {
  background: var(--scdc-bg-elevated);
  font-weight: 600;
}

/* ===== Charts ===== */
.charts-section {
  margin-top: 16px;
}

.chart-container {
  width: 100%;
  height: 320px;
  margin-bottom: 12px;
}

/* ===== Message actions ===== */
.message-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
  padding-left: 4px;
}

/* ===== Input bar ===== */
.chat-input-bar {
  display: flex;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid var(--scdc-bg-sunken);
  background: var(--scdc-bg-surface);
  align-items: center;
}

.topic-input {
  flex: 1;
}

.topic-input :deep(.el-input__wrapper) {
  border-radius: 24px;
  box-shadow: 0 0 0 1px var(--scdc-bg-sunken);
  transition: box-shadow 0.2s ease;
}

.topic-input :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px var(--scdc-ink-soft);
}

.topic-input :deep(.el-input__wrapper.is-focus),
.topic-input :deep(.el-input__wrapper:focus-within) {
  box-shadow: 0 0 0 2px var(--scdc-accent-soft);
}

.send-btn {
  border-radius: 24px;
  padding: 0 24px;
  font-weight: 600;
  height: 42px;
}

.stop-btn {
  border-radius: 24px;
  padding: 0 24px;
  font-weight: 600;
  height: 42px;
  animation: stopPulse 2s ease-in-out infinite;
}

@keyframes stopPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(245, 108, 108, 0.4); }
  50% { box-shadow: 0 0 0 6px rgba(245, 108, 108, 0); }
}

/* ===== Custom scrollbar ===== */
.chat-messages::-webkit-scrollbar,
.history-list::-webkit-scrollbar {
  width: 6px;
}

.chat-messages::-webkit-scrollbar-track,
.history-list::-webkit-scrollbar-track {
  background: transparent;
}

.chat-messages::-webkit-scrollbar-thumb,
.history-list::-webkit-scrollbar-thumb {
  background: var(--scdc-bg-sunken);
  border-radius: 3px;
}

.chat-messages::-webkit-scrollbar-thumb:hover,
.history-list::-webkit-scrollbar-thumb:hover {
  background: var(--scdc-ink-soft);
}

/* ===== Auth placeholder ===== */
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

/* ===== Mobile responsive ===== */
@media (max-width: 768px) {
  .workflow-layout {
    position: relative;
  }

  .sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    z-index: 200;
    transform: translateX(-100%);
    box-shadow: 2px 0 12px rgba(0, 0, 0, 0.1);
  }

  .sidebar.sidebar-open {
    transform: translateX(0);
  }

  .sidebar-overlay {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    z-index: 150;
    animation: fadeIn 0.2s ease;
  }

  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  .hamburger-btn {
    display: flex;
  }

  .chat-header {
    padding: 10px 16px;
  }

  .chat-messages {
    padding: 16px 0;
    gap: 16px;
  }

  .message-row {
    padding: 0 12px;
  }

  .chat-input-bar {
    padding: 12px 12px;
  }
}
</style>