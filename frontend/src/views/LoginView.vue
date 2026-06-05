<script setup lang="ts">
/**
 * 登录页面
 *
 * 提供用户名/密码表单登录功能。
 *
 * 为什么 @keyup.enter 绑定到 el-form：
 * - 用户在密码框按 Enter 可直接提交，提升操作效率
 * - Vue 的事件修饰符 .enter 避免了手动监听 keydown 事件
 *
 * 为什么错误在 apiClient 拦截器中处理：
 * - 统一错误展示（ElMessage），login 函数不需要额外 try/catch
 * - catch 块为空的目的是避免 Promise rejection 传播到控制台
 */
import { ref, reactive } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '../stores/auth';
import { User, Lock } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';

const router = useRouter();
const authStore = useAuthStore();

const loginForm = reactive({
  username: '',
  password: '',
});

const loading = ref(false);

const handleLogin = async () => {
  if (!loginForm.username || !loginForm.password) {
    ElMessage.warning('请输入用户名和密码');
    return;
  }
  loading.value = true;
  try {
    await authStore.login(loginForm.username, loginForm.password);
    ElMessage.success('登录成功，正在进入系统...');
    router.push('/');
  } catch (e: any) {
    // 错误已在 apiClient 拦截器中通过 ElMessage 展示，此处无需重复提示
    console.error('Login failed:', e);
  } finally {
    loading.value = false;
  }
};
</script>

<template>
  <div class="login-container">
    <div class="login-box">
      <div class="login-header">
        <h2 class="title">SCDC AI 智能体平台</h2>
        <p class="subtitle">单机 All-in-One 市场洞察智能决策系统</p>
      </div>
      <el-form class="login-form" @keyup.enter="handleLogin">
        <el-form-item>
          <el-input
            v-model="loginForm.username"
            placeholder="管理员账户名 / 用户名"
            :prefix-icon="User"
            size="large"
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="登录密码"
            :prefix-icon="Lock"
            size="large"
            show-password
          />
        </el-form-item>
        <el-button
          type="primary"
          size="large"
          class="login-btn"
          :loading="loading"
          @click="handleLogin"
        >
          立即登录
        </el-button>
      </el-form>
      <div class="login-footer">
        <span>默认账户: admin / password</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-container {
  height: 100vh;
  width: 100vw;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--scdc-bg-canvas);
  position: relative;
  overflow: hidden;
}

.login-container::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse at top right, rgba(180, 83, 9, 0.06), transparent 60%);
  pointer-events: none;
  z-index: 0;
}

.login-box {
  position: relative;
  z-index: 1;
  width: 420px;
  padding: 56px 48px;
  background: var(--scdc-bg-surface);
  border: 1px solid var(--scdc-bg-sunken);
  border-radius: var(--scdc-radius-lg);
  box-shadow: var(--scdc-shadow-lift);
}

.login-header {
  text-align: center;
  margin-bottom: var(--scdc-space-8);
}

.title {
  font-family: var(--scdc-font-display);
  color: var(--scdc-accent);
  font-weight: 600;
  font-size: 30px;
  letter-spacing: -0.01em;
  margin: 0 0 10px 0;
}

.subtitle {
  font-size: 14px;
  color: var(--scdc-ink-muted);
  margin: 0;
  font-family: var(--scdc-font-body);
  line-height: var(--scdc-leading-snug);
}

.login-form {
  margin-bottom: var(--scdc-space-6);
}

.login-btn {
  width: 100%;
  margin-top: var(--scdc-space-3);
  border-radius: var(--scdc-radius-md);
  height: 44px;
  font-family: var(--scdc-font-body);
  font-weight: 600;
  letter-spacing: 0.05em;
}

.login-footer {
  text-align: center;
  font-size: var(--scdc-text-xs);
  color: var(--scdc-ink-soft);
  font-family: var(--scdc-font-body);
}
</style>
