from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    secret_key: str = "supersecretkey"

    # JWT 配置
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    # 数据库与缓存
    postgres_dsn: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/scdc_db"
    async_postgres_dsn: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/scdc_db"
    redis_url: str = "redis://localhost:6379/0"

    # 邮件通知
    smtp_host: str = "smtp.example.com"
    smtp_port: int = 465
    smtp_user: str = "user@example.com"
    smtp_password: str = ""
    smtp_from_email: str = "noreply@example.com"

    # AI 模型与支撑组件
    ollama_base_url: str = "http://localhost:11434"
    default_model: str = "qwen2.5:latest"
    embedding_model: str = "nomic-embed-text"
    searxng_url: str = "http://localhost:8080"
    milvus_url: str = "http://localhost:19530"
    opensearch_url: str = "http://localhost:9200"
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "scdc-storage"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
