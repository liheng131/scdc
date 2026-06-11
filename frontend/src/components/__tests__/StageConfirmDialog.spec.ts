/**
 * Spec 2 StageConfirmDialog 集成测试
 *
 * 覆盖:
 *  - 4 个 renderer 按 ctx.stage 动态切换
 *  - canSubmit / canReject 计算属性
 *  - handleAccept → store.confirmStage({decision: 'accept'})
 *  - handleReject → store.confirmStage({decision: 'reject', user_edits, user_feedback})
 *    - 必填校验：无任何编辑时不允许 reject
 *  - 跳过模式: skipRemaining 勾选后, accept 会同步 setSkipRemaining
 *  - warning / retry-count 条件渲染
 *  - stage 标题中文映射
 *  - handleCloseAttempt（关闭二次确认）走 accept
 */
import { describe, it, expect, beforeEach, vi, type Mock } from 'vitest';
import { mount, type VueWrapper } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { nextTick, reactive } from 'vue';

// ====== Mock workflow store (state 用 reactive,函数用 vi.fn) ======
const state = reactive({
  confirmDialogVisible: false,
  confirmContext: null as any,
  confirmSubmitting: false,
});
const confirmStageMock = vi.fn();
const hideConfirmDialogMock = vi.fn();
const setSkipRemainingMock = vi.fn();

vi.mock('../../stores/workflow', () => ({
  useWorkflowStore: () => ({
    // 用 getter 始终读 state 当前值(vue 反应式追踪)
    get confirmDialogVisible() { return state.confirmDialogVisible; },
    get confirmContext() { return state.confirmContext; },
    get confirmSubmitting() { return state.confirmSubmitting; },
    confirmStage: confirmStageMock,
    hideConfirmDialog: hideConfirmDialogMock,
    setSkipRemaining: setSkipRemainingMock,
  }),
}));

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}));

// 子 renderer 替身
const rendererStubFactory = vi.hoisted(() => () => ({
  default: {
    template: '<div class="renderer-stub" :data-stage="stageOutput?.stage"></div>',
    props: ['stageOutput', 'userEdits'],
  },
}));
vi.mock('../../components/stage-renderers/CollectingContentRenderer.vue', rendererStubFactory);
vi.mock('../../components/stage-renderers/CleaningContentRenderer.vue', rendererStubFactory);
vi.mock('../../components/stage-renderers/AnalyzingContentRenderer.vue', rendererStubFactory);
vi.mock('../../components/stage-renderers/ReportingContentRenderer.vue', rendererStubFactory);

import StageConfirmDialog from '../StageConfirmDialog.vue';
import { ElMessage, ElMessageBox } from 'element-plus';

const DialogStub = {
  template: `
    <div class="el-dialog-stub" v-if="modelValue">
      <button class="close-btn" @click="$emit('update:modelValue', false)">×</button>
      <header class="title">{{ title }}</header>
      <div class="body"><slot/></div>
      <footer class="footer"><slot name="footer"/></footer>
    </div>
  `,
  props: ['modelValue', 'title', 'width', 'closeOnClickModal', 'closeOnPressEscape', 'showClose', 'beforeClose', 'alignCenter'],
};
const TagStub = { template: '<span class="el-tag-stub"><slot/></span>', props: ['type', 'size', 'effect'] };
const AlertStub = { template: '<div class="el-alert-stub" v-if="title">{{ title }}</div>', props: ['title', 'type', 'closable', 'showIcon'] };
const CollapseStub = { template: '<div class="el-collapse-stub"><slot/></div>' };
const CollapseItemStub = { template: '<div class="el-collapse-item-stub"><slot/></div>', props: ['name', 'title'] };
const InputStub = {
  template: `
    <textarea v-if="type === 'textarea'" class="el-input-stub" :value="modelValue" @input="$emit('update:modelValue', $event.target.value)"></textarea>
    <input v-else class="el-input-stub" :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" />
  `,
  props: ['modelValue', 'placeholder', 'type', 'rows', 'maxlength'],
};
const ButtonStub = {
  template: '<button class="el-button-stub" :disabled="disabled" :loading="loading" @click="$emit(\'click\')"><slot/></button>',
  props: ['type', 'icon', 'disabled', 'loading'],
};
const CheckboxStub = {
  template: '<input type="checkbox" class="el-checkbox-stub" :checked="modelValue" :disabled="disabled" @change="$emit(\'update:modelValue\', $event.target.checked)" />',
  props: ['modelValue', 'disabled'],
};
const IconStub = { template: '<i class="el-icon-stub"><slot/></i>' };

