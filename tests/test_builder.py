"""Tests de l'Agent Builder : référentiels, validation d'ICP (pure), extraction (LLM mocké)."""
import json

from app.builder.icp import valider_icp
from app.builder.referentiels import normaliser_role, normaliser_secteur
from app.schemas.ares import ICP
from app.schemas.builder import ICPValiderRequest
from tests.conftest import HEADERS

WID = "11111111-1111-1111-1111-111111111111"


def _valider(**kwargs):
    return valider_icp(ICPValiderRequest(icp=ICP(**kwargs)))


# ----- Normalisation ---------------------------------------------------------
def test_normalisation_synonymes_secteurs():
    assert normaliser_secteur("Marketing digital") == "marketing"
    assert normaliser_secteur("Agence de communication") == "communication"
    assert normaliser_secteur("Consulting") == "conseil"
    assert normaliser_secteur("ESN") == "developpement"


def test_normalisation_accents_et_casse():
    assert normaliser_secteur("COMPTABILITÉ") == "comptabilite"
    assert normaliser_secteur("  Conseil  ") == "conseil"


def test_normalisation_libelle_composite():
    # Ce que rend typiquement un scraper Google Maps.
    assert normaliser_secteur("Agence de marketing digital B2B") == "marketing"


def test_normalisation_roles():
    assert normaliser_role("CEO") == "fondateur"
    assert normaliser_role("Co-fondateur") == "fondateur"
    assert normaliser_role("Responsable") == "manager"


def test_normalisation_hors_referentiel():
    assert normaliser_secteur("plomberie industrielle") is None
    assert normaliser_role("") is None


# ----- Validation : erreurs bloquantes ---------------------------------------
def test_taille_min_superieure_max_est_une_erreur():
    res = _valider(taille_min=30, taille_max=5)
    assert res.valide is False
    assert any(d.niveau == "erreur" and d.champ == "taille_effectif" for d in res.diagnostics)


def test_secteur_inclus_et_exclu_est_une_erreur():
    res = _valider(secteurs_inclus=["marketing"], secteurs_exclus=["marketing"])
    assert res.valide is False
    assert any(d.niveau == "erreur" and d.champ == "secteurs" for d in res.diagnostics)


# ----- Validation : avertissements -------------------------------------------
def test_icp_vide_ne_filtre_rien():
    res = _valider()
    assert res.valide is True  # pas bloquant, mais inutile
    assert res.criteres_actifs == 0
    assert any("Aucun critère" in d.message for d in res.diagnostics)


def test_secteur_personnalise_est_accepte():
    # Chaque client cible son propre marché : "plomberie" est légitime.
    res = _valider(secteurs_inclus=["plomberie"])
    assert res.valide is True
    diag = next(d for d in res.diagnostics if d.champ == "secteurs_inclus")
    assert diag.niveau == "info"
    assert "personnalisé" in diag.message


def test_role_hors_catalogue_avertit():
    # Les rôles restent un catalogue fermé : ils pilotent les intitulés de poste.
    res = _valider(secteurs_inclus=["conseil"], roles_cibles=["Grand Manitou"])
    assert any(
        d.niveau == "avertissement" and d.champ == "roles_cibles" for d in res.diagnostics
    )


def test_valeur_non_normalisee_propose_la_forme_canonique():
    res = _valider(secteurs_inclus=["Marketing digital"])
    diag = next(d for d in res.diagnostics if d.champ == "secteurs_inclus")
    assert diag.suggestion == "Utiliser « marketing »."


def test_fourchette_trop_etroite_avertit():
    res = _valider(secteurs_inclus=["conseil"], taille_min=10, taille_max=12)
    assert any(d.champ == "taille_effectif" for d in res.diagnostics)


def test_icp_conforme_est_propre():
    res = _valider(
        secteurs_inclus=["marketing", "conseil"],
        secteurs_exclus=["hotellerie"],
        taille_min=5,
        taille_max=30,
        roles_cibles=["fondateur", "decideur"],
    )
    assert res.valide is True
    assert res.criteres_actifs == 3
    assert res.diagnostics == []


def test_secteur_du_catalogue_large_ne_declenche_rien():
    # "restauration" est au catalogue : un client peut parfaitement le cibler.
    res = _valider(secteurs_inclus=["restauration"], roles_cibles=["fondateur"])
    assert res.diagnostics == []


