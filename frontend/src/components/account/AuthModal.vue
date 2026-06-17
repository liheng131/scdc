<script setup lang="ts">
/**
 * 认证弹窗
 *
 * 提供登录 / 注册两个 Tab：
 * - 登录：用户名或邮箱 + 密码（identifier 字段）
 * - 注册：邮箱 + 用户名 + 密码 + 确认密码 + 数学验证
 *
 * 错误处理策略：
 * - 字段级错误通过 formErrors 映射到对应输入下方红字
 * - 兜底错误通过 ElMessage 提示
 * - 提交时清空 formErrors，保证错误不会跨次提交残留
 */
import { ref, reactive, computed, watch, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import { useAuthStore } from '@/stores/auth';
import { authApi } from '@/api';

interface Props {
  visible: boolean;
}
interface Emits {
  (e: 'update:visible', v: boolean): void;
  (e: 'success'): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

const { t } = useI18n();
const auth = useAuthStore();

// ============================================================
// 通用状态
// ============================================================
type TabName = 'login' | 'register';
const activeTab = ref<TabName>('login');
const loginFormRef = ref();
const registerFormRef = ref();
const submitting = ref(false);

// ============================================================
// 登录表单
// ============================================================
const loginForm = reactive({
  identifier: '',
  password: '',
  remember: true,
});

const loginRules = computed(() => ({
  identifier: [
    { required: true, message: t('auth.identifier'), trigger: 'blur' },
    { min: 3, max: 64, message: '3-64', trigger: 'blur' },
  ],
  password: [
    { required: true, message: t('auth.password'), trigger: 'blur' },
    { min: 4, message: t('password.ruleLength'), trigger: 'blur' },
  ],
}));

// ============================================================
// 注册表单
// ============================================================
const registerForm = reactive({
  email: '',
  username: '',
  password: '',
  confirmPassword: '',
  captchaAnswer: '',
});

const captchaToken = ref<string>('');
const captchaQuestion = ref<string>('');

const registerRules = computed(() => ({
  email: [
    { required: true, message: t('auth.email'), trigger: 'blur' },
    {
      pattern: /^[\w.+-]+@[\w-]+(\.[\w-]+)+$/,
      message: t('auth.emailFormat'),
      trigger: 'blur',
    },
  ],
  username: [
    { required: true, message: t('auth.username'), trigger: 'blur' },
    { min: 3, max: 32, message: '3-32', trigger: 'blur' },
    {
      pattern: /^[A-Za-z0-9_\u4e00-\u9fa5]+$/,
      message: t('auth.usernameFormat'),
      trigger: 'blur',
    },
  ],
  password: [
    { required: true, message: t('auth.password'), trigger: 'blur' },
    { min: 8, message: t('password.ruleLength'), trigger: 'blur' },
    {
      validator: (_: unknown, value: string, cb: (e?: Error) => void) => {
        if (!value) return cb();
        if (!/[A-Za-z]/.test(value) || !/\d/.test(value)) {
          return cb(new Error(t('password.ruleComplex')));
        }
        cb();
      },
      trigger: 'blur',
    },
  ],
  confirmPassword: [
    { required: true, message: t('auth.confirmPassword'), trigger: 'blur' },
    {
      validator: (_: unknown, value: string, cb: (e?: Error) => void) => {
        if (value !== registerForm.password) {
          return cb(new Error(t('auth.passwordMismatch')));
        }
        cb();
      },
      trigger: 'blur',
    },
  ],
  captchaAnswer: [
    { required: true, message: t('auth.captcha'), trigger: 'blur' },
    {
      validator: (_: unknown, value: number | '', cb: (e?: Error) => void) => {
        if (value === '' || value === null || value === undefined) return cb();
        if (!/^\d+$/.test(String(value))) {
          return cb(new Error(t('auth.captchaWrong')));
        }
        cb();
      },
      trigger: 'blur',
    },
  ],
}));

// 字段级错误展示对象，key 与 form 字段名对齐
const formErrors = reactive<Record<string, string>>({});

const clearFormErrors = () => {
  for (const key of Object.keys(formErrors)) {
    formErrors[key] = '';
  }
};

const resetRegisterForm = () => {
  registerForm.email = '';
  registerForm.username = '';
  registerForm.password = '';
  registerForm.confirmPassword = '';
  registerForm.captchaAnswer = '';
  captchaToken.value = '';
  captchaQuestion.value = '';
  clearFormErrors();
};

// ============================================================
// 数学验证加载
// ============================================================
const loadCaptcha = async () => {
  try {
    const res = await authApi.getCaptcha();
    if (res.data) {
      captchaToken.value = res.data.token;
      captchaQuestion.value = res.data.question;
      registerForm.captchaAnswer = '';
      formErrors.captchaAnswer = '';
    }
  } catch (e) {
    ElMessage.error(t('auth.captchaExpired'));
  }
};

// 切换到 register 时拉取验证；如果初次进入就是 register 也需要
watch(activeTab, (val) => {
  if (val === 'register' && !captchaToken.value) {
    loadCaptcha();
  }
});
onMounted(() => {
  if (activeTab.value === 'register') {
    loadCaptcha();
  }
});

// ============================================================
// 弹窗控制
// ============================================================
const close = () => emit('update:visible', false);

const goRegister = () => {
  activeTab.value = 'register';
  // 立刻拉一次新验证，避免用户切到注册页时算式为空
  loadCaptcha();
};

const goLogin = () => {
  activeTab.value = 'login';
  resetRegisterForm();
};

// ============================================================
// 登录提交
// ============================================================
async function onLoginSubmit() {
  if (!loginFormRef.value) return;
  try {
    await loginFormRef.value.validate();
  } catch {
    return;
  }
  submitting.value = true;
  try {
    await auth.login(loginForm.identifier, loginForm.password);
    ElMessage.success(t('auth.welcomeBack'));
    emit('success');
    close();
  } catch (e) {
    // auth.login 已处理错误提示
  } finally {
    submitting.value = false;
  }
}

// ============================================================
// 注册提交 + 错误映射
// ============================================================
interface ApiError {
  response?: {
    status?: number;
    data?: {
      detail?: string | { code?: string; msg?: string };
      code?: string;
    };
  };
}

function extractErrorInfo(e: unknown): { status: number; code: string } {
  const err = e as ApiError;
  const status = err?.response?.status ?? 0;
  const payload = err?.response?.data;
  // FastAPI HTTPException 形式：{ detail: "EMAIL_TAKEN" }
  // 自定义 ApiResponse 错误形式：{ code: "...", msg: "..." }
  let code = '';
  if (payload && typeof payload === 'object') {
    if (typeof payload.detail === 'string') {
      code = payload.detail;
    } else if (payload.detail && typeof payload.detail === 'object') {
      code = payload.detail.code ?? '';
    } else if (typeof payload.code === 'string') {
      code = payload.code;
    }
  }
  return { status, code };
}

async function onRegisterSubmit() {
  if (!registerFormRef.value) return;
  clearFormErrors();
  try {
    await registerFormRef.value.validate();
  } catch {
    ElMessage.error(t('auth.formInvalid'));
    return;
  }
  submitting.value = true;
  try {
    await authApi.register({
      email: registerForm.email,
      username: registerForm.username,
      password: registerForm.password,
      confirm_password: registerForm.confirmPassword,
      captcha_token: captchaToken.value,
      captcha_answer: Number(registerForm.captchaAnswer),
    });
    ElMessage.success(t('auth.registerSuccess'));
    // 注册成功后回到登录页，identifier 预填为刚注册的邮箱
    loginForm.identifier = registerForm.email;
    loginForm.password = '';
    resetRegisterForm();
    activeTab.value = 'login';
  } catch (e) {
    const { status, code } = extractErrorInfo(e);
    if (status === 409 && code === 'EMAIL_TAKEN') {
      formErrors.email = t('auth.emailTaken');
    } else if (status === 409 && code === 'USERNAME_TAKEN') {
      formErrors.username = t('auth.usernameTaken');
    } else if (status === 400 && code === 'INVALID_CAPTCHA') {
      formErrors.captchaAnswer = t('auth.captchaWrong');
      loadCaptcha();
    } else if (status === 400 && code === 'PASSWORD_MISMATCH') {
      formErrors.confirmPassword = t('auth.passwordMismatch');
    } else {
      ElMessage.error(t('auth.registerFailed'));
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <el-dialog
    :model-value="props.visible"
    :title="''"
    width="440px"
    :show-close="true"
    :close-on-click-modal="true"
    :close-on-press-escape="true"
    align-center
    @update:model-value="(v) => emit('update:visible', v)"
  >
    <div class="auth-modal">
      <h2 class="auth-title">{{ t('auth.welcomeBack') }}</h2>
      <p class="auth-subtitle">{{ t('brand.name') }} · {{ t('brand.company') }}</p>

      <el-tabs v-model="activeTab" class="auth-tabs" stretch>
        <!-- ===================== 登录 Tab ===================== -->
        <el-tab-pane :label="t('auth.login')" name="login">
          <el-form
            ref="loginFormRef"
            :model="loginForm"
            :rules="loginRules"
            size="large"
            label-position="top"
            @submit.prevent
          >
            <el-form-item :label="t('auth.identifier')" prop="identifier">
              <el-input
                v-model="loginForm.identifier"
                :placeholder="t('auth.identifierPlaceholder')"
                autocomplete="username"
                clearable
              />
            </el-form-item>
            <el-form-item :label="t('auth.password')" prop="password">
              <el-input
                v-model="loginForm.password"
                type="password"
                :placeholder="t('auth.password')"
                show-password
                autocomplete="current-password"
                @keyup.enter="onLoginSubmit"
              />
            </el-form-item>
            <el-form-item>
              <div class="login-options">
                <el-checkbox v-model="loginForm.remember">{{ t('auth.rememberMe') }}</el-checkbox>
                <a class="forgot-link">{{ t('auth.forgotPassword') }}</a>
              </div>
            </el-form-item>
            <el-button
              type="primary"
              class="submit-btn"
              :loading="submitting"
              @click="onLoginSubmit"
            >
              {{ t('auth.submit') }}
            </el-button>

            <div class="auth-foot">
              <a class="foot-link" @click="goRegister">{{ t('auth.goRegister') }}</a>
            </div>
          </el-form>
        </el-tab-pane>

        <!-- ===================== 注册 Tab ===================== -->
        <el-tab-pane :label="t('auth.register')" name="register">
          <el-form
            ref="registerFormRef"
            :model="registerForm"
            :rules="registerRules"
            size="large"
            label-position="top"
            @submit.prevent
          >
            <el-form-item :label="t('auth.email')" prop="email">
              <el-input
                v-model="registerForm.email"
                :placeholder="t('auth.emailPlaceholder')"
                autocomplete="email"
                clearable
              />
              <div v-if="formErrors.email" class="field-error">{{ formErrors.email }}</div>
            </el-form-item>

            <el-form-item :label="t('auth.username')" prop="username">
              <el-input
                v-model="registerForm.username"
                :placeholder="t('auth.username')"
                autocomplete="username"
                clearable
              />
              <div v-if="formErrors.username" class="field-error">{{ formErrors.username }}</div>
            </el-form-item>

            <el-form-item :label="t('auth.password')" prop="password">
              <el-input
                v-model="registerForm.password"
                type="password"
                :placeholder="t('auth.password')"
                show-password
                autocomplete="new-password"
              />
              <div v-if="formErrors.password" class="field-error">{{ formErrors.password }}</div>
            </el-form-item>

            <el-form-item :label="t('auth.confirmPassword')" prop="confirmPassword">
              <el-input
                v-model="registerForm.confirmPassword"
                type="password"
                :placeholder="t('auth.confirmPassword')"
                show-password
                autocomplete="new-password"
              />
              <div v-if="formErrors.confirmPassword" class="field-error">
                {{ formErrors.confirmPassword }}
              </div>
            </el-form-item>

            <!-- 数学验证行：左侧 label / 中间算式 / 右侧输入 + 换一题 -->
            <el-form-item :label="t('auth.captcha')" prop="captchaAnswer">
              <div class="captcha-row">
                <span class="captcha-question">{{ captchaQuestion || '?' }}</span>
                <el-input
                  v-model="registerForm.captchaAnswer"
                  class="captcha-input"
                  :placeholder="t('auth.captchaPlaceholder')"
                  inputmode="numeric"
                  autocomplete="off"
                />
                <a class="captcha-refresh" @click="loadCaptcha">
                  {{ t('auth.captchaRefresh') }}
                </a>
              </div>
              <div v-if="formErrors.captchaAnswer" class="field-error">
                {{ formErrors.captchaAnswer }}
              </div>
            </el-form-item>

            <el-button
              type="primary"
              class="submit-btn"
              :loading="submitting"
              @click="onRegisterSubmit"
            >
              {{ t('auth.register') }}
            </el-button>

            <div class="auth-foot">
              <a class="foot-link" @click="goLogin">{{ t('auth.haveAccount') }}</a>
            </div>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </div>
  </el-dialog>
</template>

<style scoped>
.auth-modal {
  padding: 8px 4px 4px;
}
.auth-title {
  font-family: var(--scdc-font-display);
  font-size: 26px;
  font-weight: 600;
  color: var(--scdc-accent);
  margin: 0 0 6px 0;
  letter-spacing: -0.01em;
}
.auth-subtitle {
  font-family: var(--scdc-font-body);
  font-size: 13px;
  color: var(--scdc-ink-muted);
  margin: 0 0 24px 0;
  letter-spacing: 0.02em;
}
.auth-tabs {
  margin-top: 8px;
}
.auth-tabs :deep(.el-tabs__item) {
  font-family: var(--scdc-font-body);
  font-size: 14px;
  font-weight: 500;
  color: var(--scdc-ink-muted);
}
.auth-tabs :deep(.el-tabs__item.is-active) {
  color: var(--scdc-ink-strong);
  font-weight: 600;
}
.auth-tabs :deep(.el-tabs__active-bar) {
  background-color: var(--scdc-accent);
}
.auth-tabs :deep(.el-tabs__nav-wrap::after) {
  background-color: var(--scdc-bg-sunken);
}

.login-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  margin-bottom: 8px;
}
.forgot-link {
  font-size: 13px;
  color: var(--scdc-accent);
  cursor: pointer;
  text-decoration: none;
}
.forgot-link:hover {
  color: var(--scdc-accent-hover);
}

.submit-btn {
  width: 100%;
  height: 44px;
  font-family: var(--scdc-font-body);
  font-size: 15px;
  font-weight: 500;
  letter-spacing: 0.05em;
  border-radius: var(--scdc-radius-md);
  margin-top: 4px;
}

.auth-foot {
  margin-top: var(--scdc-space-3);
  text-align: center;
  font-family: var(--scdc-font-body);
  font-size: 13px;
  color: var(--scdc-ink-muted);
}
.foot-link {
  color: var(--scdc-accent);
  cursor: pointer;
  letter-spacing: 0.02em;
}
.foot-link:hover {
  color: var(--scdc-accent-hover);
}

/* 数学验证行：label / 算式 / 输入 / 换一题 */
.captcha-row {
  display: flex;
  align-items: center;
  gap: var(--scdc-space-3);
  width: 100%;
}
.captcha-question {
  font-family: var(--scdc-font-display);
  font-size: 18px;
  font-weight: var(--scdc-weight-semibold);
  color: var(--scdc-accent);
  letter-spacing: 0.05em;
  min-width: 88px;
  text-align: center;
  padding: 6px 10px;
  background: var(--scdc-accent-soft);
  border-radius: var(--scdc-radius-sm);
  white-space: nowrap;
}
.captcha-input {
  flex: 1;
  min-width: 0;
}
.captcha-refresh {
  font-family: var(--scdc-font-body);
  font-size: 13px;
  color: var(--scdc-accent);
  cursor: pointer;
  white-space: nowrap;
  -webkit-user-select: none;
  user-select: none;
}
.captcha-refresh:hover {
  color: var(--scdc-accent-hover);
}

/* 字段级错误红字 */
.field-error {
  font-family: var(--scdc-font-body);
  font-size: 12px;
  color: var(--scdc-color-error, #c45656);
  margin-top: 4px;
  line-height: 1.4;
}
</style>
