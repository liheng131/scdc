"""
Pydantic 数据校验与序列化模块

每个 schema 文件定义对应业务实体的输入/输出/更新数据结构。
使用 Pydantic v2 的 BaseModel，自动完成请求体的 JSON 解析、验证和序列化。

为什么分离 schemas 和 models：
- models 关注数据库层（SQLAlchemy ORM 映射）
- schemas 关注 API 层（HTTP 请求/响应的数据结构）
- 两者职责分离，避免数据库细节泄露到 API 契约中
"""
