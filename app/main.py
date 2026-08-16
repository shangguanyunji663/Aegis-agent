"""应用入口:装配所有依赖并注册路由与中间件。

路由实现分散在 app/api/ 下按领域拆分的模块中,
此处只负责:构建配置 → 数据库 → 仓储 → 技能/LLM/编排器 → 工具网关与队列,
再把它们挂到 app.state 供各路由通过请求上下文访问。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.agents.harness import AegisAgentHarness
from app.agents.orchestrator import PsychOrchestrator
from app.api import admin, auth_routes, chat, pages, system
from app.api.errors import register_exception_handlers
from app.api.middleware import attach_request_context
from app.config import Settings, get_settings
from app.core.runtime import RuntimeServices
from app.database import build_engine, build_session_factory, create_schema
from app.llm import build_llm_client
from app.repository import DatabaseStore
from app.services.tool_queue import ToolQueueWorker
from app.skills import SkillRegistry
from app.tools.gateway import build_tool_gateway

# 项目根目录与静态资源目录
ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "static"
# 应用日志记录器
logger = logging.getLogger("aegis.app")


def create_app(runtime_settings: Settings | None = None) -> FastAPI:
    settings = runtime_settings or get_settings()
    knowledge_dir = settings.resolve_path(settings.knowledge_dir)
    engine = build_engine(settings)
    session_factory = build_session_factory(settings)
    create_schema(engine)
    store = DatabaseStore(session_factory, settings=settings)
    store.ensure_default_users()
    store.seed_knowledge_dir(knowledge_dir)
    runtime = RuntimeServices(settings)
    registry = SkillRegistry(knowledge_dir, store.add_report, store.search_knowledge)
    llm_client = build_llm_client(settings)
    orchestrator = PsychOrchestrator(registry, store, llm_client)
    agent_harness = AegisAgentHarness(orchestrator, store)
    tool_gateway = build_tool_gateway(settings, store)
    tool_worker = ToolQueueWorker(settings, session_factory)

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI):
        tool_worker.start()
        try:
            yield
        finally:
            tool_worker.stop()

    app = FastAPI(title="Aegis Psych Agent", version="0.2.0", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.state.settings = settings
    app.state.engine = engine
    app.state.store = store
    app.state.registry = registry
    app.state.llm_client = llm_client
    app.state.orchestrator = orchestrator
    app.state.agent_harness = agent_harness
    app.state.runtime = runtime
    app.state.tool_gateway = tool_gateway
    app.state.tool_worker = tool_worker
    app.state.knowledge_dir = knowledge_dir

    app.middleware("http")(attach_request_context)
    register_exception_handlers(app)
    app.include_router(pages.router)
    app.include_router(system.router)
    app.include_router(auth_routes.router)
    app.include_router(chat.router)
    app.include_router(admin.router)
    return app


app = create_app()
