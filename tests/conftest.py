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
