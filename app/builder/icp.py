"""Logique de l'Agent Builder : valider un ICP, et l'extraire depuis du texte libre.

Deux natures bien distinctes :
- `valider_icp` : logique PURE, aucun appel LLM, gratuite et instantanée.
  C'est elle qui protège du piège n°1 (un ICP qui ne matchera jamais rien).
- `extraire_icp` : appel Claude, contraint au référentiel.
"""
from __future__ import annotations

from app.ares.agents import dump_json, meta_depuis
from app.builder.referentiels import (
    CANAUX,
    ROLES,
    SECTEURS,
    SECTEURS_AUTRES,
    SECTEURS_SERVICES_B2B,
    TONS_DE_VOIX,
    aplatir,
    canoniser_secteur,
    normaliser_role,
    normaliser_secteur,
    stabiliser,
)
from app.gateway.router import Gateway
from app.prompts.builder import ICP_EXTRACT_SYSTEM
from app.schemas.ares import ICP
from app.schemas.builder import (
    Diagnostic,
    ICPExtraireRequest,
    ICPExtraireResponse,
    ICPValiderRequest,
    ICPValiderResponse,
    Referentiels,
    diag,
)

# En dessous de cette amplitude, la fourchette d'effectif est jugée trop étroite
# pour laisser passer un volume de leads exploitable.
_AMPLITUDE_MINIMALE = 5


def referentiels() -> Referentiels:
    """Le vocabulaire que le moteur de filtrage sait comparer."""
    return Referentiels(
        secteurs=list(SECTEURS),
        secteurs_services_b2b=list(SECTEURS_SERVICES_B2B),
        secteurs_autres=list(SECTEURS_AUTRES),
        roles=list(ROLES),
        tons_de_voix=list(TONS_DE_VOIX),
        canaux=list(CANAUX),
    )


def _diag_forme(champ: str, valeur: str, canon: str) -> Diagnostic:
    """Le libellé saisi n'est pas la forme exacte que le filtrage comparera."""
    return diag(
        "avertissement",
        champ,
        f"« {valeur} » n'est pas la forme normalisée attendue. "
        f"Le filtrage compare des valeurs exactes.",
        f"Utiliser « {canon} ».",
    )


def _criteres_actifs(icp: ICP) -> int:
    """Nombre de critères réellement discriminants : secteur, taille, rôle."""
    return sum(
        (
            bool(icp.secteurs_inclus or icp.secteurs_exclus),
            icp.taille_min is not None or icp.taille_max is not None,
            bool(icp.roles_cibles),
        )
    )


def _diagnostiquer(icp: ICP) -> list[Diagnostic]:
    """Contrôles de cohérence sur un ICP."""
    diags: list[Diagnostic] = []

    # --- Erreurs bloquantes ---------------------------------------------------
    if (
        icp.taille_min is not None
        and icp.taille_max is not None
        and icp.taille_min > icp.taille_max
    ):
        diags.append(
            diag(
                "erreur",
                "taille_effectif",
                f"La taille minimale ({icp.taille_min}) dépasse la taille maximale "
                f"({icp.taille_max}) : aucun lead ne peut correspondre.",
                "Inverser les deux valeurs.",
            )
        )

    inclus_plats = {aplatir(s) for s in icp.secteurs_inclus}
    for secteur in sorted(s for s in icp.secteurs_exclus if aplatir(s) in inclus_plats):
        diags.append(
            diag(
                "erreur",
                "secteurs",
                f"« {secteur} » est à la fois inclus et exclu. L'exclusion l'emporte : "
                f"tous les leads de ce secteur seront rejetés.",
                f"Retirer « {secteur} » d'une des deux listes.",
            )
        )

    # --- Secteurs : canonisation, jamais rejet -------------------------------
    # Chaque client cible son propre marché : un secteur absent du catalogue est
    # légitime. On vérifie seulement que la forme stockée sera comparable.
    for champ, valeurs in (
        ("secteurs_inclus", icp.secteurs_inclus),
        ("secteurs_exclus", icp.secteurs_exclus),
    ):
        for valeur in valeurs:
            connu = normaliser_secteur(valeur)  # une seule normalisation par valeur
            if connu is None:
                diags.append(
                    diag(
                        "info",
                        champ,
                        f"« {valeur} » est un secteur personnalisé (hors catalogue). "
                        f"Il sera stocké sous la forme « {stabiliser(valeur)} ».",
                        "Vérifier que le sourcing enregistre bien les leads de ce "
                        "secteur sous la même forme.",
                    )
                )
            elif aplatir(connu) != aplatir(valeur):
                diags.append(_diag_forme(champ, valeur, connu))

    # --- Rôles : le catalogue est fermé (il pilote les intitulés de poste) ----
    for valeur in icp.roles_cibles:
        canon = normaliser_role(valeur)
        if canon is None:
            diags.append(
                diag(
                    "avertissement",
                    "roles_cibles",
                    f"« {valeur} » ne fait pas partie des rôles reconnus : "
                    f"la comparaison échouera sur tous les leads.",
                    "Choisir une valeur de la liste proposée.",
                )
            )
        elif aplatir(canon) != aplatir(valeur):
            diags.append(_diag_forme("roles_cibles", valeur, canon))

    # --- ICP inexploitable ou trop restrictif --------------------------------
    if _criteres_actifs(icp) == 0:
        diags.append(
            diag(
                "avertissement",
                "icp",
                "Aucun critère renseigné : tous les leads obtiendront la même "
                "correspondance neutre et le score ne discriminera rien.",
                "Renseigner au moins les secteurs visés.",
            )
        )

    taille_bornee = icp.taille_min is not None and icp.taille_max is not None
    if taille_bornee and 0 <= icp.taille_max - icp.taille_min < _AMPLITUDE_MINIMALE:
        diags.append(
            diag(
                "avertissement",
                "taille_effectif",
                f"La fourchette d'effectif est très étroite "
                f"({icp.taille_min}-{icp.taille_max}) : peu de leads passeront le filtre.",
                "Élargir la fourchette pour obtenir du volume.",
            )
        )

    if (
        len(icp.secteurs_inclus) == 1
        and len(icp.roles_cibles) == 1
        and (icp.taille_min is not None or icp.taille_max is not None)
    ):
        diags.append(
            diag(
                "avertissement",
                "icp",
                "Un seul secteur, un seul rôle et une fourchette de taille : "
                "cet ICP est très sélectif et risque de produire peu de prospects.",
                "Ajouter un secteur ou un rôle proche.",
            )
        )

    return diags


