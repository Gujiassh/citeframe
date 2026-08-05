from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


RetrievalStrategy = Literal["dense", "hybrid"]


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://ai_pdf:ai_pdf_dev@127.0.0.1:5432/ai_pdf_workspace"
    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "ai-pdf-workspace"
    minio_secure: bool = False
    max_upload_bytes: int = Field(default=1024 * 1024 * 100)
    worker_metrics_host: str = "127.0.0.1"
    worker_metrics_port: int = Field(default=9101, ge=1, le=65535)
    research_otel_service_name: str = Field(default="citeframe", min_length=1, max_length=128)
    research_otel_endpoint: str | None = None
    research_otel_export_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    api_internal_token: str = Field(
        default="local-development-internal-token",
        validation_alias=AliasChoices("AI_PDF_API_INTERNAL_TOKEN"),
        min_length=16,
    )
    capability_fingerprint_pepper: str = Field(
        default="local-development-capability-fingerprint-pepper",
        validation_alias=AliasChoices("AI_PDF_CAPABILITY_FINGERPRINT_PEPPER"),
        min_length=16,
    )

    embedding_provider: str = Field(default="openai", pattern="^(openai|ollama)$")
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = Field(default=1024, ge=1024, le=1024)
    embedding_version: str = "embedding-v1"
    embedding_batch_size: int = Field(default=32, ge=1, le=256)
    embedding_timeout_seconds: float = Field(default=120.0, gt=0)
    embedding_query_instruction: str = (
        "Given a user question, retrieve the most relevant PDF chunks that answer the question."
    )
    retrieval_strategy: RetrievalStrategy = Field(
        default="hybrid",
        validation_alias=AliasChoices("AI_PDF_RETRIEVAL_STRATEGY"),
    )
    retrieval_candidate_k: int = Field(default=10, ge=6, le=100)
    retrieval_rrf_constant: int = Field(default=60, ge=1, le=1000)

    generation_provider: str = Field(default="openai", pattern="^(openai|deepseek)$")
    generation_model: str = "gpt-5.5"
    generation_timeout_seconds: float = Field(default=120.0, gt=0)
    generation_max_output_tokens: int = Field(default=1200, ge=64, le=8192)

    image_caption_provider: str = Field(default="openai", pattern="^openai$")
    image_caption_model: str = "gpt-5.5"
    image_caption_version: str = "image-caption-v1"
    image_caption_detail: Literal["low", "high", "original", "auto"] = "high"
    image_caption_timeout_seconds: float = Field(default=120.0, gt=0)
    image_caption_max_output_tokens: int = Field(default=320, ge=64, le=2048)

    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AI_PDF_OPENAI_API_KEY", "OPENAI_API_KEY"),
    )
    openai_api_base: str = Field(
        default="https://api.openai.com/v1",
        validation_alias=AliasChoices("AI_PDF_OPENAI_API_BASE", "OPENAI_API_BASE"),
    )
    ollama_base_url: str = Field(
        default="http://127.0.0.1:11434",
        validation_alias=AliasChoices("AI_PDF_OLLAMA_BASE_URL", "OLLAMA_BASE_URL"),
    )
    deepseek_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AI_PDF_DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY"),
    )
    deepseek_api_base: str = Field(
        default="https://api.deepseek.com",
        validation_alias=AliasChoices("AI_PDF_DEEPSEEK_API_BASE", "DEEPSEEK_API_BASE"),
    )

    model_config = SettingsConfigDict(
        env_prefix="AI_PDF_",
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
