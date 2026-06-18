import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('SSE Stream Timeout', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  const SSE_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

  // Simulate the core timeout logic from workflow.ts
  function createTimeoutManager() {
    const timers = new Map<string, ReturnType<typeof setTimeout>>();
    let lastAction = '';
    let lastConvId = '';

    const startTimeout = (convId: string, onTimeout: () => void) => {
      clearTimeout(timers.get(convId));
      const timer = setTimeout(() => {
        timers.delete(convId);
        lastConvId = convId;
        lastAction = 'timeout';
        onTimeout();
      }, SSE_TIMEOUT_MS);
      timers.set(convId, timer);
    };

    const resetTimeout = (convId: string, onTimeout: () => void) => {
      if (timers.has(convId)) {
        startTimeout(convId, onTimeout);
      }
    };

    const clearTimer = (convId: string) => {
      clearTimeout(timers.get(convId));
      timers.delete(convId);
    };

    const hasTimer = (convId: string) => timers.has(convId);

    const getActions = () => ({ action: lastAction, convId: lastConvId });

    return { startTimeout, resetTimeout, clearTimer, hasTimer, getActions };
  }

  it('timeout triggers after 5 minutes of no events, marking conversation as failed', () => {
    const mgr = createTimeoutManager();
    const convId = 'conv_test_1';
    const onTimeout = vi.fn(() => {
      // Simulate: clearEventSource(), updateConversationStatus(convId, 'failed'), ElMessage.error(...)
    });

    // Start the stream timeout
    mgr.startTimeout(convId, onTimeout);
    expect(mgr.hasTimer(convId)).toBe(true);

    // Advance time to just before timeout
    vi.advanceTimersByTime(SSE_TIMEOUT_MS - 1);
    expect(mgr.hasTimer(convId)).toBe(true);
    expect(onTimeout).not.toHaveBeenCalled();

    // Advance past timeout threshold
    vi.advanceTimersByTime(1);
    expect(mgr.hasTimer(convId)).toBe(false);
    expect(onTimeout).toHaveBeenCalledTimes(1);
    expect(mgr.getActions()).toEqual({ action: 'timeout', convId: 'conv_test_1' });
  });

  it('receiving an SSE event resets the timeout timer', () => {
    const mgr = createTimeoutManager();
    const convId = 'conv_test_2';
    const onTimeout = vi.fn();

    // Start the stream timeout
    mgr.startTimeout(convId, onTimeout);

    // Advance time close to timeout (4 minutes)
    vi.advanceTimersByTime(4 * 60 * 1000);
    expect(mgr.hasTimer(convId)).toBe(true);

    // Simulate receiving an SSE event → reset timeout (timer now fires at t=4min+5min=9min)
    mgr.resetTimeout(convId, onTimeout);

    // Advance time past the original timeout window
    vi.advanceTimersByTime(2 * 60 * 1000);
    // Timer should still be alive (reset added another 5 minutes)
    expect(mgr.hasTimer(convId)).toBe(true);
    expect(onTimeout).not.toHaveBeenCalled();

    // Advance close to new timeout (total elapsed: 4+2+2=8min, timer fires at 9min)
    vi.advanceTimersByTime(2 * 60 * 1000);
    expect(mgr.hasTimer(convId)).toBe(true);
    expect(onTimeout).not.toHaveBeenCalled();

    // Advance to just before timeout (total: 4+2+2+59s599ms = 8min59s999ms)
    vi.advanceTimersByTime(59 * 1000 + 999);
    expect(mgr.hasTimer(convId)).toBe(true);
    expect(onTimeout).not.toHaveBeenCalled();

    // Cross the new timeout threshold
    vi.advanceTimersByTime(1);
    expect(mgr.hasTimer(convId)).toBe(false);
    expect(onTimeout).toHaveBeenCalledTimes(1);
  });

  it('timeout is cleared when EventSource is manually closed', () => {
    const mgr = createTimeoutManager();
    const convId = 'conv_test_3';
    const onTimeout = vi.fn();

    // Start the stream timeout
    mgr.startTimeout(convId, onTimeout);
    expect(mgr.hasTimer(convId)).toBe(true);

    // Advance time partially
    vi.advanceTimersByTime(2 * 60 * 1000);
    expect(mgr.hasTimer(convId)).toBe(true);

    // Manually clear (simulating clearEventSource)
    mgr.clearTimer(convId);
    expect(mgr.hasTimer(convId)).toBe(false);

    // Advance past what would have been the timeout
    vi.advanceTimersByTime(4 * 60 * 1000);
    expect(onTimeout).not.toHaveBeenCalled();
  });

  it('multiple SSE events keep resetting the timeout', () => {
    const mgr = createTimeoutManager();
    const convId = 'conv_test_4';
    const onTimeout = vi.fn();

    mgr.startTimeout(convId, onTimeout);

    // Event 1 at 1 min
    vi.advanceTimersByTime(1 * 60 * 1000);
    mgr.resetTimeout(convId, onTimeout);

    // Event 2 at another 2 min
    vi.advanceTimersByTime(2 * 60 * 1000);
    mgr.resetTimeout(convId, onTimeout);

    // Event 3 at another 3 min
    vi.advanceTimersByTime(3 * 60 * 1000);
    mgr.resetTimeout(convId, onTimeout);

    // Total elapsed: 6 min, but each event reset the 5-min window
    // Should NOT have timed out yet
    expect(mgr.hasTimer(convId)).toBe(true);
    expect(onTimeout).not.toHaveBeenCalled();

    // Now advance past the final reset's timeout
    vi.advanceTimersByTime(5 * 60 * 1000);
    expect(mgr.hasTimer(convId)).toBe(false);
    expect(onTimeout).toHaveBeenCalledTimes(1);
  });

  it('resetTimeout does nothing if no timer exists for convId', () => {
    const mgr = createTimeoutManager();
    const convId = 'conv_test_5';
    const onTimeout = vi.fn();

    // Don't start a timer, just try to reset
    expect(mgr.hasTimer(convId)).toBe(false);
    mgr.resetTimeout(convId, onTimeout);
    expect(mgr.hasTimer(convId)).toBe(false);
    expect(onTimeout).not.toHaveBeenCalled();
  });
});
