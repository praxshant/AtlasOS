import os
from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Relational Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/atlasos"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40
    DB_STATEMENT_TIMEOUT_MS: int = 30000

    # Graph Database
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password123"

    # Vector Database
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_BATCH_SIZE: int = 100
    QDRANT_HNSW_M: int = 16
    QDRANT_HNSW_EF_CONSTRUCT: int = 100
    QDRANT_COLLECTION_NAME: str = "document_chunks"

    # Job Queue Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Large Language Models
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "openrouter/free"
    LLM_PROVIDER: str = "openrouter"
    
    # GraphRAG Settings
    NEO4J_MAX_DEPTH: int = 3
    NEO4J_MAX_PATH_LIMIT: int = 100

    # Hybrid Retrieval Settings
    VECTOR_WEIGHT: float = 0.6
    GRAPH_WEIGHT: float = 0.4
    ENABLE_QUERY_DECOMPOSITION: bool = True

    # Multi-Tenancy
    DEFAULT_TENANT_ID: str = "default"

    # Authentication Settings
    JWT_SECRET_KEY: str | None = None
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440 # 24 hours

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def check_jwt_secret(cls, v: str | None) -> str:
        if not v:
            raise ValueError("JWT_SECRET environment variable is required. Set it before starting the server. Generate one with: openssl rand -hex 32")
        return v

    # Upload and Security Settings
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]
    MAX_UPLOAD_SIZE_MB: int = 10
    ALLOWED_UPLOAD_EXTENSIONS: list[str] = [".pdf", ".docx", ".txt", ".log", ".csv", ".json", ".xlsx", ".xls", ".pptx", ".ppt"]
    
    # Embeddings
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-large-en-v1.5"

    # File uploads
    UPLOAD_DIR: str = "uploads"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../../.env"), 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    # Ensure upload directory exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    return settings
