# Fix Backend Unreachable 502 Checklist

- [x] docker-compose.yml 中 frontend depends_on 使用 `condition: service_healthy`
- [x] backend 服务有 healthcheck 配置（python urllib）
- [x] nginx.conf proxy_pass 路径正确处理
- [ ] 后端启动后 API 请求不再返回 502
- [ ] 容器重启后 DNS 自动解析新 IP
