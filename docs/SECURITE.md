# Sécurité — Service IA

> Comment le service IA est sécurisé, et ce qu'il reste à faire au déploiement.
> Objectif : garantir que **seul le backend** appelle le service, protéger la
> **facture LLM**, et ne jamais exposer de secret.

---

## 1. Modèle de menace (en bref)

Le service IA est un composant **interne** (server-à-server). Les risques principaux :
1. Un **appelant non autorisé** (autre que le backend) qui utilise le service.
2. Une **dérive de coût** LLM (appels massifs → facture qui explose).
3. Une **fuite de secret** (clé Claude, secret interne).
4. Une **injection de prompt** via le contenu externe traité (réponses de prospects).

---

## 2. Défense en profondeur (les couches)

### Couche 1 — Isolation réseau *(à faire au déploiement)*
Le service **ne doit pas être exposé publiquement**. Seul le backend peut l'atteindre.
- **Docker :** ne pas publier le port en prod (le `docker-compose.yml` le publie **uniquement pour le dev**).
- **Cloud :** Security Group / firewall autorisant seulement l'IP/le groupe du backend.

### Couche 2 — Authentification service-à-service *(implémenté)*
Chaque route `/api/v1/...` exige le header **`X-Internal-Key`**, comparé au secret attendu avec **`hmac.compare_digest`** (temps constant → anti timing-attack).
→ Sans le bon secret : **401**. Voir `app/core/security.py`.

### Couche 3 — TLS *(à faire au déploiement)*
Chiffrer le transport backend ↔ IA (les données peuvent contenir des PII de prospects).

### Couche 4 — mTLS *(optionnel, prod costaud)*
Authentification mutuelle par certificats. À envisager plus tard ; non requis pour le MVP.

---

## 3. Protection de la facture LLM *(implémenté)*

| Mesure | Où | Effet |
|---|---|---|
| **Plafond de coût par workspace** | `MAX_COST_PER_WORKSPACE` / `cost_tracker.enforce_limit` | bloque (HTTP **429**) au-delà du seuil |
| **Cache des réponses** | `gateway/cache.py` | appels identiques = coût 0 (`meta.cached`) |
| **Suivi des coûts** | `cost_tracker` | coût réel par workspace (`GET /costs/{id}`) |
| **Filtre/scoring sans LLM** | `ares/scoring.py` | la logique pure ne consomme aucun token |

> `MAX_COST_PER_WORKSPACE=0` = illimité (désactivé). Mettre une valeur > 0 pour activer le plafond.

---

## 4. Gestion des secrets *(implémenté / config)*

- **`ANTHROPIC_API_KEY`** — clé Claude, **server-side uniquement**, jamais renvoyée dans une réponse, jamais loggée.
- **`INTERNAL_API_KEY`** — secret partagé backend↔IA. À générer fort :
  `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
- **`.env` est gitignored** → aucun secret dans le dépôt (seul `.env.example` sans valeurs est versionné).
- **Rotation :** changer `INTERNAL_API_KEY` des deux côtés (backend + IA) en cas de fuite.

---

## 5. Robustesse & entrées *(implémenté)*

- **Validation stricte** des entrées (Pydantic) → un payload malformé est rejeté (**422**) avant tout traitement.
- **Erreurs LLM propres** : `503` (non configuré / indisponible), `502` (réponse invalide) — **jamais de 500 opaque** ni de fuite d'info technique.
- **Pas de CORS** : le service refuse par conception le contexte navigateur.
- **Utilisateur non-root** dans le conteneur Docker (surface d'attaque réduite).

---

## 6. Sécurité « métier » (garde-fous CDCF §0)

- **Prompts système blindés** : le contenu externe (réponses de prospects, données brutes) ne doit pas pouvoir **détourner** les instructions. Les prompts imposent une **sortie JSON stricte** et les garde-fous non-négociables (jamais « remplacer un humain », etc.).
- **Confiance faible → file manuelle** : aucune action automatique irréversible sans confiance suffisante.
- **Ne jamais logger** les contenus sensibles (PII de prospects) — prudence RGPD sur les logs.

---

## 7. Frontières (ce que le service NE fait PAS)

- ❌ Pas d'**authentification des utilisateurs finaux** (c'est le backend ; ici, auth **service-à-service** seulement).
- ❌ Pas d'**isolation multi-tenant des données / RLS** (backend + Postgres).
- ❌ Pas d'**accès à la base** (stateless → rien à voler côté données).
- ❌ Pas de **gestion des secrets de canal** (Orange, CRM) — backend.

→ Cette petite surface (auth d'appel + protection du coût) est justement ce qui rend le service **simple à sécuriser**.

---

## 8. Checklist de déploiement

- [ ] `INTERNAL_API_KEY` **fort** (généré, ≠ valeur d'exemple), partagé avec le backend.
- [ ] `ANTHROPIC_API_KEY` en variable d'env / gestionnaire de secrets (jamais dans le code).
- [ ] Port **non exposé** publiquement (réseau interne / Security Group : backend seulement).
- [ ] **TLS** activé entre backend et IA.
- [ ] `MAX_COST_PER_WORKSPACE` défini si on veut un plafond actif.
- [ ] Logs **sans** secrets ni PII.
- [ ] Conteneur en **non-root** (déjà le cas dans le `Dockerfile`).

---

## 9. Références
- `app/core/security.py` — l'authentification service-à-service.
- `app/gateway/cost_tracker.py` — le plafond de coût.
- `app/gateway/cache.py` — le cache.
- `CONTRAT_API.md` — les codes d'erreur et le contrat.
- `../STRUCTURE_ET_AUTONOMIE.md` — le découplage.
