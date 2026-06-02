#!/bin/sh
# 自定义 Nginx 入口脚本
#
# 作用：自定义启动日志
# 注意：此脚本被 Nginx 官方 entrypoint.sh 调用，不需要手动启动 nginx

echo "[entrypoint] Custom configuration applied"

# 不需要 exec nginx，官方 entrypoint 会执行 CMD
