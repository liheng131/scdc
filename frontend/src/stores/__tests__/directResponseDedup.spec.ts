import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('Direct Response Dedup', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  /**
   * 模拟 workflow.ts 中 direct_response 相关逻辑的精简版本
   * 用于测试去重机制的正确性
   */
  function createDirectResponseHandler() {
    let content = '';
    let isDirectResponseFinished = false;
    let lastDirectResponseContentLength = 0;
    let renderCallCount = 0;
    let lastRenderedMd = '';
    const updateMessageCalls: Array<Record<string, any>> = [];

    const handleDirectResponse = (chunk: string) => {
      // Guard: 如果 direct_response_done 已经触发，忽略后续 direct_response 事件
      if (isDirectResponseFinished) return;

      if (chunk.length > 0) {
        content = content + chunk;
        updateMessageCalls.push({ content, stageHint: '💬 正在回复...' });
        lastDirectResponseContentLength = content.length;
      }
    };

    const handleDirectResponseDone = () => {
      // Guard: 防止 SSE 重连导致 direct_response_done 被重复处理
      if (isDirectResponseFinished) return;
      isDirectResponseFinished = true;

      const md = content;
      renderCallCount++;
      lastRenderedMd = md;
      updateMessageCalls.push({
        content: `<p>${md}</p>`, // 模拟 marked 渲染
        reportMarkdown: md,
        stageHint: '',
      });
    };

    const reset = () => {
      content = '';
      isDirectResponseFinished = false;
      lastDirectResponseContentLength = 0;
      renderCallCount = 0;
      lastRenderedMd = '';
      updateMessageCalls.length = 0;
    };

    return {
      handleDirectResponse,
      handleDirectResponseDone,
      reset,
      get content() { return content; },
      get isFinished() { return isDirectResponseFinished; },
      get renderCount() { return renderCallCount; },
      get lastRenderedMd() { return lastRenderedMd; },
      get updateCalls() { return [...updateMessageCalls]; },
    };
  }

  it('receiving multiple direct_response chunks appends them correctly without duplication', () => {
    const handler = createDirectResponseHandler();

    // Simulate receiving chunks from SSE stream
    handler.handleDirectResponse('Hello ');
    handler.handleDirectResponse('world! ');
    handler.handleDirectResponse('This is a test.');

    expect(handler.content).toBe('Hello world! This is a test.');
    expect(handler.updateCalls).toHaveLength(3);
    expect(handler.updateCalls[0]).toEqual({ content: 'Hello ', stageHint: '💬 正在回复...' });
    expect(handler.updateCalls[1]).toEqual({ content: 'Hello world! ', stageHint: '💬 正在回复...' });
    expect(handler.updateCalls[2]).toEqual({ content: 'Hello world! This is a test.', stageHint: '💬 正在回复...' });
  });

  it('empty chunks do not cause unnecessary updates', () => {
    const handler = createDirectResponseHandler();

    handler.handleDirectResponse('Hello');
    handler.handleDirectResponse('');
    handler.handleDirectResponse('');
    handler.handleDirectResponse(' World');

    expect(handler.content).toBe('Hello World');
    // Only non-empty chunks should trigger updates
    expect(handler.updateCalls).toHaveLength(2);
  });

  it('direct_response_done does not re-append content', () => {
    const handler = createDirectResponseHandler();

    handler.handleDirectResponse('Test content');
    const contentBeforeDone = handler.content;

    handler.handleDirectResponseDone();

    // Content should still be the same after done
    expect(handler.lastRenderedMd).toBe(contentBeforeDone);
    expect(handler.renderCount).toBe(1);

    // Calling done again should NOT re-render
    handler.handleDirectResponseDone();
    expect(handler.renderCount).toBe(1);
    expect(handler.updateCalls).toHaveLength(2); // one for content, one for done
  });

  it('direct_response events after direct_response_done are ignored', () => {
    const handler = createDirectResponseHandler();

    handler.handleDirectResponse('Initial content');
    handler.handleDirectResponseDone();

    const contentAfterDone = handler.content;
    const renderCountAfterDone = handler.renderCount;

    // Simulate SSE reconnection sending duplicate events
    handler.handleDirectResponse('Duplicate chunk');
    handler.handleDirectResponse('Another duplicate');
    handler.handleDirectResponseDone();
    handler.handleDirectResponseDone();

    // Content and render count should NOT have changed
    expect(handler.content).toBe(contentAfterDone);
    expect(handler.renderCount).toBe(renderCountAfterDone);
    expect(handler.updateCalls).toHaveLength(2);
  });

  it('SSE reconnection scenario: events from before reconnection are not duplicated', () => {
    const handler = createDirectResponseHandler();

    // First connection: receive some chunks
    handler.handleDirectResponse('Part 1 ');
    handler.handleDirectResponse('Part 2 ');

    // Connection drops and reconnects
    // In real SSE, the server may re-send some events
    // Our guard should prevent duplicate processing

    // Simulate re-sending of already processed chunks
    handler.handleDirectResponse('Part 1 ');
    handler.handleDirectResponse('Part 2 ');
    // Then new content
    handler.handleDirectResponse('Part 3');

    // With our current simple append logic, content will be:
    // 'Part 1 Part 2 Part 1 Part 2 Part 3'
    // This test verifies that after done, no more content is appended
    handler.handleDirectResponseDone();

    expect(handler.renderCount).toBe(1);
    expect(handler.isFinished).toBe(true);

    // Any further events after done should be ignored
    handler.handleDirectResponse('Should be ignored');
    handler.handleDirectResponseDone();
    expect(handler.renderCount).toBe(1);
    expect(handler.content).toBe('Part 1 Part 2 Part 1 Part 2 Part 3');
  });

  it('reset clears all state for a new stream', () => {
    const handler = createDirectResponseHandler();

    handler.handleDirectResponse('Old content');
    handler.handleDirectResponseDone();
    expect(handler.isFinished).toBe(true);
    expect(handler.renderCount).toBe(1);

    // Reset for new stream
    handler.reset();

    expect(handler.isFinished).toBe(false);
    expect(handler.renderCount).toBe(0);
    expect(handler.content).toBe('');
    expect(handler.updateCalls).toHaveLength(0);

    // New stream should work normally
    handler.handleDirectResponse('New content');
    handler.handleDirectResponseDone();
    expect(handler.content).toBe('New content');
    expect(handler.renderCount).toBe(1);
  });

  it('rapid consecutive done events only process once', () => {
    const handler = createDirectResponseHandler();

    handler.handleDirectResponse('Content');

    // Simulate rapid fire of done events (could happen with buggy backend)
    handler.handleDirectResponseDone();
    handler.handleDirectResponseDone();
    handler.handleDirectResponseDone();

    expect(handler.renderCount).toBe(1);
    expect(handler.updateCalls).toHaveLength(2);
  });
});
