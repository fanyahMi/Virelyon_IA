"""Référentiels de l'Agent Builder — cohérence du vocabulaire, pas restriction.

Le filtrage (`ares/scoring.py:_fit`) fait une **égalité stricte** après passage en
minuscules : `"Marketing digital"` ne matche PAS `"marketing"`. Sans forme canonique
partagée, la correspondance tombe à zéro sur des leads parfaitement valides.

**Le catalogue ci-dessous est une liste de suggestions, PAS une liste fermée.**
Chaque client cible son propre marché : un client peut légitimement prospecter des
restaurants, des cliniques ou des industriels. `canoniser_secteur()` accepte donc
n'importe quelle valeur et se contente de la ramener à une forme stable.

> Ne pas confondre deux ICP : celui de **VIRELYON** (agences de services B2B, qui
> achètent la plateforme — contrainte de messaging CDCF §8) et celui de **chaque
> client** (qui il veut prospecter, et qui peut être n'importe quel marché).

Ce module est la **source unique** utilisée par :
- les listes déroulantes de l'écran Agent Builder (frontend, via le backend) ;
- la normalisation appliquée par Big Data sur `lead.secteur` ;
- l'extraction d'ICP depuis du texte libre (`builder/icp.py`) ;
- la construction du plan de recherche (`builder/plan_recherche.py`).

⚠️ Big Data **doit** appeler `canoniser_secteur()` à l'ingestion. C'est la seule
garantie que `lead.secteur` et `icp.secteurs_inclus` parlent le même langage.
"""
from __future__ import annotations

import re
import unicodedata

# --- Secteurs -----------------------------------------------------------------
# Catalogue de SUGGESTIONS proposé par défaut dans l'Agent Builder. Un client peut
# saisir un secteur absent de cette liste : il sera canonisé, pas rejeté.
SECTEURS_SERVICES_B2B: tuple[str, ...] = (
    "marketing",
    "communication",
    "conseil",
    "developpement",
    "design",
    "rh",
    "formation",
    "juridique",
    "comptabilite",
    "evenementiel",
    "traduction",
    "relation_presse",
)

# Autres secteurs courants, proposés eux aussi dans les listes.
# (Ceux-ci sont interdits en *témoignage marketing* — contrainte CDCF §8 — mais
# parfaitement légitimes comme cible de prospection d'un client.)
SECTEURS_AUTRES: tuple[str, ...] = (
    "hotellerie",
    "restauration",
    "retail",
    "sante",
    "artisanat",
    "immobilier",
    "industrie",
    "transport",
    "batiment",
    "education",
    "association",
)

SECTEURS: tuple[str, ...] = SECTEURS_SERVICES_B2B + SECTEURS_AUTRES

# --- Rôles de contact ---------------------------------------------------------
ROLES: tuple[str, ...] = (
    "fondateur",
    "decideur",
    "directeur",
    "manager",
    "operationnel",
)

# --- Tons de voix (CDCF §4.5 / présentation ARES) -----------------------------
TONS_DE_VOIX: tuple[str, ...] = (
    "professionnel",
    "chaleureux",
    "direct",
    "creatif",
)

# --- Canaux (CDCF §6) ---------------------------------------------------------
CANAUX: tuple[str, ...] = ("email", "whatsapp", "linkedin", "sms", "slack")


