import { ref, onUnmounted, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import { workflowApi } from '../api/services/workflow';

interface StreamCallbacks {
  onStageStart?: (data: any) => void;
  onStageComplete?: (data: any) => void;
  onStageError?: (data: any) => void;
  onCompleted?: (data: any) => void;
  onError?: (data: any) => void;
}

export function useWorkflowStream() {
  const eventSource = ref<EventSource | null>(null);
  const runningWorkflowId = ref<string | null>(null);
  const isConnected = ref(false);
  const currentWorkflowId = ref<string | null>(null);

  const clearEventSource = () => {
    if (eventSource.value) {
      eventSource.value.close();
      eventSource.value = null;
    }
    runningWorkflowId.value = null;
    isConnected.value = false;
  };

  const startStream = (
    workflowId: string,
    callbacks: StreamCallbacks
  ) => {
    clearEventSource();
    runningWorkflowId.value = workflowId;
    currentWorkflowId.value = workflowId;
    isConnected.value = true;

    const streamUrl = workflowApi.getStreamUrl(workflowId);
    const es = new EventSource(streamUrl);
    eventSource.value = es;

    es.addEventListener('stage_start', (e: any) => {
      const data = JSON.parse(e.data);
      callbacks.onStageStart?.(data);
    });

    es.addEventListener('stage_complete', (e: any) => {
      const data = JSON.parse(e.data);
      callbacks.onStageComplete?.(data);
    });

    es.addEventListener('stage_error', (e: any) => {
      const data = JSON.parse(e.data);
      callbacks.onStageError?.(data);
      clearEventSource();
    });

    es.addEventListener('completed', (e: any) => {
      const data = JSON.parse(e.data);
      callbacks.onCompleted?.(data);
      clearEventSource();
    });

    es.addEventListener('error', (e: any) => {
      let parsedData: any = null;
      try {
        parsedData = JSON.parse(e.data);
      } catch {
        parsedData = { error: '连接异常' };
      }
      callbacks.onError?.(parsedData);
      clearEventSource();
    });

    es.onerror = () => {
      if (runningWorkflowId.value) {
        callbacks.onError?.({ error: 'SSE 连接已断开' });
        clearEventSource();
      }
    };
  };

  return {
    eventSource,
    runningWorkflowId,
    isConnected,
    currentWorkflowId,
    startStream,
    clearEventSource,
  };
}
