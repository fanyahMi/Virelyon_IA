"""Tests de /ares/decide (§5.4)."""
from tests.conftest import HEADERS

WID = "11111111-1111-1111-1111-111111111111"
LEAD = {"nom": "Studio Créa", "secteur": "marketing"}
PALIER = {"nom": "correcte", "relances_max": 3, "cadence": [0, 4, 10, 18]}


def test_plafond_atteint_arret_sans_llm(client):
    """Plafond de relance atteint → 'arrêt' de façon déterministe, SANS clé Claude."""
    r = client.post(
        "/api/v1/ares/decide",
        headers=HEADERS,
        json={"workspace_id": WID, "lead": LEAD, "palier": PALIER, "relances_effectuees": 3},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["action"] == "arrêt"
    assert body["meta"] is None  # décision déterministe, aucun appel LLM


def test_plafond_non_atteint_appelle_llm(client, use_provider):
    use_provider('{"action": "continuer", "justification": "score correct, marge de relance"}')
    r = client.post(
        "/api/v1/ares/decide",
        headers=HEADERS,
        json={"workspace_id": WID, "lead": LEAD, "palier": PALIER, "relances_effectuees": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["action"] == "continuer"
    assert body["meta"]["model_used"] == "claude-sonnet-4-6"


def test_action_avec_accent_normalisee(client, use_provider):
    use_provider('{"action": "arret", "justification": "pas pertinent"}')  # sans accent
    r = client.post(
        "/api/v1/ares/decide",
        headers=HEADERS,
        json={"workspace_id": WID, "lead": LEAD, "palier": PALIER, "relances_effectuees": 0},
    )
    assert r.status_code == 200
    assert r.json()["action"] == "arrêt"  # normalisé vers la valeur du CDCF


def test_decide_protege(client):
    r = client.post(
        "/api/v1/ares/decide",
        json={"workspace_id": WID, "lead": LEAD, "palier": PALIER, "relances_effectuees": 0},
    )
    assert r.status_code == 401