# --- Synonymes ----------------------------------------------------------------
# Formulations courantes rencontrées dans les sources de sourcing (Google Maps,
# LinkedIn, annuaires) → valeur canonique du référentiel.
_SYNONYMES: dict[str, str] = {
    # marketing
    "marketing digital": "marketing",
    "growth": "marketing",
    "growth marketing": "marketing",
    "webmarketing": "marketing",
    "agence marketing": "marketing",
    "publicite": "marketing",
    "seo": "marketing",
    # communication
    "com": "communication",
    "agence de com": "communication",
    "agence de communication": "communication",
    "relations publiques": "communication",
    "branding": "communication",
    # conseil
    "consulting": "conseil",
    "cabinet de conseil": "conseil",
    "strategie": "conseil",
    "audit": "conseil",
    # developpement
    "dev": "developpement",
    "developpement web": "developpement",
    "developpement logiciel": "developpement",
    "esn": "developpement",
    "agence web": "developpement",
    "informatique": "developpement",
    "logiciel": "developpement",
    # design
    "ux": "design",
    "ui": "design",
    "graphisme": "design",
    "studio de design": "design",
    "direction artistique": "design",
    # rh
    "ressources humaines": "rh",
    "recrutement": "rh",
    "cabinet de recrutement": "rh",
    "chasse de tetes": "rh",
    # formation
    "organisme de formation": "formation",
    "e-learning": "formation",
    "coaching": "formation",
    # juridique
    "avocat": "juridique",
    "cabinet d'avocats": "juridique",
    "droit": "juridique",
    # comptabilite
    "expert-comptable": "comptabilite",
    "cabinet comptable": "comptabilite",
    "finance": "comptabilite",
    # evenementiel
    "evenement": "evenementiel",
    "agence evenementielle": "evenementiel",
    # traduction
    "traduction technique": "traduction",
    "localisation": "traduction",
    # relation presse
    "rp": "relation_presse",
    "attache de presse": "relation_presse",
    # hors-ICP
    "hotel": "hotellerie",
    "restaurant": "restauration",
    "commerce": "retail",
    "commerce de detail": "retail",
    "boutique": "retail",
    "medical": "sante",
    "clinique": "sante",
    "pharmacie": "sante",
    "librairie": "librairie",
    # rôles
    "ceo": "fondateur",
    "founder": "fondateur",
    "co-fondateur": "fondateur",
    "cofondateur": "fondateur",
    "dirigeant": "decideur",
    "gerant": "decideur",
    "president": "decideur",
    "dg": "directeur",
    "directeur general": "directeur",
    "cto": "directeur",
    "cmo": "directeur",
    "head of": "manager",
    "responsable": "manager",
    "chef de projet": "manager",
    "charge de": "operationnel",
    "assistant": "operationnel",
    "stagiaire": "operationnel",
}


# --- Libellés de recherche par secteur ----------------------------------------
# Traduction d'un secteur canonique vers les termes à envoyer aux sources externes.
# Déterministe et versionné : une même config produit toujours les mêmes requêtes.
#   maps    → requêtes texte pour Google Places
#   apollo  → valeurs d'industrie de l'API Apollo (anglais)
LIBELLES_RECHERCHE: dict[str, dict[str, tuple[str, ...]]] = {
    "marketing": {
        "maps": ("agence marketing", "agence de publicité"),
        "apollo": ("marketing & advertising", "advertising"),
    },
    "communication": {
        "maps": ("agence de communication", "agence de relations publiques"),
        "apollo": ("public relations & communications",),
    },
    "conseil": {
        "maps": ("cabinet de conseil", "société de conseil"),
        "apollo": ("management consulting",),
    },
    "developpement": {
        "maps": ("agence de développement web", "société informatique"),
        "apollo": ("information technology & services", "computer software"),
    },
    "design": {
        "maps": ("studio de design", "agence de design graphique"),
        "apollo": ("design", "graphic design"),
    },
    "rh": {
        "maps": ("cabinet de recrutement", "agence de ressources humaines"),
        "apollo": ("human resources", "staffing & recruiting"),
    },
    "formation": {
        "maps": ("organisme de formation", "centre de formation professionnelle"),
        "apollo": ("professional training & coaching",),
    },
    "juridique": {
        "maps": ("cabinet d'avocats", "conseil juridique"),
        "apollo": ("legal services", "law practice"),
    },
    "comptabilite": {
        "maps": ("cabinet d'expertise comptable", "cabinet comptable"),
        "apollo": ("accounting",),
    },
    "evenementiel": {
        "maps": ("agence événementielle", "organisation d'événements"),
        "apollo": ("events services",),
    },
    "traduction": {
        "maps": ("agence de traduction", "services de traduction"),
        "apollo": ("translation & localization",),
    },
    "relation_presse": {
        "maps": ("agence de relations presse", "attaché de presse"),
        "apollo": ("public relations & communications",),
    },
}

