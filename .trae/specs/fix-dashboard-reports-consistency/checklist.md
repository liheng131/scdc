# 仪表盘与智能报告页数据一致性 - 验证清单

- [x] 后端 GET /api/v1/reports 返回结构包含 `data.items` 和 `data.total`
- [x] 后端返回的报告按 created_at DESC 排序
- [x] 仪表盘"智能产出报告"数字与 reports 表总行数一致
- [x] 仪表盘"最新生成的行研报告"列表与 ReportsView 第一页内容完全一致
- [x] ReportsView 分页信息 total 正确
- [x] ReportsView 报告列表顺序与仪表盘一致
- [x] 前端无编译错误
- [x] 后端无启动错误