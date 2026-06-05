# 修复前端登录 422 参数校验失败问题

## Summary
前端登录表单提交时报 422 参数校验失败。根因是 `AuthModal.vue` 调用 `auth.login()` 时传入了 2 个参数，但 `auth.ts` 的 `login()` 方法签名只接收 1 个 `Record<string, string>` 参数。

## Current State Analysis

**调用方** `AuthModal.vue` line 53:
```ts
await auth.login(loginForm.username, loginForm.password);
```
传了 2 个参数：`username` 和 `password` 两个独立字符串。

**被调用方** `auth.ts` line 28:
```ts
login: async (data: Record<string, string>): Promise<ApiResponse<LoginResponse>> => {
  const params = new URLSearchParams();
  for (const key in data) {
    params.append(key, data[key]);
  }
  ...
}
```
只接收 1 个参数 `data`（Record 对象）。

**结果**: `loginForm.username` (字符串 "admin") 被当作 `data`，`for (const key in data)` 遍历字符串的索引，生成 `params.append("0", "a")`、`params.append("1", "d")`... 而不是正确的 `username=admin&password=password`。

## Proposed Changes

### File: `frontend/src/components/account/AuthModal.vue`
**Line 53**: 修改调用方式，将两个参数合并为一个对象。

**Before**:
```ts
await auth.login(loginForm.username, loginForm.password);
```

**After**:
```ts
await auth.login({ username: loginForm.username, password: loginForm.password });
```

## Assumptions & Decisions
- `auth.ts` 的 API 设计是正确的，`AuthModal.vue` 的调用方式有误。
- 无需修改 `auth.ts`、`client.ts` 或后端代码。

## Verification Steps
1. 本地启动后端：`cd backend && uvicorn app.main:app --reload --port 8000`
2. 本地启动前端：`cd frontend && npm run dev`
3. 访问 `http://localhost:3000`，输入 admin/password 登录
4. 确认登录成功，不再报 422 错误