# Intitulés de poste à cibler, par rôle canonique. Bilingue : les annuaires B2B
# indexent majoritairement en anglais, les sources francophones en français.
TITRES_PAR_ROLE: dict[str, tuple[str, ...]] = {
    "fondateur": ("Founder", "Co-Founder", "Owner", "Fondateur", "Cofondateur"),
    "decideur": ("CEO", "Managing Director", "President", "Gérant", "Dirigeant"),
    "directeur": ("Director", "Directeur Général", "Head of", "CTO", "CMO"),
    "manager": ("Manager", "Responsable", "Chef de projet"),
    "operationnel": ("Specialist", "Chargé de", "Consultant"),
}


def aplatir(valeur: str) -> str:
    """Minuscules, sans accents, espaces normalisés — clé de comparaison neutre."""
    texte = unicodedata.normalize("NFKD", valeur or "")
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = texte.lower().strip()
    return re.sub(r"[\s_-]+", " ", texte)


def _normaliser(valeur: str, referentiel: tuple[str, ...]) -> str | None:
    """Rattache une valeur libre au référentiel, ou None si aucune correspondance."""
    plat = aplatir(valeur)
    if not plat:
        return None

    # 1. correspondance directe avec le référentiel
    for canon in referentiel:
        if plat == aplatir(canon):
            return canon

    # 2. synonyme connu
    cible = _SYNONYMES.get(plat)
    if cible in referentiel:
        return cible

    # 3. le libellé contient un terme du référentiel ou un synonyme
    #    ("agence de marketing digital B2B" → marketing)
    for source, canon in _SYNONYMES.items():
        if canon in referentiel and re.search(rf"\b{re.escape(source)}\b", plat):
            return canon
    for canon in referentiel:
        if re.search(rf"\b{re.escape(aplatir(canon))}\b", plat):
            return canon

    return None


def normaliser_secteur(valeur: str) -> str | None:
    """`"Marketing digital"` → `"marketing"`. **None si hors catalogue.**

    À utiliser quand on a besoin de savoir si la valeur est *connue*
    (ex. trouver ses libellés de recherche). Pour stocker ou comparer, préférer
    `canoniser_secteur`, qui accepte les secteurs personnalisés.
    """
    return _normaliser(valeur, SECTEURS)


def canoniser_secteur(valeur: str) -> str:
    """Forme stable d'un secteur, **quel qu'il soit**. Ne rejette jamais.

    Un secteur du catalogue est ramené à sa valeur canonique ; un secteur
    personnalisé est simplement stabilisé (minuscules, sans accents, tirets bas).

        "Marketing digital"    → "marketing"           (catalogue)
        "Restauration rapide"  → "restauration_rapide" (personnalisé)

    C'est cette fonction que Big Data doit appeler sur `lead.secteur`, et l'Agent
    Builder sur l'ICP : la comparaison ne tient que si les deux côtés canonisent
    de la même façon.
    """
    connu = _normaliser(valeur, SECTEURS)
    if connu is not None:
        return connu
    return re.sub(r"[^a-z0-9]+", "_", aplatir(valeur)).strip("_")


def est_personnalise(valeur: str) -> bool:
    """True si le secteur ne figure pas au catalogue par défaut."""
    return _normaliser(valeur, SECTEURS) is None


def normaliser_role(valeur: str) -> str | None:
    """`"CEO"` → `"fondateur"`. None si hors référentiel."""
    return _normaliser(valeur, ROLES)
