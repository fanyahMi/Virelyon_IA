# Données de test — ARES

Jeux de données prêts à l'emploi pour tester le service IA **avec ce qui est disponible aujourd'hui**.

## Lancer les tests

1. Démarrer le service (dans un terminal) :
   ```bash
   make run            # → http://localhost:8080
   ```
2. Lancer le script (dans un autre terminal) :
   ```bash
   ./samples/run.sh
   # ou en surchargeant l'URL / la clé :
   AI_URL=http://localhost:8080 AI_KEY=demo-secret ./samples/run.sh
   ```
   > `AI_KEY` doit correspondre à `INTERNAL_API_KEY` de ton `.env`.

## Ce qui marche SANS clé Claude ✅ (logique pure / déterministe)

| Fichier | Endpoint | Résultat attendu |
|---|---|---|
| `score_bon.json` | `POST /api/v1/ares/score` | **score élevé** (dans l'ICP, complet, signaux) → palier haut |
| `score_hors_icp.json` | `POST /api/v1/ares/score` | **score bas** (secteur exclu → `fit = 0`) |
| `score_incomplet.json` | `POST /api/v1/ares/score` | score bas (faible complétude) |
| `decide_plafond.json` | `POST /api/v1/ares/decide` | **`"action": "arrêt"`** (plafond 3/3 atteint, `meta: null`) |
| — | `GET /api/v1/costs/{id}` | coûts cumulés du workspace |
| — | `GET /health` | `{"status":"ok"}` |

## Ce qui NÉCESSITE `ANTHROPIC_API_KEY` ⚠️ (sinon 503 propre)

| Fichier | Endpoint | Modèle |
|---|---|---|
| `qualify.json` | `POST /api/v1/ares/qualify` | Claude Sonnet 4.6 |
| `classify.json` | `POST /api/v1/ares/classify` | Claude Haiku 4.5 |
| `generate.json` | `POST /api/v1/ares/generate` | Claude Sonnet 4.6 |
| `decide_continuer.json` | `POST /api/v1/ares/decide` | Claude (plafond non atteint) |

Pour les activer : mettre une vraie clé dans `.env` → `ANTHROPIC_API_KEY=sk-ant-...`

## Curl manuel (exemple)
```bash
curl -X POST http://localhost:8080/api/v1/ares/score \
  -H "X-Internal-Key: demo-secret" -H "Content-Type: application/json" \
  --data @samples/score_bon.json
```

## Les leads fournis (pour comprendre le scoring)
- **Studio Créa** (`score_bon`) : marketing, 18 salariés, fondateur, complet, 2 signaux → cas idéal.
- **Hôtel du Port** (`score_hors_icp`) : secteur `hotellerie` **exclu** → éliminé par le fit.
- **Entreprise Inconnue** (`score_incomplet`) : quasi vide → faible complétude.
- **Agence Nova** (`qualify`/`generate`) : communication, décideur, avec signal de recrutement.
