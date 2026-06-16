from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://metricgraph:metricgraph@localhost:5432/metricgraph"
    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "metricgraph"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False

    # LLM via OpenRouter (OpenAI-compatible chat completions)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "openai/gpt-4o-mini"
    openrouter_site_url: str = "https://metricgraph.local"
    openrouter_app_name: str = "MetricGraph"

    # Embeddings (OpenRouter has no embeddings endpoint; use a separate
    # OpenAI-compatible provider. Leave the key empty to disable semantic
    # search and fall back to keyword-only search.)
    embedding_api_key: str = ""
    embedding_base_url: str | None = None
    embedding_model: str = "text-embedding-3-small"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    # Outbound integration hub (Slack/Teams/Linear bridge). Leave the URL empty
    # to disable event emission entirely.
    integration_webhook_url: str = ""
    integration_webhook_secret: str = ""

    # Optional Margin Catalog governance webhook (same envelope as integration hub).
    governance_webhook_url: str = ""
    governance_webhook_secret: str = ""


settings = Settings()
