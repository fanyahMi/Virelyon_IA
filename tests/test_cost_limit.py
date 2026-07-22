"""Tests du plafond de coût par workspace (§8.5)."""
import pytest

from app.gateway import router as gw_router
from app.gateway.cost_tracker import CostLimitExceeded, CostTracker
from tests.conftest import HEADERS

WID = "33333333-3333-3333-3333-333333333333"
LEAD = {"nom": "X", "secteur": "marketing"}
ICP = {"secteurs_inclus": ["marketing"]}


def test_enforce_limit_unitaire():
    ct = CostTracker()
    ct.record("w", "claude-sonnet-4-6", 1000, 1000)  # génère un coût > 0
    with pytest.raises(CostLimitExceeded):
        ct.enforce_limit("w", 0.0001)
    # limite 0 = illimité → jamais d'exception
    ct.enforce_limit("w", 0)


def test_plafond_endpoint_429(client, use_provider, monkeypatch):
    class FakeSettings:
        max_cost_per_workspace = 0.0001  # plafond très bas
        default_max_tokens = 1024

    monkeypatch.setattr(gw_router, "get_settings", lambda: FakeSettings())
    use_provider('{"qualifie": true, "confiance": 0.9, "motif": "ok"}')

    # Deux leads DIFFÉRENTS → deux appels payants (pas de cache hit).
    lead_a = {"nom": "Alpha", "secteur": "marketing"}
    lead_b = {"nom": "Beta", "secteur": "marketing"}

    # 1er appel : coût nul avant → passe, enregistre ~0.001 $
    r1 = client.post("/api/v1/ares/qualify", headers=HEADERS,
                     json={"workspace_id": WID, "lead": lead_a, "icp": ICP})
    assert r1.status_code == 200

    # 2e appel : coût cumulé ≥ plafond → 429
    r2 = client.post("/api/v1/ares/qualify", headers=HEADERS,
                     json={"workspace_id": WID, "lead": lead_b, "icp": ICP})
    assert r2.status_code == 429
