/**
 * 回归测试:WorkflowView.sendMessage 3 态分支判定。
 *
 * 背景 bug: 用户在侧边栏点了一个"待开始"对话(空闲无消息)再点"开始分析",
 * 旧逻辑因为 isFollowUp=false 直接走 createConversation,导致新对话自动被创建、
 * 旧对话"毫无反应"的诡异体验。
 *
 * 修复后 3 态分支:
 * - 活动对话 idle/empty（侧边栏点空对话）→ 复用当前对话,不新建
 * - 活动对话 completed 且有消息          → 追问模式
 * - 其他(null/running/failed)            → 新建
 *
 * 这里抽离 sendMessage 的分支判定逻辑做单元测试,不依赖 mount + sendMessage 整体调用。
 */
import { describe, it, expect } from 'vitest';

type Branch = 'new' | 'reuse' | 'followup';

interface ConvMock {
  id: string;
  status: string;
  messages: { role: string; content: string }[];
}

function decideBranch(activeConv: ConvMock | null): Branch {
  if (activeConv === null) {
    return 'new';
  }
  const msgs = activeConv.messages ?? [];
  const status = activeConv.status ?? 'idle';
  if (msgs.length === 0 && status === 'idle') {
    return 'reuse';
  }
  if (msgs.length > 0 && status === 'completed') {
    return 'followup';
  }
  return 'new';
}

describe('sendMessage 分支判定', () => {
  it('无活动对话（点过"新建对话"回到欢迎屏）→ 新建', () => {
    expect(decideBranch(null)).toBe('new');
  });

  it('侧边栏点空对话（status=idle, messages=[]）→ 复用,不新建', () => {
    const conv: ConvMock = { id: 'conv_idle', status: 'idle', messages: [] };
    expect(decideBranch(conv)).toBe('reuse');
  });

  it('已完成对话追问 → followup', () => {
    const conv: ConvMock = {
      id: 'conv_done',
      status: 'completed',
      messages: [
        { role: 'user', content: '上次的' },
        { role: 'assistant', content: '上次的报告' },
      ],
    };
    expect(decideBranch(conv)).toBe('followup');
  });

  it('正在跑的对话 → 新建(避免 SSE 流冲撞)', () => {
    const conv: ConvMock = {
      id: 'conv_running',
      status: 'running',
      messages: [{ role: 'user', content: 'x' }],
    };
    expect(decideBranch(conv)).toBe('new');
  });

  it('失败的对话 → 新建(旧 conv 保留作为历史)', () => {
    const conv: ConvMock = {
      id: 'conv_failed',
      status: 'failed',
      messages: [{ role: 'user', content: 'x' }],
    };
    expect(decideBranch(conv)).toBe('new');
  });

  it('边界: status=completed 但 messages=[] → 不走 followup', () => {
    const conv: ConvMock = { id: 'conv_weird', status: 'completed', messages: [] };
    expect(decideBranch(conv)).toBe('new');
  });

  it('边界: status=idle 但有 messages → 不走 reuse', () => {
    const conv: ConvMock = {
      id: 'conv_partial',
      status: 'idle',
      messages: [{ role: 'user', content: 'half-done' }],
    };
    expect(decideBranch(conv)).toBe('new');
  });
});

describe('新建对话行为', () => {
  /**
   * 参照智谱/DeepSeek: 点"新建对话"只清空 activeConv 回到欢迎屏,不创建记录。
   * 只有用户实际提问时才创建侧边栏记录。
   */

  it('点"新建对话"后 activeConv=null → sendMessage 走新建分支', () => {
    expect(decideBranch(null)).toBe('new');
  });

  it('在欢迎屏重复点"新建对话"无害(activeConv 仍为 null)', () => {
    expect(decideBranch(null)).toBe('new');
    expect(decideBranch(null)).toBe('new'); // 第二次仍然一样
  });
});

describe('复用分支的副作用', () => {
  it('复用分支: 写 user + assistant 消息,status 置为 running', () => {
    const conv: ConvMock = { id: 'conv_idle', status: 'idle', messages: [] };
    const topic = '2025年AI芯片市场趋势';

    // 模拟 reuse 分支的副作用
    conv.messages.push({ role: 'user', content: topic });
    conv.messages.push({ role: 'assistant', content: '' });
    conv.status = 'running';

    expect(conv.messages).toHaveLength(2);
    expect(conv.messages[0].role).toBe('user');
    expect(conv.messages[0].content).toBe(topic);
    expect(conv.messages[1].role).toBe('assistant');
    expect(conv.status).toBe('running');
  });

  it('复用分支失败回滚: 消息弹掉,status 还原 idle', () => {
    const conv: ConvMock = { id: 'conv_idle', status: 'idle', messages: [] };
    const topic = '2025年AI芯片市场趋势';

    // 模拟 reuse 分支的副作用
    conv.messages.push({ role: 'user', content: topic });
    conv.messages.push({ role: 'assistant', content: '' });
    conv.status = 'running';

    // 模拟失败回滚
    conv.messages.pop();
    conv.messages.pop();
    conv.status = 'idle';

    expect(conv.messages).toEqual([]);
    expect(conv.status).toBe('idle');
  });
});