interface ConfirmContext {
  workflowId: string;
  convId: string;
  assistantIdx: number;
  stage: 'collecting' | 'cleaning' | 'analyzing' | 'reporting';
  stageOutput: any;
  stageHistoryLength: number;
}

function makeCtx(stage: ConfirmContext['stage'], extras: Partial<ConfirmContext> = {}): ConfirmContext {
  return {
    workflowId: 'wf_test_1',
    convId: 'conv_test_1',
    assistantIdx: 0,
    stage,
    stageOutput: {},
    stageHistoryLength: 0,
    ...extras,
  };
}

async function openDialog(stage: ConfirmContext['stage'], extras: Partial<ConfirmContext> = {}) {
  const ctx = makeCtx(stage, extras);
  state.confirmContext = ctx;
  state.confirmDialogVisible = true;
  await nextTick();
  return ctx;
}

async function flushAsync() {
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
}

describe('StageConfirmDialog (Spec 2)', () => {
  let wrapper: VueWrapper<any>;

  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    state.confirmContext = null;
    state.confirmDialogVisible = false;
    state.confirmSubmitting = false;
    confirmStageMock.mockResolvedValue({
      workflow_id: 'wf_test_1',
      stage: 'collecting',
      stage_state: 'awaiting_confirmation',
      next_stage: 'cleaning',
      sse_url: null,
      stage_history_length: 1,
    });
  });

  function mountDialog() {
    return mount(StageConfirmDialog, {
      global: {
        stubs: {
          'el-dialog': DialogStub,
          'el-tag': TagStub,
          'el-alert': AlertStub,
          'el-collapse': CollapseStub,
          'el-collapse-item': CollapseItemStub,
          'el-input': InputStub,
          'el-button': ButtonStub,
          'el-checkbox': CheckboxStub,
          'el-icon': IconStub,
        },
      },
    });
  }

  // ========== 1. 4 阶段 renderer 动态切换 ==========

  it.each([
    ['collecting'],
    ['cleaning'],
    ['analyzing'],
    ['reporting'],
  ] as const)('renders correct renderer for stage=%s', async (stage) => {
    wrapper = mountDialog();
    await openDialog(stage);
    const renderer = wrapper.find('.renderer-stub');
    expect(renderer.exists()).toBe(true);
    // 子 renderer 替身会渲染(data-stage 属性可读)
    expect(renderer.attributes('data-stage')).toBeUndefined();  // stageOutput 是空对象
  });

  it('does not render renderer when ctx is null', async () => {
    wrapper = mountDialog();
    state.confirmContext = null;
    state.confirmDialogVisible = false;
    await nextTick();
    expect(wrapper.find('.renderer-stub').exists()).toBe(false);
  });

  // ========== 2. 标题中文映射 ==========

  it.each([
    ['collecting', '数据采集'],
    ['cleaning', '数据清洗'],
    ['analyzing', '分析洞察'],
    ['reporting', '生成报告'],
  ] as const)('uses correct Chinese label for stage=%s', async (stage, expectedLabel) => {
    wrapper = mountDialog();
    await openDialog(stage);
    const title = wrapper.find('.title').text();
    expect(title).toContain(expectedLabel);
  });

  // ========== 3. warning alert 条件渲染 ==========

  it('shows warning alert when stageOutput.warning present', async () => {
    wrapper = mountDialog();
    await openDialog('collecting', { stageOutput: { warning: '采集源不足' } });
    const alert = wrapper.find('.el-alert-stub');
    expect(alert.exists()).toBe(true);
    expect(alert.text()).toContain('采集源不足');
  });

  it('does not show warning alert when no warning', async () => {
    wrapper = mountDialog();
    await openDialog('collecting', { stageOutput: { sources: [] } });
    expect(wrapper.find('.el-alert-stub').exists()).toBe(false);
  });

  // ========== 4. retry count tag ==========

  it('shows "第 N+1 次确认" when stageHistoryLength > 0', async () => {
    wrapper = mountDialog();
    await openDialog('cleaning', { stageHistoryLength: 2 });
    const html = wrapper.html();
    expect(html).toContain('第 3 次确认');
  });

  it('hides retry tag when stageHistoryLength = 0', async () => {
    wrapper = mountDialog();
    await openDialog('cleaning', { stageHistoryLength: 0 });
    expect(wrapper.html()).not.toContain('次确认');
  });

  // ========== 5. handleAccept 行为 ==========

  it('handleAccept: calls confirmStage with {decision: accept}', async () => {
    wrapper = mountDialog();
    await openDialog('cleaning');
    const acceptBtn = wrapper.findAll('.el-button-stub').find((b) => b.text().includes('接受'));
    expect(acceptBtn).toBeTruthy();
    await acceptBtn!.trigger('click');
    await flushAsync();
    expect(confirmStageMock).toHaveBeenCalledWith('wf_test_1', { decision: 'accept' });
    expect(ElMessage.success).toHaveBeenCalled();
  });

  it('handleAccept: does NOT set skip remaining when checkbox unchecked', async () => {
    wrapper = mountDialog();
    await openDialog('cleaning');
    const acceptBtn = wrapper.findAll('.el-button-stub').find((b) => b.text().includes('接受'));
    await acceptBtn!.trigger('click');
    await flushAsync();
    expect(setSkipRemainingMock).not.toHaveBeenCalled();
  });

  // ========== 6. handleReject 行为 ==========

  it('handleReject: disabled when no edits provided', async () => {
    wrapper = mountDialog();
    await openDialog('analyzing');
    const rejectBtn = wrapper.findAll('.el-button-stub').find((b) => b.text().includes('重试'));
    expect(rejectBtn).toBeTruthy();
    // canReject 应当为 false,按钮 disabled
    expect(rejectBtn!.attributes('disabled')).toBeDefined();
  });

  it('handleReject: sends reject body with user_feedback', async () => {
    wrapper = mountDialog();
    await openDialog('analyzing');
    // 找到 textarea（用户反馈框）
    const textarea = wrapper.find('textarea.el-input-stub');
    expect(textarea.exists()).toBe(true);
    await textarea.setValue('需要更深入的对比');
    await nextTick();

    const rejectBtn = wrapper.findAll('.el-button-stub').find((b) => b.text().includes('重试'));
    expect(rejectBtn!.attributes('disabled')).toBeUndefined();
    await rejectBtn!.trigger('click');
    await flushAsync();

    expect(confirmStageMock).toHaveBeenCalledWith('wf_test_1', {
      decision: 'reject',
      user_edits: expect.objectContaining({}),
      user_feedback: '需要更深入的对比',
    });
  });

  // ========== 7. 跳过模式联动 ==========

  it('handleAccept: with skipRemaining checked, calls setSkipRemaining', async () => {
    wrapper = mountDialog();
    await openDialog('reporting');
    const checkbox = wrapper.find('input.el-checkbox-stub');
    expect(checkbox.exists()).toBe(true);
    await checkbox.setValue(true);
    await nextTick();

    const acceptBtn = wrapper.findAll('.el-button-stub').find((b) => b.text().includes('接受'));
    await acceptBtn!.trigger('click');
    await flushAsync();
    expect(setSkipRemainingMock).toHaveBeenCalledWith('wf_test_1', true);
  });

  // ========== 8. 关闭二次确认: 等价 accept ==========

  it('close attempt triggers ElMessageBox and on confirm calls accept', async () => {
    (ElMessageBox.confirm as Mock).mockResolvedValue('confirm');
    wrapper = mountDialog();
    await openDialog('cleaning');

    // 点击 dialog 内的关闭按钮 → 触发 update:modelValue(false) → visible setter → handleCloseAttempt
    const closeBtn = wrapper.find('.close-btn');
    expect(closeBtn.exists()).toBe(true);
    await closeBtn.trigger('click');
    await flushAsync();

    expect(ElMessageBox.confirm).toHaveBeenCalled();
    // 用户点确定 → 走 accept
    expect(confirmStageMock).toHaveBeenCalledWith('wf_test_1', { decision: 'accept' });
  });

  it('close attempt cancelled leaves dialog open (no confirmStage call)', async () => {
    (ElMessageBox.confirm as Mock).mockRejectedValue('cancel');
    wrapper = mountDialog();
    await openDialog('cleaning');

    const closeBtn = wrapper.find('.close-btn');
    expect(closeBtn.exists()).toBe(true);
    await closeBtn.trigger('click');
    await flushAsync();

    expect(ElMessageBox.confirm).toHaveBeenCalled();
    // 用户取消 → 不调 confirmStage
    expect(confirmStageMock).not.toHaveBeenCalled();
  });
});
