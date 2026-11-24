from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    # Per-agent / per-purpose model routing: simple wording tasks on the cheaper model, reasoning on OPENAI_MODEL.
    llm_routes: dict[str, str] = {"classification": "gpt-4.1-nano", "plan_question": "gpt-4.1-nano",
                                  "kb_query_rewrite": "gpt-4.1-nano", "kb_query_classification": "gpt-4.1-nano"}
    # USD per 1M tokens: [input, cached input, output]. Check https://openai.com/api/pricing before relying on totals.
    llm_prices: dict[str, list[float]] = {"gpt-4.1-mini": [0.40, 0.10, 1.60], "gpt-4.1-nano": [0.10, 0.03, 0.40],
                                          "gpt-4o-mini": [0.15, 0.075, 0.60], "gpt-5-mini": [0.25, 0.025, 2.00],
                                          "gpt-5-nano": [0.05, 0.005, 0.40]}
    database_url: str = "postgresql+psycopg://rera:rera@localhost:5432/rera"
    # Requirements below this confidence are flagged for human attention.
    # Embeddings: local and free by default (MIT-licensed, 384 dimensions); "openai" uses text-embedding-3-small (1536)
    embedding_provider: Literal["local", "openai"] = "local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    # Knowledge-base retrieval
    reranker: Literal["cross_encoder", "llm", "none"] = "cross_encoder"
    reranker_model: str = "BAAI/bge-reranker-base"
    kb_query_rewrite: bool = True
    # Retrieval-grounded generation: outputs below this combined confidence are escalated for human review
    grounding_confidence_threshold: float = 0.6
    confidence_threshold: float = 0.7
    cors_origins: list[str] = ["http://localhost:5173"]
    # Agent workflow
    max_clarification_rounds: int = 2
    interview_max_turns: int = 30
    interview_max_follow_ups: int = 2  # per topic
    baseline_owner_role: str = "product_owner"
    # Step 14: the project manager, architect, security team and compliance officer approve the SDLC choice.
    sdlc_approvers: list[str] = ["project_manager", "architect_developer", "infosec", "compliance_legal"]
    # Step 15/16: who approves the generated workflow, and who decides production readiness (go / no-go).
    workflow_approvers: list[str] = ["project_manager", "infosec", "compliance_legal"]
    readiness_approvers: list[str] = ["project_manager", "operations", "infosec", "compliance_legal"]
    # Step 16: changes to an approved baseline always need the baseline owner and the project manager.
    change_approvers: list[str] = ["product_owner", "project_manager"]

    # ---------- Step 17: platform security ----------
    # Encryption at rest (AES-256-GCM): sensitive columns and LangGraph checkpoints. See app/security/crypto.py.
    data_encryption_key: str = ""
    data_encryption_old_keys: str = ""
    # Identity and sessions
    mfa_required: bool = True
    session_idle_minutes: int = 30
    session_max_hours: int = 8
    cookie_secure: bool = False  # set true when served over HTTPS (always in production)
    expose_api_docs: bool = True  # /docs and /openapi.json without sign-in; disable in production
    # Encryption in transit: HSTS is sent when the API is served over HTTPS
    hsts_max_age: int = 31536000
    # Data retention (days); a project on legal hold is never purged
    retention_auth_sessions_days: int = 30
    retention_project_after_archive_days: int = 365
    retention_checkpoints_after_completion_days: int = 90
    retention_review_queue_days: int = 730
    retention_embedding_cache_days: int = 180
    retention_audit_days: int = 2920  # 8 years
    retention_llm_calls_days: int = 2920  # prompts and evidence are audit records (step 20)
    # Model versioning: pin dated model snapshots in production (e.g. gpt-4.1-mini-2025-04-14)
    model_pinning_required: bool = False

    @property
    def checkpoint_db_url(self) -> str:
        """Plain libpq URL for the LangGraph Postgres checkpointer (no SQLAlchemy driver suffix)."""
        return self.database_url.replace("+psycopg", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
