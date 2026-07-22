"""Tests du cache des réponses LLM (§5.4)."""
from app.gateway.provider import get_provider
from app.main import app
from tests.conftest import HEADERS

WID = "44444444-4444-4444-4444-444444444444"
LEAD = {"nom": "Cache Co", "secteur": "marketing"}
ICP = {"secteurs_inclus": ["marketing"]}


class CountingProvider:
    """Compte les appels réels au LLM."""

    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.calls = 0

    async def generate(self, model, system, user, max_tokens):
        self.calls += 1
        return self.payload, 100, 50


def test_deuxieme_appel_identique_vient_du_cache(client):
    prov = CountingProvider('{"qualifie": true, "confiance": 0.9, "motif": "ok"}')
    app.dependency_overrides[get_provider] = lambda: prov
    try:
        body = {"workspace_id": WID, "lead": LEAD, "icp": ICP}

        r1 = client.post("/api/v1/ares/qualify", headers=HEADERS, json=body)
        assert r1.status_code == 200
        assert r1.json()["meta"]["cached"] is False
        assert r1.json()["meta"]["cost_estimate"] > 0

        r2 = client.post("/api/v1/ares/qualify", headers=HEADERS, json=body)
        assert r2.status_code == 200
        assert r2.json()["meta"]["cached"] is True          # servi par le cache
        assert r2.json()["meta"]["cost_estimate"] == 0      # coût 0

        assert prov.calls == 1  # le LLM n'a été appelé qu'UNE fois
    finally:
        app.dependency_overrides.pop(get_provider, None)


def test_payload_different_nest_pas_cache(client):
    prov = CountingProvider('{"qualifie": true, "confiance": 0.9, "motif": "ok"}')
    app.dependency_overrides[get_provider] = lambda: prov
    try:
        client.post("/api/v1/ares/qualify", headers=HEADERS,
                    json={"workspace_id": WID, "lead": {"nom": "A"}, "icp": ICP})
        client.post("/api/v1/ares/qualify", headers=HEADERS,
                    json={"workspace_id": WID, "lead": {"nom": "B"}, "icp": ICP})
        assert prov.calls == 2  # deux prompts différents → deux vrais appels
    finally:
        app.dependency_overrides.pop(get_provider, None)
