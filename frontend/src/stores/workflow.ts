import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { workflowApi, type StageConfirmRequest, type StageConfirmResponse, type StageName } from '../api';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

const sanitizeHtml = (html: string): string => {
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'br', 'strong', 'em', 'u', 's', 'a', 'ul', 'ol', 'li', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'blockquote', 'code', 'pre', 'hr', 'img', 'sup', 'sub'],
    ALLOWED_ATTR: ['href', 'target', 'rel', 'src', 'alt', 'title', 'class'],
  });
};

interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  stageHint?: string;
  chartOptions?: any[];
  reportMarkdown?: string;
  stageStats?: { label: string; before: number; after?: number; icon: string }[];
  degraded?: boolean;
  partialStats?: { label: string; count: string; icon: string }[];
}

interface Conversation {
  id: string;
  topic: string;
  messages: ChatMessage[];
  status: 'idle' | 'running' | 'completed' | 'failed';
  createdAt: number;
  updatedAt: number;
}

interface StreamCallbacks {
  onStageStart?: (data: any) => void;
  onStageComplete?: (data: any) => void;
  onStageError?: (data: any) => void;
  onCompleted?: (data: any) => void;
  onError?: (data: any) => void;
  // Phase 2: 阶段进入 awaiting_confirmation
  onAwaitingConfirmation?: (data: any) => void;
}

// Phase 2: 阶段确认弹窗上下文
export interface ConfirmContext {
  workflowId: string;
  convId: string;
  assistantIdx: number;
  stage: string;
  stageOutput: any;          // 后端 stage_output 字段(含 sources 列表)
  stageHistoryLength: number;
}

const STORAGE_KEY = 'scdc_workflow_conversations';
const ACTIVE_KEY = 'scdc_workflow_active_id';
// Spec 2: 用户偏好持久化
const PREFS_KEY = 'scdc_workflow_user_preferences';

const loadConversations = (): Conversation[] => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
};

const loadUserPreferences = (): { skipAllConfirmations: boolean } => {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    return raw ? JSON.parse(raw) : { skipAllConfirmations: false };
  } catch {
    return { skipAllConfirmations: false };
  }
};

const saveConversations = (conversations: Conversation[]) => {
  const sanitized = conversations.map(c => ({
    ...c,
    messages: c.messages.map(m => ({
      role: m.role,
      content: m.content,
      stageHint: m.stageHint,
      chartOptions: m.chartOptions,
      reportMarkdown: m.reportMarkdown,
    })),
  }));
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sanitized));
};

