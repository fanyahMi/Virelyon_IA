# ARES — Documentation détaillée (Agent de prospection)

> Documentation complète de l'agent **ARES** de VIRELYON : rôle, architecture,
> fonctionnement des 11 modules, modèle de données, prompts, garde-fous, flow,
> et comment le **service IA** de ce dépôt l'implémente.
> Source : CDCF ARES v1.1. Voir aussi `../DOCUMENTATION.md` (le service) et `../samples/` (données de test).

---

## 1. Qu'est-ce qu'ARES ?

**ARES** est l'agent **agentique de prospection** de VIRELYON (SaaS d'agents IA pour agences de services B2B).

**Sa promesse :** identifier des entreprises correspondant au profil défini par le client, les **qualifier**, engager la conversation **sur le bon canal au bon moment**, et transmettre à l'équipe commerciale les prospects réellement intéressés — **sans intervention manuelle constante**.

### Ce qui le rend « agentique » (≠ simple automatisation)
La différence avec un outil d'envoi automatique = la **prise de décision contextuelle** : ARES décide *s'il faut relancer ou non*, *sur quel canal*, *avec quel ton*, et *s'il faut escalader vers un humain* — au lieu de suivre un script figé. C'est ce qui justifie l'appel à **Claude** aux points clés plutôt qu'une simple règle `if/then`.

### Ce qu'ARES n'est PAS
- ❌ Un remplaçant du commercial (positionnement validé : **« augmenter », jamais « remplacer »**).
- ❌ Un envoyeur de masse non ciblé.
- ❌ Un outil qui agit sans traçabilité (chaque décision est journalisée).

---

## 2. Position dans l'écosystème VIRELYON

```
Big Data  ──►  ARES  ──►  APEX  (support, une fois le client signé)
(données       (qualifie,     └─►  AURA  (agrège les événements → rapports)
 nettoyées)     engage,
                score)
```

- **Big Data** alimente ARES en données nettoyées (`leads_raw`).
- **ARES** qualifie, engage, score, et **produit des événements** (`lead_events`).
- **AURA** consomme ces événements pour les rapports. **ARES ne calcule jamais d'agrégat** lui-même.

---

## 3. Architecture & principe de fonctionnement

### La cascade « du pas cher au cher »
ARES minimise le coût en n'appelant le LLM que lorsque c'est nécessaire :

```
Lead brut
  │
  ▼ ① Filtre/Qualification ICP     (règles + Claude sur l'ambigu)
  ▼ ② Scoring composite            (logique PURE, 0 LLM)
  ▼ ③ Séquençage + Génération      (n8n + Claude)
  ▼ ④ Classification des réponses  (Claude Haiku)
  ▼ ⑤ Escalade / archivage / opt-out
      → à chaque étape : un lead_event (traçabilité → AURA)
```

### Stack (CDCF)
- **Orchestration :** n8n (chaque module = workflow indépendant).
- **Raisonnement :** Claude API — Haiku 4.5 (volume) / Sonnet 4.6 (raisonnement).
- **Mémoire :** Postgres + pgvector.
- **Données brutes :** pipeline Big Data → `leads_raw`.

### Séparation des rôles
- **Big Data** = qualité de la donnée en amont.
- **DEV IA** = logique de décision (ce dépôt).
- **DEV Fullstack** = exposition à l'utilisateur + persistance.

---

## 4. Les 11 modules fonctionnels

### 4.1 — Ingestion & Sourcing *(Big Data / n8n)*
Alimente ARES en prospects bruts, **sans jugement de qualité** (le jugement = module 4.2).
Sources : API B2B, import CSV, webhook formulaire. Déduplication (email/domaine/nom) avant écriture dans `leads_raw`.

### 4.2 — Qualification ICP *(DEV IA — Claude)*
Détermine si un lead correspond au profil client, **en lecture seule** sur l'ICP (`workspace_icp_config`, source unique). ARES **ne stocke jamais son propre filtre ICP** (P0-01).
- Claude évalue le lead contre les critères → statut structuré.
- Statuts : `qualifie` / `rejete` / `a_valider` (confiance insuffisante → revue humaine, jamais de rejet silencieux).
- Un lead rejeté est **archivé** (jamais supprimé).

### 4.3 — Scoring & Priorisation *(DEV IA — logique pure)*
Ordonne les leads qualifiés. Score composite **0-100** :
- **fraîcheur** du signal, **complétude** des données, **force de correspondance ICP** (fit), **engagement**.
- Pondérations **configurables par workspace** (jamais figées dans le code).

