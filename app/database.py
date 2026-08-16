from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(database_url: str) -> dict:
    kwargs = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    if database_url.startswith("mysql"):
        # MySQL 闲置 wait_timeout(默认 8h)后会断连,定期回收避免 "server has gone away"
        kwargs["pool_recycle"] = 3600
    return kwargs


def _ensure_mysql_database(database_url: str) -> None:
    """mysql URL 时自动创建目标库(utf8mb4),首次启动免手工建库。"""
    import pymysql
    from urllib.parse import urlparse

    parsed = urlparse(database_url)
    dbname = (parsed.path or "/").lstrip("/").split("?")[0]
    if not dbname:
        return
    conn = pymysql.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 3306,
        user=parsed.username or "root",
        password=parsed.password or "",
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{dbname}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
    finally:
        conn.close()


settings = get_settings()


def resolve_database_url(runtime_settings=None) -> str:
    current_settings = runtime_settings or settings
    if current_settings.database_url.startswith("sqlite:///"):
        path = current_settings.resolve_path(current_settings.database_url.removeprefix("sqlite:///"))
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path}"
    return current_settings.database_url


def build_engine(runtime_settings=None):
    resolved_url = resolve_database_url(runtime_settings)
    if resolved_url.startswith("mysql"):
        _ensure_mysql_database(resolved_url)
    return create_engine(resolved_url, **_engine_kwargs(resolved_url))


def build_session_factory(runtime_settings=None):
    return sessionmaker(bind=build_engine(runtime_settings), autoflush=False, autocommit=False)


def create_schema(bind_engine=None) -> None:
    from app import entities  # noqa: F401

    runtime_engine = bind_engine or build_engine()
    Base.metadata.create_all(bind=runtime_engine)
    migrate_legacy_schema(runtime_engine)


def readiness_check(bind_engine=None) -> bool:
    runtime_engine = bind_engine or build_engine()
    with runtime_engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True


