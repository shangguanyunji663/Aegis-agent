from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.config import Settings
from app.models import ReportStatus, UserRole


def build_client(tmp_path: Path, chat_rate_limit_per_minute: int = 40) -> TestClient:
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir(exist_ok=True)
    (knowledge_dir / "seed.md").write_text("考试压力 睡不着 焦虑 可以先稳定身体反应并拆分任务", encoding="utf-8")
    defaults = Settings(_env_file=None)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'api.sqlite'}",
        knowledge_dir=str(knowledge_dir),
        auth_default_admin_username=defaults.auth_default_admin_username,
        auth_default_admin_password=defaults.auth_default_admin_password,
        auth_default_student_username=defaults.auth_default_student_username,
        auth_default_student_password=defaults.auth_default_student_password,
        chat_rate_limit_per_minute=chat_rate_limit_per_minute,
        # 测试密封:固定自治运行时与本地依赖,断言不受 .env 影响
        agent_runtime="autonomous",
        redis_url="",
        vector_enabled=False,
    )
    app = create_app(settings)
    app.state.store.create_user("student2", "student234!", UserRole.STUDENT.value)
    return TestClient(app)


def login(client: TestClient, username: str, password: str) -> dict:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def test_readiness_and_auth_flow(tmp_path: Path):
    client = build_client(tmp_path)

    readiness = client.get("/api/readiness")
    assert readiness.status_code == 200
    assert readiness.json()["checks"]["database"] == "up"

    unauthenticated = client.get("/api/sessions")
    assert unauthenticated.status_code == 401

    payload = login(client, "student", "student123!")
    assert payload["user"]["role"] == "student"

    current = client.get("/api/auth/me")
    assert current.status_code == 200
    assert current.json()["user"]["username"] == "student"
    assert current.headers["X-Request-ID"].startswith("req-")
    assert current.headers["X-Trace-ID"].startswith("trace-")

    status = client.get("/api/agent/status")
    assert status.status_code == 200
    body = status.json()
    assert body["runtimeHarness"]["name"] == "AegisAgentHarness"
    assert body["agentFramework"]["scheduler"] == "claim-based-actor-runtime"
    assert any(agent["name"] == "SupervisorAgent" and agent["aliasOf"] == "LeadAgent" for agent in body["agents"])
    assert body["memory"]["durable"] == "sqlite"


def test_student_session_ownership_is_enforced(tmp_path: Path):
    student_client = build_client(tmp_path)
    login(student_client, "student", "student123!")
    created = student_client.post("/api/sessions", json={"title": "我的会话"})
    assert created.status_code == 200
    session_id = created.json()["session"]["id"]

    student_two = build_client(tmp_path)
    login(student_two, "student2", "student234!")
    forbidden = student_two.get(f"/api/sessions/{session_id}")
    assert forbidden.status_code == 403

    chat = student_client.post("/api/chat", json={"message": "我最近考试压力很大", "session_id": session_id})
    assert chat.status_code == 200
    assert chat.json()["session_id"] == session_id
    assert chat.json()["response_plan"]["mode"] in {"support", "research_support", "safety_template"}


def test_admin_endpoints_require_admin_role(tmp_path: Path):
    student_client = build_client(tmp_path)
    login(student_client, "student", "student123!")
    forbidden = student_client.get("/api/admin/reports")
    assert forbidden.status_code == 403

    admin_client = build_client(tmp_path)
    login(admin_client, "admin", "admin123!")
    allowed = admin_client.get("/api/admin/reports")
    assert allowed.status_code == 200


def test_admin_actions_write_audit_logs(tmp_path: Path):
    student_client = build_client(tmp_path)
    login(student_client, "student", "student123!")
    chat = student_client.post("/api/chat", json={"message": "我不想活了，想结束生命"})
    assert chat.status_code == 200

    admin_client = build_client(tmp_path)
    login(admin_client, "admin", "admin123!")
    reports = admin_client.get("/api/admin/reports").json()["reports"]
    report_id = reports[0]["id"]

    updated = admin_client.patch(f"/api/admin/reports/{report_id}", json={"status": ReportStatus.APPROVED.value})
    assert updated.status_code == 200

    audit_logs = admin_client.get("/api/admin/audit-logs")
    assert audit_logs.status_code == 200
    logs = audit_logs.json()["logs"]
    assert any(log["action"] == "update_report" and log["target_id"] == report_id for log in logs)


def test_chat_stream_emits_sse_events(tmp_path: Path):
    client = build_client(tmp_path)
    login(client, "student", "student123!")

    response = client.post("/api/chat/stream", json={"message": "我最近考试压力很大，晚上睡不着"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: start" in response.text
    assert "event: route" in response.text
    assert "event: skill" in response.text
    assert "event: token" in response.text
    assert "event: done" in response.text


def test_chat_rate_limit_falls_back_without_redis(tmp_path: Path):
    client = build_client(tmp_path, chat_rate_limit_per_minute=1)
    login(client, "student", "student123!")

    first = client.post("/api/chat", json={"message": "我最近考试压力很大"})
    second = client.post("/api/chat", json={"message": "我还是有点焦虑"})

    assert first.status_code == 200
    assert second.status_code == 429


def test_admin_knowledge_file_and_rebuild_vector_endpoints(tmp_path: Path):
    client = build_client(tmp_path)
    login(client, "admin", "admin123!")

    upload = client.post(
        "/api/admin/knowledge/file",
        files={"file": ("guide.txt", "人际冲突时，先描述事实再表达感受。".encode("utf-8"), "text/plain")},
    )
    assert upload.status_code == 200
    assert upload.json()["chunks"] >= 1

    rebuild = client.post("/api/admin/knowledge/rebuild-vector")
    assert rebuild.status_code == 200
    assert rebuild.json()["indexed_chunks"] >= 1
