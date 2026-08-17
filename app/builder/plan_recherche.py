"""ICP structuré → plan de recherche exploitable par les sources externes.

C'est le chaînon entre l'Agent Builder et le sourcing : le client définit *qui*
il veut cibler, ce module traduit en *quoi chercher où*.

**Logique PURE — aucun appel LLM.** Choix assumé : une même configuration doit
toujours produire les mêmes requêtes. Un plan de recherche qui varie d'une
exécution à l'autre rendrait le sourcing impossible à déboguer et la facturation
au volume imprévisible. La traduction passe donc par les tables versionnées de
`referentiels.py`, pas par un modèle.

Deux natures de source, à ne pas confondre :
- **découverte** — trouve des entreprises inconnues (Maps, Apollo, LinkedIn) ;
- **enrichissement** — complète une entreprise déjà trouvée (site web, Hunter).
"""
from __future__ import annotations

from app.builder.referentiels import (
    LIBELLES_RECHERCHE,
    TITRES_PAR_ROLE,
    canoniser_secteur,
    normaliser_role,
    normaliser_secteur,
)
from app.schemas.ares import ICP
from app.schemas.builder import (
    SOURCES_DECOUVERTE,
    SOURCES_ENRICHISSEMENT,
    BlocRecherche,
    Diagnostic,
    PlanRechercheRequest,
    PlanRechercheResponse,
)

# LinkedIn n'expose aucune API de recherche : toute collecte y passe par de
# l'automatisation de navigateur, contraire à ses conditions d'utilisation.
_AVERTISSEMENT_LINKEDIN = (
    "LinkedIn n'expose pas d'API de recherche : ces filtres ne sont exploitables que "
    "par automatisation de navigateur, contraire à ses conditions d'utilisation. "
    "Les mêmes décideurs sont accessibles légalement via Apollo."
)


def _libelles(icp: ICP, cle: str) -> list[str]:
    """Termes de recherche pour une source donnée, dans l'ordre de l'ICP.

    Un secteur personnalisé n'a pas de libellés prédéfinis : on retombe sur le
    libellé saisi par le client, qui reste une requête de recherche valable.
    """
    sortie: list[str] = []
    for secteur in icp.secteurs_inclus:
        canon = normaliser_secteur(secteur)
        termes = LIBELLES_RECHERCHE.get(canon, {}).get(cle, ()) if canon else ()
        if not termes:
            termes = (secteur.strip(),)  # repli : la saisie du client
        for terme in termes:
            if terme and terme not in sortie:
                sortie.append(terme)
    return sortie


def _titres(icp: ICP) -> list[str]:
    """Intitulés de poste à cibler, déduits des rôles de l'ICP."""
    sortie: list[str] = []
    for role in icp.roles_cibles:
        canon = normaliser_role(role)
        if canon is None:
            continue
        for titre in TITRES_PAR_ROLE.get(canon, ()):
            if titre not in sortie:
                sortie.append(titre)
    return sortie


def _tranche_effectif(icp: ICP) -> str | None:
    """Format attendu par Apollo : `"5,30"`. Bornes ouvertes si l'une manque."""
    if icp.taille_min is None and icp.taille_max is None:
        return None
    lo = icp.taille_min if icp.taille_min is not None else 1
    hi = icp.taille_max if icp.taille_max is not None else 10000
    return f"{lo},{hi}"


