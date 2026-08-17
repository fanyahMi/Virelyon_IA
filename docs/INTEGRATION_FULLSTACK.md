# Intégration — ce que le Fullstack doit construire pour utiliser l'IA

> **Document de passation entre le DEV IA et le DEV FULLSTACK.**
> Le frontend ne parle **jamais** au service IA — uniquement au backend.
> Réf. : `CONTRAT_API.md` (formats détaillés), `ARES.md` (logique métier), CDCF ARES v1.1.
> Statut : **cadrage** — à valider ensemble avant implémentation.

---

## 0. Deux modes d'accès aux données — lire ceci en premier

Le service IA fonctionne aujourd'hui en **mode payload**, et évolue vers un **mode lecture directe**.
Les deux coexisteront : ils ne servent pas les mêmes cas.

| | **Mode payload** (existant) | **Mode lecture directe** (décidé, à construire) |
|---|---|---|
| Qui lit la donnée | le **backend** | le **service IA** |
| Ce que le backend envoie | l'objet `lead` + l'`icp` complets | un `workspace_id` + des filtres |
| Endpoints concernés | `/qualify`, `/score`, `/generate`, `/classify`, `/decide` | `/leads/qualifies` (à créer) |
| Cas d'usage | décision **unitaire** sur un lead (ingestion, envoi, réponse) | le client demande **sa liste** de leads qualifiés |
| État | ✅ opérationnel et testé | ⏳ à construire — voir §9 |

**Pourquoi les deux.** Le mode payload reste le bon outil quand n8n traite un lead à la fois :
c'est testable sans réseau, sans base, et déjà en place. Le mode lecture directe répond au besoin
exprimé par la plateforme — *« Airtel demande les leads qui lui correspondent »* — où faire transiter
des centaines de leads dans un corps de requête n'a pas de sens.

> **Règle d'or, valable dans les deux modes :** l'IA décide, le frontend affiche,
> et un écran n'attend jamais une réponse de Claude — sauf le bac à sable.

---

## 0 bis. Résumé en une phrase

Le Fullstack a **quatre chantiers** :

