from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mistral_api_key: str
    database_url: str
    mistral_model: str = "mistral-large-latest"
    mistral_max_tokens: int = 1024
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384
    top_k_default: int = 5
    retrieval_strategy: str = "naive"
    bm25_k1: float = 1.5
    bm25_b: float = 0.75
    rrf_k: int = 60
    rerank_candidate_pool: int = 20
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    agent_max_tool_calls: int = 8
    agent_max_wall_clock_seconds: float = 60.0


settings = Settings()
