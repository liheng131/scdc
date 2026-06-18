"""
全局配置模块

使用 pydantic-settings 自动从 .env 文件和系统环境变量加载配置项。
所有模块通过 `from app.core.config import settings` 获取统一配置单例。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """应用全局配置，所有字段均可通过环境变量或 .env 文件覆盖"""

    # ===== 应用基础配置 =====
    app_env: str = "development"
    log_level: str = "INFO"
    secret_key: str = "supersecretkey"

    # ===== JWT 认证配置 =====
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 访问令牌有效期（默认 24 小时）

    # ===== 数据库与缓存 =====
    postgres_dsn: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/scdc_db"
    async_postgres_dsn: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/scdc_db"
    redis_url: str = "redis://localhost:6379/0"

    # ===== 邮件通知 =====
    smtp_host: str = "smtp.example.com"
    smtp_port: int = 465
    smtp_user: str = "user@example.com"
    smtp_password: str = ""
    smtp_from_email: str = "noreply@example.com"

    # ===== AI 模型与外部组件连接地址 =====
    ollama_base_url: str = "http://localhost:11434"    # Ollama 本地 LLM 推理服务
    default_model: str = "qwen2.5:latest"               # 默认大语言模型名称
    embedding_model: str = "nomic-embed-text"            # 向量嵌入模型名称
    llm_api_key: str = ""                                # LLM 服务 API Key（如 GPUStack）
    llm_provider: str = "ollama"                         # LLM 提供商：ollama 或 gpustack
    anysearch_api_key: str = ""                         # AnySearch 搜索引擎 API Key
    anysearch_base_url: str = "https://api.anysearch.com"  # AnySearch API base URL
    anysearch_default_max_results: int = 20             # AnySearch 单次请求默认返回数量
    anysearch_timeout: int = 15                          # AnySearch 请求默认超时（秒）
    milvus_url: str = "http://localhost:19530"           # Milvus 向量数据库
    opensearch_url: str = "http://localhost:9200"        # OpenSearch 全文搜索引擎
    minio_endpoint: str = "http://localhost:9000"        # MinIO 对象存储
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "scdc-storage"

    # 配置加载策略：优先读取 .env 文件，自动忽略未定义的环境变量
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# 全局单例配置实例
settings = Settings()
