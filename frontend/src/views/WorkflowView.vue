<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  Promotion,        // 发送(向上箭头)
  VideoPause,       // 暂停(运行中)
  Paperclip,        // 附件(回形针)
  Download, CopyDocument, Delete, Plus, Close, Document,
} from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import * as echarts from 'echarts';
import { workflowApi, reportsApi } from '../api';
import { parsersApi } from '../api/services/parsers';
import { useWorkflowStore } from '../stores/workflow';
import { useAuthStore } from '@/stores/auth';
import StageProgressBar from '../components/StageProgressBar.vue';
import StageDetailDialog from '../components/StageDetailDialog.vue';

const auth = useAuthStore();
const { t } = useI18n();

// 附件上传相关常量
const ACCEPTED_EXTENSIONS = '.pdf,.doc,.docx,.md,.markdown,.txt,.png,.jpg,.jpeg,.bmp,.tiff,.tif,.xls,.xlsx';
const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20MB

interface PendingAttachment {
  key: string; // 本地 v-for key
  file: File;
  status: 'pending' | 'uploading' | 'done' | 'error';
  progress: number; // 0-100,-1 表示失败
  attachment_id?: string;
  error?: string;
}

/** 消息中已发送的附件(展示在用户消息 bubble 内) */
interface SentAttachment {
  attachment_id: string;
  filename: string;
  file_size: number;
  file_type: string;
}

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

// 四阶段进度条相关
const WORKFLOW_STAGES = [
  { key: 'collecting', label: '数据采集', icon: '' },
  { key: 'cleaning', label: '数据清洗', icon: '🧹' },
  { key: 'analyzing', label: '数据分析', icon: '📊' },
  { key: 'reporting', label: '报告生成', icon: '📝' },
];

// 阶段详情弹窗
const detailDialogVisible = ref(false);
const detailStageKey = ref('');
const detailStageName = ref('');
const detailStageData = ref<any>(null);

const handleStageDetail = (stageKey: string) => {
  const lastMsg = messages.value[messages.value.length - 1];
  if (!lastMsg?.stageDetails?.[stageKey]) return;
  const stageDef = WORKFLOW_STAGES.find(s => s.key === stageKey);
  detailStageKey.value = stageKey;
  detailStageName.value = stageDef?.label || stageKey;
  // 传递完整的 { summary, detail } 对象，summary 含 duration_seconds，detail 含具体内容
  detailStageData.value = lastMsg.stageDetails[stageKey];
  detailDialogVisible.value = true;
};

// 从 stageDetails 构建 hover tooltip 摘要
const stageSummaries = computed(() => {
  const lastMsg = messages.value[messages.value.length - 1];
  if (!lastMsg?.stageDetails) return {};
  const summaries: Record<string, { text: string }> = {};
  const details = lastMsg.stageDetails;
  if (details.collecting?.summary) {
    const s = details.collecting.summary;
    summaries.collecting = { text: `耗时 ${s.duration_seconds || 0} 秒 | 搜索 ${s.keywords_count || 0} 个关键词，共 ${s.total_search_results || 0} 条结果，采集 ${s.item_count || 0} 条` };
  }
  if (details.cleaning?.summary) {
    const s = details.cleaning.summary;
    summaries.cleaning = { text: `耗时 ${s.duration_seconds || 0} 秒 | 清洗 ${s.total_in || 0} 条数据，保留 ${s.total_out || 0} 条，移除 ${s.removed_count || 0} 条` };
  }
  if (details.analyzing?.summary) {
    const s = details.analyzing.summary;
    summaries.analyzing = { text: `耗时 ${s.duration_seconds || 0} 秒 | RAG 命中 ${s.rag_results_count || 0} 条，分析 ${s.insight_count || 0} 条洞察，覆盖 ${s.dimensions?.length || 0} 个维度` };
  }
  if (details.reporting?.summary) {
    const s = details.reporting.summary;
    summaries.reporting = { text: `耗时 ${s.duration_seconds || 0} 秒 | 报告 ${s.report_length || 0} 字，${s.chart_count || 0} 张图表` };
  }
  return summaries;
});

// 附件上传状态
const pendingAttachments = ref<PendingAttachment[]>([]);
const fileInputRef = ref<HTMLInputElement | null>(null);
const isDragOver = ref(false);

// 格式化文件大小
const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
};

// 触发文件选择
const triggerFileInput = () => {
  fileInputRef.value?.click();
};

// 文件 input change
const onFileInputChange = (e: Event) => {
  const input = e.target as HTMLInputElement;
  if (input.files) {
    addFiles(Array.from(input.files));
    input.value = ''; // 重置,允许选择同一文件
  }
};

// 添加文件到待上传列表
const addFiles = (files: File[]) => {
  for (const file of files) {
    // 验证扩展名
    const ext = '.' + (file.name.split('.').pop() || '').toLowerCase();
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      ElMessage.warning(`不支持的文件格式: ${file.name}`);
      continue;
    }
    // 验证大小
    if (file.size > MAX_FILE_SIZE) {
      ElMessage.warning(`文件过大（>20MB）: ${file.name}`);
      continue;
    }
    pendingAttachments.value.push({
      key: `${Date.now()}_${Math.random().toString(36).slice(2)}`,
      file,
      status: 'pending',
      progress: 0,
    });
  }
};

// 移除待上传附件
const removeAttachment = (key: string) => {
  pendingAttachments.value = pendingAttachments.value.filter(a => a.key !== key);
};

