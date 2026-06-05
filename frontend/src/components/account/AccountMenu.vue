<script setup lang="ts">
import { ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useAuthStore } from '@/stores/auth';
import { usePreferencesStore, type Locale, type ThemeMode } from '@/stores/preferences';
import AuthModal from './AuthModal.vue';
import ChangePasswordModal from './ChangePasswordModal.vue';

const { t, locale } = useI18n();
const auth = useAuthStore();
const prefs = usePreferencesStore();

const popoverVisible = ref(false);
const subPanel = ref<'main' | 'appearance' | 'language'>('main');

const authModalVisible = ref(false);
const passwordModalVisible = ref(false);

const userName = computed(() => auth.user?.username || auth.user?.name || 'User');
const userRole = computed(() => auth.user?.role || 'feishu_personal');
const userInitial = computed(() => {
  const s = userName.value;
  return (s?.charAt(0) || 'U').toUpperCase();
});

// 当前主题显示
const themeDisplay = computed(() => {
  return t(
    prefs.theme === 'system' ? 'account.themeSystem' :
    prefs.theme === 'light' ? 'account.themeLight' : 'account.themeDark'
  );
});

// 当前语言显示
const langDisplay = computed(() => {
  return locale.value === 'zh-CN' ? t('account.langZh') : t('account.langEn');
});

function onSelect(sub: 'appearance' | 'language') {
  subPanel.value = sub;
}
function onBack() {
  subPanel.value = 'main';
}

function setTheme(mode: ThemeMode) {
  prefs.setTheme(mode);
  subPanel.value = 'main';
  popoverVisible.value = false;
}
function setLang(l: Locale) {
  prefs.setLocale(l);
  subPanel.value = 'main';
  popoverVisible.value = false;
}

function openSwitchAccount() {
  popoverVisible.value = false;
  subPanel.value = 'main';
  // 短暂延迟避免与 popover 关闭冲突
  setTimeout(() => {
    authModalVisible.value = true;
  }, 100);
}
function openChangePassword() {
  popoverVisible.value = false;
  subPanel.value = 'main';
  setTimeout(() => {
    passwordModalVisible.value = true;
  }, 100);
}
async function onHelp() {
  popoverVisible.value = false;
  try {
    await ElMessageBox.alert(
      `<div style="line-height:1.7;color:var(--scdc-ink);">
        <p>${t('account.helpDocs')}: docs.unilumin-insight.example</p>
        <p>${t('auth.contactAdmin')}: admin@unilumin-insight.example</p>
        <p>${t('account.submitTicket')}: 在工单系统中提交</p>
      </div>`,
      t('account.help'),
      { dangerouslyUseHTMLString: true, confirmButtonText: 'OK' }
    );
  } catch { /* 用户关闭 */ }
}
async function onLogout() {
  popoverVisible.value = false;
  try {
    await ElMessageBox.confirm(
      t('account.logout') + '?',
      t('account.logout'),
      { confirmButtonText: t('account.logout'), cancelButtonText: '取消', type: 'warning' }
    );
  } catch {
    return; // 用户取消
  }
  auth.logout();
  ElMessage.success(t('account.logout'));
}

function onPopoverShow() {
  subPanel.value = 'main';
}
</script>

<template>
  <div class="account-menu-wrapper">
    <el-popover
      v-model:visible="popoverVisible"
      placement="bottom-end"
      :width="280"
      :show-arrow="false"
      :hide-after="0"
      trigger="click"
      popper-class="account-menu-popover"
      @show="onPopoverShow"
    >
      <template #reference>
        <button class="avatar-btn" :title="userName">
          <span class="avatar-circle">{{ userInitial }}</span>
        </button>
      </template>

      <!-- 主面板 -->
      <div v-if="subPanel === 'main'" class="menu-panel">
        <div class="user-header">
          <div class="avatar-circle large">{{ userInitial }}</div>
          <div class="user-info">
            <div class="user-name">{{ userName }}</div>
            <el-tag size="small" class="role-tag" round>{{ userRole }}</el-tag>
          </div>
        </div>

        <div class="menu-list">
          <button class="menu-row" @click="onSelect('appearance')">
            <span class="row-label">{{ t('account.appearance') }}</span>
            <span class="row-right">
              <span class="row-value">{{ themeDisplay }}</span>
              <span class="row-arrow">›</span>
            </span>
          </button>
          <button class="menu-row" @click="onSelect('language')">
            <span class="row-label">{{ t('account.language') }}</span>
            <span class="row-right">
              <span class="row-value">{{ langDisplay }}</span>
              <span class="row-arrow">›</span>
            </span>
          </button>
          <button class="menu-row" @click="openSwitchAccount">
            <span class="row-label">{{ t('account.switchAccount') }}</span>
            <span class="row-arrow">›</span>
          </button>

          <div class="menu-divider" />

          <button class="menu-row" @click="openChangePassword">
            <span class="row-label">{{ t('account.settings') }}</span>
            <span class="row-arrow">›</span>
          </button>
          <button class="menu-row" @click="onHelp">
            <span class="row-label">{{ t('account.help') }}</span>
            <span class="row-arrow">›</span>
          </button>

          <div class="menu-divider" />

          <button class="menu-row logout" @click="onLogout">
            <span class="row-label">{{ t('account.logout') }}</span>
          </button>
        </div>
      </div>

      <!-- 外观子面板 -->
      <div v-else-if="subPanel === 'appearance'" class="menu-panel sub-panel">
        <button class="sub-header" @click="onBack">
          <span class="back-arrow">‹</span>
          <span class="sub-title">{{ t('account.appearance') }}</span>
        </button>
        <button
          v-for="opt in (['system','light','dark'] as ThemeMode[])"
          :key="opt"
          class="menu-row"
          @click="setTheme(opt)"
        >
          <span class="row-label">
            {{ t(opt === 'system' ? 'account.themeSystem' : opt === 'light' ? 'account.themeLight' : 'account.themeDark') }}
          </span>
          <span v-if="prefs.theme === opt" class="check">✓</span>
        </button>
      </div>

      <!-- 语言子面板 -->
      <div v-else-if="subPanel === 'language'" class="menu-panel sub-panel">
        <button class="sub-header" @click="onBack">
          <span class="back-arrow">‹</span>
          <span class="sub-title">{{ t('account.language') }}</span>
        </button>
        <button class="menu-row" @click="setLang('zh-CN')">
          <span class="row-label">{{ t('account.langZh') }}</span>
          <span v-if="locale === 'zh-CN'" class="check">✓</span>
        </button>
        <button class="menu-row" @click="setLang('en-US')">
          <span class="row-label">{{ t('account.langEn') }}</span>
          <span v-if="locale === 'en-US'" class="check">✓</span>
        </button>
      </div>
    </el-popover>

    <AuthModal v-model:visible="authModalVisible" />
    <ChangePasswordModal v-model:visible="passwordModalVisible" />
  </div>