def migrate_legacy_schema(bind_engine) -> None:
    inspector = inspect(bind_engine)
    if bind_engine.dialect.name != "sqlite":
        return
    if "chat_sessions" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("chat_sessions")}
        if "owner_user_public_id" not in columns:
            with bind_engine.begin() as connection:
                connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN owner_user_public_id VARCHAR(64) DEFAULT ''"))
    if "knowledge_chunks" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("knowledge_chunks")}
        if "embedding_json" not in columns:
            with bind_engine.begin() as connection:
                connection.execute(text("ALTER TABLE knowledge_chunks ADD COLUMN embedding_json TEXT DEFAULT '[]'"))
        if "metadata_json" not in columns:
            with bind_engine.begin() as connection:
                connection.execute(text("ALTER TABLE knowledge_chunks ADD COLUMN metadata_json TEXT DEFAULT '{}'"))
    existing_tables = set(inspector.get_table_names())
    if "agent_private_memories" not in existing_tables:
        with bind_engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE agent_private_memories ("
                "id INTEGER PRIMARY KEY, "
                "agent_name VARCHAR(80), "
                "session_public_id VARCHAR(64), "
                "content TEXT, "
                "metadata_json TEXT DEFAULT '{}', "
                "created_at DATETIME)"
            ))
            connection.execute(text("CREATE INDEX ix_agent_private_memories_agent_name ON agent_private_memories (agent_name)"))
            connection.execute(text("CREATE INDEX ix_agent_private_memories_session_public_id ON agent_private_memories (session_public_id)"))
    if "agent_model_profiles" not in existing_tables:
        with bind_engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE agent_model_profiles ("
                "id INTEGER PRIMARY KEY, "
                "agent_name VARCHAR(80) UNIQUE, "
                "provider VARCHAR(32) DEFAULT 'inherit', "
                "model VARCHAR(128) DEFAULT '', "
                "temperature FLOAT DEFAULT 0.2, "
                "system_prompt TEXT DEFAULT '', "
                "enabled VARCHAR(8) DEFAULT 'true', "
                "created_at DATETIME, "
                "updated_at DATETIME)"
            ))
            connection.execute(text("CREATE INDEX ix_agent_model_profiles_agent_name ON agent_model_profiles (agent_name)"))
    if "tool_audit_records" not in existing_tables:
        with bind_engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE tool_audit_records ("
                "id INTEGER PRIMARY KEY, "
                "public_id VARCHAR(64) UNIQUE, "
                "tool_kind VARCHAR(80), "
                "action VARCHAR(80), "
                "decision VARCHAR(32), "
                "reason TEXT DEFAULT '', "
                "actor_role VARCHAR(32) DEFAULT '', "
                "risk_level VARCHAR(32) DEFAULT '', "
                "report_public_id VARCHAR(64) DEFAULT '', "
                "case_public_id VARCHAR(64) DEFAULT '', "
                "job_public_id VARCHAR(64) DEFAULT '', "
                "payload_json TEXT DEFAULT '{}', "
                "created_at DATETIME)"
            ))
            connection.execute(text("CREATE INDEX ix_tool_audit_records_public_id ON tool_audit_records (public_id)"))
            connection.execute(text("CREATE INDEX ix_tool_audit_records_tool_kind ON tool_audit_records (tool_kind)"))
            connection.execute(text("CREATE INDEX ix_tool_audit_records_decision ON tool_audit_records (decision)"))
    if "dead_letter_records" not in existing_tables:
        with bind_engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE dead_letter_records ("
                "id INTEGER PRIMARY KEY, "
                "public_id VARCHAR(64) UNIQUE, "
                "job_public_id VARCHAR(64), "
                "tool_kind VARCHAR(80), "
                "reason TEXT DEFAULT '', "
                "payload_json TEXT DEFAULT '{}', "
                "created_at DATETIME)"
            ))
            connection.execute(text("CREATE INDEX ix_dead_letter_records_public_id ON dead_letter_records (public_id)"))
            connection.execute(text("CREATE INDEX ix_dead_letter_records_job_public_id ON dead_letter_records (job_public_id)"))
            connection.execute(text("CREATE INDEX ix_dead_letter_records_tool_kind ON dead_letter_records (tool_kind)"))
    if "tool_jobs" in existing_tables:
        columns = {column["name"] for column in inspector.get_columns("tool_jobs")}
        if "run_after" not in columns:
            with bind_engine.begin() as connection:
                connection.execute(text("ALTER TABLE tool_jobs ADD COLUMN run_after DATETIME"))
                connection.execute(text("UPDATE tool_jobs SET run_after = COALESCE(updated_at, created_at) WHERE run_after IS NULL"))
    if "excel_records" not in existing_tables:
        with bind_engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE excel_records ("
                "id INTEGER PRIMARY KEY, "
                "public_id VARCHAR(64) UNIQUE, "
                "report_public_id VARCHAR(64) DEFAULT '', "
                "case_public_id VARCHAR(64) DEFAULT '', "
                "file_path TEXT DEFAULT '', "
                "status VARCHAR(32) DEFAULT '', "
                "message TEXT DEFAULT '', "
                "payload_json TEXT DEFAULT '{}', "
                "created_at DATETIME, "
                "updated_at DATETIME)"
            ))
            connection.execute(text("CREATE INDEX ix_excel_records_public_id ON excel_records (public_id)"))
            connection.execute(text("CREATE INDEX ix_excel_records_report_public_id ON excel_records (report_public_id)"))
            connection.execute(text("CREATE INDEX ix_excel_records_case_public_id ON excel_records (case_public_id)"))
            connection.execute(text("CREATE INDEX ix_excel_records_status ON excel_records (status)"))
    if "alert_records" not in existing_tables:
        with bind_engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE alert_records ("
                "id INTEGER PRIMARY KEY, "
                "public_id VARCHAR(64) UNIQUE, "
                "report_public_id VARCHAR(64) DEFAULT '', "
                "case_public_id VARCHAR(64) DEFAULT '', "
                "channel VARCHAR(32) DEFAULT '', "
                "recipient TEXT DEFAULT '', "
                "status VARCHAR(32) DEFAULT '', "
                "message TEXT DEFAULT '', "
                "payload_json TEXT DEFAULT '{}', "
                "created_at DATETIME, "
                "updated_at DATETIME)"
            ))
            connection.execute(text("CREATE INDEX ix_alert_records_public_id ON alert_records (public_id)"))
            connection.execute(text("CREATE INDEX ix_alert_records_report_public_id ON alert_records (report_public_id)"))
            connection.execute(text("CREATE INDEX ix_alert_records_case_public_id ON alert_records (case_public_id)"))
            connection.execute(text("CREATE INDEX ix_alert_records_channel ON alert_records (channel)"))
            connection.execute(text("CREATE INDEX ix_alert_records_status ON alert_records (status)"))
