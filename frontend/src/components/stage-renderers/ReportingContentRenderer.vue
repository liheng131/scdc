<script setup lang="ts">
/**
 * Spec 2 阶段内容渲染器: reporting
 *
 * 自包含 reporting 阶段 UI:
 *  - 报告 markdown 预览(只读)
 *  - 章节结构列表,每条可勾选删除 + 点击编辑内容
 *  - 折叠区:增/改章节
 *
 * Props:
 *   stageOutput: { report, sections, stage: 'reporting' }
 *
 * Emits:
 *   update:userEdits: { edited_sections: { [heading]: text }, removed_section_ids: string[] }
 */
import { ref, computed, watch } from 'vue';
import { Edit, View, Document } from '@element-plus/icons-vue';

interface Section {
  id?: string;
  heading: string;
  level?: number;
  content: string;
  order?: number;
}

const props = defineProps<{
  stageOutput: any;
}>();

const emit = defineEmits<{
  (e: 'update:userEdits', value: { edited_sections?: Record<string, string>; removed_section_ids?: string[] }): void;
}>();

// 本地状态
const removedIds = ref<Set<string>>(new Set());
const editedSections = ref<Record<string, string>>({});
const editingSectionId = ref<string | null>(null);
const editingText = ref<string>('');
const previewMode = ref<'preview' | 'sections' | 'raw'>('preview');

const reportMarkdown = computed(() => props.stageOutput?.report || '');
const sections = computed<Section[]>(() => {
  const o = props.stageOutput;
  if (!o) return [];
  if (Array.isArray(o.sections)) return o.sections;
  return [];
});

// 给每条 section 生成稳定 id
const getSectionId = (sec: Section, idx: number) => sec.id || sec.heading || `idx-${idx}`;

const toggleSection = (id: string) => {
  if (removedIds.value.has(id)) {
    removedIds.value.delete(id);
  } else {
    removedIds.value.add(id);
  }
  removedIds.value = new Set(removedIds.value);
  notifyEdits();
};

const isRemoved = (id: string) => removedIds.value.has(id);

// 编辑章节
const startEdit = (sec: Section) => {
  const id = getSectionId(sec, sections.value.indexOf(sec));
  editingSectionId.value = id;
  editingText.value = editedSections.value[id] ?? sec.content;
};

const saveEdit = () => {
  if (editingSectionId.value == null) return;
  editedSections.value = { ...editedSections.value, [editingSectionId.value]: editingText.value };
  editingSectionId.value = null;
  editingText.value = '';
  notifyEdits();
};

const cancelEdit = () => {
  editingSectionId.value = null;
  editingText.value = '';
};

// reset
watch(() => props.stageOutput, (v) => {
  if (v) {
    removedIds.value = new Set();
    editedSections.value = {};
    editingSectionId.value = null;
    editingText.value = '';
  }
}, { immediate: true });

// emit
const notifyEdits = () => {
  emit('update:userEdits', {
    edited_sections: Object.keys(editedSections.value).length > 0 ? editedSections.value : undefined,
    removed_section_ids: removedIds.value.size > 0 ? Array.from(removedIds.value) : undefined,
  });
};

