"""Endpoints de l'agent ARES. Tous protégés par l'authentification service-à-service
(verify_caller) : seul le backend peut appeler."""
import anthropic
from fastapi import APIRouter, Depends, HTTPException

from app.ares import agents, scoring
from app.core.security import verify_caller
from app.gateway.cost_tracker import CostLimitExceeded
from app.gateway.provider import LLMNotConfiguredError
from app.gateway.router import Gateway, get_gateway
from app.schemas.ares import (
    ClassifyRequest,
    ClassifyResponse,
    DecideRequest,
    DecideResponse,
    GenerateRequest,
    GenerateResponse,
    QualifyRequest,
    QualifyResponse,
    ScoreRequest,
    ScoreResponse,
)

router = APIRouter(prefix="/ares", tags=["ares"], dependencies=[Depends(verify_caller)])


def _llm_guard(coro):
    """Convertit les erreurs LLM en réponses HTTP propres (pas de 500 opaque)."""
    async def _run():
        try:
            return await coro
        except CostLimitExceeded as exc:
            raise HTTPException(status_code=429, detail=str(exc))
        except LLMNotConfiguredError as exc:
            raise HTTPException(status_code=503, detail=f"LLM non configuré : {exc}")
        except anthropic.APIError as exc:  # auth, rate limit, connexion, statut…
            raise HTTPException(
                status_code=503,
                detail=f"Fournisseur LLM indisponible ({exc.__class__.__name__}).",
            )
        except (KeyError, ValueError) as exc:  # JSON manquant / invalide
            raise HTTPException(status_code=502, detail=f"Réponse LLM invalide : {exc}")

    return _run()


@router.post("/qualify", response_model=QualifyResponse)
async def qualify(req: QualifyRequest, gw: Gateway = Depends(get_gateway)):
    return await _llm_guard(agents.qualify(gw, req))


@router.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest, gw: Gateway = Depends(get_gateway)):
    return await _llm_guard(agents.generate(gw, req))


@router.post("/classify", response_model=ClassifyResponse)
async def classify(req: ClassifyRequest, gw: Gateway = Depends(get_gateway)):
    return await _llm_guard(agents.classify(gw, req))


@router.post("/decide", response_model=DecideResponse)
async def decide(req: DecideRequest, gw: Gateway = Depends(get_gateway)):
    # Garde-fou déterministe (plafond de relance) sans LLM ; sinon décision via Claude.
    return await _llm_guard(agents.decide(gw, req))


@router.post("/score", response_model=ScoreResponse)
async def score(req: ScoreRequest):
    # Logique pure — pas d'appel LLM.
    return scoring.compute_score(req)
