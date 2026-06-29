"""Windows 专用后端启动脚本

解决 Playwright 在 Windows 上的 NotImplementedError:
1. 强制设置 WindowsProactorEventLoopPolicy
2. 猴子补丁 asyncio.set_event_loop_policy, 阻止 uvicorn 重置为 SelectorEventLoop
3. 用 uvicorn.run 编程式启动, 使用 loop="asyncio"
4. 关闭 reload 以避免子进程 policy 问题

用法:
    python start_windows.py
"""
import asyncio
import sys
import os

# === 第一优先级: 设置事件循环策略 + 猴子补丁 ===
if sys.platform == "win32":
    from asyncio import WindowsSelectorEventLoopPolicy, WindowsProactorEventLoopPolicy

    # 保存原始的 set_event_loop_policy
    _original_set_policy = asyncio.set_event_loop_policy

    def _patched_set_policy(policy):
        """阻止 uvicorn 重置为 WindowsSelectorEventLoopPolicy"""
        if isinstance(policy, WindowsSelectorEventLoopPolicy):
            import logging
            logging.getLogger(__name__).warning(
                "[Windows]  Blocked uvicorn from resetting event loop policy to WindowsSelectorEventLoopPolicy"
            )
            return  # 忽略这次调用
        _original_set_policy(policy)

    # 应用猴子补丁
    asyncio.set_event_loop_policy = _patched_set_policy

    # 设置正确的策略
    asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())
    print("[start_windows] [OK] WindowsProactorEventLoopPolicy set")
    print("[start_windows] [OK] Monkey-patched asyncio.set_event_loop_policy to block SelectorEventLoop")

# === 第二优先级: 把 backend 加入 PYTHONPATH, 避免 ModuleNotFoundError ===
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
print(f"[start_windows] PYTHONPATH += {BACKEND_DIR}")

# === 第三优先级: 用 uvicorn.run 启动 ===
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")

    print(f"[start_windows] starting uvicorn on {host}:{port} (loop=asyncio)")
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        loop="asyncio",
        reload=False,
        log_level="info",
    )
