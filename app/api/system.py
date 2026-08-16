"""系统状态路由:健康探活、依赖就绪检查、Agent 运行时状态与技能清单。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import current_principal
from app.core.auth import AuthPrincipal
from app.database import readiness_check

router = APIRouter()


@router.get("/api/health")
def health(request: Request) -> dict:
    state = request.app.state
    llm_client = state.llm_client
    settings = state.settings
    orchestrator = state.orchestrator
    return {
        "status": "UP",
        "provider": llm_client.provider,
        "llm": llm_client.status(),
        "agent_runtime": settings.agent_runtime,
        "agent_models": orchestrator.model_registry.status(),
    }


@router.get("/api/agent/status")
def agent_status(request: Request, principal: AuthPrincipal = Depends(current_principal)) -> dict:
    state = request.app.state
    settings = state.settings
    orchestrator = state.orchestrator
    agent_harness = state.agent_harness
    store = state.store
    tool_gateway = state.tool_gateway
    return {
        "runtimeHarness": {
            "name": agent_harness.name,
            "description": "统一管理输入脱敏、上下文注入、Agent runtime 调用、trace/report 输出和工具计划。",
        },
        "agentFramework": {
            "requested": settings.agent_runtime,
            "active": (
                (orchestrator.langgraph_runtime.framework_name if orchestrator.langgraph_runtime else "langgraph_unavailable")
                if settings.agent_runtime == "langgraph"
                else (orchestrator.autonomous_runtime.framework_name if settings.agent_runtime == "autonomous" else "ordered_runtime")
            ),
            "scheduler": {
                "langgraph": "langgraph-state-graph",
                "autonomous": "claim-based-actor-runtime",
            }.get(settings.agent_runtime, "ordered-runtime"),
            "langgraph": "enabled" if settings.agent_runtime == "langgraph" else "disabled_by_request",
            "maxRounds": settings.agent_max_rounds,
            "maxClaimsPerRound": settings.agent_max_claims_per_round,
            "state": {
                "langgraph": "typed-state-graph",
                "autonomous": "append-only-blackboard",  # Agent 的产出(artifact)以追加方式写入 blackboard
            }.get(settings.agent_runtime, "shared-context"),
        },
        "agents": [
            {"name": "MemoryAgent", "role": "session and private memory"},
            {"name": "SupervisorAgent", "aliasOf": "LeadAgent", "role": "intent routing"},
            {"name": "LeadAgent", "role": "intent routing"},  # 主导 Agent
            {"name": "RiskGuardianAgent", "role": "risk assessment and response safety review"},
            {"name": "KnowledgeAgent", "role": "RAG and standard skill context"},
            {"name": "CounselorAgent", "role": "support response planning"},
            {"name": "CompanionAgent", "role": "low-risk companion response planning"},
        ],
        "memory": store.memory_backend_status(),
        "models": orchestrator.model_registry.status(),
        "toolBackend": tool_gateway.backend,
        "toolQueue": {
            "enabled": settings.tool_queue_enabled,
            "mode": "background-worker" if settings.tool_queue_enabled else "manual",
            "pollIntervalSeconds": settings.tool_queue_poll_interval_seconds,
            "batchSize": settings.tool_queue_batch_size,
            "workerThreads": settings.tool_queue_worker_threads,
        },
        "viewer": principal.username,
        "role": principal.role,
    }


# 与 /api/health 的区别:health 只判断进程存活,readiness 判断依赖是否就绪。
@router.get("/api/readiness")
def readiness(request: Request) -> dict:
    state = request.app.state
    checks = {
        "database": "up" if readiness_check(state.engine) else "down",
        "redis": state.runtime.redis_status(),
        "vector": state.store.knowledge_status().get("vector_backend", "disabled"),
    }
    return {"status": "READY" if checks["database"] == "up" else "DEGRADED", "checks": checks}


@router.get("/api/skills")
def skills(request: Request) -> dict:
    registry = request.app.state.registry
    return {"skills": registry.schemas(), "standard_skills": registry.standard_skill_status()}
