# Service IA — Structure & Autonomie

> À partager avec l'équipe. Montre l'organisation du service IA et **pourquoi il est
> indépendant** : le seul lien avec le reste du projet est un **contrat d'API**, pas du code.

---

## 1. Le principe : découplé par un contrat, pas par du code

```
   AUTRES SERVICES (peu importe leur techno)              MON SERVICE IA (DEV IA)
   ─────────────────────────────────────                 ───────────────────────

   ┌───────────────┐                                     ┌──────────────────────────┐
   │   BACKEND      │            HTTP + JSON              │      SERVICE IA           │
   │  (fullstack)   │   POST /api/v1/ares/qualify         │  ┌────────────────────┐  │
   │                │ ──────────────────────────────────► │  │  organisation       │  │
   │                │   Header  X-Internal-Key: <secret>  │  │  INTERNE            │  │
   │                │ ◄────────────────────────────────── │  │  = INVISIBLE        │  │
   │                │   { qualifie, confiance, motif }     │  │  et LIBRE           │  │
   └───────────────┘                                     │  └────────────────────┘  │
          │                                              └──────────────────────────┘
   ┌───────────────┐                                                  ▲
   │     n8n        │ ─────────────────────────────────────────────────┤
   └───────────────┘            (appellent le même contrat)            │
   ┌───────────────┐                                                  │
   │   Big Data     │ ─────────────────────────────────────────────────┘
   └───────────────┘

   ┌──────────────────────────────────────────────────────────────────────────┐
   │  LE SEUL LIEN = LE CONTRAT (endpoints + schémas JSON + header d'auth).     │
   │  Aucune dépendance de code. Aucune structure interne imposée de l'extérieur.│
   └──────────────────────────────────────────────────────────────────────────┘
```

**Autrement dit :** les autres services ne voient de moi **que mes endpoints HTTP**.
Ce qu'il y a *à l'intérieur* (mes dossiers, mon code) ne les concerne pas et ne les
impacte pas.

---

## 2. Le sens de la dépendance (à sens unique)

```
   BACKEND  ───dépend de───►  CONTRAT (API)  ◄───implémenté par───  SERVICE IA

   • Le backend dépend de mon CONTRAT (stable, versionné) — pas de mon CODE.
   • Moi, je ne dépends de RIEN chez le backend : service STATELESS,
     il reçoit tout dans la requête et ne touche aucune base de données.
```

→ **Je peux développer, tester et livrer sans attendre personne.** Le backend peut
changer toute son archi (Python, Node, Supabase…) : tant que le contrat tient, rien
ne casse chez moi.

---

## 3. Ma structure interne (mon domaine)

```
Virelyon_IA/
└─ app/
   ├─ api/v1/        ← LA SURFACE PUBLIQUE (le contrat) : la seule chose visible de l'extérieur
   │   └─ endpoints : /ares/{qualify, score, generate, classify}, /costs, /health
   │
   ├─ core/          ← config + sécurité (authentification service-à-service)
   ├─ gateway/       ← accès Claude (routage Haiku/Sonnet, suivi des coûts)
   ├─ ares/          ← logique des agents (scoring pur + décisions via LLM)
   ├─ prompts/       ← prompts système (garde-fous)
   └─ schemas/       ← contrats Pydantic (validation entrée/sortie)
```

```
   ┌──────────────── frontière du service ────────────────┐
   │                                                        │
   │   [ api/v1 ]  ← visible de tous (HTTP)                 │  ← seule partie "publique"
   │       │                                                │
   │       ▼                                                │
   │   [ ares ] → [ gateway ] → Claude                      │  ← MON organisation,
   │       ▲                                                │     libre et privée
   │   [ core · schemas · prompts ]                         │
   │                                                        │
   └────────────────────────────────────────────────────────┘
```

**Règle :** tout ce qui est sous `app/` (hors la surface `api/v1`) est **mon domaine**,
libre de structure. Les autres n'ont besoin que de `api/v1` — via HTTP.

---

## 4. Ce qu'on partage vs ce qui reste à moi

| Sujet | Qui décide |
|---|---|
| **Contrat d'API** (endpoints, schémas JSON) | 🤝 **ensemble** (point de coordination) |
| **Intégration** (URL, header `X-Internal-Key`, réseau) | 🤝 **ensemble** |
| **Déploiement** (Docker, comment le service tourne à côté) | 🤝 **ensemble** |
| **Structure interne du service** (dossiers, code, patterns) | 👤 **moi (DEV IA)** |
| **Choix des modèles, prompts, logique agent** | 👤 **moi (DEV IA)** |

---

## 5. En une phrase

> **Mon service IA est un composant autonome, relié au reste du projet par un seul
> contrat HTTP.** On s'aligne sur le contrat, l'authentification et le déploiement —
> et chaque service reste maître de son organisation interne. C'est ce qui nous permet
> d'avancer **en parallèle, sans nous bloquer**.

*(Principe d'ingénierie standard : service ownership / bounded context.)*