### 4.3.1 — Paliers de relance *(nouveau v1.1)*
Le score pilote **le nombre et la cadence des relances** — c'est ce qui différencie ARES d'un envoyeur de masse :

| Palier de score | Relances max | Cadence |
|---|---|---|
| ≥ 95 % | 5 | J0 → J+3 → J+7 → J+12 → J+18 → J+25 |
| 90–94 % | 4 | J0 → J+3 → J+8 → J+15 → J+22 |
| 70–89 % | 3 | J0 → J+4 → J+10 → J+18 |
| < 70 % | 1 | J0 → J+7, puis archivage |

Avant chaque relance : on lit `score` + `relances_effectuees`, on compare au plafond du palier ; on ne relance que si le plafond n'est pas atteint.

### 4.4 — Séquençage multicanal *(n8n + DEV IA)*
Exécute la cadence multi-étapes/multi-canaux. Vérifie les quotas et fenêtres horaires avant envoi ; vérifie le palier avant chaque relance. **Réponse détectée → interruption immédiate** de la séquence (priorité absolue).

### 4.5 — Génération de messages *(DEV IA — Claude)*
Produit un message pertinent et **non générique** par lead (profil + étape + historique + ton de voix).
- **Garde-fou système :** jamais suggérer un remplacement humain.
- Niveau d'autonomie : `supervision` (validation humaine) ou `autonome`.