def test_canonisation_des_secteurs_personnalises():
    from app.builder.referentiels import canoniser_secteur, est_personnalise

    # Hors catalogue : stabilisé en slug, jamais rejeté.
    assert canoniser_secteur("Plomberie industrielle") == "plomberie_industrielle"
    assert est_personnalise("Plomberie industrielle") is True
    # Au catalogue : ramené à sa forme canonique.
    assert canoniser_secteur("Marketing digital") == "marketing"
    assert est_personnalise("Marketing digital") is False


def test_sous_specialite_est_absorbee_par_son_secteur_parent():
    """« Restauration rapide » → « restauration ».

    Voulu : Big Data applique la même canonisation à l'ingestion, donc les deux
    côtés restent comparables. On perd la nuance, on garde la correspondance.
    """
    from app.builder.referentiels import canoniser_secteur

    assert canoniser_secteur("Restauration rapide") == "restauration"
    assert canoniser_secteur("Conseil en stratégie") == "conseil"


# ----- Endpoints -------------------------------------------------------------
def test_referentiels_endpoint(client):
    r = client.get("/api/v1/builder/referentiels", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert "marketing" in body["secteurs"]
    assert "fondateur" in body["roles"]
    assert set(body["secteurs_services_b2b"]).isdisjoint(body["secteurs_autres"])


def test_referentiels_exige_la_cle(client):
    assert client.get("/api/v1/builder/referentiels").status_code == 401


def test_valider_endpoint(client):
    payload = {"icp": {"secteurs_inclus": ["marketing"], "taille_min": 30, "taille_max": 5}}
    r = client.post("/api/v1/builder/icp/valider", json=payload, headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["valide"] is False


def test_extraire_endpoint(client, use_provider):
    use_provider(
        json.dumps(
            {
                "icp": {
                    "secteurs_inclus": ["Marketing digital", "conseil"],
                    "secteurs_exclus": [],
                    "taille_min": 5,
                    "taille_max": 30,
                    "roles_cibles": ["CEO"],
                },
                "confiance": 0.9,
                "non_reconnu": [],
            }
        )
    )
    payload = {
        "workspace_id": WID,
        "texte": "Agences de marketing digital et de conseil, 5 à 30 personnes, je vise les CEO",
    }
    r = client.post("/api/v1/builder/icp/extraire", json=payload, headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    # Le modèle a renvoyé des libellés libres : la renormalisation les a canonisés.
    assert body["icp"]["secteurs_inclus"] == ["marketing", "conseil"]
    assert body["icp"]["roles_cibles"] == ["fondateur"]
    assert body["confiance"] == 0.9


def test_extraire_canonise_les_secteurs_personnalises(client, use_provider):
    use_provider(
        json.dumps(
            {
                "icp": {
                    "secteurs_inclus": ["marketing", "plomberie"],
                    "secteurs_exclus": [],
                    "taille_min": None,
                    "taille_max": None,
                    "roles_cibles": [],
                },
                "confiance": 0.6,
                "non_reconnu": [],
            }
        )
    )
    payload = {"workspace_id": WID, "texte": "agences marketing et plombiers"}
    r = client.post("/api/v1/builder/icp/extraire", json=payload, headers=HEADERS)
    body = r.json()
    # Une valeur inventée par le modèle ne doit JAMAIS entrer dans l'ICP.
    # Un secteur personnalisé est canonisé, pas jeté.
    assert body["icp"]["secteurs_inclus"] == ["marketing", "plomberie"]


def test_extraire_n_invente_pas_de_fourchette(client, use_provider):
    use_provider(
        json.dumps(
            {
                "icp": {
                    "secteurs_inclus": ["conseil"],
                    "secteurs_exclus": [],
                    "taille_min": None,
                    "taille_max": None,
                    "roles_cibles": [],
                },
                "confiance": 0.7,
                "non_reconnu": [],
            }
        )
    )
    payload = {"workspace_id": WID, "texte": "cabinets de conseil"}
    r = client.post("/api/v1/builder/icp/extraire", json=payload, headers=HEADERS)
    icp = r.json()["icp"]
    assert icp["taille_min"] is None and icp["taille_max"] is None
