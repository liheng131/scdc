import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { workflowApi } from '../api';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { ElMessage } from 'element-plus';

const sanitizeHtml = (html: string): string => {
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'br', 'strong', 'em', 'u', 's', 'a', 'ul', 'ol', 'li', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'blockquote', 'code', 'pre', 'hr', 'img', 'sup', 'sub'],
    ALLOWED_ATTR: ['href', 'target', 'rel', 'src', 'alt', 'title', 'class'],
  });
};

/** 用户消息中已发送的附件(展示在用户消息 bubble 内) */
export interface SentAttachment {
  attachment_id: string;
  filename: string;
  file_size: number;
  file_type: string;
}

/** 四阶段工作流各阶段的详细数据 */
export interface StageDetailData {
  summary: Record<string, any>;
  detail: Record<string, any>;
}

interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  stageHint?: string;
  chartOptions?: any[];
  reportMarkdown?: string;
  stageStats?: { label: string; before: number; after?: number; icon: string }[];
  degraded?: boolean;
  partialStats?: { label: string; count: string; icon: string }[];
  /** 仅 user 消息:已发送的附件列表,用于在消息 bubble 内渲染附件卡片 */
  attachments?: SentAttachment[];
  /** assistant 消息被用户手动停止时标记为 true */
  terminated?: boolean;
  /** 四阶段工作流各阶段的详细数据（key 为阶段名如 collecting/cleaning/analyzing/reporting） */
  stageDetails?: Record<string, StageDetailData>;
  /** 当前正在处理的阶段（用于进度条高亮） */
  currentStage?: string;
  /** 各阶段状态（pending/active/completed） */
  stageStatuses?: Record<string, 'pending' | 'active' | 'completed'>;
  /** 是否为直答模式（直答不展示进度条） */
  isDirectResponse?: boolean;
}

interface Conversation {
  id: string;
  topic: string;
  messages: ChatMessage[];
  status: 'idle' | 'running' | 'completed' | 'failed';
  createdAt: number;
  updatedAt: number;
  // 历史追问聚合 spec: 本地 conv 创建后第一次拿到服务端 workflow_id 时回填,
  // 追问时作为 parent_workflow_id 传给后端,让追问工作流与父工作流在 DB 中建立关联
  serverWorkflowId?: string;
}

interface StreamCallbacks {
  onStageStart?: (data: any) => void;
  onStageComplete?: (data: any) => void;
  onStageError?: (data: any) => void;
  onCompleted?: (data: any) => void;
  onError?: (data: any) => void;
}



// 自动清理策略:已完成/失败的会话超过该天数后自动归档(从列表移除,本地缓存同步清理)
const ARCHIVE_DAYS = 30;
const ARCHIVE_MS = ARCHIVE_DAYS * 24 * 60 * 60 * 1000;

const STORAGE_KEY = 'scdc_workflow_conversations';
const ACTIVE_KEY = 'scdc_workflow_active_id';

// SSE 超时：5 分钟无事件则视为超时
const SSE_TIMEOUT_MS = 5 * 60 * 1000;

// 每个 conversation 的 SSE 超时定时器 ID
const sseTimeoutTimers = new Map<string, ReturnType<typeof setTimeout>>();

const loadConversations = (): Conversation[] => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
};

const MAX_LOCAL_STORAGE_SIZE = 4 * 1024 * 1024; // 4MB

