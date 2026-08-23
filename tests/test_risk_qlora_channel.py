"""QLoRA 风险增强通道接入测试:开关、回退、只升不降与 URL 防护。"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from app.agents.classic import RiskGuardianAgent
from app.config import Settings
from app.llm.client import MockLLMClient, RiskQloraClient
from app.models import RiskLevel
from app.skills import SkillRegistry


def _build_agent(tmp_path: Path, client, enabled: bool = True) -> RiskGuardianAgent:
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    (knowledge_dir / "crisis.md").write_text("自杀 轻生 危机干预", encoding="utf-8")
    registry = SkillRegistry(knowledge_dir, lambda report: None)
    return RiskGuardianAgent(registry, llm_client=client, llm_channel_enabled=enabled)


def _start_stub_server(responses: dict) -> tuple[HTTPServer, str]:
    """responses: message -> risk dict;未命中返回 None(解析失败场景)。"""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            message = json.loads(self.rfile.read(length).decode("utf-8"))["message"]
            out = responses.get(message)
            body = json.dumps({"risk_level": out and out["risk_level"],
                               "reason": out and out.get("reason", "")}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}"


def test_qlora_channel_upgrades_rules_to_high(tmp_path: Path):
    """隐喻高危:规则 low,QLoRA 判 high -> 只升不降融合为 high 并触发报告资格。"""
    message = "我好想让这一切永远地停下"
    server, url = _start_stub_server({message: {"risk_level": "high", "reason": "隐喻式暂停意愿"}})
    try:
        client = RiskQloraClient(MockLLMClient(), url=url, timeout=2.0)
        agent = _build_agent(tmp_path, client)
        result, level, _ = agent.assess(message)
        assert level is RiskLevel.HIGH
        assert result.output["risk_channels"]["llm"] == "high"
        assert result.output["report_eligible"] is True
    finally:
        server.shutdown()


def test_qlora_channel_never_downgrades_rules(tmp_path: Path):
    """规则已判 high,QLoRA 判 medium -> 维持 high(只升不降)。"""
    message = "我想结束自己的生命"  # 规则引擎必然命中 high
    server, url = _start_stub_server({message: {"risk_level": "medium", "reason": "误判"}})
    try:
        client = RiskQloraClient(MockLLMClient(), url=url, timeout=2.0)
        agent = _build_agent(tmp_path, client)
        _, level, _ = agent.assess(message)
        assert level is RiskLevel.HIGH
    finally:
        server.shutdown()


def test_qlora_service_down_falls_back_to_rules(tmp_path: Path):
    """服务不可达 -> 回退纯规则,不抛异常,通道标记 llm=skipped。"""
    client = RiskQloraClient(MockLLMClient(), url="http://127.0.0.1:1", timeout=0.2)
    agent = _build_agent(tmp_path, client)
    result, level, _ = agent.assess("今天心情不太好")
    assert level in {RiskLevel.LOW, RiskLevel.MEDIUM}
    assert result.output["risk_channels"]["llm"] == "skipped"


def test_qlora_invalid_payload_treated_as_fallback(tmp_path: Path):
    """服务返回非法 risk_level -> 视为通道失败,回退规则。"""
    message = "最近总是睡不好"
    server, url = _start_stub_server({message: {"risk_level": None, "reason": ""}})
    try:
        client = RiskQloraClient(MockLLMClient(), url=url, timeout=2.0)
        assert client.assess_risk(message) is None
        agent = _build_agent(tmp_path, client)
        result, _, _ = agent.assess(message)
        assert result.output["risk_channels"]["llm"] == "skipped"
    finally:
        server.shutdown()


def test_qlora_url_must_be_loopback():
    """SSRF 防护:非环回地址在构造期即拒绝。"""
    for bad in ("http://192.168.1.5:8301", "ftp://127.0.0.1:8301", "http://evil.example.com"):
        try:
            RiskQloraClient(MockLLMClient(), url=bad, timeout=1.0)
        except ValueError:
            continue
        raise AssertionError(f"should reject: {bad}")


def test_qlora_disabled_by_default():
    """默认关闭:未开启时行为与既有通道完全一致。"""
    settings = Settings()
    assert settings.risk_qlora_enabled is False
    assert settings.risk_qlora_url.startswith("http://127.0.0.1")
