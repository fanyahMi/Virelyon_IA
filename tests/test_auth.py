from tests.conftest import HEADERS


def test_sans_cle_rejete(client, score_payload):
    r = client.post("/api/v1/ares/score", json=score_payload)
    assert r.status_code == 401


def test_mauvaise_cle_rejete(client, score_payload):
    r = client.post("/api/v1/ares/score", json=score_payload, headers={"X-Internal-Key": "wrong"})
    assert r.status_code == 401


def test_bonne_cle_acceptee(client, score_payload):
    r = client.post("/api/v1/ares/score", json=score_payload, headers=HEADERS)
    assert r.status_code == 200
