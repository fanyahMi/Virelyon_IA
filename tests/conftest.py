"""Fixtures de test. Le provider LLM est mocké : aucun appel réseau, aucune clé requise."""
import os

# Forcer une clé interne connue AVANT tout import de l'app (précède le .env).
os.environ["INTERNAL_API_KEY"] = "test-key"

import pytest
from fastapi.testclient import TestClient

from app.gateway.cache import response_cache
from app.gateway.provider import get_provider
from app.main import app

HEADERS = {"X-Internal-Key": "test-key"}


@pytest.fixture(autouse=True)
def _clear_cache():
    """Cache vidé avant chaque test → isolation déterministe."""
    response_cache.clear()
    yield


class FakeProvider:
    """Provider factice : renvoie un payload JSON fixe + un usage de tokens fixe."""

    def __init__(self, payload: str) -> None:
        self.payload = payload

    async def generate(self, model, system, user, max_tokens):
        return self.payload, 100, 50


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def use_provider():
    """Injecte un FakeProvider renvoyant `payload`."""
    def _set(payload: str):
        app.dependency_overrides[get_provider] = lambda: FakeProvider(payload)

    yield _set
    app.dependency_overrides.pop(get_provider, None)


class FauxClientHTTP:
    """Client httpx factice : rend une charge JSON, ou lève l'exception fournie."""

    def __init__(self, charge=None, exception=None) -> None:
        self.charge = charge
        self.exception = exception

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def post(self, *_a, **_kw):
        if self.exception is not None:
            raise self.exception
        import httpx

        return httpx.Response(
            200, json=self.charge, request=httpx.Request("POST", "http://test")
        )


@pytest.fixture
def faux_http(monkeypatch):
    """Remplace le client httpx d'un connecteur, et son registre côté exécuteur."""
    def _set(module: str, charge=None, exception=None, cle="cle-de-test"):
        monkeypatch.setattr(
            f"app.sourcing.{module}.httpx.AsyncClient",
            lambda *a, **k: FauxClientHTTP(charge, exception),
        )
        from app.sourcing.apollo import Apollo
        from app.sourcing.hunter import Hunter
        from app.sourcing.linkedin import LinkedIn
        from app.sourcing.places import Places
        from app.sourcing.site_web import SiteWeb

        registre = {c.source: c for c in (Apollo(cle), Places(""), Hunter(""),
                                         SiteWeb(), LinkedIn())}
        monkeypatch.setattr("app.sourcing.executeur._connecteurs", lambda: registre)

    return _set


@pytest.fixture
def score_payload():
    return {
        "workspace_id": "11111111-1111-1111-1111-111111111111",
        "lead": {
            "nom": "Studio Créa",
            "secteur": "marketing",
            "taille_effectif": 18,
            "role_contact": "fondateur",
            "contact": {"email": "contact@studio.co"},
            "montant_potentiel": 5000,
        },
        "icp": {
            "secteurs_inclus": ["marketing", "conseil"],
            "secteurs_exclus": ["hotellerie"],
            "taille_min": 5,
            "taille_max": 30,
            "roles_cibles": ["fondateur", "decideur"],
        },
    }
