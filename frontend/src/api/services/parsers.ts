/**
 * 解析器 API 服务
 *
 * 封装文件上传和解析相关的接口。
 * - uploadFile: 单文件上传与解析
 * - batchUpload: 多文件批量上传与解析
 */
import apiClient, { type ApiResponse } from '../client';

export interface UploadFileResponse {
  attachment_id: string;
  filename: string;
  file_type: string;
  file_size: number;
  file_hash: string;
  parsed: boolean;
  reused: boolean;
}

export interface BatchUploadSuccessItem {
  attachment_id: string;
  filename: string;
  file_type: string;
  file_size: number;
  file_hash: string;
  parsed: boolean;
  reused: boolean;
}

export interface BatchUploadFailedItem {
  filename: string;
  error: string;
}

export interface BatchUploadResponse {
  success: BatchUploadSuccessItem[];
  failed: BatchUploadFailedItem[];
  attachment_ids: string[];
}

export const parsersApi = {
  uploadFile: async (
    file: File,
    onProgress?: (percent: number) => void,
  ): Promise<ApiResponse<UploadFileResponse>> => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await apiClient.post('/api/v1/parsers/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        if (onProgress && e.total) {
          onProgress(Math.round((e.loaded * 100) / e.total));
        }
      },
    });
    return res.data;
  },

  batchUpload: async (
    files: File[],
    onFileProgress?: (filename: string, percent: number) => void,
  ): Promise<ApiResponse<BatchUploadResponse>> => {
    // 一次只支持一个文件的上传进度(axios onUploadProgress 是总进度)。
    // 多文件场景: 串行上传,逐文件报告进度,符合成熟 AI 平台的体验。
    const success: BatchUploadSuccessItem[] = [];
    const failed: BatchUploadFailedItem[] = [];
    const attachment_ids: string[] = [];

    for (const file of files) {
      // 模拟进度动画: 小文件上传太快,浏览器 onUploadProgress 来不及触发多次回调,
      // 用 requestAnimationFrame 模拟 0→80% 的平滑进度,真实完成时跳到 100%。
      let simulatedPercent = 0;
      let uploadDone = false;
      const animateProgress = () => {
        if (uploadDone) return;
        // 非线性增速: 前段快、后段慢,模拟真实上传体验
        const step = Math.max(1, Math.round((80 - simulatedPercent) * 0.08));
        simulatedPercent = Math.min(simulatedPercent + step, 80);
        onFileProgress?.(file.name, simulatedPercent);
        if (simulatedPercent < 80) {
          requestAnimationFrame(animateProgress);
        }
      };
      requestAnimationFrame(animateProgress);

      try {
        onFileProgress?.(file.name, 0);
        const res = await apiClient.post<ApiResponse<UploadFileResponse>>(
          '/api/v1/parsers/upload',
          (() => {
            const fd = new FormData();
            fd.append('file', file);
            return fd;
          })(),
          {
            headers: { 'Content-Type': 'multipart/form-data' },
            onUploadProgress: (e) => {
              if (e.total) {
                const realPercent = Math.round((e.loaded * 100) / e.total);
                // 真实进度超过模拟进度时才更新(避免倒退)
                if (realPercent > simulatedPercent) {
                  simulatedPercent = realPercent;
                  onFileProgress?.(file.name, realPercent);
                }
              }
            },
          },
        );
        uploadDone = true;
        const data = res.data.data;
        if (data) {
          success.push(data);
          attachment_ids.push(data.attachment_id);
          onFileProgress?.(file.name, 100);
        }
      } catch (e: any) {
        uploadDone = true;
        const msg = e?.response?.data?.detail || e?.message || 'Upload failed';
        failed.push({ filename: file.name, error: msg });
        onFileProgress?.(file.name, -1); // -1 表示失败
      }
    }

    return {
      code: failed.length === 0 ? 0 : 1,
      msg: failed.length === 0 ? 'ok' : 'partial',
      data: { success, failed, attachment_ids },
    };
  },
};
