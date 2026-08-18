"""Endpoints de l'agent ARES. Tous protégés par l'authentification service-à-service
(verify_caller) : seul le backend peut appeler."""
from fastapi import APIRouter, Depends

from app.ares import agents, scoring
from app.core.security import verify_caller
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


@router.post("/qualify", response_model=QualifyResponse)
async def qualify(req: QualifyRequest, gw: Gateway = Depends(get_gateway)):
    return await agents.qualify(gw, req)


@router.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest, gw: Gateway = Depends(get_gateway)):
    return await agents.generate(gw, req)


@router.post("/classify", response_model=ClassifyResponse)
async def classify(req: ClassifyRequest, gw: Gateway = Depends(get_gateway)):
    return await agents.classify(gw, req)


@router.post("/decide", response_model=DecideResponse)
async def decide(req: DecideRequest, gw: Gateway = Depends(get_gateway)):
    # Garde-fou déterministe (plafond de relance) sans LLM ; sinon décision via Claude.
    return await agents.decide(gw, req)


@router.post("/score", response_model=ScoreResponse)
async def score(req: ScoreRequest):
    # Logique pure — pas d'appel LLM.
    return scoring.compute_score(req)
