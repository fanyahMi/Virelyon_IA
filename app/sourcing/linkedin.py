"""Connecteur LinkedIn — volontairement non implémenté.

LinkedIn n'expose aucune API de recherche : toute collecte y passerait par de
l'automatisation de navigateur, contraire à ses conditions d'utilisation. Les
mêmes décideurs sont accessibles légalement via Apollo, qui est branché.

Le connecteur existe quand même pour que la source soit DÉCLARÉE plutôt
qu'absente : le plan de recherche la construit, et l'exécuteur explique pourquoi
elle ne s'exécute pas.
"""
from app.sourcing.base import Connecteur


class LinkedIn(Connecteur):
    source = "linkedin"
    motif_non_implemente = (
        "Aucune API de recherche — utiliser Apollo pour identifier les décideurs."
    )

    def apercu(self, bloc, limite):
        return []
