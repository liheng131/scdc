/**
 * Vite 类型声明文件
 *
 * 为 Vite 构建工具和 Vue SFC（单文件组件）提供 TypeScript 类型支持。
 * 声明 .vue 文件模块类型，使 TypeScript 能够正确识别 .vue 文件的导入。
 *
 * /// <reference types="vite/client" /> 引入 Vite 客户端的全局类型定义，
 * 包括 import.meta.env 等 Vite 特有 API 的类型提示。
 */
/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}
