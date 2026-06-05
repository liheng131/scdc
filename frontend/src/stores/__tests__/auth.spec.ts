import { describe, it, expect, beforeEach, vi } from 'vitest';
import { setActivePinia, createPinia } from 'pinia';
import { useAuthStore } from '../auth';

vi.mock('../../api', () => ({
  authApi: {
    login: vi.fn().mockResolvedValue({
      code: 0,
      data: {
        access_token: 'fake-jwt-token',
        user: { id: 1, username: 'admin', role: 'admin' },
      },
      msg: 'success',
    }),
    getCurrentUser: vi.fn().mockResolvedValue({
      code: 0,
      data: { id: 1, username: 'admin', role: 'admin' },
      msg: 'success',
    }),
  },
}));

describe('Auth Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
  });

  it('initializes with default values', () => {
    const store = useAuthStore();
    expect(store.token).toBe('');
    expect(store.isAuthenticated).toBe(false);
    expect(store.user).toBeNull();
  });

  it('performs login correctly and sets token', async () => {
    const store = useAuthStore();
    await store.login('admin', 'pwd');
    expect(store.token).toBe('fake-jwt-token');
    expect(store.isAuthenticated).toBe(true);
    expect(store.user).toEqual({ id: 1, username: 'admin', role: 'admin' });
    expect(localStorage.getItem('token')).toBe('fake-jwt-token');
  });

  it('performs logout and clears state', async () => {
    const store = useAuthStore();
    await store.login('admin', 'pwd');
    expect(store.isAuthenticated).toBe(true);

    // mock window.location
    const originalLocation = window.location;
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { pathname: '/login', href: '' },
    });

    store.logout();
    expect(store.token).toBe('');
    expect(store.isAuthenticated).toBe(false);
    expect(store.user).toBeNull();
    expect(localStorage.getItem('token')).toBeNull();

    Object.defineProperty(window, 'location', {
      writable: true,
      value: originalLocation,
    });
  });
});
