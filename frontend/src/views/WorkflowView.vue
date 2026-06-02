<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue';
import { Promotion, Download, CopyDocument, Delete, ChatLineSquare, Refresh, Plus } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import * as echarts from 'echarts';
import { workflowApi, reportsApi } from '../api';
import { useWorkflowStore } from '../stores/workflow';

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
const showHistorySidebar = ref(false);
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

const quickAsk = (topic: string) => {
  inputTopic.value = topic;
  startAnalysis();
};

const startAnalysis = () => {
  const topic = inputTopic.value.trim();
  if (!topic || loading.value) return;

  workflowStore.clearEventSource();
  currentStageHint.value = null;
  if (slowHintTimer) {
    clearTimeout(slowHintTimer);
    slowHintTimer = null;
  }
  showSlowHint.value = false;

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
      workflowStore.startWorkflowStream(conv.id, assistantIdx, res.data.workflow_id, {
        onStageStart: (data) => {
          showSlowHint.value = false;
          if (slowHintTimer) clearTimeout(slowHintTimer);
          slowHintTimer = setTimeout(() => {
            showSlowHint.value = true;
          }, 60000);
          currentStageHint.value = { icon: data.icon, label: data.label };
          scrollToBottom();
        },
        onStageComplete: (_data) => {
          showSlowHint.value = false;
          if (slowHintTimer) clearTimeout(slowHintTimer);
          slowHintTimer = setTimeout(() => {
            showSlowHint.value = true;
          }, 60000);
        },
        onStageError: (data) => {
          if (slowHintTimer) {
            clearTimeout(slowHintTimer);
            slowHintTimer = null;
          }
          showSlowHint.value = false;
          loading.value = false;
          currentStageHint.value = null;
          ElMessage.error(`${data.label}失败`);
        },
        onCompleted: (data) => {
          if (slowHintTimer) {
            clearTimeout(slowHintTimer);
            slowHintTimer = null;
          }
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
        onError: (data) => {
          if (slowHintTimer) {
            clearTimeout(slowHintTimer);
            slowHintTimer = null;
          }
          showSlowHint.value = false;
          loading.value = false;
          currentStageHint.value = null;
          ElMessage.error(`工作流异常: ${data.error}`);
        },
      });

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
  showHistorySidebar.value = false;
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
  <div class="workflow-layout">
    <div class="insight-chat">
      <div class="chat-header">
        <h2 class="chat-title">
          <el-button text :icon="ChatLineSquare" @click="showHistorySidebar = !showHistorySidebar">
            历史记录
          </el-button>
          <el-button text :icon="Plus" @click="handleNewConversation">
            新建对话
          </el-button>
        </h2>
        <div v-if="workflowStore.activeConversation" class="current-topic">
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
          placeholder="输入你想分析的市场主题..."
          :disabled="loading"
          size="large"
          clearable
          @keyup.enter="startAnalysis"
          class="topic-input"
        >
          <template #prefix>
            <el-icon><Promotion /></el-icon>
          </template>
        </el-input>
        <el-button
          type="primary"
          size="large"
          :icon="Promotion"
          :loading="loading"
          :disabled="!inputTopic.trim() || loading"
          @click="startAnalysis"
        >
          开始分析
        </el-button>
      </div>
    </div>

    <transition name="slide">
      <div v-if="showHistorySidebar" class="history-sidebar">
        <div class="history-header">
          <h3>历史对话</h3>
          <div class="history-actions">
            <el-button text size="small" :icon="Refresh" @click="workflowStore.loadHistoryFromServer()">
              刷新
            </el-button>
            <el-button text size="small" @click="showHistorySidebar = false">
              ✕
            </el-button>
          </div>
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
      </div>
    </transition>
  </div>
</template>

<style scoped>
.workflow-layout {
  display: flex;
  height: calc(100vh - 140px);
  position: relative;
}

.insight-chat {
  display: flex;
  flex-direction: column;
  flex: 1;
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
  transition: margin-right 0.3s ease;
}

.chat-header {
  display: flex;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid #e2e8f0;
  gap: 12px;
}

.chat-title {
  margin: 0;
  font-size: 16px;
}

.current-topic {
  font-size: 14px;
  color: #718096;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px 0;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.slow-hint {
  margin-bottom: 12px;
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 60px 40px;
}

.empty-icon {
  font-size: 56px;
  margin-bottom: 16px;
}

.empty-state h2 {
  font-size: 24px;
  font-weight: 700;
  color: #2d3748;
  margin: 0 0 8px;
}

.empty-state p {
  font-size: 14px;
  color: #718096;
  max-width: 460px;
  line-height: 1.6;
  margin: 0 0 24px;
}

.suggestions-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
}

.suggestion-tag {
  padding: 8px 18px;
  background: #f0f4ff;
  color: #409eff;
  border-radius: 20px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.suggestion-tag:hover {
  background: #e6f0ff;
  border-color: #409eff;
  transform: translateY(-1px);
}

.message-row {
  display: flex;
  gap: 12px;
  padding: 0 16px;
}

.user-row {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}

.user-avatar {
  background: #e6f0ff;
}

.assistant-avatar {
  background: #f0fdf4;
}

.message-bubble {
  padding: 12px 18px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.6;
  max-width: 85%;
}

.user-bubble {
  background: #409eff;
  color: white;
  border-bottom-right-radius: 4px;
}

.assistant-bubble {
  background: #f7f8fa;
  color: #2d3748;
  border-bottom-left-radius: 4px;
  border: 1px solid #e2e8f0;
}

.message-body {
  flex: 1;
  min-width: 0;
}

.stage-hint-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
  color: #718096;
  margin-bottom: 4px;
}

.stage-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 8px 14px;
  margin-bottom: 12px;
  background: #f0fdf4;
  border-radius: 10px;
  border: 1px solid #d1fae5;
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
  color: #4a5568;
  font-weight: 500;
}

