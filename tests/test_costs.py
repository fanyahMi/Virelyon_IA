from tests.conftest import HEADERS

WID = "22222222-2222-2222-2222-222222222222"


def test_cout_agrege_par_workspace(client, use_provider):
    use_provider('{"qualifie": true, "confiance": 0.7, "motif": "ok"}')
    # un appel LLM enregistre un coût
    client.post("/api/v1/ares/qualify", headers=HEADERS,
                json={"workspace_id": WID, "lead": {"nom": "X"}, "icp": {}})

    r = client.get(f"/api/v1/costs/{WID}", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["input_tokens"] == 100
    assert body["output_tokens"] == 50
    assert body["cost"] > 0


def test_costs_protege(client):
    r = client.get(f"/api/v1/costs/{WID}")
    assert r.status_code == 401
