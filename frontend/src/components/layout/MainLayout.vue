<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useAuthStore } from '@/stores/auth';
import AuthModal from '@/components/account/AuthModal.vue';
import AccountMenu from '@/components/account/AccountMenu.vue';

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const auth = useAuthStore();

const activeIndex = computed(() => route.path);

const authModalVisible = ref(false);
const accountMenuRef = ref<InstanceType<typeof AccountMenu> | null>(null);

const menuItems = [
  { path: '/', key: 'nav.dashboard' },
  { path: '/workflow', key: 'nav.workflow' },
  { path: '/reports', key: 'nav.reports' },
  { path: '/settings', key: 'nav.settings' },
];

function onMenuSelect(index: string) {
  router.push(index);
}

function openAuthModal() {
  authModalVisible.value = true;
}

function onAuthSuccess() {
  authModalVisible.value = false;
  // auth store 已通过 fetchCurrentUser 自动更新 user
}
</script>

<template>
  <el-container class="main-layout">
    <el-header class="header" height="72px">
      <!-- 左：品牌区 -->
      <div class="brand">
        <div class="brand-name">
          <span class="brand-accent">U-</span>{{ t('brand.name').replace('U-', '') }}
        </div>
        <div class="brand-company">{{ t('brand.company') }}</div>
      </div>

      <!-- 中：水平导航 -->
      <el-menu
        mode="horizontal"
        :default-active="activeIndex"
        :ellipsis="false"
        class="top-menu"
        @select="onMenuSelect"
      >
        <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
          {{ t(item.key) }}
        </el-menu-item>
      </el-menu>

      <!-- 右：登录按钮 / 头像 -->
      <div class="header-right">
        <template v-if="auth.isAuthenticated">
          <AccountMenu ref="accountMenuRef" />
        </template>
        <el-button
          v-else
          type="primary"
          round
          class="login-btn"
          @click="openAuthModal"
        >
          {{ t('auth.loginRegister') }}
        </el-button>
      </div>
    </el-header>

    <!-- 面包屑（保留在头部下方） -->
    <div class="breadcrumb-bar">
      <el-breadcrumb separator="/">
        <el-breadcrumb-item :to="{ path: '/' }">{{ t('nav.dashboard') }}</el-breadcrumb-item>
        <el-breadcrumb-item v-if="route.meta.title">{{ route.meta.title }}</el-breadcrumb-item>
      </el-breadcrumb>
    </div>

    <el-main class="main-content">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </el-main>

    <!-- 登录 / 注册模态 -->
    <AuthModal v-model:visible="authModalVisible" @success="onAuthSuccess" />
  </el-container>
</template>

<style scoped>
.main-layout {
  min-height: 100vh;
  background: var(--scdc-bg-canvas);
}

.header {
  display: flex;
  align-items: center;
  gap: 40px;
  padding: 0 40px;
  background: var(--scdc-bg-surface);
  border-bottom: 1px solid var(--scdc-bg-sunken);
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 1px 4px rgba(60, 40, 20, 0.04);
}

/* 品牌区 */
.brand {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex-shrink: 0;
  min-width: 180px;
}
.brand-name {
  font-family: var(--scdc-font-display);
  font-size: 20px;
  font-weight: 600;
  color: var(--scdc-ink-strong);
  letter-spacing: -0.01em;
  line-height: 1.2;
}
.brand-accent {
  color: var(--scdc-accent);
}
.brand-company {
  font-family: var(--scdc-font-body);
  font-size: 11px;
  font-weight: 500;
  color: var(--scdc-ink-muted);
  letter-spacing: 0.12em;
  line-height: 1;
  text-transform: none;
}

/* 水平菜单 */
.top-menu {
  flex: 1;
  border-bottom: none !important;
  min-width: 0;
}
.top-menu :deep(.el-menu-item) {
  font-family: var(--scdc-font-body);
  font-size: 14px;
  font-weight: 500;
  color: var(--scdc-ink-muted);
  padding: 0 24px !important;
  height: 64px;
  line-height: 64px;
  border-bottom: 2px solid transparent !important;
  transition: color var(--scdc-transition-fast), border-color var(--scdc-transition-fast);
}
.top-menu :deep(.el-menu-item:hover) {
  color: var(--scdc-ink);
  border-bottom-color: transparent !important;
  background: var(--scdc-bg-hover) !important;
}
.top-menu :deep(.el-menu-item.is-active) {
  color: var(--scdc-accent);
  font-weight: 600;
  border-bottom-color: var(--scdc-accent) !important;
  background: transparent !important;
}

/* 右侧区域 */
.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-shrink: 0;
}
.login-btn {
  font-family: var(--scdc-font-body);
  font-size: 14px;
  height: 36px;
  padding: 0 24px;
  letter-spacing: 0.03em;
  font-weight: 500;
}

/* 面包屑 */
.breadcrumb-bar {
  padding: 12px 40px 0;
  background: var(--scdc-bg-canvas);
}
.breadcrumb-bar :deep(.el-breadcrumb__item:last-child .el-breadcrumb__inner) {
  color: var(--scdc-ink);
  font-weight: 500;
}
.breadcrumb-bar :deep(.el-breadcrumb__item:not(:last-child) .el-breadcrumb__inner) {
  color: var(--scdc-ink-muted);
}

/* 主内容 */
.main-content {
  padding: 28px 40px 56px;
  background: var(--scdc-bg-canvas);
  max-width: 1440px;
  margin: 0 auto;
  width: 100%;
}

/* 路由切换淡入 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 180ms ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* 响应式 */
@media (max-width: 1200px) {
  .header { gap: 24px; padding: 0 24px; }
  .brand { min-width: 140px; }
  .top-menu :deep(.el-menu-item) { padding: 0 16px !important; }
  .breadcrumb-bar { padding-left: 24px; padding-right: 24px; }
  .main-content { padding: 24px 24px 48px; }
}

@media (max-width: 900px) {
  .header { gap: 16px; padding: 0 16px; }
  .brand { min-width: auto; }
  .brand-company { display: none; }
  .top-menu :deep(.el-menu-item) { padding: 0 12px !important; }
  .breadcrumb-bar { padding-left: 16px; padding-right: 16px; }
  .main-content { padding: 16px; }
}
</style>