.stat-count {
  color: #2d3748;
  font-weight: 700;
  background: #e6ffed;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
}

.degraded-warning {
  margin-bottom: 12px;
}

.partial-stats {
  padding: 14px 16px;
  margin-bottom: 12px;
  background: #fff7ed;
  border-radius: 10px;
  border: 1px solid #fed7aa;
}

.partial-stats-title {
  font-size: 14px;
  font-weight: 600;
  color: #c2410c;
  margin-bottom: 10px;
}

.partial-stat-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 0;
  font-size: 13px;
  color: #7c2d12;
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
  background: #409eff;
  animation: pulse 1.4s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.2); }
}

.typing-row {
  display: flex;
  padding: 0 16px 0 52px;
}

.typing-dots {
  display: flex;
  gap: 4px;
  padding: 8px 14px;
  background: #f7f8fa;
  border-radius: 14px;
  border-bottom-left-radius: 4px;
  border: 1px solid #e2e8f0;
}

.typing-dots span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #a0aec0;
  animation: dot-bounce 1.4s ease-in-out infinite;
}

.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes dot-bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

.report-body {
  max-width: 100% !important;
}

.report-body :deep(h1) {
  font-size: 20px;
  font-weight: 700;
  color: #1a202c;
  margin: 0 0 12px;
  padding-bottom: 8px;
  border-bottom: 2px solid #e2e8f0;
}

.report-body :deep(h2) {
  font-size: 17px;
  font-weight: 700;
  color: #2d3748;
  margin: 20px 0 10px;
}

.report-body :deep(h3) {
  font-size: 15px;
  font-weight: 600;
  color: #4a5568;
  margin: 16px 0 8px;
}

.report-body :deep(p) {
  margin: 6px 0;
  line-height: 1.7;
}

.report-body :deep(blockquote) {
  margin: 10px 0;
  padding: 8px 16px;
  background: #f0f4ff;
  border-left: 3px solid #409eff;
  color: #4a5568;
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
  color: #409eff;
  text-decoration: none;
}

.report-body :deep(a:hover) {
  text-decoration: underline;
}

.report-body :deep(code) {
  background: #edf2f7;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
  color: #e53e3e;
}

.report-body :deep(hr) {
  border: none;
  border-top: 1px solid #e2e8f0;
  margin: 16px 0;
}

.report-body :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: 8px;
  margin: 12px 0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.report-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  font-size: 13px;
}

.report-body :deep(th), .report-body :deep(td) {
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  text-align: left;
}

.report-body :deep(th) {
  background: #f7f8fa;
  font-weight: 600;
}

.charts-section {
  margin-top: 16px;
}

.chart-container {
  width: 100%;
  height: 320px;
  margin-bottom: 12px;
}

.message-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
  padding-left: 4px;
}

.chat-input-bar {
  display: flex;
  gap: 12px;
  padding: 16px 0;
  border-top: 1px solid #e2e8f0;
  background: white;
}

.topic-input {
  flex: 1;
}

.history-sidebar {
  width: 320px;
  background: white;
  border-left: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  box-shadow: -2px 0 8px rgba(0, 0, 0, 0.05);
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid #e2e8f0;
}

.history-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #2d3748;
}

.history-actions {
  display: flex;
  gap: 4px;
}

.history-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.history-empty {
  padding: 40px 16px;
  text-align: center;
  color: #a0aec0;
}

.history-item {
  display: flex;
  align-items: center;
  padding: 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
  margin-bottom: 4px;
}

.history-item:hover {
  background: #f7f8fa;
}

.history-item.active {
  background: #e6f0ff;
  border: 1px solid #409eff;
}

.history-item-content {
  flex: 1;
  min-width: 0;
}

.history-item-title {
  font-size: 14px;
  font-weight: 500;
  color: #2d3748;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 4px;
}

.history-item-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.status-badge {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
}

.status-running {
  background: #fff3e0;
  color: #f57c00;
}

.status-completed {
  background: #e8f5e9;
  color: #2e7d32;
}

.status-failed {
  background: #ffebee;
  color: #c62828;
}

.status-idle {
  background: #f5f5f5;
  color: #757575;
}

.history-item-time {
  color: #a0aec0;
}

.history-item-delete {
  opacity: 0;
  transition: opacity 0.2s;
  color: #e53e3e;
}

.history-item:hover .history-item-delete {
  opacity: 1;
}

.slide-enter-active,
.slide-leave-active {
  transition: all 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
  opacity: 0;
}
</style>