export const useWorkflowStore = defineStore('workflow', () => {
  const conversations = ref<Conversation[]>(loadConversations());
  const activeConversationId = ref<string | null>(
    localStorage.getItem(ACTIVE_KEY) || null
  );
  const eventSource = ref<EventSource | null>(null);
  const runningWorkflowId = ref<string | null>(null);
  const activeConvIdForStream = ref<string | null>(null);
  const activeAssistantIdxForStream = ref<number>(-1);
  const streamCallbacks = ref<StreamCallbacks>({});

  // Phase 2: 阶段确认弹窗状态
  const confirmContext = ref<ConfirmContext | null>(null);
  const confirmDialogVisible = ref(false);
  const confirmSubmitting = ref(false);

  // Spec 2: 跳过模式状态
  // skipRemainingForWorkflow: 内存中（本次工作流），存 workflow_id 集合
  const skipRemainingForWorkflow = ref<Set<string>>(new Set());
  // userPreferences: 持久化到 localStorage（全局偏好）
  const userPreferences = ref<{ skipAllConfirmations: boolean }>(loadUserPreferences());

  const activeConversation = computed(() => {
    if (!activeConversationId.value) return null;
    return conversations.value.find(c => c.id === activeConversationId.value) || null;
  });

  const setActiveConversation = (id: string | null) => {
    activeConversationId.value = id;
    if (id) {
      localStorage.setItem(ACTIVE_KEY, id);
    } else {
      localStorage.removeItem(ACTIVE_KEY);
    }
  };

  const createConversation = (topic: string): Conversation => {
    const id = `conv_${Date.now()}`;
    const now = Date.now();
    const conv: Conversation = {
      id,
      topic,
      messages: [],
      status: 'idle',
      createdAt: now,
      updatedAt: now,
    };
    conversations.value.unshift(conv);
    saveConversations(conversations.value);
    setActiveConversation(id);
    return conv;
  };

  const addMessage = (convId: string, message: ChatMessage) => {
    const conv = conversations.value.find(c => c.id === convId);
    if (conv) {
      conv.messages.push(message);
      conv.updatedAt = Date.now();
      saveConversations(conversations.value);
    }
  };

  const updateMessage = (convId: string, index: number, updates: Partial<ChatMessage>) => {
    const conv = conversations.value.find(c => c.id === convId);
    if (conv && conv.messages[index]) {
      Object.assign(conv.messages[index], updates);
      conv.updatedAt = Date.now();
      saveConversations(conversations.value);
    }
  };

  const updateConversationStatus = (convId: string, status: Conversation['status']) => {
    const conv = conversations.value.find(c => c.id === convId);
    if (conv) {
      conv.status = status;
      conv.updatedAt = Date.now();
      saveConversations(conversations.value);
    }
  };

  const deleteConversation = (id: string) => {
    conversations.value = conversations.value.filter(c => c.id !== id);
    saveConversations(conversations.value);
    if (activeConversationId.value === id) {
      setActiveConversation(null);
    }
  };

  const clearAllConversations = () => {
    conversations.value = [];
    saveConversations([]);
    setActiveConversation(null);
  };

  const resetActiveConversation = () => {
    setActiveConversation(null);
  };

  const isStreamFinished = ref(false);

  const setupStreamListeners = (convId: string, assistantIdx: number, callbacks: StreamCallbacks) => {
    activeConvIdForStream.value = convId;
    activeAssistantIdxForStream.value = assistantIdx;
    streamCallbacks.value = callbacks;
    isStreamFinished.value = false;
  };

  const attachEventSourceListeners = (es: EventSource) => {
    es.addEventListener('stage_start', (e: any) => {
      const data = JSON.parse(e.data);
      if (streamCallbacks.value.onStageStart) {
        streamCallbacks.value.onStageStart(data);
      }
      if (activeConvIdForStream.value && activeAssistantIdxForStream.value >= 0) {
        updateMessage(activeConvIdForStream.value, activeAssistantIdxForStream.value, {
          stageHint: `${data.icon} 正在${data.label}...`,
        });
      }
    });

    es.addEventListener('stage_complete', (e: any) => {
      const data = JSON.parse(e.data);
      if (streamCallbacks.value.onStageComplete) {
        streamCallbacks.value.onStageComplete(data);
      }
      // Phase 2: 阶段结束后,如果是 awaiting_confirmation 状态,触发确认弹窗
      if (data && data.stage_state === 'awaiting_confirmation') {
        if (streamCallbacks.value.onAwaitingConfirmation) {
          streamCallbacks.value.onAwaitingConfirmation(data);
        }
      }
    });

    es.addEventListener('direct_response', (e: any) => {
      const data = JSON.parse(e.data);
      if (activeConvIdForStream.value && activeAssistantIdxForStream.value >= 0) {
        const conv = conversations.value.find(c => c.id === activeConvIdForStream.value);
        if (conv && conv.messages[activeAssistantIdxForStream.value]) {
          const currentContent = conv.messages[activeAssistantIdxForStream.value].content || '';
          updateMessage(activeConvIdForStream.value, activeAssistantIdxForStream.value, {
            content: currentContent + (data.content || ''),
            stageHint: '💬 正在回复...',
          });
        }
      }
    });

    es.addEventListener('direct_response_done', (e: any) => {
      isStreamFinished.value = true;
      const data = JSON.parse(e.data);

      if (activeConvIdForStream.value && activeAssistantIdxForStream.value >= 0) {
        const conv = conversations.value.find(c => c.id === activeConvIdForStream.value);
        const assistantMsg = conv && conv.messages[activeAssistantIdxForStream.value];
        const md = assistantMsg?.content || '';
        let renderedContent = '';
        if (md) {
          try {
            renderedContent = sanitizeHtml(marked.parse(md) as string);
          } catch {
            renderedContent = md.replace(/\n/g, '<br>');
          }
        }
        updateMessage(activeConvIdForStream.value, activeAssistantIdxForStream.value, {
          content: renderedContent,
          reportMarkdown: md,
          stageHint: '',
          chartOptions: data.chart_configs || [],
        });
        if (activeConvIdForStream.value) {
          updateConversationStatus(activeConvIdForStream.value, 'completed');
        }
      }

      if (streamCallbacks.value.onCompleted) {
        streamCallbacks.value.onCompleted({
          workflow_id: data.workflow_id || null,
          report_markdown: null,
          chart_configs: data.chart_configs || [],
          sections: [],
          collected_count: 0,
          cleaned_count: 0,
          insight_count: 0,
        });
      }

      clearEventSource();
    });

    es.addEventListener('stage_error', (e: any) => {
      isStreamFinished.value = true;
      const data = JSON.parse(e.data);
      if (streamCallbacks.value.onStageError) {
        streamCallbacks.value.onStageError(data);
      }
      if (activeConvIdForStream.value && activeAssistantIdxForStream.value >= 0) {
        updateMessage(activeConvIdForStream.value, activeAssistantIdxForStream.value, {
          stageHint: '',
          content: `❌ ${data.label}失败：${data.error}`,
        });
        if (activeConvIdForStream.value) {
          updateConversationStatus(activeConvIdForStream.value, 'failed');
        }
      }
      clearEventSource();
    });

    es.addEventListener('completed', (e: any) => {
      isStreamFinished.value = true;
      const data = JSON.parse(e.data);
      if (streamCallbacks.value.onCompleted) {
        streamCallbacks.value.onCompleted(data);
      }
      if (activeConvIdForStream.value && activeAssistantIdxForStream.value >= 0) {
        const md = data.report_markdown || '';
        let content = '';
        if (md) {
          try {
            content = sanitizeHtml(marked.parse(md) as string);
          } catch {
            content = md.replace(/\n/g, '<br>');
          }
        }

        const stageStats: ChatMessage['stageStats'] = [];
        if (data.collected_count !== undefined) {
          stageStats.push({ label: '搜索信息', before: data.collected_count, icon: '🔍' });
        }
        if (data.cleaned_count !== undefined) {
          stageStats.push({ label: '整理数据', before: data.collected_count, after: data.cleaned_count, icon: '🧹' });
        }
        if (data.insight_count !== undefined) {
          stageStats.push({ label: '分析洞察', before: data.insight_count, icon: '🧠' });
        }
        stageStats.push({ label: '生成报告', before: 1, icon: '📝' });

        updateMessage(activeConvIdForStream.value, activeAssistantIdxForStream.value, {
          content,
          reportMarkdown: md,
          chartOptions: data.chart_configs || [],
          stageHint: '',
          stageStats,
          degraded: !!(data.result && data.result.degraded),
        });
        if (activeConvIdForStream.value) {
          updateConversationStatus(activeConvIdForStream.value, 'completed');
        }
      }
      clearEventSource();
    });

    es.addEventListener('error', (e: any) => {
      // Phase 7: 区分服务端命名 error 事件 vs 浏览器内部 error
      // - e.data 有值 → 服务端显式发了 `event: error\ndata: {...}`,应当展示给用户
      // - e.data 为空 → EventSource 自身的连接抖动(自动重连中),不应立即报错
      //   这种情况让 onerror 处理最终状态,这里只记日志
      if (!e.data) {
        console.warn('[SSE] Browser-internal error (likely auto-reconnect in progress)');
        return;
      }
      isStreamFinished.value = true;
      let parsedData: any = null;
      try {
        parsedData = JSON.parse(e.data);
      } catch {
        // 服务端发了非 JSON 的 error 命名事件
        parsedData = { error: `服务流异常: ${e.data}` };
      }

      if (streamCallbacks.value.onError) {
        streamCallbacks.value.onError(parsedData);
      }

      if (activeConvIdForStream.value && activeAssistantIdxForStream.value >= 0 && parsedData.partial_results) {
        const pr = parsedData.partial_results;
        const partialStats: ChatMessage['partialStats'] = [];
        if (pr.collected_count !== undefined) {
          partialStats.push({ label: '数据采集', count: `收集了 ${pr.collected_count} 条资讯`, icon: '🔍' });
        }
        if (pr.cleaned_count !== undefined) {
          partialStats.push({ label: '数据清洗', count: `保留了 ${pr.cleaned_count} 条有效数据`, icon: '🧹' });
        }
        if (pr.insight_count !== undefined) {
          partialStats.push({ label: 'AI分析', count: `生成了 ${pr.insight_count} 条洞察`, icon: '🧠' });
        }
        updateMessage(activeConvIdForStream.value, activeAssistantIdxForStream.value, {
          stageHint: '',
          partialStats,
        });
        if (activeConvIdForStream.value) {
          updateConversationStatus(activeConvIdForStream.value, 'failed');
        }
      }

      clearEventSource();
    });

    // 浏览器内部 error 事件的兜底:延迟判定是否真的连不上
    // EventSource 自动重连有节奏(~3s),CLOSED 状态才算"彻底断开"
    es.onerror = () => {
      if (runningWorkflowId.value && !isStreamFinished.value) {
        const es = eventSource.value;
        const readyState = es?.readyState;
        // 0=CONNECTING 1=OPEN 2=CLOSED
        // OPEN/CONNECTING 状态下 onerror 触发 = 瞬态抖动,EventSource 正在自动重连,静默
        // CLOSED 状态下 = EventSource 已放弃,才是真断开
        if (readyState === 2 /* CLOSED */) {
          if (streamCallbacks.value.onError) {
            streamCallbacks.value.onError({ error: 'SSE 连接已断开(已停止重连)' });
          }
          clearEventSource();
        } else {
          console.warn('[SSE] onerror fired, readyState=', readyState, ', waiting for auto-reconnect');
        }
      }
    };
  };

  const startWorkflowStream = (convId: string, assistantIdx: number, workflowId: string, callbacks: StreamCallbacks) => {
    clearEventSource();
    setupStreamListeners(convId, assistantIdx, callbacks);
    const streamUrl = workflowApi.getStreamUrl(workflowId);
    runningWorkflowId.value = workflowId;
    const es = new EventSource(streamUrl);
    eventSource.value = es;
    attachEventSourceListeners(es);
  };

  // Phase 2: 单独启动 collecting 阶段流(confirm 重试用)
  const startCollectingStream = (convId: string, assistantIdx: number, workflowId: string, callbacks: StreamCallbacks) => {
    clearEventSource();
    setupStreamListeners(convId, assistantIdx, callbacks);
    const streamUrl = workflowApi.getCollectingStreamUrl(workflowId);
    runningWorkflowId.value = workflowId;
    const es = new EventSource(streamUrl);
    eventSource.value = es;
    attachEventSourceListeners(es);
  };

  // Spec 2: 通用 stage 启动方法（替代 startCollectingStream，覆盖 4 阶段）
  // stage ∈ 'collecting' | 'cleaning' | 'analyzing' | 'reporting'
  const startStageStream = (convId: string, assistantIdx: number, workflowId: string, stage: StageName, callbacks: StreamCallbacks) => {
    clearEventSource();
    setupStreamListeners(convId, assistantIdx, callbacks);
    const streamUrl = workflowApi.getStreamUrlForStage(workflowId, stage);
    runningWorkflowId.value = workflowId;
    const es = new EventSource(streamUrl);
    eventSource.value = es;
    attachEventSourceListeners(es);
  };

  // Spec 2: 跳过模式控制
  const setSkipRemaining = (workflowId: string, on: boolean) => {
    if (on) {
      skipRemainingForWorkflow.value.add(workflowId);
    } else {
      skipRemainingForWorkflow.value.delete(workflowId);
    }
    // 触发响应式更新
    skipRemainingForWorkflow.value = new Set(skipRemainingForWorkflow.value);
  };

  const setUserPreference = <K extends keyof typeof userPreferences.value>(
    key: K,
    value: typeof userPreferences.value[K]
  ) => {
    userPreferences.value[key] = value;
    // 持久化
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify(userPreferences.value));
    } catch {
      // ignore quota errors
    }
  };

  // Spec 2: 决定是否自动 skip 当前 stage
  const shouldAutoSkip = (workflowId: string | null): boolean => {
    if (userPreferences.value.skipAllConfirmations) return true;
    if (workflowId && skipRemainingForWorkflow.value.has(workflowId)) return true;
    return false;
  };

  // Spec 2: 弹窗打开后，清除"本次跳过"标记（避免影响其他工作流）
  const clearSkipRemaining = (workflowId: string) => {
    skipRemainingForWorkflow.value.delete(workflowId);
    skipRemainingForWorkflow.value = new Set(skipRemainingForWorkflow.value);
  };

  // Phase 2: 显示/隐藏阶段确认弹窗
  const showConfirmDialog = (ctx: ConfirmContext) => {
    confirmContext.value = ctx;
    confirmDialogVisible.value = true;
  };

  const hideConfirmDialog = () => {
    confirmDialogVisible.value = false;
    confirmContext.value = null;
    confirmSubmitting.value = false;
  };

  // Phase 2: 调用后端 /confirm 端点
  // decision='accept' → 后端返回 next_stage='cleaning' + sse_url
  // decision='reject' → 后端返回 next_stage='collecting' + sse_url
  // 根据 next_stage 决定是启动完整流(走 cleaning→analyzing→reporting)还是只跑 collecting
  const confirmStage = async (
    workflowId: string,
    body: StageConfirmRequest
  ): Promise<StageConfirmResponse> => {
    confirmSubmitting.value = true;
    try {
      const res = await workflowApi.confirmStage(workflowId, body);
      const data = (res.data || res) as unknown as StageConfirmResponse;
      hideConfirmDialog();
      return data;
    } catch (e: any) {
      confirmSubmitting.value = false;
      throw e;
    }
  };

  const clearEventSource = () => {
    if (eventSource.value) {
      eventSource.value.close();
      eventSource.value = null;
    }
    runningWorkflowId.value = null;
    activeConvIdForStream.value = null;
    activeAssistantIdxForStream.value = -1;
    streamCallbacks.value = {};
  };

  const stopWorkflow = () => {
    clearEventSource();
    if (activeConversation.value) {
      updateConversationStatus(activeConversation.value.id, 'completed');
    }
  };

  const loadHistoryFromServer = async () => {
    try {
      const res = await workflowApi.getHistory();
      if (res.data && Array.isArray(res.data)) {
        const serverConvs: Conversation[] = res.data.map((item: any) => {
          const messages: ChatMessage[] = [];
          messages.push({ role: 'user', content: item.topic });

          if (item.result && item.result.report_markdown) {
            const md = item.result.report_markdown;
            let content = md;
            try {
              content = sanitizeHtml(marked.parse(md) as string);
            } catch {
              content = md.replace(/\n/g, '<br>');
            }
            messages.push({
              role: 'assistant',
              content,
              reportMarkdown: md,
              chartOptions: item.result.chart_configs || [],
            });
          }

          return {
            id: `server_${item.workflow_id}`,
            topic: item.topic,
            messages,
            status: item.status || 'completed',
            createdAt: Date.now(),
            updatedAt: Date.now(),
          };
        });

        const existingIds = new Set(conversations.value.map(c => c.id));
        const newConvs = serverConvs.filter((c: Conversation) => !existingIds.has(c.id));
        if (newConvs.length > 0) {
          conversations.value = [...newConvs, ...conversations.value];
          saveConversations(conversations.value);
        }
      }
    } catch (e) {
      console.error('Failed to load history from server:', e);
    }
  };

  const isWorkflowRunning = computed(() => !!runningWorkflowId.value);

  return {
    conversations,
    activeConversationId,
    activeConversation,
    eventSource,
    runningWorkflowId,
    isWorkflowRunning,
    // Phase 2: 阶段确认弹窗
    confirmContext,
    confirmDialogVisible,
    confirmSubmitting,
    setActiveConversation,
    createConversation,
    addMessage,
    updateMessage,
    updateConversationStatus,
    deleteConversation,
    clearAllConversations,
    resetActiveConversation,
    startWorkflowStream,
    startCollectingStream,    // Phase 2 (kept for backward compat)
    startStageStream,         // Spec 2: 通用 stage 启动
    showConfirmDialog,        // Phase 2
    hideConfirmDialog,        // Phase 2
    confirmStage,             // Phase 2
    // Spec 2: 跳过模式
    skipRemainingForWorkflow,
    userPreferences,
    setSkipRemaining,
    setUserPreference,
    shouldAutoSkip,
    clearSkipRemaining,
    clearEventSource,
    stopWorkflow,
    loadHistoryFromServer,
  };
});