// 拖拽相关
const onDragOver = (e: DragEvent) => {
  e.preventDefault();
  isDragOver.value = true;
};

const onDragLeave = (e: DragEvent) => {
  e.preventDefault();
  isDragOver.value = false;
};

const onDrop = (e: DragEvent) => {
  e.preventDefault();
  isDragOver.value = false;
  if (e.dataTransfer?.files) {
    addFiles(Array.from(e.dataTransfer.files));
  }
};

// 上传所有待上传附件并返回 attachment_ids
const uploadPendingAttachments = async (): Promise<string[]> => {
  if (pendingAttachments.value.length === 0) return [];
  // 进入 uploading 状态
  pendingAttachments.value.forEach(a => {
    a.status = 'uploading';
    a.progress = 0;
  });
  try {
    const files = pendingAttachments.value.map(a => a.file);
    // 串行上传,逐文件回传进度(成熟 AI 平台惯例)
    const res = await parsersApi.batchUpload(files, (filename, percent) => {
      const att = pendingAttachments.value.find(a => a.file.name === filename);
      if (!att) return;
      if (percent < 0) {
        att.status = 'error';
        att.error = 'Upload failed';
      } else {
        att.progress = percent;
        if (percent >= 100) {
          att.status = 'done';
        }
      }
    });
    if (res.data) {
      const successList = res.data.success || [];
      const failedList = res.data.failed || [];

      // 标记每个文件的上传状态
      pendingAttachments.value.forEach((a) => {
        const ok = successList.find(s => s.filename === a.file.name);
        if (ok) {
          a.status = 'done';
          a.attachment_id = ok.attachment_id;
          a.progress = 100;
        } else {
          a.status = 'error';
          a.error = 'Upload failed';
        }
      });

      const attachmentIds = res.data.attachment_ids || [];

      if (failedList.length > 0) {
        ElMessage.warning(`部分文件上传失败: ${failedList.map(f => f.filename).join(', ')}`);
      }
      return attachmentIds;
    }
    return [];
  } catch (e: any) {
    pendingAttachments.value.forEach(a => {
      a.status = 'error';
      a.error = e?.message || 'Upload failed';
    });
    throw e;
  }
};

/** 把已上传好的附件整理为 SentAttachment,准备塞进用户消息 */
const snapshotSentAttachments = (attachmentIds: string[]): SentAttachment[] => {
  return pendingAttachments.value
    .filter(a => a.status === 'done' && a.attachment_id && attachmentIds.includes(a.attachment_id))
    .map(a => ({
      attachment_id: a.attachment_id!,
      filename: a.file.name,
      file_size: a.file.size,
      file_type: (a.file.name.split('.').pop() || '').toLowerCase(),
    }));
};

const messages = computed(() => {
  return workflowStore.activeConversation?.messages || [];
});

const suggestions = [
  '2025年AI芯片市场趋势',
  '新能源汽车产业链竞争格局',
  '全球云计算市场份额分析',
  '中国SaaS行业投资机会',
];

onMounted(async () => {
  // 先验证 token 有效性(若 stale → fetchCurrentUser 内部已 logout,isAuthenticated 变 false)
  // 避免带 stale token 去打 history/list 接口,导致 401 + 工作流异常提示
  if (auth.token) {
    try {
      await auth.fetchCurrentUser();
    } catch {
      // fetchCurrentUser 内部已处理 logout,这里静默
    }
  }
  if (auth.isAuthenticated) {
    workflowStore.loadHistoryFromServer();
  }
});

onUnmounted(() => {
  if (slowHintTimer) {
    clearTimeout(slowHintTimer);
    slowHintTimer = null;
  }
  showSlowHint.value = false;
  pendingAttachments.value = [];
  chartRefs.value.forEach((el) => {
    const instance = echarts.getInstanceByDom(el);
    if (instance) instance.dispose();
  });
});

