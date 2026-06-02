# Fix Nginx Error Logs Checklist

- [x] nginx.conf 中添加了 Docker DNS resolver (127.0.0.11)
- [x] nginx.conf 中添加了 proxy_next_upstream 重试机制
- [x] nginx.conf 中添加了 proxy_connect_timeout 快速失败
- [x] 自定义 entrypoint.sh 已创建（如需要）
- [x] frontend/Dockerfile 已更新使用自定义入口脚本（如需要）
- [ ] 容器重建后无 "can not modify" 警告（如实现了 entrypoint.sh）
- [ ] 后端启动完成后 API 请求正常，无持续 502 错误