</template>

<style scoped>
.account-menu-wrapper {
  display: inline-block;
}

.avatar-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
}
.avatar-circle {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--scdc-accent-soft);
  color: var(--scdc-accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--scdc-font-display);
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0;
  transition: box-shadow var(--scdc-transition-fast), transform var(--scdc-transition-fast);
}
.avatar-circle.large {
  width: 44px;
  height: 44px;
  font-size: 18px;
}
.avatar-btn:hover .avatar-circle {
  box-shadow: 0 0 0 2px var(--scdc-accent);
}

.menu-panel {
  font-family: var(--scdc-font-body);
}
.user-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 0 16px;
  border-bottom: 1px solid var(--scdc-bg-sunken);
  margin-bottom: 4px;
}
.user-info { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.user-name {
  font-family: var(--scdc-font-display);
  font-size: 16px;
  font-weight: 600;
  color: var(--scdc-ink-strong);
  letter-spacing: -0.005em;
}
.role-tag {
  align-self: flex-start;
  background: var(--scdc-accent-soft);
  color: var(--scdc-accent-hover);
  border: none;
  font-size: 11px;
  height: 20px;
  padding: 0 8px;
}

.menu-list {
  display: flex;
  flex-direction: column;
}
.menu-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  background: none;
  border: none;
  padding: 10px 8px;
  border-radius: var(--scdc-radius-sm);
  cursor: pointer;
  font-family: var(--scdc-font-body);
  font-size: 14px;
  color: var(--scdc-ink);
  text-align: left;
  transition: background var(--scdc-transition-fast);
}
.menu-row:hover {
  background: var(--scdc-bg-hover);
}
.menu-row.logout { color: var(--scdc-danger); }
.menu-row.logout:hover { background: var(--scdc-danger-soft); }

.row-right { display: flex; align-items: center; gap: 8px; }
.row-value {
  font-size: 13px;
  color: var(--scdc-ink-muted);
  font-variant-numeric: tabular-nums;
}
.row-arrow {
  color: var(--scdc-ink-soft);
  font-size: 18px;
  line-height: 1;
}
.check {
  color: var(--scdc-accent);
  font-weight: 700;
  font-size: 15px;
}

.menu-divider {
  height: 1px;
  background: var(--scdc-bg-sunken);
  margin: 6px 4px;
}

/* 子面板 */
.sub-panel { padding: 0; }
.sub-header {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  background: none;
  border: none;
  padding: 4px 8px 12px;
  cursor: pointer;
  font-family: var(--scdc-font-body);
  color: var(--scdc-ink-muted);
  font-size: 13px;
  border-bottom: 1px solid var(--scdc-bg-sunken);
  margin-bottom: 4px;
  border-radius: 0;
  text-align: left;
}
.sub-header:hover { background: transparent; color: var(--scdc-ink); }
.back-arrow { font-size: 18px; line-height: 1; }
.sub-title { font-weight: 500; }
</style>

<style>
/* el-popover 全局类（必须非 scoped） */
.account-menu-popover.el-popper {
  background: var(--scdc-bg-surface) !important;
  border: 1px solid var(--scdc-bg-sunken) !important;
  padding: 16px !important;
  border-radius: var(--scdc-radius-lg) !important;
  box-shadow: var(--scdc-shadow-lift) !important;
  min-width: 280px;
}
.account-menu-popover.el-popper .el-popper__arrow::before {
  border-color: var(--scdc-bg-sunken) !important;
  background: var(--scdc-bg-surface) !important;
}
</style>
