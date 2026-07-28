"""Every AI assistant service API router."""

from __future__ import annotations

from app.api.agents import router as agents_router
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.insights import router as insights_router
from app.api.knowledge import router as knowledge_router
from app.api.prompts import router as prompts_router

__all__ = [
    "agents_router",
    "chat_router",
    "health_router",
    "insights_router",
    "knowledge_router",
    "prompts_router",
]
