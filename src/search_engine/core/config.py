"""Typed application settings loaded from environment variables.

Why it exists: database credentials and other config must not be hardcoded,
and the existing `.env` `DATABASE_URL` cannot be parsed safely because the
password contains `@`.

Responsibility: expose a single `settings` object. Build the async SQLAlchemy
URL from `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`.

Communicates with: `database.database` (reads `settings.database_url`) and
`core.security` (JWT secret and token lifetimes).
Does not talk to FastAPI routes or the LangGraph agent.
"""

from pathlib import Path
from urllib.parse import quote_plus

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime settings. Extra keys in `.env` (API keys, unused URL) are ignored."""

    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    gemini_api_key: SecretStr
    jwt_secret_key: str
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    jwt_algorithm: str = "HS256"
    rag_storage_dir: Path = _PROJECT_ROOT / "data" / "uploads"
    rag_max_upload_bytes: int = 10 * 1024 * 1024
    rag_max_docx_uncompressed_bytes: int = 100 * 1024 * 1024
    rag_pdf_boilerplate_min_pages: int = 3
    rag_pdf_boilerplate_page_ratio: float = 0.6
    rag_pdf_boilerplate_margin_ratio: float = 0.08
    rag_pdf_boilerplate_max_line_characters: int = 200
    rag_chunk_size: int = 1_000
    rag_chunk_overlap: int = 200
    rag_embedding_model: str = "models/gemini-embedding-001"
    rag_embedding_dimensions: int = 1_536
    rag_embedding_document_task_type: str = "RETRIEVAL_DOCUMENT"
    rag_embedding_query_task_type: str = "RETRIEVAL_QUERY"
    rag_embedding_normalize: bool = True
    rag_embedding_batch_size: int = 100
    rag_embedding_max_concurrency: int = 2
    rag_embedding_max_retries: int = 3
    rag_embedding_retry_base_seconds: float = 1.0
    rag_retrieval_top_k: int = 5
    rag_retrieval_max_top_k: int = 50
    rag_retrieval_max_query_characters: int = 2_000
    rag_retrieval_max_document_filters: int = 100
    rag_retrieval_default_min_similarity: float | None = None
    rag_answer_model: str = "gemini-3.5-flash-lite"
    rag_answer_temperature: float = 0.0
    rag_answer_timeout_seconds: float = 45.0
    rag_answer_max_retries: int = 2
    rag_answer_max_output_tokens: int = 1_024
    rag_answer_max_input_tokens: int = 8_192
    rag_answer_max_context_tokens: int = 6_000
    rag_answer_token_margin: int = 256
    rag_answer_max_sources: int = 8
    rag_answer_evidence_excerpt_characters: int = 320

    def _postgres_url(self, driver: str) -> str:
        password = quote_plus(self.db_password)
        return (
            f"{driver}://{self.db_user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def database_url(self) -> str:
        """Async PostgreSQL URL with the password percent-encoded."""
        return self._postgres_url("postgresql+asyncpg")

    @property
    def sync_database_url(self) -> str:
        """Sync PostgreSQL URL for Alembic migrations."""
        return self._postgres_url("postgresql+psycopg")


settings = Settings()
