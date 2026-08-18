"""Service IA VIRELYON — service de décision STATELESS pour les agents (ARES…).

Sécurité : PAS de CORS (jamais appelé par un navigateur), authentification
service-à-service sur tous les endpoints métier (voir core/security.py).
"""
import anthropic
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.v1.endpoints import health
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.gateway.cost_tracker import CostLimitExceeded
from app.gateway.provider import LLMNotConfiguredError, ReponseLLMInvalide

app = FastAPI(
    title="virelyon-ai-service",
    version="0.1.0",
    description="Service de décision IA (ARES/APEX/AURA) — stateless, appelé par le backend.",
)

# Volontairement : aucun middleware CORS (accès server-à-server uniquement).

app.include_router(health.router)                 # GET /health (public)
app.include_router(api_router, prefix="/api/v1")  # /api/v1/ares, /api/v1/costs


# --- Erreurs LLM → statuts HTTP, une seule fois pour tout le service ---------
# Enregistré ici plutôt qu'enveloppé endpoint par endpoint : tout futur endpoint
# passant par la passerelle est protégé sans rien faire, et il n'y a plus de
# wrapper à ne pas oublier.
def _erreur(code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=code, content={"detail": detail})


@app.exception_handler(CostLimitExceeded)
async def _plafond_atteint(_: Request, exc: CostLimitExceeded) -> JSONResponse:
    return _erreur(429, str(exc))


@app.exception_handler(LLMNotConfiguredError)
async def _llm_non_configure(_: Request, exc: LLMNotConfiguredError) -> JSONResponse:
    return _erreur(503, f"LLM non configuré : {exc}")


@app.exception_handler(anthropic.APIError)
async def _llm_indisponible(_: Request, exc: anthropic.APIError) -> JSONResponse:
    return _erreur(503, f"Fournisseur LLM indisponible ({exc.__class__.__name__}).")


@app.exception_handler(ReponseLLMInvalide)
async def _reponse_llm_invalide(_: Request, exc: ReponseLLMInvalide) -> JSONResponse:
    return _erreur(502, f"Réponse LLM invalide : {exc}")


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"service": "virelyon-ai", "env": get_settings().ai_env, "docs": "/docs"}
