"""Connecteur Apollo — la source la plus complète pour la prospection B2B.

Elle couvre à elle seule les quatre promesses du produit : trouver l'entreprise,
connaître sa taille, identifier le décideur, obtenir un email professionnel.

⚠️ Les noms exacts des paramètres doivent être revérifiés contre la documentation
Apollo au moment de brancher une vraie clé : cette API évolue.
"""
from __future__ import annotations

import httpx

from app.schemas.ares import Lead
from app.schemas.builder import BlocRecherche
from app.schemas.sourcing import RequeteHTTP
from app.sourcing.base import CLE_MASQUEE, TIMEOUT, Connecteur, construire_lead

URL = "https://api.apollo.io/api/v1/mixed_people/search"


class Apollo(Connecteur):
    source = "apollo"
    variable_cle = "APOLLO_API_KEY"

    def _entetes(self, cle: str) -> dict:
        """Une seule définition : l'aperçu et l'appel réel ne peuvent pas diverger."""
        return {"Content-Type": "application/json", "Cache-Control": "no-cache",
                "x-api-key": cle}

    def _corps(self, bloc: BlocRecherche, limite: int) -> dict:
        corps: dict = {"page": 1, "per_page": min(limite, 100)}
        filtres = bloc.filtres or {}
        for cle in (
            "organization_industries",
            "organization_num_employees_ranges",
            "person_titles",
        ):
            if filtres.get(cle):
                corps[cle] = filtres[cle]
        return corps

    def apercu(self, bloc: BlocRecherche, limite: int) -> list[RequeteHTTP]:
        return [
            RequeteHTTP(
                methode="POST",
                url=URL,
                entetes=self._entetes(CLE_MASQUEE),
                corps=self._corps(bloc, limite),
            )
        ]

    async def executer(self, bloc: BlocRecherche, limite: int) -> list[Lead]:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            reponse = await client.post(
                URL, headers=self._entetes(self.cle), json=self._corps(bloc, limite)
            )
            reponse.raise_for_status()
            data = reponse.json()

        leads: list[Lead] = []
        for personne in (data.get("people") or [])[:limite]:
            org = personne.get("organization") or {}
            nom = org.get("name") or personne.get("organization_name")
            if not nom:
                continue  # sans entreprise, le lead n'est pas exploitable
            leads.append(
                construire_lead(
                    nom=nom,
                    secteur=org.get("industry"),
                    taille_effectif=org.get("estimated_num_employees"),
                    titre_contact=personne.get("title"),
                    email=personne.get("email"),
                    site_web=org.get("website_url"),
                    nom_contact=personne.get("name"),
                    source=self.source,
                )
            )
        return leads
