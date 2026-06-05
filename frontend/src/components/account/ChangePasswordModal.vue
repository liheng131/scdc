<script setup lang="ts">
import { ref, reactive, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import { authApi } from '@/api/services/auth';

interface Props { visible: boolean }
interface Emits {
  (e: 'update:visible', v: boolean): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();
const { t } = useI18n();

const formRef = ref();
const submitting = ref(false);

const form = reactive({
  current: '',
  new: '',
  confirm: '',
});

const rules = computed(() => ({
  current: [
    { required: true, message: t('password.current'), trigger: 'blur' },
  ],
  new: [
    { required: true, message: t('password.new'), trigger: 'blur' },
    { min: 8, message: t('password.ruleLength'), trigger: 'blur' },
    {
      validator: (_: unknown, v: string, cb: (err?: Error) => void) => {
        if (!/[A-Za-z]/.test(v) || !/\d/.test(v)) {
          return cb(new Error(t('password.ruleComplex')));
        }
        cb();
      },
      trigger: 'blur',
    },
  ],
  confirm: [
    { required: true, message: t('password.confirm'), trigger: 'blur' },
    {
      validator: (_: unknown, v: string, cb: (err?: Error) => void) => {
        if (v !== form.new) {
          return cb(new Error(t('password.ruleMismatch')));
        }
        cb();
      },
      trigger: 'blur',
    },
  ],
}));

const close = () => emit('update:visible', false);

async function onSubmit() {
  if (!formRef.value) return;
  try {
    await formRef.value.validate();
  } catch {
    return;
  }
  submitting.value = true;
  try {
    await authApi.changePassword({ current: form.current, new: form.new });
    ElMessage.success(t('password.success'));
    // 清空表单
    form.current = '';
    form.new = '';
    form.confirm = '';
    close();
  } catch (e: any) {
    // 后端未实现 → 友好提示
    if (e?.message === 'NOT_IMPLEMENTED' || e?.response?.status === 404) {
      ElMessage.warning(t('password.inDev'));
    } else {
      ElMessage.error(e?.response?.data?.detail || e?.message || t('password.inDev'));
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
    :close-on-click-modal="!submitting"
    :close-on-press-escape="!submitting"
    align-center
    @update:model-value="(v) => emit('update:visible', v)"
  >
    <div class="password-modal">
      <h2 class="modal-title">{{ t('password.title') }}</h2>
      <p class="modal-subtitle">{{ t('brand.name') }}</p>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        size="large"
        label-position="top"
        @submit.prevent
      >
        <el-form-item :label="t('password.current')" prop="current">
          <el-input
            v-model="form.current"
            type="password"
            show-password
            autocomplete="current-password"
          />
        </el-form-item>
        <el-form-item :label="t('password.new')" prop="new">
          <el-input
            v-model="form.new"
            type="password"
            show-password
            autocomplete="new-password"
          />
        </el-form-item>
        <el-form-item :label="t('password.confirm')" prop="confirm">
          <el-input
            v-model="form.confirm"
            type="password"
            show-password
            autocomplete="new-password"
            @keyup.enter="onSubmit"
          />
        </el-form-item>
        <el-button
          type="primary"
          class="submit-btn"
          :loading="submitting"
          @click="onSubmit"
        >
          {{ t('password.submit') }}
        </el-button>
      </el-form>
    </div>
  </el-dialog>
</template>

<style scoped>
.password-modal {
  padding: 8px 4px 4px;
}
.modal-title {
  font-family: var(--scdc-font-display);
  font-size: 24px;
  font-weight: 600;
  color: var(--scdc-accent);
  margin: 0 0 6px 0;
  letter-spacing: -0.01em;
}
.modal-subtitle {
  font-family: var(--scdc-font-body);
  font-size: 13px;
  color: var(--scdc-ink-muted);
  margin: 0 0 24px 0;
}
.submit-btn {
  width: 100%;
  height: 44px;
  font-family: var(--scdc-font-body);
  font-size: 15px;
  letter-spacing: 0.05em;
  border-radius: var(--scdc-radius-md);
  margin-top: 4px;
}
</style>
