# 修复 Nginx 容器不断重启问题

## 问题分析

Nginx 容器不断重启，entrypoint 脚本被反复执行。日志显示：
```
[entrypoint] Skipping 10-listen-on-ipv6-by-default.sh
[entrypoint] Launching /docker-entrypoint.d/20-envsubst-on-templates.sh
[entrypoint] Launching /docker-entrypoint.d/30-tune-worker-processes.sh
[entrypoint] Launching /docker-entrypoint.d/99-custom-entrypoint.sh
```
**最后一行"Launching 99-custom-entrypoint.sh"说明脚本在执行自己！**

### 根本原因

`entrypoint.sh` 第16-32行遍历所有 `/docker-entrypoint.d/*.sh` 脚本并执行，包括它自己（99-custom-entrypoint.sh）：

```bash
for f in /docker-entrypoint.d/*.sh; do
    case "$f" in
        */10-listen-on-ipv6-by-default.sh)
            continue
            ;;
        *)
            if [ -x "$f" ]; then
                "$f"  # ← 这里会执行自己！
            fi
            ;;
    esac
done
```

执行流程：
1. 容器启动执行 ENTRYPOINT: `/docker-entrypoint.d/99-custom-entrypoint.sh`
2. 脚本遍历所有 *.sh，遇到自己时再次执行
3. 子进程又遍历所有 *.sh，又执行自己...
4. 无限递归创建子进程，Nginx 无法正常启动

## 解决方案

### 方案：保持官方 ENTRYPOINT，只添加自定义脚本

**不需要覆盖 Nginx 官方 ENTRYPOINT！**

官方 `/docker-entrypoint.sh` 已经会自动执行 `/docker-entrypoint.d/` 下的所有脚本。我们只需要：

1. **Dockerfile 改动**：
   - 移除 `ENTRYPOINT ["/docker-entrypoint.d/99-custom-entrypoint.sh"]`
   - 保持官方 ENTRYPOINT（`/docker-entrypoint.sh`）
   - 保留 CMD（`["nginx", "-g", "daemon off;"]`）

2. **entrypoint.sh 改动**：
   - 移除最后的 `exec nginx -g "daemon off;"`（官方 entrypoint 会执行 CMD）
   - 移除遍历执行其他脚本的循环（官方 entrypoint 已经会执行）
   - 只保留跳过 IPv6 脚本的逻辑（如果需要）

### 具体修改

**文件：`frontend/Dockerfile`**
```dockerfile
# 删除第31行
# ENTRYPOINT ["/docker-entrypoint.d/99-custom-entrypoint.sh"]
```

**文件：`frontend/entrypoint.sh`**
```bash
#!/bin/sh
# 自定义 Nginx 入口脚本
# 
# 作用：跳过 IPv6 自动配置脚本
# 注意：此脚本被 Nginx 官方 entrypoint.sh 调用，不需要手动启动 nginx

# 跳过 IPv6 配置脚本
echo "[entrypoint] Skipping 10-listen-on-ipv6-by-default.sh (config already has listen directive)"
# 官方 entrypoint.sh 已经会跳过这个脚本（通过检查配置文件是否已有 listen 指令）
# 所以这个自定义脚本实际上可以什么都不做，或者只输出日志

echo "[entrypoint] Custom entrypoint script completed"
# 不需要 exec nginx，官方 entrypoint 会执行 CMD
```

实际上，Nginx 官方 entrypoint 的 `10-listen-on-ipv6-by-default.sh` 脚本已经智能检查：
- 如果配置文件已有 listen 指令，会自动跳过
- 日志中 "Skipping 10-listen-on-ipv6-by-default.sh (config already has listen directive)" 就是官方脚本输出的

所以**最简单的修复是：删除 entrypoint.sh 中遍历执行其他脚本的循环，只保留日志输出或直接删除自定义脚本**。

## 实施步骤

1. 修改 `frontend/entrypoint.sh`：移除循环执行其他脚本的逻辑和 `exec nginx`
2. 修改 `frontend/Dockerfile`：移除自定义 ENTRYPOINT 行
3. 重新构建前端 Docker 镜像
4. 重新启动服务
5. 验证容器正常运行且不再重复打印 entrypoint 日志
