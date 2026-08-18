"""Connecteur Hunter — recherche d'email sur un domaine connu.

ENRICHISSEMENT : Hunter ne découvre rien, il complète une entreprise déjà trouvée
(il lui faut un domaine). Pas encore branché.
"""
from app.sourcing.base import Connecteur


class Hunter(Connecteur):
    source = "hunter"
    variable_cle = "HUNTER_API_KEY"
    nature = "enrichissement"
    motif_non_implemente = "Enrichissement d'email : à brancher après la découverte."

    def apercu(self, bloc, limite):
        return []