### 4.6 — Classification des réponses *(DEV IA — Claude Haiku)*
Comprend la réponse du prospect → **5 catégories fermées** :
`Intéressé` / `À recontacter plus tard` / `Pas intéressé` / `Demande de retrait` / `Question hors-scope` (+ extraction d'une date de relance).
Confiance faible → **file manuelle** (jamais d'action auto irréversible).

### 4.7 — Escalade / Handoff commercial *(n8n + backend)*
Lead « Intéressé » → notifie l'équipe (in-app + email) + sync CRM. L'historique complet est joint (pas de reprise à froid).

### 4.8 — Conformité & Anti-abus *(transverse)*
RGPD / opt-out : moyen de retrait dans chaque message ; rate limiting par canal + workspace. **`suppression_list` bloque AVANT la génération** (sécurité par construction).

### 4.9 — Mémoire & Continuité *(pgvector)*
Chaque interaction est indexée par embedding → ARES retrouve le contexte même après des semaines d'inactivité (évite tout « reset » perçu comme non professionnel).

### 4.10 — Multilinguisme *(transverse)*
Langue par défaut = celle du workspace ; possibilité de forcer selon la langue détectée du prospect. **Aucun texte en dur** ; jamais de mélange de langues dans un message.

### 4.11 — Observabilité *(transverse)*
Chaque décision (qualif, scoring, envoi, classif, escalade) → un **événement horodaté et justifié** dans `lead_events`. ARES **ne calcule pas d'agrégat** (c'est AURA).

---

## 5. Modèle de données (tables ARES)

| Table | Rôle |
|---|---|
| `workspace_icp_config` | ICP (source unique) — **lecture seule** pour ARES |
| `leads_raw` | prospects bruts (alimentés par Big Data) |
| `leads` | pipeline actif : `qualification_status`, `score`, `score_breakdown`, `relances_effectuees`, `statut_pipeline`, `canal_prefere` |
| `sequences` / `sequence_steps` | cadences (étape, canal, délai, condition d'arrêt) |
| `messages` | messages générés (contenu, statut d'envoi, version de prompt) |
| `suppression_list` | opt-out / RGPD (portée workspace ou globale) |
| `agent_config` | réglages : `autonomy_level`, `quotas_par_canal`, `paliers_relance_score` — **jamais de filtre ICP** |
| `embeddings` | mémoire vectorielle (pgvector) |
| `lead_events` | journal d'observabilité → AURA |

Statuts pipeline : `Identifié → Contacté → Répondu → Qualifié → Transmis au commercial`.

---

## 6. Les 4 points d'appel à Claude (prompts §5)

| Prompt | Module | Entrée | Sortie (JSON structuré) | Tier |
|---|---|---|---|---|
| **Qualification** (§5.1) | 4.2 | ICP + profil lead | `{qualifie, confiance, motif}` | reasoning (Sonnet) |
| **Génération** (§5.2) | 4.5 | profil + étape + ton + historique | `{texte, canal}` + garde-fou | reasoning (Sonnet) |
| **Classification** (§5.3) | 4.6 | message entrant | `{categorie(5), confiance, date_relance?}` | fast (Haiku) |
| **Décision** (§5.4) | 4.4/4.6/4.7 | lead + palier + relances_effectuees | `{action(continuer/pause/escalade/arrêt), justification}` | reasoning |

**Toutes les sorties sont en JSON structuré** — jamais de texte libre.

---

## 7. Garde-fous NON-négociables (critères de recette — §0)

1. 🚫 Jamais suggérer de **remplacer** un humain (« augmenter », pas « remplacer »).
2. 🚫 ARES ne stocke **aucun filtre ICP** (source unique `workspace_icp_config`).
3. 🚫 Aucune **barrière d'effectif** codée en dur (pas de « 5-30 »).
4. 🚫 SMS Orange **jamais bloquant** pour l'activation.
5. ✅ Sorties Claude **toujours structurées** (JSON).
6. ✅ `suppression_list` bloque **avant** la génération.
7. ✅ Confiance faible → **file manuelle**, jamais d'action auto irréversible.
8. ✅ Toute décision → **événement** dans `lead_events`.
9. ✅ Réponse détectée → **interruption immédiate** de la séquence.
10. ✅ Multilingue sans reprise de code.

---

## 8. Comment le service IA (ce dépôt) implémente ARES

Le service IA couvre la partie **DEV IA** d'ARES (décisions + logique), en **stateless** : il reçoit les données dans la requête, décide, renvoie du JSON. Il ne touche pas la base ; c'est le backend/n8n qui orchestre et persiste.

| Module ARES | Endpoint du service | Type |
|---|---|---|
| 4.2 Qualification | `POST /api/v1/ares/qualify` | Claude (Sonnet) |
| 4.3 / 4.3.1 Scoring + paliers | `POST /api/v1/ares/score` | **logique pure** |
| 4.5 Génération | `POST /api/v1/ares/generate` | Claude (Sonnet) |
| 4.6 Classification | `POST /api/v1/ares/classify` | Claude (Haiku) |
| 4.4/4.6/4.7 Décision | `POST /api/v1/ares/decide` | garde-fou déterministe + Claude |
| — Coûts (marge §5.4) | `GET /api/v1/costs/{workspace_id}` | — |

**Optimisations coût intégrées :** cache des réponses (`meta.cached`), plafond de coût par workspace (HTTP 429), suivi des coûts. **Sans clé Claude**, `score` et `decide` (cas plafond) fonctionnent déjà.

Ce qui **n'est pas** dans le service : ingestion/enrichissement (Big Data), séquençage/envois/`suppression_list` (n8n + backend), persistance + RLS (backend).

---

## 9. Cycle de vie complet d'un lead (§7.A)

```
Sourcing/Import (4.1) → leads_raw
   → Qualification ICP (4.2)
   → Scoring + palier (4.3 / 4.3.1)
   → Séquençage multicanal (4.4) ⇄ Génération (4.5)
   → Réponse du prospect → Classification (4.6)
   → selon le cas : Escalade (4.7) | archivage | suppression_list (4.8)
   → à chaque étape : lead_event (4.11) → agrégé par AURA
```

---

## 10. Intégrations (toutes NON bloquantes pour l'activation)

| Intégration | Rôle | Bloquant ? |
|---|---|---|
| Source B2B (sourcing) | leads bruts | Non (CSV suffit) |
| Email (SMTP/API) | canal principal | Recommandé |
| SMS Orange Developer | canal différenciant | **Non** (garde-fou §0) |
| LinkedIn | sourcing + engagement | Non |
| CRM (HubSpot/Salesforce) | handoff | Non |
| Enrichissement B2B | améliore le scoring | Non |

---

## 11. Exigences non-fonctionnelles (§8)

- **Performance :** qualif/scoring **asynchrones** — le dashboard reste < 2 s même sur import massif.
- **Sécurité :** isolation stricte par workspace (RLS) ; secrets de canal jamais côté client ; `suppression_list` invulnérable.
- **Scalabilité :** file d'attente pour absorber les pics d'ingestion.
- **Multilinguisme :** aucune reprise de code pour ajouter une langue.
- **Rate limiting :** quotas par canal/workspace + paliers de relance par score.

---

## 12. Références
- CDCF ARES v1.1 (`../../Virelyon_Front_et_Back/CDCF_ARES_...`).
- `../DOCUMENTATION.md` — le service IA en détail.
- `../samples/README.md` — jeux de données de test.
- `../../Virelyon_Front_et_Back/ARES_PLAN.md` — plan de réalisation complet.