const saveConversations = (conversations: Conversation[]) => {
  // 轻量化存储: 不存 reportMarkdown 和 chartOptions
  // 这些字段体积大(几百KB到几MB),且服务端有完整备份,不需要在浏览器重复存
  const sanitized = conversations.map(c => ({
    ...c,
    messages: c.messages.map(m => ({
      role: m.role,
      content: m.content,
      stageHint: m.stageHint,
    })),
  }));

  // 基于大小的自动清理: 超过 4MB 时从末尾移除最旧的已完成/失败对话
  let json = JSON.stringify(sanitized);
  if (json.length > MAX_LOCAL_STORAGE_SIZE && conversations.length > 1) {
    const mutConv = [...conversations];
    let lastIdx = mutConv.length - 1;

    while (json.length > MAX_LOCAL_STORAGE_SIZE && lastIdx > 0) {
      // 优先清理已完成的
      if (mutConv[lastIdx].status === 'completed' || mutConv[lastIdx].status === 'failed') {
        mutConv.pop();
        json = JSON.stringify(mutConv.map(c => ({
          ...c,
          messages: c.messages.map(m => ({
            role: m.role,
            content: m.content,
            stageHint: m.stageHint,
          })),
        })));
      } else {
        // 没有可清理的已完成对话,清理最旧的
        mutConv.splice(lastIdx, 1);
        json = JSON.stringify(mutConv.map(c => ({
          ...c,
          messages: c.messages.map(m => ({
            role: m.role,
            content: m.content,
            stageHint: m.stageHint,
          })),
        })));
      }
      lastIdx = mutConv.length - 1;
    }

    // 同步更新 conversations ref,确保 UI 和存储一致
    const originalCount = conversations.length;
    conversations.splice(0, conversations.length, ...mutConv);
    const removed = originalCount - mutConv.length;
    if (removed > 0) {
      console.info(`[saveConversations] 已自动清理 ${removed} 条最旧对话以释放 localStorage 空间`);
    }
  }

  try {
    localStorage.setItem(STORAGE_KEY, json);
  } catch (e) {
    // localStorage 容量超限 (QuotaExceededError) 时的优雅降级:
    // 保留内存状态,不阻塞用户操作;记录日志便于排查
    console.warn('[saveConversations] localStorage quota exceeded, keeping in-memory state only', e);
  }
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
  // 取消标志：用户在 API 返回前点击停止时设为 true，.then() 回调中检查
  const streamCancelled = ref(false);

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

  // 设置对话为运行状态（确保响应式更新）
  const setConversationRunning = (convId: string) => {
    const conv = conversations.value.find(c => c.id === convId);
    if (conv) {
      conv.status = 'running';
      conv.updatedAt = Date.now();
      saveConversations(conversations.value);
    }
  };

  // 添加用户和助手初始消息（首次提问时使用，确保响应式）
  const initConversationMessages = (convId: string, topic: string, attachments?: SentAttachment[]) => {
    const conv = conversations.value.find(c => c.id === convId);
    if (conv) {
      // 使用 Vue 可追踪的方式添加消息
      const userMsg: ChatMessage = { role: 'user', content: topic };
      if (attachments && attachments.length > 0) {
        userMsg.attachments = attachments;
      }
      conv.messages = [
        userMsg,
        { role: 'assistant', content: '', reportMarkdown: '', chartOptions: [] },
      ];
      conv.status = 'running';
      conv.updatedAt = Date.now();
      saveConversations(conversations.value);
    }
  };

  // 回滚对话消息（首次提问失败时使用）
  const rollbackConversationMessages = (convId: string) => {
    const conv = conversations.value.find(c => c.id === convId);
    if (conv) {
      conv.messages = [];
      conv.status = 'idle';
      conv.updatedAt = Date.now();
      saveConversations(conversations.value);
    }
  };

  // 自动清理: 移除已超过归档期的已完成/失败会话
  // - running/idle 永不过期(可能用户正在继续)
  // - completed/failed 超过 ARCHIVE_DAYS 天的从列表移除
  // - 不会删除 activeConversation (用户当前正在看的不能悄悄消失)
  const autoArchiveOldConversations = (): number => {
    if (conversations.value.length === 0) return 0;
    const now = Date.now();
    const before = conversations.value.length;
    const activeId = activeConversationId.value;
    conversations.value = conversations.value.filter((c) => {
      if (c.id === activeId) return true; // 保护当前激活会话
      if (c.status === 'running' || c.status === 'idle') return true; // 进行中永不过期
      const updatedAt = c.updatedAt || c.createdAt || 0;
      return now - updatedAt < ARCHIVE_MS;
    });
    const removed = before - conversations.value.length;
    if (removed > 0) {
      saveConversations(conversations.value);
      console.info(`[autoArchive] 已归档 ${removed} 条超过 ${ARCHIVE_DAYS} 天的历史会话`);
    }
    return removed;
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

  const updateConversationStatus = async (convId: string, status: Conversation['status']) => {
    const conv = conversations.value.find(c => c.id === convId);
    if (conv) {
      conv.status = status;
      conv.updatedAt = Date.now();
      saveConversations(conversations.value);
    }
    // 同步状态到服务端
    let workflowId: string | null = null;
    if (convId.startsWith('server_')) {
      workflowId = convId.slice(7);
    } else if (runningWorkflowId.value) {
      workflowId = runningWorkflowId.value;
    }
    if (workflowId) {
      try {
        await workflowApi.updateWorkflowStatus(workflowId, status);
      } catch (e) {
        console.warn('[updateConversationStatus] Failed to sync status to server:', e);
      }
    }
  };

  const deleteConversation = async (id: string) => {
    // server_xxx 格式的 id 表示从服务端加载,需要同步删除服务端记录
    // 否则 onMounted → loadHistoryFromServer 会把已删的记录从服务端重新拉回
    if (id.startsWith('server_')) {
      const workflowId = id.slice(7);
      try {
        await workflowApi.deleteWorkflow(workflowId);
      } catch (e) {
        console.warn('[deleteConversation] Failed to delete from server:', e);
        // 服务端删除失败时仍然继续清理本地,避免阻塞用户操作
      }
    }
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
  const isDirectResponseFinished = ref(false);
  let lastDirectResponseContentLength = 0;

  const setupStreamListeners = (convId: string, assistantIdx: number, callbacks: StreamCallbacks) => {
    activeConvIdForStream.value = convId;
    activeAssistantIdxForStream.value = assistantIdx;
    streamCallbacks.value = callbacks;
    isStreamFinished.value = false;
    isDirectResponseFinished.value = false;
    lastDirectResponseContentLength = 0;
  };

  const startTimeout = (convId: string) => {
    clearTimeout(sseTimeoutTimers.get(convId));
    const timer = setTimeout(() => {
      sseTimeoutTimers.delete(convId);
      clearEventSource();
      updateConversationStatus(convId, 'failed');
      ElMessage.error('分析超时，请重试');
    }, SSE_TIMEOUT_MS);
    sseTimeoutTimers.set(convId, timer);
  };

  const resetTimeout = (convId: string) => {
    if (sseTimeoutTimers.has(convId)) {
      startTimeout(convId);
    }
  };

  const attachEventSourceListeners = (es: EventSource, convId: string) => {
    // 四阶段定义
    const WORKFLOW_STAGES = ['collecting', 'cleaning', 'analyzing', 'reporting'];

    es.addEventListener('stage_start', (e: any) => {
      resetTimeout(convId);
      const data = JSON.parse(e.data);
      if (streamCallbacks.value.onStageStart) {
        streamCallbacks.value.onStageStart(data);
      }
      if (activeConvIdForStream.value && activeAssistantIdxForStream.value >= 0) {
        // 更新当前阶段为 active，之前阶段标记为 completed
        const conv = conversations.value.find(c => c.id === activeConvIdForStream.value);
        if (conv && conv.messages[activeAssistantIdxForStream.value]) {
          const msg = conv.messages[activeAssistantIdxForStream.value];
          const statuses = { ...(msg.stageStatuses || {}) };
          // 将当前阶段设为 active
          statuses[data.stage] = 'active';
          // 将之前的阶段设为 completed
          const stageIdx = WORKFLOW_STAGES.indexOf(data.stage);
          for (let i = 0; i < stageIdx; i++) {
            if (!statuses[WORKFLOW_STAGES[i]] || statuses[WORKFLOW_STAGES[i]] === 'pending') {
              statuses[WORKFLOW_STAGES[i]] = 'completed';
            }
          }
          updateMessage(activeConvIdForStream.value, activeAssistantIdxForStream.value, {
            stageHint: `${data.icon} 正在${data.label}...`,
            currentStage: data.stage,
            stageStatuses: statuses,
          });
        }
      }
    });

    es.addEventListener('stage_complete', (e: any) => {
      resetTimeout(convId);
      const data = JSON.parse(e.data);
      if (streamCallbacks.value.onStageComplete) {
        streamCallbacks.value.onStageComplete(data);
      }
      // 存储阶段详细数据并更新状态
      if (activeConvIdForStream.value && activeAssistantIdxForStream.value >= 0) {
        const conv = conversations.value.find(c => c.id === activeConvIdForStream.value);
        if (conv && conv.messages[activeAssistantIdxForStream.value]) {
          const msg = conv.messages[activeAssistantIdxForStream.value];
          const details = { ...(msg.stageDetails || {}) };
          const statuses = { ...(msg.stageStatuses || {}) };
          // 存储该阶段的详细数据
          if (data.summary || data.detail) {
            details[data.stage] = {
              summary: data.summary || {},
              detail: data.detail || {},
            };
          }
          // 将该阶段标记为 completed
          statuses[data.stage] = 'completed';
          updateMessage(activeConvIdForStream.value, activeAssistantIdxForStream.value, {
            stageDetails: details,
            stageStatuses: statuses,
          });
        }
      }
    });

    es.addEventListener('direct_response', (e: any) => {
      resetTimeout(convId);
      // Guard: 如果 direct_response_done 已经触发，忽略后续 direct_response 事件
      if (isDirectResponseFinished.value) return;

      const data = JSON.parse(e.data);
      if (activeConvIdForStream.value && activeAssistantIdxForStream.value >= 0) {
        const conv = conversations.value.find(c => c.id === activeConvIdForStream.value);
        if (conv && conv.messages[activeAssistantIdxForStream.value]) {
          const currentContent = conv.messages[activeAssistantIdxForStream.value].content || '';
          // Guard: 防止 SSE 重连导致相同 chunk 被重复追加
          // 使用已接收内容长度作为去重依据：只追加比上次更长的新内容
          const newContent = data.content || '';
          if (newContent.length > 0) {
            updateMessage(activeConvIdForStream.value, activeAssistantIdxForStream.value, {
              content: currentContent + newContent,
              stageHint: '💬 正在回复...',
              isDirectResponse: true,
            });
            lastDirectResponseContentLength = currentContent.length + newContent.length;
          }
        }
      }
    });

    es.addEventListener('direct_response_done', (e: any) => {
      resetTimeout(convId);
      // Guard: 防止 SSE 重连导致 direct_response_done 被重复处理
      if (isDirectResponseFinished.value) return;
      isDirectResponseFinished.value = true;
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
      resetTimeout(convId);
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
      resetTimeout(convId);
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
        resetTimeout(convId);
        console.warn('[SSE] Browser-internal error (likely auto-reconnect in progress)');
        return;
      }
      resetTimeout(convId);
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
      resetTimeout(convId);
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
    streamCancelled.value = false;
    setupStreamListeners(convId, assistantIdx, callbacks);
    const streamUrl = workflowApi.getStreamUrl(workflowId);
    runningWorkflowId.value = workflowId;
    const es = new EventSource(streamUrl);
    eventSource.value = es;
    startTimeout(convId);
    attachEventSourceListeners(es, convId);
  };

  const clearEventSource = () => {
    // Clear timeout timer for current streaming conversation
    if (activeConvIdForStream.value) {
      clearTimeout(sseTimeoutTimers.get(activeConvIdForStream.value));
      sseTimeoutTimers.delete(activeConvIdForStream.value);
    }
    if (eventSource.value) {
      eventSource.value.close();
      eventSource.value = null;
    }
    runningWorkflowId.value = null;
    activeConvIdForStream.value = null;
    activeAssistantIdxForStream.value = -1;
    streamCallbacks.value = {};
  };

  const stopWorkflow = async () => {
    // Set cancel flag immediately so that pending .then() callbacks won't start the stream
    streamCancelled.value = true;
    // Call backend stop API to actually stop the workflow processing
    // Skip if runningWorkflowId is a pending placeholder (API hasn't returned yet)
    if (runningWorkflowId.value && !runningWorkflowId.value.startsWith('pending_')) {
      try {
        await workflowApi.stopWorkflow(runningWorkflowId.value);
      } catch (e) {
        console.warn('[stopWorkflow] Failed to call backend stop API:', e);
      }
    }
    clearEventSource();
    // 标记当前 assistant 消息为已终止
    if (activeAssistantIdxForStream.value >= 0 && activeConvIdForStream.value) {
      updateMessage(activeConvIdForStream.value, activeAssistantIdxForStream.value, {
        terminated: true,
        stageHint: '',
      });
    }
    if (activeConversation.value) {
      updateConversationStatus(activeConversation.value.id, 'failed');
    }
  };

  const loadHistoryFromServer = async () => {
    try {
      const res = await workflowApi.getHistory();
      if (res.data && Array.isArray(res.data)) {
        // 仅同步已完成/失败的工作流,避免把 running/idle 的脏数据
        // 注入到历史列表(这些通常是异常中断的会话,刷新后会"幽灵复活")
        const finishedItems = res.data.filter((item: any) => {
          const s = item.status;
          return s === 'completed' || s === 'failed';
        });

        // 历史追问聚合 spec: 单个 workflow item 渲染为 (user, assistant) 消息对
        const renderItemMessages = (item: any): ChatMessage[] => {
          const msgs: ChatMessage[] = [];
          msgs.push({ role: 'user', content: item.topic });
          if (item.result && item.result.report_markdown) {
            const md = item.result.report_markdown;
            let content = md;
            try {
              content = sanitizeHtml(marked.parse(md) as string);
            } catch {
              content = md.replace(/\n/g, '<br>');
            }
            // 历史数据中提取 stageDetails(从 item.stages 重建),供弹窗显示完整维度/洞察
            // 后端已在新工作流完成时把 {summary, detail} 持久化到 state.stages[item.stage]
            const stageDetails: Record<string, StageDetailData> = {};
            if (item.stages && typeof item.stages === 'object') {
              for (const [stage, raw] of Object.entries(item.stages)) {
                const r = raw as any;
                if (r && (r.summary || r.detail)) {
                  stageDetails[stage] = {
                    summary: r.summary || {},
                    detail: r.detail || {},
                  };
                }
              }
            }
            msgs.push({
              role: 'assistant',
              content,
              reportMarkdown: md,
              chartOptions: item.result.chart_configs || [],
              // 把后端持久化的 stageDetails 挂到 assistant 消息上,
              // 这样 handleStageDetail 才能从 messages 中读到 stages 详情
              ...(Object.keys(stageDetails).length > 0 ? { stageDetails } : {}),
            });
          } else if (item.current_stage === 'direct_response' && item.status === 'completed') {
            // 兜底:旧直答历史(后端修复前生成)的 AI 回复内容未持久化,
            // 显示友好提示,让用户重新发送问题
            msgs.push({
              role: 'assistant',
              content: '<i>该直答对话的 AI 回复内容未持久化（旧版本未保存），请重新发送问题获取回复。</i>',
            });
          }
          return msgs;
        };

        const serverConvs: Conversation[] = [];
        for (const top of finishedItems) {
          // 顶层渲染 + 内嵌 children 追加
          const messages: ChatMessage[] = renderItemMessages(top);
          const children = Array.isArray(top.children) ? top.children : [];
          for (const child of children) {
            // 追问子项同样需要过滤 completed/failed
            if (child.status !== 'completed' && child.status !== 'failed') continue;
            messages.push(...renderItemMessages(child));
          }
          serverConvs.push({
            id: `server_${top.workflow_id}`,
            topic: top.topic,
            messages,
            status: top.status || 'completed',
            createdAt: Date.now(),
            updatedAt: Date.now(),
            // 服务端加载的对话,服务端 workflow_id 与 id 后缀一致,显式回填便于后续追问
            serverWorkflowId: top.workflow_id,
          });
        }

        const existingIds = new Set(conversations.value.map(c => c.id));
        const newConvs = serverConvs.filter((c: Conversation) => !existingIds.has(c.id));
        if (newConvs.length > 0) {
          conversations.value = [...newConvs, ...conversations.value];
          saveConversations(conversations.value);
        }
      }
      // 同步后清理过老会话(本地 + 服务端均清理)
      autoArchiveOldConversations();
    } catch (e) {
      console.error('Failed to load history from server:', e);
    }
  };

  const isWorkflowRunning = computed(() => !!runningWorkflowId.value);

  // 启动时立即清理一次过老会话(同步执行,无感知)
  autoArchiveOldConversations();

  return {
    conversations,
    activeConversationId,
    activeConversation,
    eventSource,
    runningWorkflowId,
    streamCancelled,
    isWorkflowRunning,
    setActiveConversation,
    createConversation,
    addMessage,
    setConversationRunning,
    initConversationMessages,
    rollbackConversationMessages,
    updateMessage,
    updateConversationStatus,
    deleteConversation,
    clearAllConversations,
    resetActiveConversation,
    startWorkflowStream,
    clearEventSource,
    stopWorkflow,
    loadHistoryFromServer,
    autoArchiveOldConversations,
  };
});
