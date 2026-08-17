"""Connecteur Google Places — découverte locale.

Complète Apollo sur les TPE de quartier que les annuaires B2B connaissent mal.

Limite structurelle à connaître : Places ne rend **ni l'effectif ni le décideur**.
Les leads qui en sortent sont donc incomplets par nature — ils devront passer par
Hunter (email) et l'extraction de site web avant d'être vraiment exploitables.
Leur score de complétude sera naturellement plus bas.
"""
from __future__ import annotations

import httpx

from app.schemas.ares import Lead
from app.schemas.builder import BlocRecherche
from app.schemas.sourcing import RequeteHTTP
from app.sourcing.base import CLE_MASQUEE, TIMEOUT, Connecteur, construire_lead

URL = "https://places.googleapis.com/v1/places:searchText"
CHAMPS = "places.displayName,places.websiteUri,places.formattedAddress,places.primaryType"


class Places(Connecteur):
    source = "google_maps"
    variable_cle = "GOOGLE_PLACES_API_KEY"

    def apercu(self, bloc: BlocRecherche, limite: int) -> list[RequeteHTTP]:
        return [
            RequeteHTTP(
                methode="POST",
                url=URL,
                params={"X-Goog-Api-Key": CLE_MASQUEE, "X-Goog-FieldMask": CHAMPS},
                corps={"textQuery": requete, "pageSize": min(limite, 20)},
            )
            for requete in bloc.requetes
        ]

    async def executer(self, bloc: BlocRecherche, limite: int) -> list[Lead]:
        self.exiger_cle()
        entetes = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.cle,
            "X-Goog-FieldMask": CHAMPS,
        }
        leads: list[Lead] = []
        vus: set[str] = set()

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            for requete in bloc.requetes:
                if len(leads) >= limite:
                    break
                reponse = await client.post(
                    URL,
                    headers=entetes,
                    json={"textQuery": requete, "pageSize": min(limite, 20)},
                )
                reponse.raise_for_status()
                for lieu in reponse.json().get("places") or []:
                    nom = (lieu.get("displayName") or {}).get("text")
                    if not nom or nom in vus:
                        continue  # déduplication entre requêtes du même plan
                    vus.add(nom)
                    leads.append(
                        construire_lead(
                            nom=nom,
                            # Places ne rend pas d'industrie exploitable : on retient
                            # le type qu'il fournit, la qualification tranchera.
                            secteur=lieu.get("primaryType"),
                            site_web=lieu.get("websiteUri"),
                            source=self.source,
                        )
                    )
                    if len(leads) >= limite:
                        break
        return leads