// 简易 markdown 渲染(标题 + 段落 + 列表)
const renderMarkdown = (md: string) => {
  if (!md) return '';
  return md
    .split('\n\n')
    .map((para) => {
      const trimmed = para.trim();
      if (!trimmed) return '';
      // H1-H3
      const h3 = trimmed.match(/^###\s+(.*)/);
      if (h3) return `<h3>${h3[1]}</h3>`;
      const h2 = trimmed.match(/^##\s+(.*)/);
      if (h2) return `<h2>${h2[1]}</h2>`;
      const h1 = trimmed.match(/^#\s+(.*)/);
      if (h1) return `<h1>${h1[1]}</h1>`;
      // list
      if (/^[-*]\s+/.test(trimmed)) {
        return '<ul>' + trimmed.split('\n').map(l => {
          const m = l.match(/^[-*]\s+(.*)/);
          return m ? `<li>${m[1]}</li>` : '';
        }).join('') + '</ul>';
      }
      return `<p>${trimmed}</p>`;
    })
    .join('');
};
</script>

<template>
  <div>
    <!-- 视图切换 -->
    <el-radio-group v-model="previewMode" size="default" class="mode-switch">
      <el-radio-button value="preview">
        <el-icon><View /></el-icon> 预览
      </el-radio-button>
      <el-radio-button value="sections">
        <el-icon><Document /></el-icon> 章节编辑
      </el-radio-button>
      <el-radio-button value="raw">
        原始 Markdown
      </el-radio-button>
    </el-radio-group>

    <!-- 视图1: 预览 -->
    <div v-if="previewMode === 'preview'" class="preview-pane">
      <div v-if="!reportMarkdown" class="empty">
        <el-empty description="无报告内容" :image-size="80" />
      </div>
      <div v-else class="markdown-content" v-html="renderMarkdown(reportMarkdown)" />
    </div>

    <!-- 视图2: 章节编辑 -->
    <div v-else-if="previewMode === 'sections'">
      <div v-if="sections.length === 0" class="empty">
        <el-empty description="无章节结构" :image-size="80" />
      </div>
      <el-scrollbar :height="sections.length > 4 ? '320px' : 'auto'" class="sections-scroll">
        <div
          v-for="(sec, i) in sections"
          :key="getSectionId(sec, i)"
          class="section-card"
          :class="{ 'section-removed': isRemoved(getSectionId(sec, i)) }"
        >
          <el-checkbox
            :model-value="isRemoved(getSectionId(sec, i))"
            @change="toggleSection(getSectionId(sec, i))"
            class="section-checkbox"
          />
          <div class="section-content">
            <div class="section-head">
              <el-tag size="small" :type="sec.level === 1 ? 'danger' : sec.level === 2 ? 'warning' : 'info'" effect="light">
                H{{ sec.level || 2 }}
              </el-tag>
              <span class="section-heading">{{ sec.heading }}</span>
              <el-button
                text
                size="small"
                :icon="Edit"
                @click="startEdit(sec)"
              >
                编辑
              </el-button>
            </div>
            <div v-if="editingSectionId === getSectionId(sec, i)" class="section-edit-area">
              <el-input
                v-model="editingText"
                type="textarea"
                :rows="6"
                :maxlength="5000"
                show-word-limit
              />
              <div class="edit-actions">
                <el-button size="small" @click="cancelEdit">取消</el-button>
                <el-button size="small" type="primary" @click="saveEdit">保存</el-button>
              </div>
            </div>
            <div v-else class="section-body">
              {{ (editedSections[getSectionId(sec, i)] || sec.content).slice(0, 200) }}{{ (editedSections[getSectionId(sec, i)] || sec.content).length > 200 ? '…' : '' }}
              <el-tag v-if="editedSections[getSectionId(sec, i)]" size="small" type="success" effect="plain" class="edited-tag">
                已编辑
              </el-tag>
            </div>
          </div>
        </div>
      </el-scrollbar>
    </div>

    <!-- 视图3: 原始 markdown -->
    <div v-else class="raw-pane">
      <el-input
        :model-value="reportMarkdown"
        type="textarea"
        :rows="12"
        readonly
        class="raw-input"
      />
    </div>
  </div>
</template>

<style scoped>
.mode-switch {
  margin-bottom: 12px;
}

.preview-pane,
.raw-pane {
  border: 1px solid var(--scdc-bg-sunken, #e8e3d6);
  border-radius: 8px;
  background: var(--scdc-bg-elevated, #faf7f0);
  padding: 16px;
  margin-bottom: 12px;
  max-height: 360px;
  overflow-y: auto;
}

.markdown-content {
  font-size: 13px;
  line-height: 1.7;
  color: var(--scdc-ink, #333);
}

.markdown-content :deep(h1) {
  font-size: 18px;
  font-weight: 700;
  margin: 12px 0 8px;
  color: var(--scdc-accent, #b45309);
}

.markdown-content :deep(h2) {
  font-size: 16px;
  font-weight: 700;
  margin: 10px 0 6px;
  color: var(--scdc-accent, #b45309);
}

.markdown-content :deep(h3) {
  font-size: 14px;
  font-weight: 600;
  margin: 8px 0 4px;
  color: var(--scdc-ink, #333);
}

.markdown-content :deep(p) {
  margin: 6px 0;
}

.markdown-content :deep(ul) {
  margin: 6px 0;
  padding-left: 20px;
}

.markdown-content :deep(li) {
  margin: 2px 0;
}

.empty {
  display: flex;
  justify-content: center;
  padding: 20px 0;
}

.sections-scroll {
  border: 1px solid var(--scdc-bg-sunken, #e8e3d6);
  border-radius: 8px;
  background: var(--scdc-bg-elevated, #faf7f0);
  padding: 8px 12px;
  margin-bottom: 12px;
}

.section-card {
  display: flex;
  gap: 10px;
  padding: 10px 8px;
  margin-bottom: 8px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: #fff;
  transition: all 0.2s;
}

.section-card.section-removed {
  border-color: var(--scdc-danger, #f56c6c);
  background: #fef0f0;
  opacity: 0.7;
}

.section-checkbox {
  margin-top: 4px;
  flex-shrink: 0;
}

.section-content {
  flex: 1;
  min-width: 0;
}

.section-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.section-heading {
  font-size: 14px;
  font-weight: 600;
  color: var(--scdc-ink, #333);
  flex: 1;
  min-width: 0;
}

.section-body {
  font-size: 13px;
  line-height: 1.6;
  color: var(--scdc-ink-muted, #666);
  padding-left: 4px;
  border-left: 2px solid var(--scdc-bg-sunken, #e8e3d6);
}

.edited-tag {
  margin-left: 6px;
  vertical-align: middle;
}

.section-edit-area {
  margin-top: 6px;
}

.edit-actions {
  margin-top: 6px;
  display: flex;
  justify-content: flex-end;
  gap: 6px;
}

.raw-input :deep(textarea) {
  font-family: var(--scdc-font-mono, monospace);
  font-size: 12px;
  background: var(--scdc-bg-sunken, #f4f1e8);
}
</style>
