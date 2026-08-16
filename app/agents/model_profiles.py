from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.llm import LLMClient, build_llm_client


DEFAULT_AGENT_MODEL_PROFILES = [
    {
        "agent_name": "MemoryAgent",
        "provider": "inherit",
        "model": "",
        "temperature": 0.0,
        "system_prompt": "Maintain compact non-diagnostic memory for this session.",
    },
    {
        "agent_name": "LeadAgent",
        "provider": "inherit",
        "model": "",
        "temperature": 0.0,
        "system_prompt": "Classify intent and route the user turn.",
    },
    {
        "agent_name": "RiskGuardianAgent",
        "provider": "inherit",
        "model": "",
        "temperature": 0.0,
        "system_prompt": "Assess safety risk and review responses before final acceptance.",
    },
    {
        "agent_name": "KnowledgeAgent",
        "provider": "inherit",
        "model": "",
        "temperature": 0.1,
        "system_prompt": "Gather memory, knowledge, grounding, and Skill constraints.",
    },
    {
        "agent_name": "CounselorAgent",
        "provider": "inherit",
        "model": "",
        "temperature": 0.2,
        "system_prompt": "Generate supportive psychological support responses.",
    },
    {
        "agent_name": "CompanionAgent",
        "provider": "inherit",
        "model": "",
        "temperature": 0.3,
        "system_prompt": "Generate direct low-risk companion responses.",
    },
]


@dataclass
class AgentModelRegistry:
    settings: Settings
    store: Any
    base_client: LLMClient

    def ensure_defaults(self) -> None:
        self.store.ensure_agent_model_profiles(DEFAULT_AGENT_MODEL_PROFILES)

    def profile_for(self, agent_name: str) -> dict:
        return self.store.get_agent_model_profile(agent_name)

    def client_for(self, agent_name: str) -> LLMClient:
        profile = self.profile_for(agent_name)
        provider = str(profile.get("provider") or "inherit").strip().lower()
        if provider in {"", "inherit"}:
            return self.base_client
        settings = self.settings.model_copy(update={
            "ai_provider": provider,
            "openai_model": profile.get("model") or self.settings.openai_model,
            "ollama_model": profile.get("model") or self.settings.ollama_model,
        })
        return build_llm_client(settings)

    def status(self) -> dict:
        return {
            "profiles": self.store.list_agent_model_profiles(),
            "base_provider": self.base_client.provider,
            "base_model": self.base_client.model,
        }