watch(() => workflowStore.activeConversationId, () => {
  showSidebar.value = false;
  nextTick(() => {
    // 不显式 dispose,让 renderChartsForMessages 在渲染新图表时自动处理
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

const quickAsk = (topic: string) => {
  inputTopic.value = topic;
  sendMessage();
};

const handleStop = async () => {
  await workflowStore.stopWorkflow();
  loading.value = false;
  if (slowHintTimer) {
    clearTimeout(slowHintTimer);
    slowHintTimer = null;
  }
  showSlowHint.value = false;
  currentStageHint.value = null;
};

// 阶段回调 (统一四阶段连续执行,无人工审阅)
const buildStreamCallbacks = (convId: string, assistantIdx: number, isFollowUp: boolean) => {
  return {
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
  };
};

const sendMessage = async () => {
  const topic = inputTopic.value.trim();
  if (!topic || loading.value) return;

  workflowStore.clearEventSource();
  // 重置取消标志，确保新消息能正常启动流
  workflowStore.streamCancelled = false;
  currentStageHint.value = null;
  if (slowHintTimer) {
    clearTimeout(slowHintTimer);
    slowHintTimer = null;
  }
  showSlowHint.value = false;

  // 1) 先上传附件（如有）
  let attachmentIds: string[] = [];
  let sentAttachments: SentAttachment[] = [];
  if (pendingAttachments.value.length > 0) {
    try {
      attachmentIds = await uploadPendingAttachments();
      sentAttachments = snapshotSentAttachments(attachmentIds);
    } catch (e: any) {
      ElMessage.error('附件上传失败，请重试');
      loading.value = false;
      return;
    }
  }

  const activeConv = workflowStore.activeConversation;
  // 3 态分支:
  //   - 活动对话 messages 长度 > 0 → 追问(不强制要求 status === 'completed',
  //     因为失败/运行中断/未关联服务端的对话也可以让用户接着发追问,后端会新建子工作流)
  //   - 活动对话 idle 且空(点过侧边栏一个还没开始过的对话)→ 复用它
  //   - 其他(activeConv=null 或 status==='running')→ 新建对话
  //
  // 新建对话行为(参照智谱/DeepSeek):
  //   - 点"新建对话"只清空 activeConv 回到欢迎屏,不创建侧边栏记录
  //   - 在欢迎屏提问时走 else 分支,此时才真正创建对话记录
  const isFollowUp = !!activeConv && activeConv.messages.length > 0 && activeConv.status !== 'running';
  const isIdleEmpty = !!activeConv && activeConv.messages.length === 0 && activeConv.status === 'idle';

  inputTopic.value = '';
  loading.value = true;
  scrollToBottom();

  if (isFollowUp) {
    // 追问模式：在当前对话中追加消息
    // 历史追问聚合 spec: 解析父工作流 ID 用于建立 DB 父子关联
    //   - activeConv.id 以 'server_' 开头 → 取去掉前缀的部分
    //   - 否则取 activeConv.serverWorkflowId(第一次提问时回填的服务端 ID)
    //   - 都没有(异常状态)→ 退回到新建对话模式
    let parentWorkflowId: string | null = null;
    if (activeConv.id.startsWith('server_')) {
      parentWorkflowId = activeConv.id.slice('server_'.length);
    } else if (activeConv.serverWorkflowId) {
      parentWorkflowId = activeConv.serverWorkflowId;
    }

    if (!parentWorkflowId) {
      // 本地未提交过的对话或异常状态:按 spec 规约回退到新建对话并提问
      ElMessage.warning('该对话尚未与服务端关联,将以新对话形式发送');
      const newConv = workflowStore.createConversation(topic);
      workflowStore.initConversationMessages(newConv.id, topic, sentAttachments);
      loading.value = false;
      return;
    }

    activeConv.messages.push({
      role: 'user',
      content: topic,
      attachments: sentAttachments.length > 0 ? sentAttachments : undefined,
    });
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

    const cbs = buildStreamCallbacks(activeConv.id, assistantIdx, isFollowUp);

    const followUpBody: { message: string; conversation_history: { role: string; content: string }[]; attachment_ids?: string[]; parent_workflow_id: string } = {
      message: topic,
      conversation_history: conversationHistory,
      parent_workflow_id: parentWorkflowId,
    };
    if (attachmentIds.length > 0) {
      followUpBody.attachment_ids = attachmentIds;
    }
    // 提前设置 runningWorkflowId 占位，让停止按钮在 API 返回前就能生效
    const pendingWfId = `pending_${activeConv.id}_${Date.now()}`;
    workflowStore.runningWorkflowId = pendingWfId;
    workflowApi.followUp(followUpBody)
      .then((res) => {
        // 检查是否在 API 返回前用户已点击停止
        if (workflowStore.streamCancelled) {
          loading.value = false;
          workflowStore.runningWorkflowId = null;
          return;
        }
        workflowStore.runningWorkflowId = res.data.workflow_id;
        workflowStore.startWorkflowStream(
          activeConv.id,
          assistantIdx,
          res.data.workflow_id,
          cbs,
        );
        // 追问已启动,清理附件列表
        pendingAttachments.value = [];
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
  } else if (isIdleEmpty) {
    // 复用分支:用户在侧边栏点了一个待开始的空对话
    activeConv.messages.push({
      role: 'user',
      content: topic,
      attachments: sentAttachments.length > 0 ? sentAttachments : undefined,
    });
    activeConv.messages.push({
      role: 'assistant',
      content: '',
      reportMarkdown: '',
      chartOptions: [],
    });
    activeConv.status = 'running';

    const assistantIdx = 1;
    const cbs = buildStreamCallbacks(activeConv.id, assistantIdx, isFollowUp);

  const startBody: { topic: string; max_items?: number; attachment_ids?: string[] } = {
      topic,
      max_items: 10,  // 与后端 WorkflowStartRequest 默认值一致
    };
    if (attachmentIds.length > 0) {
      startBody.attachment_ids = attachmentIds;
    }

    // 提前设置 runningWorkflowId 占位，让停止按钮在 API 返回前就能生效
    const pendingWfId = `pending_${activeConv.id}_${Date.now()}`;
    workflowStore.runningWorkflowId = pendingWfId;
    workflowApi.start(startBody)
      .then((res) => {
        // 检查是否在 API 返回前用户已点击停止
        if (workflowStore.streamCancelled) {
          loading.value = false;
          workflowStore.runningWorkflowId = null;
          return;
        }
        workflowStore.runningWorkflowId = res.data.workflow_id;
        // 历史追问聚合 spec: 回填服务端 workflow_id,后续追问可作为 parent 关联
        activeConv.serverWorkflowId = res.data.workflow_id;
        workflowStore.startWorkflowStream(
          activeConv.id,
          assistantIdx,
          res.data.workflow_id,
          cbs,
        );

        showSlowHint.value = false;
        if (slowHintTimer) clearTimeout(slowHintTimer);
        slowHintTimer = setTimeout(() => {
          showSlowHint.value = true;
        }, 60000);
        // 工作流已启动,清理附件列表
        pendingAttachments.value = [];
      })
      .catch(() => {
        activeConv.messages.pop();
        activeConv.status = 'idle';
        if (slowHintTimer) {
          clearTimeout(slowHintTimer);
          slowHintTimer = null;
        }
        showSlowHint.value = false;
        ElMessage.error('启动分析失败，请检查后端服务');
        loading.value = false;
      });
  } else {
    // 首次分析模式：创建新对话（此时 activeConv=null 或 running/failed）
    // 参照智谱/DeepSeek: 只有用户实际提问时才创建侧边栏记录
    const conv = workflowStore.createConversation(topic);

    // 使用 store 方法确保 Vue 响应式正确追踪
    workflowStore.initConversationMessages(conv.id, topic, sentAttachments);

    const assistantIdx = 1;
    const cbs = buildStreamCallbacks(conv.id, assistantIdx, isFollowUp);

  const startBody: { topic: string; max_items?: number; attachment_ids?: string[] } = {
      topic,
      max_items: 10,  // 与后端 WorkflowStartRequest 默认值一致
    };
    if (attachmentIds.length > 0) {
      startBody.attachment_ids = attachmentIds;
    }

    // 提前设置 runningWorkflowId 占位，让停止按钮在 API 返回前就能生效
    const pendingWfId = `pending_${conv.id}_${Date.now()}`;
    workflowStore.runningWorkflowId = pendingWfId;
    workflowApi.start(startBody)
      .then((res) => {
        // 检查是否在 API 返回前用户已点击停止
        if (workflowStore.streamCancelled) {
          loading.value = false;
          workflowStore.runningWorkflowId = null;
          return;
        }
        workflowStore.runningWorkflowId = res.data.workflow_id;
        // 历史追问聚合 spec: 回填服务端 workflow_id,后续追问可作为 parent 关联
        conv.serverWorkflowId = res.data.workflow_id;
        workflowStore.startWorkflowStream(
          conv.id,
          assistantIdx,
          res.data.workflow_id,
          cbs,
        );

        showSlowHint.value = false;
        if (slowHintTimer) clearTimeout(slowHintTimer);
        slowHintTimer = setTimeout(() => {
          showSlowHint.value = true;
        }, 60000);
        // 工作流已启动,清理附件列表
        pendingAttachments.value = [];
      })
      .catch(() => {
        workflowStore.rollbackConversationMessages(conv.id);
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
  // 参照智谱/DeepSeek: 点击"新建对话"只清空当前状态回到欢迎屏,不创建侧边栏记录。
  // 重复点击无害(activeConv 已经是 null)。
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
    await workflowStore.deleteConversation(id);
    ElMessage.success('已删除');
  } catch {
    // cancelled
  }
};

const handleExportReport = async (markdown: string, fmt: string, template_id?: string, msgIdx?: number) => {
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

  // HTML 导出：fetch iframe 中正在展示的 HTML + 后端内联 CSS 后下载
  if (fmt === 'html' && msgIdx !== undefined) {
    const iframe = document.querySelector(`iframe[data-msg-idx="${msgIdx}"]`) as HTMLIFrameElement | null;
    if (!iframe) {
      ElMessage.error('报告 iframe 未找到，请刷新页面后重试');
      return;
    }
    const src = iframe.getAttribute('src');
    if (!src) {
      ElMessage.error('报告未加载完成');
      return;
    }
    try {
      // 通过后端内联 CSS 后返回
      const token = localStorage.getItem('token') || '';
      const inlineUrl = src.replace('/preview?', '/inline-html?') + '&token=' + token;
      const response = await fetch(inlineUrl);
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const htmlContent = await response.text();
      const blob = new Blob([htmlContent], { type: 'text/html;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report_${Date.now()}.html`;
      a.click();
      URL.revokeObjectURL(url);
      ElMessage.success('HTML 报告已导出');
    } catch (e: any) {
      ElMessage.error('导出失败：' + (e.message || '网络错误'));
    }
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
      // 从对应 assistant 消息的 stageDetails.reporting.detail 中提取图片数据
      const assistantMsg = messages.value
        .slice()
        .reverse()
        .find(m => m.role === 'assistant' && m.reportMarkdown === markdown);
      const reportingDetail = assistantMsg?.stageDetails?.reporting?.detail;
      const chartImages = reportingDetail?.chart_images || [];
      const dimensionIllustrations = reportingDetail?.dimension_illustrations || [];

      const res = await reportsApi.createFromWorkflow({
        task_id: wfId,
        title: workflowStore.activeConversation?.topic || 'Untitled',
        content_markdown: markdown,
        summary: markdown?.substring(0, 200),
        chart_images: chartImages,
        dimension_illustrations: dimensionIllustrations,
      });
      reportId = res.data.id;
      reportIdCache.value[wfId] = reportId;
    } catch {
      ElMessage.error('创建报告失败，请重试');
      return;
    }
  }

  const exportUrl = reportsApi.exportReportUrl(reportId, fmt, template_id, true, selectedTheme.value);
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

// PPT 模板列表（用于导出对话框二级菜单）
interface PptTemplate {
  id: string;
  name: string;
  description: string;
  file: string;
  layouts_count: number;
}
const pptTemplates = ref<PptTemplate[]>([]);
const loadPptTemplates = async () => {
  try {
    const res = await reportsApi.listPptTemplates();
    pptTemplates.value = (res.data?.items || []) as PptTemplate[];
  } catch {
    pptTemplates.value = [];
  }
};
onMounted(() => {
  loadPptTemplates();
});

const handleCopyReport = (markdown: string) => {
  if (!markdown) return;
  navigator.clipboard.writeText(markdown).then(() => {
    ElMessage.success('报告已复制到剪贴板');
  }).catch(() => {
    ElMessage.error('复制失败');
  });
};

// 报告预览相关
const previewReportIds = ref<Record<number, number>>({});
const previewBlobUrls = ref<Record<number, string>>({});

// html-ppt 主题切换器（Phase 1）
// 36 套主题，与后端 HTMLReportGenerator.available_themes 对齐
const HTML_PPT_THEMES = [
  'minimal-white', 'tokyo-night', 'dracula', 'aurora', 'cyberpunk-neon',
  'bauhaus', 'blueprint', 'catppuccin-mocha', 'corporate-clean', 'editorial-serif',
  'glassmorphism', 'gruvbox-dark', 'japanese-minimal', 'magazine-bold', 'memphis-pop',
  'midcentury', 'neo-brutalism', 'news-broadcast', 'nord', 'pitch-deck-vc',
  'rainbow-gradient', 'retro-tv', 'rose-pine', 'sharp-mono', 'soft-pastel',
  'solarized-light', 'sunset-warm', 'swiss-grid', 'terminal-green', 'vaporwave',
  'xiaohongshu-white', 'y2k-chrome', 'academic-paper', 'arctic-cool', 'catppuccin-latte',
  'engineering-whiteprint',
];
// 从 localStorage 读用户上次选的主题
const selectedTheme = ref<string>(localStorage.getItem('html_ppt_theme') || 'minimal-white');
// 记录每个消息的当前主题，用于 force re-render
const themeByMessage = ref<Record<number, string>>({});

function changeTheme(idx: number, theme: string) {
  selectedTheme.value = theme;
  localStorage.setItem('html_ppt_theme', theme);
  themeByMessage.value[idx] = theme;
  // 与 loadPreview 使用相同的 wfId 查找逻辑
  const conv = workflowStore.activeConversation;
  const wfId = conv?.id || conv?.serverWorkflowId || '';
  const reportId = previewReportIds.value[idx]
    || reportIdCache.value[wfId]
    || reportIdCache.value[conv?.serverWorkflowId || '']
    || reportIdCache.value[conv?.id || '']
    || (messages.value[idx] as any)?.reportId;
  if (!reportId) {
    ElMessage.warning('报告未加载，无法切换主题');
    return;
  }
  const token = localStorage.getItem('token') || '';
  const base = import.meta.env.VITE_API_BASE_URL || '';
  const newUrl = `${base}/api/v1/reports/${reportId}/preview?theme=${encodeURIComponent(theme)}&token=${encodeURIComponent(token)}&_t=${Date.now()}`;
  // 强制重建 iframe：先清空删除 DOM 中的旧 iframe，再 nextTick 后创建新 iframe
  delete previewBlobUrls.value[idx];
  nextTick(() => {
    previewBlobUrls.value[idx] = newUrl;
  });
}

async function openPresenterMode(idx: number) {
  const conv = workflowStore.activeConversation;
  const wfId = conv?.id || conv?.serverWorkflowId || '';
  const reportId = previewReportIds.value[idx]
    || reportIdCache.value[wfId]
    || reportIdCache.value[conv?.serverWorkflowId || '']
    || reportIdCache.value[conv?.id || '']
    || (messages.value[idx] as any)?.reportId;
  if (!reportId) {
    ElMessage.warning('报告未加载，无法打开演讲者模式');
    return;
  }
  const token = localStorage.getItem('token') || '';
  const base = import.meta.env.VITE_API_BASE_URL || '';
  const theme = themeByMessage[idx] || selectedTheme.value;
  const url = `${base}/api/v1/reports/${reportId}/preview?theme=${encodeURIComponent(theme)}&token=${encodeURIComponent(token)}`;
  window.open(url, '_blank', 'width=1920,height=1080');
}

/** 加载报告预览（自动调用，无需用户点击） */
const loadPreview = async (msgIndex: number, msg: any) => {
  if (previewBlobUrls.value[msgIndex]) return; // 已加载
  if (!msg.reportMarkdown) return;
  const wfId = workflowStore.activeConversation?.id
    || workflowStore.activeConversation?.serverWorkflowId;
  if (!wfId) return;

  let reportId = msg.reportId || previewReportIds.value[msgIndex];
  if (!reportId) {
    reportId = reportIdCache.value[wfId];
  }
  // 如果已通过 msg.reportId 或缓存获得 reportId，也要更新缓存
  if (reportId) {
    reportIdCache.value[wfId] = reportId;
    previewReportIds.value[msgIndex] = reportId;
  }
  if (!reportId) {
    try {
      const res = await reportsApi.getReports({ task_id: wfId });
      if (res.data && res.data.length > 0) {
        reportId = res.data[0].id;
        reportIdCache.value[wfId] = reportId;
        previewReportIds.value[msgIndex] = reportId;
      }
    } catch { /* ignore */ }
  }
  if (!reportId && msg.reportMarkdown) {
    try {
      const res = await reportsApi.createFromWorkflow({
        task_id: wfId,
        title: workflowStore.activeConversation?.topic || 'Untitled',
        content_markdown: msg.reportMarkdown,
        summary: msg.reportMarkdown.substring(0, 200),
      });
      reportId = res.data.id;
      reportIdCache.value[wfId] = reportId;
      previewReportIds.value[msgIndex] = reportId;
    } catch { return; }
  }
  if (!reportId) return;

  // 使用 token 查询参数直接加载 iframe，避免 blob URL 导致的静态资源加载失败问题
  const token = localStorage.getItem('token') || '';
  const base = import.meta.env.VITE_API_BASE_URL || '';
  const theme = themeByMessage[msgIndex] || selectedTheme.value;
  const directUrl = `${base}/api/v1/reports/${reportId}/preview?theme=${encodeURIComponent(theme)}&token=${encodeURIComponent(token)}`;
  previewBlobUrls.value[msgIndex] = directUrl;
};

// 监听消息变化，自动为报告消息加载预览
watch(
  () => workflowStore.activeConversation?.messages,
  (msgs) => {
    if (!msgs) return;
    // 切换对话时清空旧的预览 URLs（索引会重新从 0 开始）
    const currentKeys = new Set(msgs.map((_: any, i: number) => i));
    for (const key of Object.keys(previewBlobUrls.value)) {
      if (!currentKeys.has(Number(key))) {
        delete previewBlobUrls.value[Number(key)];
        delete previewReportIds.value[Number(key)];
      }
    }
    msgs.forEach((msg: any, idx: number) => {
      if (msg.reportMarkdown && !previewBlobUrls.value[idx]) {
        loadPreview(idx, msg);
      }
    });
  },
  { deep: true, immediate: true }
);

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
              <span class="history-item-time">{{ formatTime(conv.updatedAt) }}</span>
            </div>
          </div>
          <el-button
            text
            size="small"
            :icon="Delete"
            aria-label="删除对话"
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
          <!-- 用户消息行 -->
          <div v-if="msg.role === 'user'" class="message-row user-row">
            <div class="message-avatar user-avatar">
              <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 12C14.21 12 16 10.21 16 8C16 5.79 14.21 4 12 4C9.79 4 8 5.79 8 8C8 10.21 9.79 12 12 12ZM12 14C9.33 14 4 15.34 4 18V20H20V18C20 15.34 14.67 14 12 14Z" fill="white"/>
              </svg>
            </div>
            <div class="message-body user-message-body">
              <div class="message-sender user-sender">
                <span class="sender-name">我</span>
              </div>
              <div v-if="msg.attachments && msg.attachments.length" class="user-attachments">
                <div
                  v-for="att in msg.attachments"
                  :key="att.attachment_id"
                  class="user-attachment-card"
                  :title="att.filename"
                >
                  <div class="att-icon">
                    <el-icon><Document /></el-icon>
                  </div>
                  <div class="att-meta">
                    <div class="att-name">{{ att.filename }}</div>
                    <div class="att-sub">{{ (att.file_type || '').toUpperCase() }} · {{ formatFileSize(att.file_size) }}</div>
                  </div>
                </div>
              </div>
              <div class="message-content user-content">{{ msg.content }}</div>
            </div>
          </div>

          <!-- AI 消息行 -->
          <div v-else class="message-row assistant-row">
            <div class="message-avatar assistant-avatar">
              <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 2C6.48 2 2 6.48 2 12C2 17.52 6.48 22 12 22C17.52 22 22 17.52 22 12C22 6.48 17.52 2 12 2ZM12 6C13.66 6 15 7.34 15 9C15 10.66 13.66 12 12 12C10.34 12 9 10.66 9 9C9 7.34 10.34 6 12 6ZM12 20C9.33 20 7.12 18.29 6.34 16C7.72 14.72 9.78 14 12 14C14.22 14 16.28 14.72 17.66 16C16.88 18.29 14.67 20 12 20Z" fill="white"/>
              </svg>
            </div>
            <div class="message-body">
              <div class="message-sender assistant-sender">
                <span class="sender-name">AI 助手</span>
                <span class="sender-badge">AI</span>
              </div>
              <div v-if="msg.terminated" class="terminated-hint">本次回答已终止</div>
              <!-- 四阶段进度条（仅非直答模式且正在运行或已完成时显示） -->
              <StageProgressBar
                v-if="!msg.isDirectResponse && msg.stageStatuses"
                :stages="WORKFLOW_STAGES"
                :currentStage="msg.currentStage || ''"
                :stageStatuses="msg.stageStatuses"
                :stageSummaries="stageSummaries"
                @detail="handleStageDetail"
              />
              <div v-if="msg.stageHint && !msg.stageStatuses" class="stage-hint-banner">
                <span class="stage-pulse"></span>
                <span>{{ msg.stageHint }}</span>
              </div>
              <div v-if="msg.stageStats && msg.stageStats.length && !previewBlobUrls[idx]" class="stage-stats">
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
              <div v-if="msg.partialStats && msg.partialStats.length && !previewBlobUrls[idx]" class="partial-stats">
                <div class="partial-stats-title">报告中段生成失败，但已完成以下阶段：</div>
                <div v-for="(stat, si) in msg.partialStats" :key="si" class="partial-stat-item">
                  <span class="partial-stat-icon">{{ stat.icon }}</span>
                  <span class="partial-stat-text">{{ stat.label }}：{{ stat.count }}</span>
                </div>
              </div>
              <!-- 报告消息：用 iframe 展示 html-ppt 风格报告（所见即所得） -->
              <div
                v-if="msg.reportMarkdown && !(loading && idx === messages.length - 1) && previewBlobUrls[idx]"
                class="report-iframe-wrapper"
                :key="'report-' + idx + '-' + (themeByMessage[idx] || selectedTheme)"
              >
                <div class="report-toolbar">
                  <el-select
                    :model-value="themeByMessage[idx] || selectedTheme"
                    @update:model-value="(v: string) => changeTheme(idx, v)"
                    size="small"
                    style="width: 200px"
                    filterable
                    placeholder="选择主题"
                  >
                    <el-option v-for="t in HTML_PPT_THEMES" :key="t" :label="t" :value="t" />
                  </el-select>
                  <el-button size="small" text @click="openPresenterMode(idx)" title="打开演讲者模式（html-ppt 的 S 键同步）">
                    🎤 演讲者模式
                  </el-button>
                </div>
                <iframe :src="previewBlobUrls[idx]" class="report-iframe" :data-msg-idx="idx" sandbox="allow-scripts allow-same-origin"></iframe>
              </div>
              <!-- 非报告消息 / 报告尚未加载完成：显示原始内容 -->
              <div
                v-else-if="msg.content"
                class="message-content assistant-content report-body"
                v-html="msg.content"
              ></div>
              <div v-if="msg.chartOptions && msg.chartOptions.length && !previewBlobUrls[idx]" class="charts-section">
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
                <el-dropdown trigger="click" @command="(cmd: {fmt: string; template_id?: string}) => handleExportReport(msg.reportMarkdown!, cmd.fmt, cmd.template_id, idx)">
                  <el-button size="small" text :icon="Download">
                    导出报告
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item :command="{fmt: 'md'}">Markdown (.md)</el-dropdown-item>
                      <el-dropdown-item :command="{fmt: 'docx'}">Word (.docx)</el-dropdown-item>
                      <el-dropdown-item :command="{fmt: 'pdf'}">PDF (.pdf)</el-dropdown-item>
                      <el-dropdown-item :command="{fmt: 'html'}">网页 (.html)</el-dropdown-item>
                      <el-sub-menu v-if="pptTemplates.length > 0" teleported>
                        <template #title>PowerPoint (.pptx)</template>
                        <el-dropdown-item
                          v-for="t in pptTemplates"
                          :key="t.id"
                          :command="{fmt: 'pptx', template_id: t.id}"
                        >
                          {{ t.name }}
                          <span style="color:#909399; font-size:11px; margin-left:4px;">({{ t.layouts_count }}版式)</span>
                        </el-dropdown-item>
                      </el-sub-menu>
                      <el-dropdown-item v-else :command="{fmt: 'pptx'}">PowerPoint (.pptx)</el-dropdown-item>
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

      <div
        class="chat-input-bar"
        :class="{ 'drag-over': isDragOver }"
        @dragover="onDragOver"
        @dragleave="onDragLeave"
        @drop="onDrop"
      >
        <input
          ref="fileInputRef"
          type="file"
          multiple
          :accept="ACCEPTED_EXTENSIONS"
          style="display: none"
          @change="onFileInputChange"
        />

        <div v-if="pendingAttachments.length > 0" class="pending-attachments">
          <div
            v-for="att in pendingAttachments"
            :key="att.key"
            class="attachment-chip"
            :class="`status-${att.status}`"
          >
            <el-icon class="chip-icon"><Document /></el-icon>
            <div class="chip-body">
              <div class="chip-line">
                <span class="chip-name">{{ att.file.name }}</span>
                <span class="chip-size">{{ formatFileSize(att.file.size) }}</span>
              </div>
              <div v-if="att.status === 'uploading'" class="chip-progress">
                <div class="chip-progress-bar">
                  <div class="chip-progress-fill" :style="{ width: att.progress + '%' }"></div>
                </div>
                <span class="chip-progress-text">{{ att.progress }}%</span>
              </div>
              <div v-else-if="att.status === 'done'" class="chip-state done">已就绪</div>
              <div v-else-if="att.status === 'error'" class="chip-state error" :title="att.error">上传失败</div>
              <div v-else class="chip-state">待发送</div>
            </div>
            <el-button
              text
              size="small"
              :icon="Close"
              aria-label="移除附件"
              class="chip-remove"
              @click="removeAttachment(att.key)"
            />
          </div>
        </div>

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
          circle
          size="large"
          :icon="Paperclip"
          class="icon-btn"
          :disabled="loading"
          title="添加附件"
          @click="triggerFileInput"
        />
        <el-button
          v-if="loading"
          circle
          type="warning"
          size="large"
          :icon="VideoPause"
          class="icon-btn pause-btn"
          title="暂停生成"
          @click="handleStop"
        />
        <el-button
          v-else
          circle
          type="primary"
          size="large"
          :icon="Promotion"
          class="icon-btn send-btn"
          :disabled="!inputTopic.trim()"
          title="发送"
          @click="sendMessage"
        />
      </div>
    </main>
  </div>

  <div v-else class="auth-placeholder">
    <div class="placeholder-inner">
      <div class="placeholder-icon">U</div>
      <h2 class="placeholder-title">{{ t('placeholder.needLogin') }}</h2>
      <p class="placeholder-desc">{{ t('placeholder.needLoginDesc') }}</p>
      <p class="placeholder-brand">{{ t('brand.name') }} · {{ t('brand.company') }}</p>
    </div>
  </div>

  <!-- 阶段详情弹窗 -->
  <StageDetailDialog
    v-model:visible="detailDialogVisible"
    :stageName="detailStageName"
    :stageKey="detailStageKey"
    :stageDetail="detailStageData"
  />
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
  gap: 12px;
  padding: 16px 24px;
  max-width: 900px;
  width: 100%;
  margin: 0 auto;
}

.user-row {
  justify-content: flex-end;
}

.message-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.message-avatar svg {
  width: 18px;
  height: 18px;
}

.user-avatar {
  background: #4A90D9;
}

.assistant-avatar {
  background: var(--scdc-accent);
}

.message-sender {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.sender-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--scdc-ink-strong);
}

.sender-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--scdc-bg-elevated);
  color: var(--scdc-ink-muted);
  font-weight: 500;
}

.terminated-hint {
  font-size: 13px;
  color: var(--scdc-ink-soft);
  font-style: italic;
  margin-bottom: 8px;
}

.message-content {
  font-size: 14px;
  line-height: 1.7;
  color: var(--scdc-ink);
}

.user-content {
  text-align: left;
}

.assistant-content {
  text-align: left;
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
  flex-wrap: wrap;
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

/* ===== Attachment upload UI ===== */
.pending-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 12px 0;
  width: 100%;
}

.attachment-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px 6px 10px;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-5);
  border-radius: 10px;
  font-size: 12px;
  min-width: 220px;
  max-width: 280px;
}

.attachment-chip.status-error {
  background: var(--el-color-danger-light-9);
  border-color: var(--el-color-danger-light-5);
}

.attachment-chip.status-done {
  background: var(--el-color-success-light-9);
  border-color: var(--el-color-success-light-5);
}

.chip-icon {
  color: var(--el-color-primary);
  flex-shrink: 0;
  font-size: 18px;
}

.attachment-chip.status-error .chip-icon {
  color: var(--el-color-danger);
}

.attachment-chip.status-done .chip-icon {
  color: var(--el-color-success);
}

.chip-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.chip-line {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
}

.chip-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
  flex: 1;
  min-width: 0;
}

.chip-size {
  color: var(--el-text-color-secondary);
  font-size: 11px;
  flex-shrink: 0;
}

.chip-progress {
  display: flex;
  align-items: center;
  gap: 6px;
}

.chip-progress-bar {
  flex: 1;
  height: 4px;
  background: rgba(64, 158, 255, 0.15);
  border-radius: 2px;
  overflow: hidden;
  min-width: 60px;
}

.chip-progress-fill {
  height: 100%;
  background: var(--el-color-primary);
  border-radius: 2px;
  transition: width 0.2s ease;
  background-image: linear-gradient(
    90deg,
    var(--el-color-primary) 0%,
    var(--el-color-primary-light-3) 50%,
    var(--el-color-primary) 100%
  );
  background-size: 200% 100%;
  animation: chip-progress-shimmer 1.4s linear infinite;
}

@keyframes chip-progress-shimmer {
  0%   { background-position: 0% 0; }
  100% { background-position: -200% 0; }
}

.chip-progress-text {
  font-size: 11px;
  color: var(--el-color-primary);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
  min-width: 30px;
  text-align: right;
}

.chip-state {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.chip-state.done {
  color: var(--el-color-success);
}

.chip-state.error {
  color: var(--el-color-danger);
}

.chip-remove {
  padding: 0 2px !important;
  flex-shrink: 0;
}

.chat-input-bar.drag-over {
  background: var(--el-color-primary-light-9);
  border-radius: 8px;
}

/* ===== Round icon buttons (chat input bar) ===== */
.icon-btn {
  width: 44px !important;
  height: 44px !important;
  min-height: 44px !important;
  padding: 0 !important;
  font-size: 20px;
  margin-left: 4px;
  flex-shrink: 0;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.icon-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.25);
}

.icon-btn.pause-btn {
  animation: pause-btn-pulse 1.6s ease-in-out infinite;
}

@keyframes pause-btn-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(230, 162, 60, 0.5); }
  50%      { box-shadow: 0 0 0 6px rgba(230, 162, 60, 0); }
}

/* ===== User message attachments (rendered inside chat history) ===== */
.user-message-body {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}

.user-attachments {
  display: inline-flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  align-self: flex-start;
}

.user-attachment-card {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--scdc-bg-sunken);
  border-radius: 12px;
  box-shadow: var(--scdc-shadow-soft);
  min-width: 200px;
  max-width: 100%;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.user-attachment-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
}

.user-attachment-card .att-icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--scdc-accent-soft, rgba(64, 158, 255, 0.12));
  color: var(--scdc-accent, #409eff);
  border-radius: 8px;
  font-size: 18px;
  flex-shrink: 0;
}

.user-attachment-card .att-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.user-attachment-card .att-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--scdc-ink, #303133);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-attachment-card .att-sub {
  font-size: 11px;
  color: var(--scdc-ink-soft, #909399);
  letter-spacing: 0.02em;
}
/* ===== Report iframe (html-ppt 所见即所得) ===== */
.report-iframe-wrapper {
  margin-top: 16px;
  border: 1px solid var(--scdc-border-color);
  border-radius: var(--scdc-radius-md);
  overflow: hidden;
  background: #fff;
}

.report-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: #f7f7fa;
  border-bottom: 1px solid var(--scdc-border-color);
}

.report-iframe {
  width: 100%;
  height: 800px;
  border: none;
  display: block;
}

</style>