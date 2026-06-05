/**
 * 用户偏好设置（Pinia Store）
 *
 * 集中管理两类前端偏好：
 * 1. locale  - 当前语言（zh-CN / en-US）
 * 2. theme   - 主题模式（system / light / dark）
 *
 * 持久化策略：
 * - 通过 localStorage 保存用户显式选择，避免每次刷新都被重置
 * - locale 与 i18n 实例双向同步，保证 $t() 与 store.locale 始终一致
 * - theme=system 时，resolvedTheme 会跟随 prefers-color-scheme 媒体查询自动更新
 *
 * 主题应用方式：
 * - 通过给 document.documentElement 设置 data-theme 属性切换
 * - :root[data-theme="dark"] 块在 variables.css 中定义暗色 Token
 *
 * init()：
 * - 由 main.ts 在应用挂载前调用一次
 * - 应用当前主题到 <html data-theme="...">
 * - 注册 prefers-color-scheme 媒体查询监听，仅在 system 模式下响应
 */

import { defineStore } from 'pinia';
import { ref } from 'vue';
import { i18n } from '../i18n';

export type Locale = 'zh-CN' | 'en-US';
export type ThemeMode = 'system' | 'light' | 'dark';
export type ResolvedTheme = 'light' | 'dark';

const LOCALE_STORAGE_KEY = 'scdc.locale';
const THEME_STORAGE_KEY = 'scdc.theme';

/**
 * 从 localStorage 读取 locale，并做白名单校验，
 * 避免被外部篡改成无效值导致 i18n 报 MISSING。
 */
function readStoredLocale(): Locale {
  const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
  if (stored === 'zh-CN' || stored === 'en-US') {
    return stored;
  }
  return 'zh-CN';
}

/**
 * 从 localStorage 读取 theme，同样做白名单校验。
 */
function readStoredTheme(): ThemeMode {
  const stored = localStorage.getItem(THEME_STORAGE_KEY);
  if (stored === 'system' || stored === 'light' || stored === 'dark') {
    return stored;
  }
  return 'system';
}

/**
 * 根据系统 prefers-color-scheme 计算默认主题。
 */
function detectSystemTheme(): ResolvedTheme {
  if (typeof window === 'undefined' || !window.matchMedia) {
    return 'light';
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light';
}

export const usePreferencesStore = defineStore('preferences', () => {
  // === 状态 ===
  const locale = ref<Locale>(readStoredLocale());
  const theme = ref<ThemeMode>(readStoredTheme());
  const resolvedTheme = ref<ResolvedTheme>(
    theme.value === 'system' ? detectSystemTheme() : theme.value
  );

  // 系统主题媒体查询监听器引用，便于在 system 模式下注册/清理
  let systemMediaQuery: MediaQueryList | null = null;
  const handleSystemThemeChange = (event: MediaQueryListEvent) => {
    // 仅在 system 模式下生效；其他模式下用户已显式锁定
    if (theme.value !== 'system') return;
    resolvedTheme.value = event.matches ? 'dark' : 'light';
    applyThemeToDom(resolvedTheme.value);
  };

  /**
   * 将主题应用到 <html data-theme="...">。
   * 组件层无需感知，CSS 变量自动覆盖。
   */
  function applyThemeToDom(t: ResolvedTheme): void {
    if (typeof document === 'undefined') return;
    document.documentElement.setAttribute('data-theme', t);
  }

  // === Actions ===

  /**
   * 切换语言并同步到 vue-i18n。
   */
  function setLocale(l: Locale): void {
    locale.value = l;
    localStorage.setItem(LOCALE_STORAGE_KEY, l);
    // 同步 i18n 全局 locale（vue-i18n 在 legacy: false 下使用 ref）
    i18n.global.locale.value = l;
  }

  /**
   * 切换主题。
   * - 'system' 时根据系统偏好解析为 light/dark 并监听媒体查询
   * - 'light' / 'dark' 时直接应用，不再响应系统变化
   */
  function setTheme(t: ThemeMode): void {
    theme.value = t;
    localStorage.setItem(THEME_STORAGE_KEY, t);

    if (t === 'system') {
      resolvedTheme.value = detectSystemTheme();
      ensureSystemListener();
    } else {
      resolvedTheme.value = t;
      detachSystemListener();
    }
    applyThemeToDom(resolvedTheme.value);
  }

  /**
   * 注册系统主题媒体查询监听（幂等）。
   */
  function ensureSystemListener(): void {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    if (systemMediaQuery) return;
    systemMediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    // addEventListener 在现代浏览器中可用；旧 Safari 需用 addListener
    if (typeof systemMediaQuery.addEventListener === 'function') {
      systemMediaQuery.addEventListener('change', handleSystemThemeChange);
    } else {
      // 类型降级：旧 API
      const legacy = systemMediaQuery as unknown as {
        addListener: (cb: (e: MediaQueryListEvent) => void) => void;
      };
      legacy.addListener(handleSystemThemeChange);
    }
  }

  /**
   * 注销系统主题媒体查询监听。
   */
  function detachSystemListener(): void {
    if (!systemMediaQuery) return;
    if (typeof systemMediaQuery.removeEventListener === 'function') {
      systemMediaQuery.removeEventListener('change', handleSystemThemeChange);
    } else {
      const legacy = systemMediaQuery as unknown as {
        removeListener: (cb: (e: MediaQueryListEvent) => void) => void;
      };
      legacy.removeListener(handleSystemThemeChange);
    }
    systemMediaQuery = null;
  }

  /**
   * 应用初始化钩子，由 main.ts 在 mount 之前调用一次：
   * 1. 将 store 中的 locale 同步到 i18n（保证刷新后文案不闪回 fallback）
   * 2. 根据当前 theme 计算 resolvedTheme 并写入 <html data-theme>
   * 3. 若 theme=system，注册媒体查询监听
   */
  function init(): void {
    // 同步 locale 到 i18n
    i18n.global.locale.value = locale.value;

    // 解析当前主题
    if (theme.value === 'system') {
      resolvedTheme.value = detectSystemTheme();
      ensureSystemListener();
    } else {
      resolvedTheme.value = theme.value;
    }
    applyThemeToDom(resolvedTheme.value);
  }

  return {
    // state
    locale,
    theme,
    resolvedTheme,
    // actions
    setLocale,
    setTheme,
    init,
  };
});
