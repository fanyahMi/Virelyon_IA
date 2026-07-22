"""Points de décision d'ARES appelant Claude (via la passerelle).

Chaque fonction : construit l'entrée JSON, appelle le bon tier, valide la sortie
structurée, et joint les métadonnées (modèle, tokens, coût).
"""
import json

from app.gateway.router import Gateway
from app.prompts.ares import (
    CLASSIFY_SYSTEM,
    DECIDE_SYSTEM,
    GENERATE_SYSTEM,
    QUALIFY_SYSTEM,
)
from app.schemas.ares import (
    Action,
    ClassifyRequest,
    ClassifyResponse,
    DecideRequest,
    DecideResponse,
    GenerateRequest,
    GenerateResponse,
    QualifyRequest,
    QualifyResponse,
)
from app.schemas.common import Meta, Usage

_ACTION_ALIASES = {
    "continuer": Action.continuer,
    "pause": Action.pause,
    "escalade": Action.escalade,
    "arrêt": Action.arret,
    "arret": Action.arret,
}


def _meta(info: dict) -> Meta:
    return Meta(
        model_used=info["model_used"],
        usage=Usage(input_tokens=info["input_tokens"], output_tokens=info["output_tokens"]),
        cost_estimate=info["cost"],
        cached=info.get("cached", False),
    )


def _dump(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


async def qualify(gw: Gateway, req: QualifyRequest) -> QualifyResponse:
    user = _dump({"lead": req.lead.model_dump(mode="json"), "icp": req.icp.model_dump()})
    data, info = await gw.complete_json("reasoning", QUALIFY_SYSTEM, user, req.workspace_id)
    return QualifyResponse(
        qualifie=bool(data["qualifie"]),
        confiance=float(data["confiance"]),
        motif=str(data.get("motif", "")),
        meta=_meta(info),
    )


async def generate(gw: Gateway, req: GenerateRequest) -> GenerateResponse:
    user = _dump(
        {
            "lead": req.lead.model_dump(mode="json"),
            "etape": req.etape,
            "ton_de_voix": req.ton_de_voix,
            "historique": req.historique,
            "langue": req.language,
        }
    )
    data, info = await gw.complete_json(
        "reasoning", GENERATE_SYSTEM, user, req.workspace_id, max_tokens=1500
    )
    return GenerateResponse(
        texte=str(data["texte"]),
        canal=str(data.get("canal", "email")),
        meta=_meta(info),
    )


async def classify(gw: Gateway, req: ClassifyRequest) -> ClassifyResponse:
    user = _dump({"message": req.message_entrant, "langue": req.language})
    data, info = await gw.complete_json("fast", CLASSIFY_SYSTEM, user, req.workspace_id)
    return ClassifyResponse(
        categorie=str(data["categorie"]),
        confiance=float(data["confiance"]),
        date_relance=data.get("date_relance"),
        meta=_meta(info),
    )


async def decide(gw: Gateway, req: DecideRequest) -> DecideResponse:
    # Garde-fou DÉTERMINISTE (§4.3.1 / §5.4) : plafond de relance atteint → arrêt,
    # sans appel LLM (gratuit, instantané, respecte toujours le plafond).
    if req.relances_effectuees >= req.palier.relances_max:
        return DecideResponse(
            action=Action.arret,
            justification=(
                f"Plafond de relance atteint ({req.relances_effectuees}/"
                f"{req.palier.relances_max}, palier {req.palier.nom}) — arrêt de la séquence."
            ),
            meta=None,
        )

    user = _dump(
        {
            "lead": req.lead.model_dump(mode="json"),
            "palier": req.palier.model_dump(),
            "relances_effectuees": req.relances_effectuees,
            "contexte": req.contexte,
        }
    )
    data, info = await gw.complete_json("reasoning", DECIDE_SYSTEM, user, req.workspace_id)
    action = _ACTION_ALIASES.get(str(data["action"]).strip().lower())
    if action is None:
        raise ValueError(f"action inconnue: {data.get('action')!r}")
    return DecideResponse(action=action, justification=str(data.get("justification", "")), meta=_meta(info))
