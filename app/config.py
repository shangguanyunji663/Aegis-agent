from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///data/aegis.sqlite"
    ai_provider: str = "mock"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_provider: str = "openai"  # openai(兼容API) | local(chromadb 本地嵌入,零外部依赖)
    embedding_timeout_seconds: float = 30.0
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    llm_timeout_seconds: float = 15.0
    llm_thinking_enabled: bool = False
    llm_support_temperature: float = 0.6  # 支持性回复采样温度(偏高更像真人);风险/改写/评审仍固定 0.0
    risk_llm_channel_enabled: bool = True
    # QLoRA 风险增强通道:指向隔离 Transformers 推理服务(见 D:\AegisTraining\training\scripts\serve_risk_qlora.py)。
    # 开启后 RiskGuardian 的 LLM 通道改用微调模型;关闭则完全保持既有行为。
    risk_qlora_enabled: bool = False
    risk_qlora_url: str = "http://127.0.0.1:8301"
    risk_qlora_timeout_seconds: float = 8.0
    function_calling_enabled: bool = True
    langgraph_checkpoint_enabled: bool = True
    langgraph_checkpoint_path: str = "data/langgraph-checkpoints.sqlite"
    knowledge_dir: str = "knowledge"
    max_knowledge_upload_bytes: int = 1_000_000
    knowledge_top_k: int = 4
    knowledge_candidate_k: int = 16
    knowledge_chunk_size: int = 512
    knowledge_chunk_overlap: int = 64
    knowledge_hybrid_vector_weight: float = 0.65
    knowledge_hybrid_bm25_weight: float = 0.35
    knowledge_rerank_enabled: bool = True
    knowledge_fusion_mode: str = "weighted"  # weighted | rrf
    knowledge_cache_enabled: bool = False
    knowledge_cache_ttl_seconds: int = 300
    knowledge_cache_max_entries: int = 128
    rag_eval_dataset: str = "eval/fixtures/rag_queries.json"
    rag_eval_output: str = "data/eval/rag-eval-report.json"
    memory_recent_messages: int = 15
    memory_summary_max_chars: int = 3000
    vector_enabled: bool = False
    vector_required: bool = False
    vector_backend: str = "chroma"
    chroma_dir: str = "data/chroma"
    chroma_host: str = ""
    chroma_port: int = 8000
    chroma_collection_name: str = "aegis_knowledge"
    chroma_snapshot_dir: str = "data/chroma-snapshots"
    chroma_snapshot_keep: int = 5
    vector_top_k: int = 16
    redis_url: str = ""
    redis_lock_timeout_seconds: int = 30
    chat_rate_limit_per_minute: int = 40
    server_host: str = "127.0.0.1"
    server_port: int = 8091
    auth_session_cookie: str = "aegis_session"
    auth_session_ttl_hours: int = 24
    auth_default_admin_username: str = "admin"
    auth_default_admin_password: str = "admin123!"
    auth_default_student_username: str = "student"
    auth_default_student_password: str = "student123!"
    auth_teacher_invite_code: str = "aegis-teacher"
    slow_request_threshold_ms: int = 800
    tool_backend: str = "internal"
    tool_output_dir: str = "data/tool-outputs"
    excel_path: str = "data/tool-outputs/aegis-risk-ledger.xlsx"
    alert_email_delivery_mode: str = "log"
    alert_email_to: str = ""
    alert_email_from: str = ""
    alert_email_subject_prefix: str = "[Aegis 高风险预警]"
    alert_webhook_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    smtp_timeout_seconds: float = 10.0
    alert_email_rate_limit_per_minute: int = 10
    tool_queue_enabled: bool = True
    tool_queue_poll_interval_seconds: float = 2.0
    tool_queue_batch_size: int = 20
    tool_queue_worker_threads: int = 4
    tool_queue_retry_delay_seconds: float = 5.0
    mcp_enabled: bool = False
    agent_runtime: str = "autonomous"
    agent_max_rounds: int = 8
    agent_max_claims_per_round: int = 4
    agent_max_claims_per_agent: int = 3
    agent_final_acceptance_min_confidence: float = 0.6
    skill_distill_enabled: bool = True
    skill_distill_min_repeat: int = 3
    skill_distill_dir: str = "skills/auto"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    def resolve_path(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else self.project_root / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
