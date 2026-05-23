"""
业务服务层模块

封装数据库操作和第三方服务调用，为 API 路由（api/routes/）提供业务逻辑。
每个 Service 类是一个无状态的服务单元，通过依赖注入方式获取数据库会话（AsyncSession）。

为什么分离 Service 层：
- API 路由只处理 HTTP 请求/响应，不直接操作数据库
- Service 封装 CRUD 逻辑，便于单元测试和复用
- 多个路由可共享同一 Service（如 TaskService 被 scheduler、trigger 等多个模块引用）
"""
