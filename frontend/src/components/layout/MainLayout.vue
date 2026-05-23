<script setup lang="ts">
/**
 * 主布局组件（侧边栏 + 顶部导航）
 *
 * 所有需要登录认证的页面共享此布局。
 *
 * 为什么侧边栏用 el-menu 的 router 属性：
 * - el-menu 原生支持 router-link 集成，点击菜单项自动触发路由切换
 * - default-active 绑定 route.path 自动高亮当前页面菜单项
 *
 * 为什么可折叠设计（isCollapse）：
 * - 收起侧边栏释放横向空间，适配较小屏幕或用户偏好
 * - el-menu 的 collapse 属性原生支持折叠动画
 *
 * 为什么使用 transition 包裹 RouterView：
 * - fade-transform 动画提供页面切换的视觉过渡，提升用户体验
 * - mode="out-in" 确保旧页面完全离开再进入新页面，避免布局闪烁
 */
import { ref } from 'vue';
import { useRoute } from 'vue-router';
import { useAuthStore } from '../../stores/auth';
import {
  House,
  DataLine,
  List,
  Document,
  Collection,
  Setting,
  SwitchButton,
  Fold,
  Expand
} from '@element-plus/icons-vue';

const authStore = useAuthStore();
const route = useRoute();

const isCollapse = ref(false);

const toggleCollapse = () => {
  isCollapse.value = !isCollapse.value;
};

const handleLogout = () => {
  authStore.logout();
};
</script>

<template>
  <el-container class="main-layout">
    <el-aside :width="isCollapse ? '64px' : '240px'" class="aside">
      <div class="logo-area">
        <span v-if="!isCollapse" class="logo-text">SCDC 洞察智能体</span>
        <span v-else class="logo-text-short">AI</span>
      </div>
      <el-menu
        :default-active="route.path"
        class="side-menu"
        :collapse="isCollapse"
        background-color="#1e222d"
        text-color="#a0aec0"
        active-text-color="#ffffff"
        router
      >
        <el-menu-item index="/">
          <el-icon><House /></el-icon>
          <template #title>仪表盘 Dashboard</template>
        </el-menu-item>
        <el-menu-item index="/data-sources">
          <el-icon><DataLine /></el-icon>
          <template #title>数据源管理 Data Sources</template>
        </el-menu-item>
        <el-menu-item index="/tasks">
          <el-icon><List /></el-icon>
          <template #title>分析任务 Tasks</template>
        </el-menu-item>
        <el-menu-item index="/reports">
          <el-icon><Document /></el-icon>
          <template #title>智能研报 Reports</template>
        </el-menu-item>
        <el-menu-item index="/templates">
          <el-icon><Collection /></el-icon>
          <template #title>大纲模板 Templates</template>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <template #title>系统设置 Settings</template>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="header-left">
          <el-button text @click="toggleCollapse">
            <el-icon :size="20"><Expand v-if="isCollapse" /><Fold v-else /></el-icon>
          </el-button>
          <el-breadcrumb separator="/" class="breadcrumb">
            <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item>{{ route.meta.title || route.name }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <div class="user-info" v-if="authStore.user">
            <el-avatar :size="32" src="https://cube.elemecdn.com/3/7c/3ea6beec64369c2642b92c6726f1epng.png" />
            <span class="username">{{ authStore.user.username }}</span>
            <el-tag size="small" type="success" class="role-tag">{{ authStore.user.role }}</el-tag>
          </div>
          <el-button type="danger" text @click="handleLogout" title="退出登录">
            <el-icon :size="18"><SwitchButton /></el-icon>
          </el-button>
        </div>
      </el-header>
      <el-main class="main-content">
        <router-view v-slot="{ Component }">
          <transition name="fade-transform" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.main-layout {
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background-color: #f5f7fa;
}

.aside {
  background-color: #1e222d;
  transition: width 0.3s ease;
  display: flex;
  flex-direction: column;
}

.logo-area {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #161922;
  color: white;
  font-weight: bold;
  letter-spacing: 1px;
}

.logo-text {
  font-size: 18px;
  background: linear-gradient(135deg, #409eff, #67c23a);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.logo-text-short {
  font-size: 20px;
  color: #409eff;
}

.side-menu {
  border-right: none;
  flex: 1;
}

.side-menu .el-menu-item.is-active {
  background-color: #2b3040 !important;
  border-left: 4px solid #409eff;
}

.header {
  background-color: white;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 60px;
  padding: 0 20px;
}

.header-left, .header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.breadcrumb {
  margin-left: 8px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.username {
  font-weight: 500;
  color: #2d3748;
}

.role-tag {
  text-transform: uppercase;
}

.main-content {
  padding: 24px;
  overflow-y: auto;
  height: calc(100vh - 60px);
}

.fade-transform-enter-active,
.fade-transform-leave-active {
  transition: all 0.2s ease;
}

.fade-transform-enter-from {
  opacity: 0;
  transform: translateX(10px);
}

.fade-transform-leave-to {
  opacity: 0;
  transform: translateX(-10px);
}
</style>
