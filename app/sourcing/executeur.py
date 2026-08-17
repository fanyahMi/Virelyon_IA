"""Exécution d'un plan de recherche : requêtes → leads bruts.

Enchaîne trois étapes :
1. construire le plan (`builder/plan_recherche.py`) ;
2. exécuter chaque source via son connecteur — ou la simuler en `dry_run` ;
3. écarter les leads dont le secteur est explicitement exclu par l'ICP.

Ce qu'on ne fait PAS ici : qualifier, scorer, persister. Le sourcing ramène de la
matière ; le jugement reste aux endpoints ARES.
"""
from __future__ import annotations

import httpx

from app.builder.plan_recherche import construire_plan
from app.builder.referentiels import canoniser_secteur
from app.core.config import get_settings
from app.schemas.ares import Lead
from app.schemas.builder import BlocRecherche, Diagnostic, PlanRechercheRequest
from app.schemas.sourcing import (
    ExecuterPlanRequest,
    ExecuterPlanResponse,
    ResultatSource,
)
from app.sourcing.apollo import Apollo
from app.sourcing.base import Connecteur, SourceNonConfiguree
from app.sourcing.places import Places

# Sources non encore branchées — déclarées explicitement plutôt que silencieuses.
NON_IMPLEMENTES = {
    "hunter": "Enrichissement d'email : à brancher après la découverte.",
    "site_web": "Extraction de page : nécessite l'appel LLM d'extraction.",
    "linkedin": "Aucune API de recherche — utiliser Apollo pour les décideurs.",
}


def _connecteurs() -> dict[str, Connecteur]:
    s = get_settings()
    return {
        "apollo": Apollo(s.apollo_api_key),
        "google_maps": Places(s.google_places_api_key),
    }


async def _executer_bloc(
    connecteur: Connecteur, bloc: BlocRecherche, limite: int, dry_run: bool
) -> tuple[ResultatSource, list[Lead]]:
    requetes = connecteur.apercu(bloc, limite)

    if dry_run:
        return (
            ResultatSource(source=bloc.source, statut="simule", requetes=requetes),
            [],
        )

    if not connecteur.configure():
        return (
            ResultatSource(
                source=bloc.source,
                statut="non_configuree",
                requetes=requetes,
                erreur=f"{connecteur.variable_cle} non renseignée.",
            ),
            [],
        )

    try:
        leads = await connecteur.executer(bloc, limite)
    except SourceNonConfiguree as exc:
        return (
            ResultatSource(source=bloc.source, statut="non_configuree", erreur=str(exc)),
            [],
        )
    except httpx.HTTPStatusError as exc:
        return (
            ResultatSource(
                source=bloc.source,
                statut="erreur",
                requetes=requetes,
                erreur=f"HTTP {exc.response.status_code} — {exc.response.reason_phrase}",
            ),
            [],
        )
    except httpx.HTTPError as exc:
        return (
            ResultatSource(
                source=bloc.source,
                statut="erreur",
                requetes=requetes,
                erreur=f"{exc.__class__.__name__} : {exc}",
            ),
            [],
        )

    return (
        ResultatSource(
            source=bloc.source, statut="ok", nb_leads=len(leads), requetes=requetes
        ),
        leads,
    )


async def executer_plan(req: ExecuterPlanRequest) -> ExecuterPlanResponse:
    plan = construire_plan(
        PlanRechercheRequest(
            workspace_id=req.workspace_id,
            icp=req.icp,
            sources=req.sources,
            zone=req.zone,
        )
    )
    diagnostics: list[Diagnostic] = list(plan.diagnostics)

    # Une erreur bloquante du plan (ex. aucun secteur ciblé) arrête tout :
    # exécuter des requêtes vides coûterait de l'argent pour rien.
    if any(d.niveau == "erreur" for d in diagnostics):
        return ExecuterPlanResponse(par_source=[], diagnostics=diagnostics)

    connecteurs = _connecteurs()
    par_source: list[ResultatSource] = []
    leads: list[Lead] = []

    for bloc in plan.decouverte + plan.enrichissement:
        if bloc.source in NON_IMPLEMENTES:
            par_source.append(
                ResultatSource(
                    source=bloc.source,
                    statut="non_implemente",
                    erreur=NON_IMPLEMENTES[bloc.source],
                )
            )
            continue

        connecteur = connecteurs.get(bloc.source)
        if connecteur is None:
            continue

        resultat, trouves = await _executer_bloc(connecteur, bloc, req.limite, req.dry_run)
        par_source.append(resultat)
        leads.extend(trouves)

    # Aucune source externe ne sait exclure un secteur : on filtre ici.
    exclus = {canoniser_secteur(s) for s in req.icp.secteurs_exclus}
    retenus = [lead for lead in leads if canoniser_secteur(lead.secteur or "") not in exclus]
    rejetes = len(leads) - len(retenus)

    if req.dry_run:
        diagnostics.append(
            Diagnostic(
                niveau="info",
                champ="dry_run",
                message=(
                    "Mode simulation : aucune requête n'a été envoyée. Les appels qui "
                    "seraient effectués figurent dans `par_source[].requetes`."
                ),
                suggestion="Passer dry_run à false une fois les clés d'API configurées.",
            )
        )

    return ExecuterPlanResponse(
        leads=retenus,
        par_source=par_source,
        rejetes_hors_icp=rejetes,
        diagnostics=diagnostics,
    )
