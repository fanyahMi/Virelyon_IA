"""Connecteur Site web — extraction du secteur et de l'activité depuis une page.

ENRICHISSEMENT : nécessite une URL d'entreprise déjà trouvée, et un appel LLM
d'extraction (une page web n'a aucune structure exploitable par des règles).
Pas encore branché.
"""
from app.sourcing.base import Connecteur


class SiteWeb(Connecteur):
    source = "site_web"
    nature = "enrichissement"
    motif_non_implemente = "Extraction de page : nécessite l'appel LLM d'extraction."

    def apercu(self, bloc, limite):
        return []
