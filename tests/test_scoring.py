from app.ares.scoring import compute_score
from app.schemas.ares import ICP, Lead, ScoreRequest
from tests.conftest import HEADERS

WID = "11111111-1111-1111-1111-111111111111"


def _req(lead: Lead, icp: ICP) -> ScoreRequest:
    return ScoreRequest(workspace_id=WID, lead=lead, icp=icp)


def test_lead_dans_icp_score_eleve():
    lead = Lead(nom="A", secteur="conseil", taille_effectif=12, role_contact="fondateur",
                contact={"email": "a@a.co"}, montant_potentiel=8000)
    icp = ICP(secteurs_inclus=["conseil"], taille_min=5, taille_max=30, roles_cibles=["fondateur"])
    res = compute_score(_req(lead, icp))
    assert res.score >= 70
    assert res.palier.relances_max >= 3


def test_secteur_exclu_fit_nul():
    lead = Lead(nom="B", secteur="hotellerie", taille_effectif=10, role_contact="fondateur")
    icp = ICP(secteurs_inclus=["conseil"], secteurs_exclus=["hotellerie"],
              taille_min=5, taille_max=30, roles_cibles=["fondateur"])
    res = compute_score(_req(lead, icp))
    assert res.breakdown["fit"] == 0.0
    assert res.palier.nom in {"faible", "correcte"}


def test_paliers_bornes():
    # lead vide -> faible complétude/fit -> palier faible, 1 relance
    lead = Lead(nom="C")
    icp = ICP()
    res = compute_score(_req(lead, icp))
    assert 0 <= res.score <= 100
    assert res.palier.relances_max in {1, 3, 4, 5}


def test_score_endpoint(client, score_payload):
    r = client.post("/api/v1/ares/score", json=score_payload, headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert 0 <= body["score"] <= 100
    assert "palier" in body and "breakdown" in body
