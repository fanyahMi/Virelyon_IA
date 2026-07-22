"""Tests des endpoints LLM avec un provider mocké (aucun appel réseau)."""
from tests.conftest import HEADERS

WID = "11111111-1111-1111-1111-111111111111"
LEAD = {"nom": "Studio Créa", "secteur": "marketing"}
ICP = {"secteurs_inclus": ["marketing"]}


def test_qualify_mocke(client, use_provider):
    use_provider('{"qualifie": true, "confiance": 0.9, "motif": "correspond à l\'ICP"}')
    r = client.post("/api/v1/ares/qualify", headers=HEADERS,
                    json={"workspace_id": WID, "lead": LEAD, "icp": ICP})
    assert r.status_code == 200
    body = r.json()
    assert body["qualifie"] is True
    assert body["confiance"] == 0.9
    assert body["meta"]["model_used"] == "claude-sonnet-4-6"
    assert body["meta"]["cost_estimate"] > 0


def test_classify_mocke(client, use_provider):
    use_provider('```json\n{"categorie": "Intéressé", "confiance": 0.8, "date_relance": null}\n```')
    r = client.post("/api/v1/ares/classify", headers=HEADERS,
                    json={"workspace_id": WID, "message_entrant": "Oui, ça m'intéresse !"})
    assert r.status_code == 200
    body = r.json()
    assert body["categorie"] == "Intéressé"
    assert body["meta"]["model_used"] == "claude-haiku-4-5"  # tier fast


def test_generate_mocke(client, use_provider):
    use_provider('{"texte": "Bonjour, ...", "canal": "email"}')
    r = client.post("/api/v1/ares/generate", headers=HEADERS,
                    json={"workspace_id": WID, "lead": LEAD, "etape": "J0"})
    assert r.status_code == 200
    assert r.json()["canal"] == "email"


def test_reponse_llm_invalide_502(client, use_provider):
    use_provider("ceci n'est pas du JSON")
    r = client.post("/api/v1/ares/qualify", headers=HEADERS,
                    json={"workspace_id": WID, "lead": LEAD, "icp": ICP})
    assert r.status_code == 502