def construire_plan(req: PlanRechercheRequest) -> PlanRechercheResponse:
    icp = req.icp
    demandees = [s for s in req.sources] or list(SOURCES_DECOUVERTE + SOURCES_ENRICHISSEMENT)
    diags: list[Diagnostic] = []

    inconnues = [s for s in demandees if s not in SOURCES_DECOUVERTE + SOURCES_ENRICHISSEMENT]
    for source in inconnues:
        diags.append(
            Diagnostic(
                niveau="avertissement",
                champ="sources",
                message=f"Source « {source} » inconnue : ignorée.",
                suggestion="Sources reconnues : "
                + ", ".join(SOURCES_DECOUVERTE + SOURCES_ENRICHISSEMENT),
            )
        )

    if not icp.secteurs_inclus:
        diags.append(
            Diagnostic(
                niveau="erreur",
                champ="icp.secteurs_inclus",
                message=(
                    "Aucun secteur ciblé : impossible de construire une requête de "
                    "recherche. Le sourcing ne peut pas démarrer."
                ),
                suggestion="Renseigner au moins un secteur dans l'ICP.",
            )
        )

    titres = _titres(icp)
    tranche = _tranche_effectif(icp)
    decouverte: list[BlocRecherche] = []
    enrichissement: list[BlocRecherche] = []

    # --- Google Maps (Places) : requêtes texte ------------------------------
    if "google_maps" in demandees:
        libelles = _libelles(icp, "maps")
        # La zone n'est JAMAIS déduite (CDCF §8) — on la concatène si le client l'a fournie.
        requetes = [f"{lib} {req.zone}".strip() if req.zone else lib for lib in libelles]
        if libelles and not req.zone:
            diags.append(
                Diagnostic(
                    niveau="avertissement",
                    champ="zone",
                    message=(
                        "Aucune zone fournie : Google Places renverra des résultats "
                        "dispersés et peu exploitables."
                    ),
                    suggestion="Demander au client la zone à prospecter.",
                )
            )
        for secteur in icp.secteurs_inclus:
            canon = normaliser_secteur(secteur)
            if canon is None or canon not in LIBELLES_RECHERCHE:
                diags.append(
                    Diagnostic(
                        niveau="info",
                        champ="icp.secteurs_inclus",
                        message=(
                            f"Aucun libellé de recherche prédéfini pour « {secteur} » : "
                            f"la saisie du client est utilisée telle quelle comme requête."
                        ),
                        suggestion=(
                            "Ajouter des libellés dans LIBELLES_RECHERCHE si ce secteur "
                            "revient souvent."
                        ),
                    )
                )
        decouverte.append(
            BlocRecherche(source="google_maps", type="requetes_texte", requetes=requetes)
        )

    # --- Apollo : filtres structurés ----------------------------------------
    if "apollo" in demandees:
        filtres: dict = {}
        industries = _libelles(icp, "apollo")
        if industries:
            filtres["organization_industries"] = industries
        if tranche:
            filtres["organization_num_employees_ranges"] = [tranche]
        if titres:
            filtres["person_titles"] = titres
        decouverte.append(BlocRecherche(source="apollo", type="filtres", filtres=filtres))

    # --- LinkedIn : filtres, mais réserve juridique -------------------------
    if "linkedin" in demandees:
        filtres = {}
        if titres:
            filtres["titres"] = titres
        if tranche:
            filtres["taille_entreprise"] = tranche
        secteurs_lus = [canoniser_secteur(x) for x in icp.secteurs_inclus]
        if secteurs_lus:
            filtres["secteurs"] = secteurs_lus
        decouverte.append(
            BlocRecherche(
                source="linkedin",
                type="filtres",
                filtres=filtres,
                avertissement=_AVERTISSEMENT_LINKEDIN,
            )
        )
        diags.append(
            Diagnostic(
                niveau="avertissement",
                champ="sources",
                message=_AVERTISSEMENT_LINKEDIN,
                suggestion="Utiliser Apollo pour identifier les décideurs.",
            )
        )

    # --- Site web : extraction (enrichissement) -----------------------------
    if "site_web" in demandees:
        enrichissement.append(
            BlocRecherche(
                source="site_web",
                type="extraction",
                champs_cibles=["secteur", "description", "taille_estimee", "signaux"],
            )
        )

    # --- Hunter : recherche d'email sur un domaine connu --------------------
    if "hunter" in demandees:
        filtres = {}
        if titres:
            filtres["titres_recherches"] = titres
        enrichissement.append(
            BlocRecherche(source="hunter", type="domain_search", filtres=filtres)
        )

    # Aucune source externe ne sait exclure un secteur : le filtre est appliqué
    # après collecte, par la qualification.
    exclus = [canoniser_secteur(x) for x in icp.secteurs_exclus]
    if exclus:
        diags.append(
            Diagnostic(
                niveau="avertissement",
                champ="icp.secteurs_exclus",
                message=(
                    "Les secteurs exclus ne peuvent pas être filtrés à la source : "
                    "ils seront écartés après collecte, par la qualification."
                ),
            )
        )

    return PlanRechercheResponse(
        decouverte=decouverte,
        enrichissement=enrichissement,
        secteurs_exclus=exclus,
        diagnostics=diags,
    )
