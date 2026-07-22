"""Service IA VIRELYON — service de décision STATELESS pour les agents (ARES…).

Sécurité : PAS de CORS (jamais appelé par un navigateur), authentification
service-à-service sur tous les endpoints métier (voir core/security.py).
"""
from fastapi import FastAPI

from app.api.v1.endpoints import health
from app.api.v1.router import api_router
from app.core.config import get_settings

app = FastAPI(
    title="virelyon-ai-service",
    version="0.1.0",
    description="Service de décision IA (ARES/APEX/AURA) — stateless, appelé par le backend.",
)

# Volontairement : aucun middleware CORS (accès server-à-server uniquement).

app.include_router(health.router)                 # GET /health (public)
app.include_router(api_router, prefix="/api/v1")  # /api/v1/ares, /api/v1/costs


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"service": "virelyon-ai", "env": get_settings().ai_env, "docs": "/docs"}
