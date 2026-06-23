#!/bin/sh
# 自定义 Nginx 入口脚本
#
# 作用：禁用 Nginx 官方 entrypoint 的 IPv6 自动配置脚本
#       避免其在 default.conf 不存在时报警告或修改配置。
#
# 后续由官方 entrypoint 调用 CMD（nginx -g 'daemon off;'）启动 nginx。

# 临时禁用 10-listen-on-ipv6-by-default.sh（避免它处理 default.conf）
if [ -f /docker-entrypoint.d/10-listen-on-ipv6-by-default.sh ]; then
    mv /docker-entrypoint.d/10-listen-on-ipv6-by-default.sh \
       /docker-entrypoint.d/10-listen-on-ipv6-by-default.sh.disabled
fi

echo "[entrypoint] Custom configuration applied"
# 官方 entrypoint 会执行 CMD，不需要手动启动 nginx