def valider_icp(req: ICPValiderRequest) -> ICPValiderResponse:
    """Vérifie qu'un ICP peut réellement fonctionner. Aucun appel LLM."""
    diags = _diagnostiquer(req.icp)
    return ICPValiderResponse(
        valide=not any(d.niveau == "erreur" for d in diags),
        diagnostics=diags,
        criteres_actifs=_criteres_actifs(req.icp),
    )


def _normaliser_liste(valeurs: list[str], normaliser) -> tuple[list[str], list[str]]:
    """Retourne (valeurs canoniques dédoublonnées, valeurs non reconnues)."""
    retenues: list[str] = []
    rejetees: list[str] = []
    for valeur in valeurs:
        canon = normaliser(str(valeur))
        if canon is None:
            rejetees.append(str(valeur))
        elif canon not in retenues:
            retenues.append(canon)
    return retenues, rejetees


async def extraire_icp(gw: Gateway, req: ICPExtraireRequest) -> ICPExtraireResponse:
    """Texte libre du client → ICP structuré, contraint au référentiel.

    Le modèle propose ; on renormalise systématiquement derrière lui, car un LLM
    peut renvoyer une valeur hors référentiel malgré la consigne.
    """
    ref = referentiels()
    user = dump_json(
        {
            "texte": req.texte,
            "language": req.language,
            "referentiel_secteurs": ref.secteurs,
            "referentiel_roles": ref.roles,
        }
    )
    data, info = await gw.complete_json(
        "reasoning", ICP_EXTRACT_SYSTEM, user, req.workspace_id
    )

    brut = data.get("icp") or {}
    inclus, rej_inclus = _normaliser_liste(brut.get("secteurs_inclus") or [], canoniser_secteur)
    exclus, rej_exclus = _normaliser_liste(brut.get("secteurs_exclus") or [], canoniser_secteur)
    roles, rej_roles = _normaliser_liste(brut.get("roles_cibles") or [], normaliser_role)

    def _entier(valeur) -> int | None:
        try:
            return int(valeur) if valeur is not None else None
        except (TypeError, ValueError):
            return None

    icp = ICP(
        secteurs_inclus=inclus,
        secteurs_exclus=exclus,
        taille_min=_entier(brut.get("taille_min")),
        taille_max=_entier(brut.get("taille_max")),
        roles_cibles=roles,
    )

    # Ce que le modèle a signalé + ce que la renormalisation a écarté.
    non_reconnu: list[str] = []
    for terme in list(data.get("non_reconnu") or []) + rej_inclus + rej_exclus + rej_roles:
        terme = str(terme)
        if terme and terme not in non_reconnu:
            non_reconnu.append(terme)

    diags = _diagnostiquer(icp)
    if non_reconnu:
        diags.append(
            diag(
                "avertissement",
                "icp",
                "Certains éléments de la description n'ont pas pu être rattachés au "
                "référentiel : " + ", ".join(f"« {t} »" for t in non_reconnu),
                "Les compléter à la main dans les listes.",
            )
        )

    try:
        confiance = min(1.0, max(0.0, float(data.get("confiance", 0.5))))
    except (TypeError, ValueError):
        confiance = 0.5

    return ICPExtraireResponse(
        icp=icp,
        confiance=confiance,
        non_reconnu=non_reconnu,
        diagnostics=diags,
        meta=meta_depuis(info),
    )