1. **brancher** le service IA (config, client HTTP, gestion d'erreurs),
2. **appeler** l'IA aux 5 points de décision et **persister** les résultats,
3. **exposer** au frontend une API qui lit des colonnes déjà remplies,
4. **construire** 8 pages, dont une seule appelle l'IA en direct.

---

## 1. Périmètre — qui fait quoi

| Responsabilité | DEV IA | DEV FULLSTACK |
|---|---|---|
| Logique de décision (prompts, scoring, garde-fous) | ✅ | — |
| Endpoints du service IA | ✅ | consomme |
| Client HTTP vers le service IA | — | ✅ |
| Schéma de base + migrations | — | ✅ |
| Persistance des décisions (mode payload) | — | ✅ |
| Lecture Supabase depuis l'IA (mode direct) | ✅ | fournit accès + schéma |
| Isolation multi-tenant côté API (JWT) | — | ✅ |
| Isolation multi-tenant côté IA (session Postgres) | ✅ | — |
| API REST exposée au frontend | — | ✅ |
| Pages du dashboard | — | ✅ |
| Déclenchement asynchrone (tâches de fond) | — | ✅ (avec n8n) |

> **En mode payload**, le service IA n'écrit rien : toute colonne remplie par une décision
> l'est par le backend, dans sa propre transaction.
> **En mode lecture directe**, l'IA lit `leads` et `workspace_icp_config` elle-même — et
> devient alors responsable de poser `workspace_id` sur sa propre session (voir §9.2).

---

## 2. Le socle (à faire une fois)

### 2.1 Configuration

```bash
AI_URL=http://ia:8080              # URL du service IA
AI_INTERNAL_KEY=<secret partagé>   # header X-Internal-Key sur chaque appel
```

Un client `httpx` async, avec le header `X-Internal-Key` sur toutes les routes `/api/v1/...`.
La route `/health` est publique (pas de header).

> ⚠️ **`AI_INTERNAL_KEY` ne doit jamais franchir la frontière serveur** — ni dans une réponse
> d'API, ni dans une page, ni dans un log. Le service IA a **CORS désactivé** : il est conçu
> pour des appels server-à-server uniquement. Un dashboard qui porterait cette clé exposerait
> le budget Claude de **tous** les workspaces.

### 2.2 Colonnes à créer

Le service IA produit des décisions ; le backend doit prévoir où les ranger.

**Table `leads`**

| Colonne | Type | Rempli après |
|---|---|---|
| `qualification_status` | text — `qualifie` / `rejete` / `a_valider` | `/qualify` |
| `qualification_confiance` | float 0-1 | `/qualify` |
| `qualification_motif` | text | `/qualify` |
| `score` | int 0-100 | `/score` |
| `score_breakdown` | jsonb | `/score` |
| `palier` | text (`quasi_parfait`, `tres_forte`, `correcte`, `faible`) | `/score` |
| `relances_max` | int | `/score` |
| `relances_effectuees` | int | à chaque envoi |
| `statut_pipeline` | text | transitions Kanban |
| `prochaine_relance` | timestamptz | séquençage |

**Autres tables** : `messages` (contenu généré, canal, statut d'envoi),
`lead_events` (journal horodaté de **chaque** décision — exigence d'observabilité §4.11),
`agent_config`, `workspace_icp_config`, `suppression_list`, `embeddings`.

### 2.3 Gestion des erreurs

| Code | Signification | Action du backend |
|---|---|---|
| `200` | OK | lire la réponse |
| `401` | `X-Internal-Key` manquante ou invalide | alerte de configuration — **ne pas réessayer** |
| `422` | payload invalide | bug backend — corriger l'envoi |
| `429` | **plafond de coût du workspace atteint** | **arrêter ce workspace** — ne surtout pas réessayer |
| `502` | réponse LLM invalide | réessayer une fois, puis journaliser |
| `503` | LLM indisponible ou non configuré | réessayer avec backoff |

> **Timeouts :** un appel Sonnet prend 5 à 15 secondes. Prévoir un timeout généreux
> (30 s) côté client HTTP — mais **jamais** dans le chemin d'une requête utilisateur (voir §3.3).

---

## 3. Les 5 branchements IA

### 3.1 Vue d'ensemble

| Quand | Endpoint IA | Corps envoyé | À persister |
|---|---|---|---|
| Nouveau lead ingéré | `POST /api/v1/ares/qualify` | `{workspace_id, lead, icp}` | statut, confiance, motif, `lead_event` |
| Juste après qualification | `POST /api/v1/ares/score` | `{workspace_id, lead, icp, scoring_config}` | score, breakdown, palier |
| Avant chaque envoi | `POST /api/v1/ares/generate` | `{workspace_id, lead, etape, ton_de_voix, historique, language}` | ligne dans `messages` |
| Réponse reçue d'un prospect | `POST /api/v1/ares/classify` | `{workspace_id, message_entrant, language}` | catégorie, `lead_event` |
| Avant relance / après classification | `POST /api/v1/ares/decide` | `{workspace_id, lead, palier, relances_effectuees}` | action, `lead_event` |

Formats exacts des objets `lead`, `icp`, `scoring_config` : voir **`CONTRAT_API.md` §3**.

### 3.2 En mode payload, envoyer l'objet complet

Sur ces 5 endpoints, le service IA **ne va rien chercher en base**. Si `lead.secteur` ou
l'`icp` sont absents, la décision part sur du vide — **sans erreur visible**. C'est le piège
le plus coûteux : tout a l'air de marcher, mais les scores sont faux.

> Cela reste vrai même une fois le mode lecture directe en place : ces 5 endpoints
> conservent leur contrat actuel. Seul le nouvel endpoint de §9 lit la base lui-même.

Le backend doit donc, avant chaque appel :
- lire le lead **complet** depuis la base,
- lire l'ICP depuis `workspace_icp_config` (source unique — jamais un ICP stocké ailleurs),
- lire `scoring_config` depuis `agent_config` si le workspace a des poids personnalisés.

### 3.3 Jamais en synchrone dans une requête utilisateur

La qualification et le scoring tournent en **tâche de fond** (n8n ou file interne),
jamais pendant qu'un utilisateur attend devant son écran.

C'est une exigence du CDCF §8.1 : le dashboard doit répondre en **moins de 2 secondes**.
Un appel Sonnet en prend 5 à 15. Les deux sont incompatibles.

```
❌ Client clique → backend appelle Claude → 12 s d'attente → affichage
✅ Ingestion → tâche de fond → colonnes remplies → Client clique → SELECT → 200 ms
```

### 3.4 Coût : ce qui est cher, ce qui est gratuit

| Endpoint | Appel LLM | Coût | Conséquence |
|---|---|---|---|
| `/score` | **aucun** — logique pure | **gratuit** | recalculable à volonté |
| `/decide` | Haiku (ou aucun si plafond atteint) | faible | — |
| `/classify` | Haiku | faible | une fois par réponse reçue |
| `/qualify` | Sonnet | **élevé** | **ne jamais relancer sur un lead déjà qualifié** |
| `/generate` | Sonnet | **élevé** | une fois par message |

> Persister le verdict de `/qualify` n'est pas une optimisation : c'est ce qui empêche
> de repayer Claude à chaque rafraîchissement d'écran.

### 3.5 Le seuil de confiance — garde-fou de recette

`/qualify` renvoie `{qualifie: bool, confiance: float, motif: str}`.

Le CDCF impose **trois** statuts, pas deux :

```
confiance >= seuil  et  qualifie=true   → qualifie
confiance >= seuil  et  qualifie=false  → rejete   (archivé, jamais supprimé)
confiance <  seuil                      → a_valider  → file manuelle
```

Seuil recommandé : **0,7**, configurable par workspace.

> Garde-fou CDCF §0 : *« Confiance faible → file manuelle, jamais d'action auto irréversible. »*
> Un lead rejeté à 55 % de confiance ne doit **pas** être écarté silencieusement.

### 3.6 Ordre d'appel

```
Lead ingéré par Big Data
   ▼
/qualify  ──── rejete ────► archivage + lead_event  (fin)
   │ qualifie / a_valider
   ▼
/score  → score + palier
   ▼
séquençage n8n (J0, puis cadence du palier)
   ▼
/generate → message → envoi sur le canal
   ▼
réponse du prospect (webhook)
   ▼
/classify → catégorie
   ▼
/decide → continuer | pause | escalade | arrêt
```

À chaque étape : **un `lead_event`**. C'est ce qui alimente les rapports AURA.

---

## 4. API à exposer au frontend

Le frontend ne parle qu'au backend. Endpoints minimum :

| Méthode | Route | Rôle | Appelle l'IA ? |
|---|---|---|---|
| `GET` | `/api/v1/ares/leads?statut=&min_score=&page=` | pipeline Kanban | ❌ SQL pur |
| `POST` | `/api/v1/ares/leads/qualifies` | liste des leads qualifiés d'un workspace | ✅ relais vers l'IA (§9) |
| `PATCH` | `/api/v1/ares/leads/{id}` | déplacer dans le Kanban | ❌ |
| `GET` | `/api/v1/ares/leads/{id}` | fiche détaillée | ❌ |
| `GET` | `/api/v1/ares/validation` | file d'attente humaine | ❌ |
| `POST` | `/api/v1/ares/validation/{id}/approuver` | approuver un message | ❌ |
| `GET`/`PUT` | `/api/v1/workspace/agent-config` | les 5 réglages | ❌ |
| `GET`/`PUT` | `/api/v1/workspace/icp` | ICP structuré | ❌ |
| `POST` | `/api/v1/workspace/formation` | upload de documents | ❌ |
| `POST` | `/api/v1/ares/sandbox` | bac à sable | ✅ **en direct** |
| `POST` | `/api/v1/ares/sourcing/run` | « Rechercher maintenant » | ❌ (déclenche Big Data) |
| `GET` | `/api/v1/ares/rapports` | agrégats + coûts | ❌ |

> **Deux endpoints seulement appellent l'IA en direct** : le bac à sable et la liste des
> leads qualifiés. Tous les autres lisent des colonnes déjà remplies — c'est ce qui rend
> le dashboard instantané.

**Isolation :** le `workspace_id` vient du **JWT**, jamais d'un paramètre de requête —
sinon un utilisateur peut lire les données d'un autre client.

---

## 5. Pages du dashboard

| Page | Contenu | Source | IA en direct |
|---|---|---|---|
| **Agent Builder** | objectif, ICP, canaux, ton de voix | `agent_config`, `workspace_icp_config` | ❌ |
| **Formation** | dépôt de fichiers + état d'indexation | `embeddings` | ❌ |
| **Intégrations** | connexion canaux et CRM | `integration` | ❌ |
| **Bac à sable** | compréhension · action prévue · réponse proposée | appel IA | ✅ |
| **Pipeline** (Kanban) | leads triés par score, avec palier | colonnes persistées | ❌ |
| **Fiche lead** | motif de qualification, détail du score, historique | colonnes persistées | ❌ |
| **File de validation** | messages à approuver + leads `a_valider` | `messages`, `leads` | ❌ |
| **Rapports** | volume, taux de réponse, coût API | agrégats | ❌ |

### 5.1 Détails d'affichage qui comptent

- **Pipeline** — afficher le score **et** le palier. Le score seul ne dit pas au commercial
  combien de relances vont partir (`quasi_parfait` = 5 relances, `faible` = 1).
- **Fiche lead** — afficher le `motif` de qualification en toutes lettres. C'est la phrase
  qui rend la décision de l'IA acceptable ; sans elle, le client subit un verdict opaque.
- **Leads `a_valider`** — un badge distinct. Ce ne sont ni des qualifiés ni des rejetés,
  mais des cas où l'IA a dit « je ne suis pas sûre ».
- **Bac à sable** — afficher les **trois** blocs, pas seulement le message généré.
  Voir « ce qu'ARES a compris » est ce qui crée la confiance.
- **Mode supervision** — prévoir la **validation par lot**. Valider 50 messages un par un
  annule la promesse de gain de temps.

### 5.2 Statuts du pipeline (CDCF)

```
Identifié → Contacté → Répondu → Qualifié → Transmis au commercial
```

---

## 6. Pièges connus

### 6.1 Le référentiel de secteurs — le piège n°1

Le filtrage ICP compare `lead.secteur` et `icp.secteurs_inclus/exclus` avec une
**égalité stricte** (après passage en minuscules).

```
"Marketing"          vs  "marketing"          → ✅ match
"Marketing digital"  vs  "marketing"          → ❌ AUCUN match
```

Si l'Agent Builder laisse saisir du texte libre alors que Big Data écrit des valeurs
normalisées, **la correspondance tombe à zéro sur des leads parfaitement valides** —
et ça ressemblera à un bug de l'IA.

**Solution :** listes déroulantes dans l'Agent Builder, alimentées par le même référentiel
de secteurs que celui utilisé par Big Data.

### 6.2 Le bac à sable coûte de l'argent

C'est le seul endroit où l'utilisateur final déclenche des appels Claude **à volonté**.

- Rate limit par workspace **obligatoire**.
- Comptage **séparé** du budget de prospection — sinon un client curieux consomme
  le plafond destiné à ses vrais leads.

### 6.3 Capturer l'issue réelle dès la v1

Un bouton dans le pipeline pour marquer **signé / perdu / sans réponse**, enregistré
à côté de la prédiction de l'IA.

Même si la calibration automatique n'arrive que plus tard : **une donnée non collectée
est perdue définitivement**. Sans historique, l'apprentissage démarrera à zéro.

### 6.4 Le jour 1 est vide

Le client termine sa configuration, arrive sur son dashboard… et il n'y a rien, parce que
le sourcing tourne la nuit. Prévoir un bouton **« Rechercher maintenant »** ou un message
explicite. Un dashboard vide sans explication, c'est un client qui croit que le produit
est cassé.

### 6.5 La liste de suppression bloque avant génération

Une demande de retrait (RGPD) doit bloquer **avant** l'appel à `/generate` — pas après.
Le workflow de génération ne doit jamais être invoqué pour un contact présent dans
`suppression_list` (CDCF §4.8, sécurité par construction).

---

## 7. Checklist de livraison

Le backend est « prêt à utiliser l'IA » quand :

- [ ] `AI_URL` + `AI_INTERNAL_KEY` configurés, clé **jamais** exposée côté client
- [ ] Client HTTP avec `X-Internal-Key`, timeout 30 s, gestion des codes §2.3
- [ ] Colonnes de §2.2 créées via migration Alembic
- [ ] Les 5 appels branchés, chacun suivi d'une **persistance transactionnelle**
- [ ] Qualification et scoring en **tâche de fond**, jamais dans une requête utilisateur
- [ ] Seuil de confiance appliqué → statut `a_valider` + file manuelle
- [ ] `lead_event` écrit à **chaque** décision
- [ ] `workspace_id` issu du **JWT**, jamais d'un paramètre client
- [ ] Endpoints de §4 exposés, tous en lecture SQL sauf le bac à sable
- [ ] Rate limit + comptage séparé sur le bac à sable
- [ ] ICP saisi en **valeurs normalisées** (listes, pas texte libre)
- [ ] Accès Supabase + schéma réel transmis au DEV IA (§9.4) pour le mode lecture directe

---

## 8. Ce qui n'existe pas encore

À savoir avant de dessiner des écrans :

- **Seul ARES est implémenté.** APEX (support) et AURA (reporting) sont en phase 2 —
  leurs endpoints n'existent pas.
- **Le mode lecture directe** (§9) est **décidé mais non construit** : le service n'a
  aujourd'hui aucune dépendance base de données.
- **Le bac à sable** n'est pas encore construit côté IA (il ne figure pas au CDCF v1.1,
  il vient de la présentation « ARES C'est QUI ? »).
- **La Formation d'ARES** (RAG sur les documents client) n'est pas branchée : `/generate`
  fonctionne, mais sans base de connaissance injectée.
- **Aucun temps réel côté IA** : requête/réponse uniquement, pas de WebSocket ni de
  streaming. Pour du direct, la solution viendra de Supabase Realtime ou d'un webhook n8n.

---

## 9. Mode lecture directe — le service IA lit Supabase

> **Décision d'équipe** : pour répondre à « ce client demande les leads qui lui correspondent »,
> ce n'est pas le backend qui envoie toutes les données — c'est le service IA qui lit la base
> et renvoie au backend ce que l'utilisateur a demandé.
> **État : à construire.** Cette section décrit la cible, pas l'existant.

### 9.1 L'endpoint

```http
POST /api/v1/ares/leads/qualifies
X-Internal-Key: <secret>

{ "workspace_id": "<uuid du client>", "limit": 50, "min_score": 70 }
```

```json
{
  "leads": [
    { "id": "…", "nom": "Studio Créa", "secteur": "marketing",
      "score": 88, "palier": "correcte",
      "qualification_status": "qualifie", "motif": "…" }
  ],
  "total": 87,
  "meta": { "leads_analyses": 12, "leads_en_cache": 75, "cost_estimate": 0.03 }
}
```

Le backend n'envoie **plus** les leads : il envoie un `workspace_id` et des filtres.
Le service IA lit `leads` et `workspace_icp_config`, qualifie ce qui doit l'être, et renvoie
la liste triée par score décroissant.

### 9.2 Isolation multi-tenant — le point critique

Dès lors que le service IA ouvre sa propre connexion, **il devient responsable de l'isolation**.
C'est le risque n°1 du projet : une erreur ici et un client voit les prospects d'un autre.

Trois règles :

1. Le `workspace_id` vient **du backend, dans le corps de la requête** — jamais d'un paramètre
   que l'utilisateur final pourrait manipuler. Le backend le tire du **JWT**.
2. Le service IA pose `SET LOCAL app.workspace_id` sur chaque transaction, avec un rôle
   applicatif **non-superuser** et les policies RLS actives.
3. **Pas de clé `service_role` Supabase** : elle contourne le RLS et ramène l'isolation à
   du filtrage manuel, contournable par une requête oubliée.

### 9.3 Comment la liste reste rapide

À chaque appel, le service ne qualifie que ce qui ne l'est pas déjà :

```
SELECT … WHERE workspace_id = <client>
   ├─ lead déjà qualifié en base       → renvoyé tel quel   (0 appel LLM)
   ├─ secteur dans secteurs_exclus     → rejeté par règle   (0 appel LLM)
   └─ le reste                         → Claude Sonnet, puis ÉCRITURE du verdict
```

Sans cette écriture, chaque rafraîchissement d'écran relance Claude sur les mêmes leads :
facture multipliée et liste qui change d'une fois sur l'autre. Avec, le premier appel est
lent puis tout devient instantané — ce qui permet de tenir la contrainte des 2 secondes.

> **Conséquence à acter :** en mode lecture directe, **le service IA écrit en base**
> (colonnes de qualification uniquement). C'est un changement par rapport au mode payload,
> où seul le backend écrit. À confirmer avec le Fullstack pour éviter que les deux
> écrivent les mêmes colonnes.

### 9.4 Ce qu'il faut fournir au DEV IA pour construire ce mode

- [ ] **Mode d'accès** : connexion Postgres directe (recommandé) ou API Supabase
- [ ] **Chaîne de connexion** ou URL + clé, à placer en variable d'environnement
- [ ] **Schéma réel** : noms exacts des tables et colonnes créées par Big Data
- [ ] **Un échantillon** : `SELECT DISTINCT secteur FROM leads LIMIT 20` — pour vérifier
      que les valeurs sont normalisées et non du texte libre (voir §6.1)
- [ ] **Confirmation** que le service IA a le droit d'écrire les colonnes de qualification
