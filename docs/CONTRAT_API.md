# Contrat d'API — Service IA (pour le backend)

> **La seule chose dont le backend a besoin pour appeler le service IA.**
> Le service est **stateless** : le backend passe les données dans la requête, l'IA
> renvoie une décision en JSON. Le backend **persiste** et gère l'isolation (RLS).
> Le Swagger vivant : `http://<host>/docs`.

---

## 1. Généralités

| | |
|---|---|
| **Base URL (dev)** | `http://localhost:8080` |
| **Auth** | header **`X-Internal-Key: <secret>`** sur toutes les routes `/api/v1/...` |
| **Content-Type** | `application/json` |
| **Multi-tenant** | `workspace_id` (UUID) **obligatoire** dans chaque requête métier |
| **CORS** | désactivé (appels **server-à-server** uniquement) |

> `/health` est public (pas de header). Tout le reste exige `X-Internal-Key`.

---

## 2. Codes de réponse

| Code | Signification | Action côté backend |
|---|---|---|
| `200` | OK | lire la réponse |
| `401` | `X-Internal-Key` manquante/invalide | vérifier le secret partagé |
| `422` | payload invalide (validation) | corriger le corps de la requête |
| `429` | **plafond de coût du workspace atteint** | ne plus appeler ce workspace (ou relever le plafond) |
| `502` | réponse LLM invalide | réessayer / journaliser |
| `503` | LLM non configuré ou indisponible | vérifier `ANTHROPIC_API_KEY` / réessayer |

---

## 3. Objets partagés (le backend les envoie)

**Lead**
```json
{
  "nom": "Studio Créa",
  "secteur": "marketing",
  "taille_effectif": 18,
  "role_contact": "fondateur",
  "contact": { "email": "contact@studiocrea.co" },
  "montant_potentiel": 8000,
  "donnees_brutes": { "signaux_bruts": [ { "type": "levee_de_fonds", "detail": "Série A 3M€" } ] },
  "ingested_at": "2026-07-20T09:00:00Z",
  "langue": "fr"
}
```
*(seul `nom` est requis ; les autres champs améliorent la décision.)*

**ICP** (profil client idéal — le backend le lit depuis `workspace_icp_config`)
```json
{
  "secteurs_inclus": ["marketing", "conseil"],
  "secteurs_exclus": ["hotellerie"],
  "taille_min": 5,
  "taille_max": 30,
  "roles_cibles": ["fondateur", "decideur"]
}
```

**Meta** (jointe à chaque réponse issue d'un appel LLM)
```json
{ "model_used": "claude-sonnet-4-6", "usage": { "input_tokens": 512, "output_tokens": 80 }, "cost_estimate": 0.0021, "cached": false }
```

---

## 4. Endpoints

### `POST /api/v1/ares/qualify` — Qualification (Claude Sonnet)
**Entrée**
```json
{ "workspace_id": "UUID", "lead": { … }, "icp": { … } }
```
**Sortie**
```json
{ "qualifie": true, "confiance": 0.9, "motif": "correspond à l'ICP", "meta": { … } }
```

### `POST /api/v1/ares/score` — Scoring (logique pure, sans LLM)
**Entrée** — `scoring_config` optionnel (pondérations par workspace)
```json
{ "workspace_id": "UUID", "lead": { … }, "icp": { … },
  "scoring_config": { "poids_fraicheur": 0.25, "poids_completude": 0.25, "poids_fit": 0.4, "poids_engagement": 0.1 } }
```
**Sortie**
```json
{ "score": 96, "breakdown": { "fraicheur": 1.0, "completude": 1.0, "fit": 1.0, "engagement": 0.6, "poids": { … } },
  "palier": { "nom": "quasi_parfait", "relances_max": 5, "cadence": [0,3,7,12,18,25] } }
```

### `POST /api/v1/ares/generate` — Génération de message (Claude Sonnet)
**Entrée**
```json
{ "workspace_id": "UUID", "lead": { … }, "etape": "J0",
  "ton_de_voix": "professionnel", "historique": [], "language": "fr" }
```
**Sortie**
```json
{ "texte": "Bonjour, …", "canal": "email", "meta": { … } }
```

### `POST /api/v1/ares/classify` — Classification de réponse (Claude Haiku)
**Entrée**
```json
{ "workspace_id": "UUID", "message_entrant": "Oui, ça m'intéresse…", "language": "fr" }
```
**Sortie** — `categorie` ∈ { Intéressé, À recontacter plus tard, Pas intéressé, Demande de retrait, Question hors-scope }
```json
{ "categorie": "Intéressé", "confiance": 0.8, "date_relance": null, "meta": { … } }
```

### `POST /api/v1/ares/decide` — Décision de prochaine action
**Entrée** — inclut le palier et le compteur de relances (v1.1)
```json
{ "workspace_id": "UUID", "lead": { … },
  "palier": { "nom": "correcte", "relances_max": 3, "cadence": [0,4,10,18] },
  "relances_effectuees": 1, "contexte": "Aucune réponse après J0 et J+4." }
```
**Sortie** — `action` ∈ { continuer, pause, escalade, arrêt }. `meta: null` si décision **déterministe** (plafond atteint, aucun appel LLM).
```json
{ "action": "continuer", "justification": "score correct, marge de relance", "meta": { … } }
```

### `GET /api/v1/costs/{workspace_id}` — Coûts cumulés (pour FINANCE)
```json
{ "workspace_id": "UUID", "input_tokens": 1520, "output_tokens": 340, "cost": 0.0057 }
```

### `GET /health` — Santé (public)
```json
{ "status": "ok", "service": "virelyon-ai" }
```

---

## 5. Exemple d'appel
```bash
curl -X POST http://localhost:8080/api/v1/ares/score \
  -H "X-Internal-Key: $INTERNAL_API_KEY" -H "Content-Type: application/json" \
  --data '{"workspace_id":"11111111-1111-1111-1111-111111111111",
           "lead":{"nom":"Studio Créa","secteur":"marketing","taille_effectif":18,"role_contact":"fondateur"},
           "icp":{"secteurs_inclus":["marketing"],"taille_min":5,"taille_max":30,"roles_cibles":["fondateur"]}}'
```

---

## 6. Ce que le backend doit faire de son côté
- **Persister** les résultats (leads, statuts, `messages`, `lead_events`) — l'IA ne touche pas la base.
- **Appliquer l'isolation multi-tenant** (RLS) — l'IA ne fait que recevoir `workspace_id`.
- **Fournir l'ICP** (depuis `workspace_icp_config`) dans les requêtes qualify/score.
- **Gérer les secrets de canal** (Orange, CRM) — hors périmètre IA.
- **Orchestrer** (séquençage, relances, envois) via n8n ; appeler l'IA aux points de décision.

## 7. Ce que le backend n'a PAS à faire
- Connaître la structure interne du service IA (seul le contrat ci-dessus compte).
- Savoir si un endpoint utilise Claude ou une logique pure (transparent).
- Gérer les modèles/prompts (côté DEV IA).

> **Point de coordination unique :** ce contrat + le header d'auth + le déploiement.
> La structure interne du service IA reste à l'équipe DEV IA (voir `../STRUCTURE_ET_AUTONOMIE.md`).
