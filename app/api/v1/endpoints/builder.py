"""Endpoints de l'Agent Builder — alimentent l'écran de paramétrage du client.

Le service IA ne persiste rien : il fournit le vocabulaire, transforme du texte
libre en ICP structuré, et vérifie qu'un ICP peut réellement fonctionner.
C'est le backend qui enregistre le résultat dans `workspace_icp_config`.
"""
import anthropic
from fastapi import APIRouter, Depends, HTTPException

from app.builder import icp as icp_logic
from app.builder import plan_recherche as plan_logic
from app.core.security import verify_caller
from app.gateway.cost_tracker import CostLimitExceeded
from app.gateway.provider import LLMNotConfiguredError
from app.gateway.router import Gateway, get_gateway
from app.schemas.builder import (
    ICPExtraireRequest,
    ICPExtraireResponse,
    ICPValiderRequest,
    ICPValiderResponse,
    PlanRechercheRequest,
    PlanRechercheResponse,
    Referentiels,
)

router = APIRouter(prefix="/builder", tags=["builder"], dependencies=[Depends(verify_caller)])


def _llm_guard(coro):
    """Convertit les erreurs LLM en réponses HTTP propres (pas de 500 opaque)."""
    async def _run():
        try:
            return await coro
        except CostLimitExceeded as exc:
            raise HTTPException(status_code=429, detail=str(exc))
        except LLMNotConfiguredError as exc:
            raise HTTPException(status_code=503, detail=f"LLM non configuré : {exc}")
        except anthropic.APIError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Fournisseur LLM indisponible ({exc.__class__.__name__}).",
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=f"Réponse LLM invalide : {exc}")

    return _run()


@router.get("/referentiels", response_model=Referentiels)
def get_referentiels():
    """Vocabulaire normalisé du filtrage — alimente les listes déroulantes du front.

    Logique pure, aucun appel LLM. À appeler une fois au chargement de l'écran.
    """
    return icp_logic.referentiels()


@router.post("/icp/valider", response_model=ICPValiderResponse)
def valider_icp(req: ICPValiderRequest):
    """Vérifie qu'un ICP peut fonctionner : contradictions, valeurs hors référentiel,
    critères manquants, sélectivité excessive.

    Logique pure, aucun appel LLM — utilisable à chaque frappe côté front.
    """
    return icp_logic.valider_icp(req)


@router.post("/plan-recherche", response_model=PlanRechercheResponse)
def plan_recherche(req: PlanRechercheRequest):
    """ICP → requêtes prêtes à exécuter, par source de prospection.

    C'est le chaînon entre l'Agent Builder et le sourcing : sans lui, personne ne
    sait quoi chercher sur Google Maps ou Apollo.

    Logique pure, aucun appel LLM — un même ICP produit toujours le même plan.
    """
    return plan_logic.construire_plan(req)


@router.post("/icp/extraire", response_model=ICPExtraireResponse)
async def extraire_icp(req: ICPExtraireRequest, gw: Gateway = Depends(get_gateway)):
    """Transforme la description en langage normal du client en ICP structuré.

    Appel Claude (Sonnet). Le résultat est renormalisé sur le référentiel : ce qui
    n'a pas pu être rattaché ressort dans `non_reconnu` plutôt que d'être inventé.
    """
    return await _llm_guard(icp_logic.extraire_icp(gw, req))
