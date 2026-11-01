# Analyse des flux, fonctionnalités et mécaniques — Puryfier

> Version analysée : `0.3.0`
> Date : 31 octobre 2026
> Périmètre : backend FastAPI/Beanie, frontend React/Vite, workers, WebSockets, SDK PuryFi, tests.
> Méthode : lecture du code, des tests et de la documentation du SDK PuryFi.

**Vérifications effectuées**

| Suite | Résultat |
| --- | --- |
| Backend `pytest` | **204 tests passent** |
| Frontend `vitest` | **68 tests passent** (16 fichiers) |
| Build / lint | non relancés dans cette analyse |

---

## Sommaire

1. [Résumé exécutif](#1-résumé-exécutif)
2. [Cartographie du système](#2-cartographie-du-système)
3. [Acteurs, surfaces et authentification](#3-acteurs-surfaces-et-authentification)
4. [Données et états](#4-données-et-états)
5. [Flux détaillés](#5-flux-détaillés)
6. [Inventaire des fonctionnalités](#6-inventaire-des-fonctionnalités)
7. [Catalogue des mécaniques](#7-catalogue-des-mécaniques)
8. [Où changer quoi](#8-où-changer-quoi)
9. [Invariants à préserver](#9-invariants-à-préserver)
10. [Constats, limites et dettes](#10-constats-limites-et-dettes)
11. [Décisions à prendre](#11-décisions-à-prendre)

---

## 1. Résumé exécutif

Puryfier est un **pont événementiel entre Chaster et PuryFi**. Il ne remplace ni Chaster ni PuryFi : il observe les événements du lock Chaster, pousse des commandes d'état vers le plugin PuryFi, et transforme les scans de médias PuryFi en temps ajouté au lock Chaster.

Quatre boucles structurent l'application :

| Boucle | Déclencheur | Effet |
| --- | --- | --- |
| **Liaison** | Le wearer ouvre la page session et génère un lien | Un `link_token` permet au plugin PuryFi de se connecter en WebSocket |
| **Synchronisation lock** | Webhooks Chaster `lock_frozen` / `lock_unfrozen` | Verrouillage/déverrouillage de PuryFi, avec mot de passe d'urgence |
| **Pénalité médias** | Événements `staticMediaScan` de PuryFi | Ajout de temps au lock Chaster par paliers |
| **Statut temps réel** | Connexion/déconnexion et changements d'état PuryFi | Mise à jour de l'iframe Chaster sans refresh |

Les mécaniques réellement modifiables sont concentrées dans **quatre endroits** :

| Fichier | Ce qu'il contient |
| --- | --- |
| `server/src/domain/entities.py` | Schéma de configuration : `lock_on_freeze`, `unlock_on_unfreeze`, `censorPicsConfig` |
| `server/src/domain/use_cases/lock_events.py` | Règles freeze/unfreeze et séquence des commandes PuryFi |
| `server/src/domain/use_cases/media_scan.py` | Filtre des labels, seuil, calcul de la durée, application de la pénalité |
| `server/src/workers/media_scans.py` | Fenêtre de regroupement des scans, concurrence, retries |

Les autres couches (transport WebSocket, queue durable, inbox webhook, registry, watchers) sont surtout de **l'infrastructure** : on peut changer les règles métier sans les réécrire, à condition de respecter les invariants de la section 9.

**Points marquants pour un changement de mécanique**

- Le modèle de pénalité actuel est **binaire et global** : un scan contenant au moins un label censorable compte pour 1, quel que soit le label, le score ou le nombre d'objets. Aucun poids, cooldown ou plafond journalier.
- `readUserState` est une permission **obligatoire** : si elle n'est pas accordée, les commandes freeze/unfreeze restent en file, même si le profil PuryFi n'a aucune importance pour le joueur.
- Le lock PuryFi est configuré avec `timer: null` et `timerPlus: null` : un freeze Puryfier **efface donc tout timer PuryFi existant**.
- La suppression d'une session Chaster ferme la connexion et purge les données **sans déverrouiller PuryFi** au préalable.
- Le token de liaison est **permanent** : pas de rotation, pas de révocation, pas d'expiration.
- L'état `gelé/dégelé` de Chaster n'est **pas persisté** côté serveur : il est seulement déduit de l'événement webhook au moment où il arrive. Cela limite les mécaniques de type « Guard » ou « réconciliation ».
- La configuration locale n'est **pas réécrite** depuis Chaster à chaque lecture : après la création, la copie locale fait foi. Le handler `extension_updated` est un no-op, donc une modification faite ailleurs ne se propage pas.
- L'application est **mono-processus par conception** : registry de connexions, watchers et batch de scans vivent en mémoire. Le multi-instance nécessiterait Redis ou équivalent.

---

## 2. Cartographie du système

### 2.1 Vue d'ensemble

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Chaster (hôte de l'iframe)                                           │
│  - page extension principale : /extension/main                       │
│  - page configuration : /extension/configuration                     │
│  - hash JSON : mainToken / partnerConfigurationToken                 │
│  - postMessage : capabilities, partner_configuration_save            │
└───────────────┬──────────────────────────────────────────────────────┘
                │ iframe + hash + postMessage
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Frontend React + Vite                                                │
│  - Session.tsx : liaison, profil, état, mot de passe keyholder       │
│  - Configuration.tsx : options + sauvegarde vers Chaster             │
│  - usePuryfiRealtimeStatus : WebSocket de statut                     │
└───────────────┬──────────────────────────────────────────────────────┘
                │ HTTP /api/...          WS /ws/session|configuration/...
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Backend FastAPI                                                      │
│                                                                      │
│  api/session.py ──────► use_cases/session.py                         │
│  api/configuration.py ─► use_cases/configuration.py                  │
│  api/webhooks.py ─────► webhook_inbox (Mongo) ─► workers/handlers.py │
│  api/realtime.py ─────► realtime/registry.py + realtime/watchers.py  │
│                                                                      │
│  domain/use_cases/lock_events.py     (freeze/unfreeze)               │
│  domain/use_cases/media_scan.py      (pénalités)                     │
│  workers/media_scans.py              (batching 15 s)                 │
│  workers/outbound.py                 (drain de la queue)             │
│  realtime/connection.py              (acteur par connexion PuryFi)   │
└──────┬───────────────────────┬───────────────────────┬───────────────┘
       │ Beanie/MongoDB        │ HTTP Chaster API      │ WS msgpack
       ▼                       ▼                       ▼
┌──────────────┐      ┌────────────────────┐   ┌──────────────────────┐
│ MongoDB      │      │ api.chaster.app    │   │ Plugin PuryFi        │
│ - sessions   │      │ - auth session     │   │ - ready              │
│ - queue      │      │ - configuration    │   │ - intents            │
│ - inbox      │      │ - add_time         │   │ - setState/getState  │
└──────────────┘      │ - logs             │   │ - staticMediaScan    │
                      └────────────────────┘   └──────────────────────┘
```

### 2.2 Endpoints exposés

| Endpoint | Type | Authentification | Rôle |
| --- | --- | --- | --- |
| `GET /api/session/{main_token}` | HTTP | Token Chaster validé par l'API Chaster | Ouvrir une session, créer la config locale, retourner le DTO selon le rôle |
| `POST /api/session/{main_token}/link-token` | HTTP | Token Chaster | Générer ou réutiliser le `link_token` PuryFi (wearer uniquement) |
| `GET /api/configuration/{configuration_token}` | HTTP | Token Chaster | Lire la configuration et l'état de liaison |
| `PUT /api/configuration/{configuration_token}` | HTTP | Token Chaster | Valider, sauvegarder dans Chaster puis en local |
| `POST /api/webhooks/extensions/chaster` | HTTP | Basic auth `CHASTER_WEBHOOK_USER` / `CHASTER_WEBHOOK_PWD` | Ingress webhook Chaster |
| `WS /ws/{user_link_token}` | WebSocket msgpack | `link_token` présent en base | Connexion du plugin PuryFi |
| `WS /ws/session/{main_token}` | WebSocket JSON | Token Chaster validé à la connexion | Statut temps réel pour la page session |
| `WS /ws/configuration/{configuration_token}` | WebSocket JSON | Token Chaster validé à la connexion | Statut temps réel pour la page configuration |
| `GET /health`, `GET /healthz` | HTTP | Aucune | Liveness |

### 2.3 Sens des dépendances

Le domaine est volontairement **sans FastAPI, Beanie, msgpack ni MongoDB** :

```text
api/ + realtime/ + workers/ + infra/
              │
              ▼
        domain/use_cases
              │
              ▼
        domain/ports (Protocols)
              ▲
              │ implémentations
        infra/ + realtime/
```

Conséquence pratique : changer une règle métier dans `domain/use_cases` ne doit pas nécessiter de toucher au transport. Les adaptateurs sont injectés par `server/src/container.py`.

---

## 3. Acteurs, surfaces et authentification

| Acteur | Surface | Preuve d'identité | Portée |
| --- | --- | --- | --- |
| Chaster (iframe) | Hash `mainToken` / `partnerConfigurationToken` | Token opaque fourni par Chaster | Session ou configuration |
| Chaster (webhooks) | HTTP Basic | Credentials configurés | Événements de toutes les sessions |
| Navigateur / wearer | HTTP + WS session | `mainToken` dans le hash puis dans l'URL | Session, lien PuryFi |
| Navigateur / keyholder | HTTP + WS session | `mainToken` dans le hash puis dans l'URL | Session, mot de passe d'urgence |
| Plugin PuryFi | WS msgpack `/ws/{link_token}` | `link_token` secret et permanent | Une session Chaster |
| Workers internes | MongoDB | Aucune (même processus) | Queue, inbox, compteurs |
| Chaster API | HTTPS Bearer | `CHASTER_DEVELOPER_TOKEN` | API développeur |

**Politique de rôle**

- `role == "keyholder"` : reçoit `lock_password` en clair, jamais le `link_token`.
- `role == "wearer"` : reçoit le `link_token`, jamais le `lock_password`.
- Tout autre rôle : ne reçoit ni l'un ni l'autre. La politique est « deny by default ».
- Seul le wearer peut créer un `link_token` (`PermissionDeniedError` sinon).

**Secrets**

- Le `link_token` est un `cuid2`, stocké en clair, unique via index partiel. Il apparaît dans l'URL WebSocket ; les logs utilisent `token_fingerprint`.
- Le `lock_password` est généré par `secrets.token_urlsafe(16)`, stocké en clair, jamais loggé, retourné uniquement au keyholder.
- `SECRET_KEY` existe dans les settings mais **n'est pas encore utilisé** pour chiffrer les secrets au repos.
- Les réponses `/api/session/*` et `/api/configuration/*` sont envoyées avec `Cache-Control: no-store`.

---

## 4. Données et états

### 4.1 Collections MongoDB

#### `users_lock_configurations` (`UserLockConfiguration`)

| Champ | Rôle |
| --- | --- |
| `session_id` | Identifiant de session Chaster, **unique** |
| `lock_id` | Identifiant du lock Chaster (non unique) |
| `link_token` | Token de liaison PuryFi, unique seulement s'il est une string non nulle |
| `has_linked_plugin` | Passe à `true` au premier drain réussi, reste `true` ensuite |
| `keyholder_id`, `wearer_id` | Identités Chaster |
| `puryfi_username`, `puryfi_support_tier` | Profil PuryFi persisté |
| `seen_censored_objects` | Compteur persistant de médias censurés non encore consommés par un palier |
| `lock_password` | Mot de passe d'urgence PuryFi, en clair |
| `config` | `ChasterExtensionConfigSchema` |

Index : `session_id` unique, `lock_id` simple, `link_token` unique partiel sur `{"$type": "string"}`.

#### `queued_messages` (`QueuedMessage`)

| Champ | Rôle |
| --- | --- |
| `link_token` | Destinataire |
| `msg_type` | `setState`, `enterLockPassword`, etc. |
| `payload` | Payload msgpack sérialisé en JSON Mongo |
| `created_at` | Ordre d'insertion + TTL 7 jours |

Limite applicative : **100 messages par token**. Au-delà, le plus ancien est supprimé pour faire de la place.

#### `webhook_inbox` (`WebhookInboxEntry`)

| Champ | Rôle |
| --- | --- |
| `event_key` | Clé d'idempotence métier, unique |
| `event` | `action_log.created`, `extension_session.deleted`, etc. |
| `payload` | Payload Chaster complet |
| `status` | `pending`, `processing`, `done`, `failed` |
| `attempts` | Nombre de tentatives |
| `available_at`, `locked_until` | Leasing et backoff |
| `last_error` | Erreur assainie |
| `created_at` | TTL 7 jours |

### 4.2 État en mémoire

| Objet | Contenu | Durée de vie |
| --- | --- | --- |
| `Connection` | Socket, session, config courante, intents, profil, `puryfi_enabled`, `puryfi_has_lock`, mailbox, pending RPC | Vie de la socket |
| `ConnectionManager` | `link_token -> Connection` | Processus |
| `SessionWatcherManager` | `session_id -> {WebSocket}` | Processus |
| `MediaScanBatcher` | `session_id -> batch` (compteur + deadline + flag flush) | Fenêtre de 15 s, flushée au shutdown |
| `WebhookInboxWorker` | Task, Event de réveil | Processus |

**Conséquence :** l'application doit tourner avec **un seul worker uvicorn**. Le `Dockerfile` ne passe pas `--workers`, donc c'est le cas par défaut. Un scale horizontal casserait le registry, les watchers et le batching.

### 4.3 États de la connexion PuryFi

```text
absent
  │ ouverture WS + token valide
  ▼
connecté, non ready
  │ ready accepté (API compatible)
  ▼
ready
  │ intents obligatoires accordés
  ▼
ready + intents
  │ premier drain (même vide)
  ▼
lié (has_linked_plugin = true)
```

| État | `is_online` HTTP/WS | `has_linked_plugin` | `ready` | `intents_granted` |
| --- | --- | --- | --- | --- |
| Jamais connecté | `false` | `false` | — | — |
| Connecté sans `ready` | `false` | `false` | `false` | `false` |
| `ready` mais intents pending | `true` | `false` | `true` | `false` |
| `ready` + intents, drain en cours | `true` | `false` | `true` | `true` |
| Lié et connecté | `true` | `true` | `true` | `true` |
| Déconnecté après liaison | `false` | `true` | — | — |

C'est cette distinction qui permet à l'UI d'afficher **« Not linked »** (jamais vu) vs **« Offline »** (déjà lié, socket absente).

### 4.4 États du lock Chaster vs état PuryFi attendu

| État Chaster | Configuration | État PuryFi attendu par Puryfier |
| --- | --- | --- |
| Gelé | `lock_on_freeze = false` | Aucune action |
| Gelé | `lock_on_freeze = true` | `lockConfiguration.password = secret` + `enabled = true` |
| Dégelé | `unlock_on_unfreeze = false` | Aucune action |
| Dégelé | `unlock_on_unfreeze = true` | `enterLockPassword(secret)` + `enabled = false` |

**Important :** l'application **ne vérifie pas** que PuryFi est réellement dans cet état. Elle envoie les commandes et considère l'action traitée si le drain réussit. Il n'y a pas de réconciliation active.

---

## 5. Flux détaillés

### 5.1 F1 — Ouverture de la page session

**Fichiers :** `front/src/pages/Session.tsx`, `front/src/lib/chaster.ts`, `server/src/api/session.py`, `server/src/domain/use_cases/session.py`.

```text
Chaster iframe
  │ hash = { mainToken }
  ▼
Session.tsx
  │ GET /api/session/{mainToken}
  ▼
api/session.py → open_session()
  │ 1. ChasterGateway.get_session_auth(mainToken)
  │ 2. ChasterExtensionConfigSchema(**auth.config)
  │ 3. sessions.get_or_create(session_id, config=..., lock_id, keyholder_id, wearer_id)
  │ 4. _session_response(session, role, puryfi)
  ▼
DTO ChasterExtensionSessionSchema
  - is_online calculé depuis le registry
  - link_token seulement pour le wearer
  - lock_password seulement pour le keyholder
  - config locale
```

**Mécaniques**

- `get_or_create` est un `find_one_and_update` avec `$setOnInsert` et `upsert=True` : atomique, pas de doublon en cas de concurrence.
- **La configuration Chaster n'est lue qu'à la création.** Si le document local existe déjà, son `config` n'est pas rafraîchi par un nouvel appel à `GET /api/session`.
- Le front ouvre le WebSocket de statut **après** le retour REST, pour éviter une course avec la création de la session.

**Erreurs**

| Cas | Réponse |
| --- | --- |
| Token Chaster invalide | Statut upstream (401/404, etc.) |
| Chaster indisponible | 502 |
| Config Chaster invalide | 502 `Invalid configuration from Chaster` |
| MongoDB indisponible | 500 |

---

### 5.2 F2 — Page de configuration et sauvegarde

**Fichiers :** `front/src/pages/Configuration.tsx`, `front/src/lib/http/configuration.ts`, `server/src/api/configuration.py`, `server/src/domain/use_cases/configuration.py`.

**Chargement**

```text
Configuration.tsx
  │ hash = { partnerConfigurationToken }
  │ GET /api/configuration/{token}
  ▼
get_configuration()
  │ ChasterGateway.get_configuration(token)
  │ si pas de sessionId → DTO { has_session: false, config }
  │ sinon get_or_create(session_id, config) puis DTO + statut
  ▼
GeneralConfigurationOptions + CensoredMediaOptions
```

**Sauvegarde**

```text
Chaster host
  │ postMessage "partner_configuration_save"
  ▼
Configuration.tsx (origine chaster.app uniquement)
  │ postToParent("save_loading")
  │ PUT /api/configuration/{token} avec le config courant
  ▼
update_configuration()
  │ 1. ChasterGateway.update_configuration(token, payload)
  │ 2. sessionId retourné par Chaster
  │ 3. sessions.update(session_id, config=payload)
  │ 4. puryfi.update_cached_config(link_token, payload)
  ▼
postToParent("save_success") ou "save_failed"
```

**Mécaniques**

- Pas d'auto-save : la sauvegarde est déclenchée par Chaster via `postMessage`.
- Le payload est validé par Pydantic avant l'appel Chaster (`Field(ge=1, le=...)`).
- Le payload validé est la source de vérité locale même si la réponse Chaster omet `config`.
- `update_cached_config` met à jour la config en mémoire de la connexion PuryFi via sa mailbox, sans renvoyer de commande au plugin.
- Le front écoute uniquement `event.origin === "https://chaster.app"`.
- `has_session = false` : la configuration peut être consultée/modifiée sans lock actif ; elle sera appliquée au prochain lock.
- Si le document local existe déjà, `get_or_create` ne met à jour que les champs absents (`$setOnInsert`) : le `config` retourné est la **copie locale**, pas la valeur relue depuis Chaster.
- **Limite :** `extension_updated` (webhook) est un no-op. Une configuration modifiée hors de cette page ne rafraîchit pas la copie locale.

---

### 5.3 F3 — Liaison PuryFi

**Fichiers :** `front/src/components/common/sessions/wearer/LinkPuryfiCard.tsx`, `LinkTokenModal.tsx`, `server/src/domain/use_cases/session.py`.

```text
Wearer clique "Generate WebSocket URL"
  │ readChasterIframeParams() → mainToken
  │ POST /api/session/{mainToken}/link-token
  ▼
create_link_token()
  │ auth.role doit être "wearer"
  │ si session.link_token absent → cuid() + update
  ▼
retourne { link_token }
  │
  ▼
getPuryfiWebSocketUrl(token) = ws(s)://<backend>/ws/<token>
  │ copié dans PuryFi → Extras → Plugins → WebSocket
  ▼
Plugin se connecte
```

**Mécaniques**

- Un seul token par session, réutilisé tant qu'il existe.
- Le token est **permanent** : aucun endpoint de rotation/révocation.
- Le keyholder ne voit jamais le token ; il voit seulement « waiting for the wearer ».
- Le token est un bearer secret : quiconque le possède peut se connecter au slot PuryFi de la session.
- La connexion est validée **avant** `accept()` : token inconnu → close `4004`.
- Une nouvelle connexion pour le même token remplace l'ancienne et la ferme avec le code `4001`.

---

### 5.4 F4 — Handshake du plugin PuryFi

**Fichiers :** `server/src/api/realtime.py`, `server/src/realtime/connection.py`, `server/src/realtime/protocol.py`, `server/src/workers/outbound.py`.

```text
WS /ws/{link_token}
  │ validation en base
  │ accept()
  │ Connection.start() → mailbox worker
  │ registry.add(connection, token)
  ▼
PuryFi → { type: "ready", version, apiVersion, instanceId }
  │ validation API [1.0.0, 2.0.0)
  │ réponse { type: "ok" } ou { type: "error", name: "incompatibleApiVersion" }
  │ si ok et premier ready :
  │   - publish_status()
  │   - spawn bootstrap
  ▼
bootstrap (timeout 60 s)
  │ 1. setPluginManifest
  │ 2. setPluginConfiguration
  │ 3. getPluginIntents
  │ 4. si intents obligatoires manquants : requestPluginIntents
  │ 5. si intents optionnels manquants : requestPluginIntents (non bloquant)
  │ 6. _complete_intents_setup() si intents accordés
  ▼
_complete_intents_setup()
  │ - refresh_snapshot() : getState user, enabled, lockConfiguration
  │ - subscribeToState user (+ enabled / lockConfiguration si accordés)
  │ - subscribeToStaticMediaScans
  │ - _on_intents_granted() → flush_queue()
  ▼
drain_queued_messages()
  │ link_puryfi() : marque has_linked_plugin
  │ fetch queue ordonnée
  │ send_message puis delete après succès
```

**Intents demandés**

| Intent | Statut | Usage |
| --- | --- | --- |
| `readUserState` | **obligatoire** | Lire `user.username` et `user.supportTier` |
| `writeLockConfigurationState` | **obligatoire** | `setState lockConfiguration`, `enterLockPassword` |
| `writeEnabledState` | **obligatoire** | `setState enabled` |
| `readMediaProcesses` | **obligatoire** | `subscribeToStaticMediaScans` |
| `readEnabledState` | optionnel | Afficher `puryfi_enabled` |
| `readLockConfigurationState` | optionnel | Afficher `puryfi_has_lock` |

**Mécaniques**

- Le `ready` doit être acquitté avant tout autre message.
- Un `ready` dupliqué ne relance pas le handshake (`_ready_handled`).
- Le handshake ne bloque **pas** sur les intents optionnels.
- Les intents obligatoires manquants ne ferment pas la connexion : les commandes restent en file jusqu'à `intentsGrant`.
- `intentsGrant` déclenche la fin du setup et le drain si les intents obligatoires sont désormais tous accordés.
- Le premier drain, même avec une queue vide, marque le plugin comme lié.
- Le profil et l'état sont rafraîchis par des tâches supervisées ; une erreur de profil ne casse pas le handshake.
- Une socket malformée ou une erreur de handler ferme la connexion avec `1011` et nettoie le registry.

**Point d'attention SDK**

La documentation PuryFi est contradictoire sur `enterLockPassword` : la section du message indique `writeLockConfigurationState`, le tableau des intents indique `writeWBlistConfigurationState`. Puryfier ne demande que `writeLockConfigurationState`. À vérifier avec le runtime cible avant de modifier cette partie.

---

### 5.5 F5 — Freeze Chaster → lock PuryFi

**Fichiers :** `server/src/api/webhooks.py`, `server/src/workers/webhook_inbox.py`, `server/src/workers/handlers.py`, `server/src/domain/use_cases/lock_events.py`.

```text
Chaster → POST /api/webhooks/extensions/chaster
  │ Basic auth
  │ validation event/requestId/actionLog.type
  │ build_event_key() = "action_log.created:{actionLog._id}"
  │ insert webhook_inbox (unique)
  └─ 202 immédiat

WebhookInboxWorker
  │ claim lease 300 s
  │ dispatch "lock_frozen"
  ▼
handle_lock_frozen()
  │ 1. extraire session_id
  │ 2. charger la session locale
  │ 3. vérifier config.lock_on_freeze
  │ 4. générer un mot de passe (secrets.token_urlsafe(16))
  │ 5. sessions.update(lock_password=...)
  │ 6. queue.enqueue(setState lockConfiguration)
  │ 7. queue.enqueue(setState enabled=true)
  │ 8. si connexion ready + intents → flush_queue()
  ▼
PuryFi
  │ setState { path: "lockConfiguration",
  │           value: { password: {secret}, timer: null, timerPlus: null } }
  │ setState { path: "enabled", value: true }
```

**Mécaniques**

- Le mot de passe est **régénéré à chaque freeze**.
- L'ordre est volontaire : `lockConfiguration` d'abord, `enabled` ensuite. Si le premier échoue, le second n'est pas envoyé.
- Le queue est durable : si PuryFi est offline, les commandes restent en base.
- `timer` et `timerPlus` sont explicitement remis à `null` : **tout timer PuryFi existant est effacé**.
- Le keyholder peut révéler/copier le mot de passe depuis la page session.
- Aucun log Chaster n'est créé pour le freeze/unfreeze.
- Si le webhook est rejoué avec un nouveau `requestId`, la clé métier `action_log._id` empêche une seconde génération de mot de passe.

**Échecs**

| Cas | Comportement |
| --- | --- |
| Session inconnue / pas de config / pas de token | `status: ok`, action ignorée |
| `lock_on_freeze = false` | `status: ok`, ignorée |
| PuryFi offline | Commandes en queue, action `lock_frozen_queued_no_connection` |
| PuryFi connecté mais pas ready/intents | Commandes en queue, action `lock_frozen_queued_not_ready` |
| Échec d'envoi | Le message reste en queue, l'action n'est pas `processed` |
| Handler lève une erreur | Retry inbox avec backoff |

---

### 5.6 F6 — Unfreeze Chaster → unlock PuryFi

```text
Webhook action_log.created / type = lock_unfrozen
  ▼
handle_lock_unfrozen()
  │ 1. charger la session
  │ 2. vérifier config.unlock_on_unfreeze
  │ 3. lire session.lock_password
  │ 4. si absent → { status: "error", error: "no_lock_password" }
  │ 5. queue.enqueue(enterLockPassword(secret))
  │ 6. queue.enqueue(setState enabled=false)
  │ 7. flush si ready + intents
  ▼
PuryFi
  │ enterLockPassword { secret }
  │ setState { path: "enabled", value: false }
```

**Mécaniques**

- Si le mot de passe est absent, le handler renvoie une **erreur** : l'inbox retente jusqu'à 5 fois puis marque l'entrée `failed`. Le dégel Chaster n'est donc pas silencieusement perdu côté inbox, mais PuryFi reste potentiellement verrouillé.
- Le mot de passe n'est **pas effacé** après un unfreeze réussi. Il reste disponible pour le keyholder et pour un éventuel nouveau dégel.
- `enterLockPassword` retire le lock PuryFi s'il correspond ; `enabled = false` désactive PuryFi.
- Si `enterLockPassword` échoue (mot de passe modifié manuellement, lock absent, etc.), `enabled = false` n'est pas envoyé : le drain s'arrête à la première erreur. C'est un point important pour une mécanique de réconciliation.

---

### 5.7 F7 — Scan de média → pénalité de temps

**Fichiers :** `server/src/realtime/connection.py`, `server/src/workers/media_scans.py`, `server/src/domain/use_cases/media_scan.py`, `server/src/infra/repositories.py`.

```text
PuryFi émet staticMediaScan { objects: [...] }
  │
  ▼
Connection.handle_message()
  │ pas d'I/O : media_scans.record_nowait(session, objects)
  ▼
MediaScanBatcher.record_nowait()
  │ 1. ignorer si feature désactivée
  │ 2. is_censorable(objects) ?
  │ 3. ouvrir un batch si absent, deadline = now + 15 s
  │ 4. batch.count += 1
  ▼
à la deadline (poll 0.5 s)
  │ flush :
  │   record_batch(session, count)
  │     - increment_censored_count_by(count)
  │     - si total >= limit_count :
  │         claim_censored_penalties(limit, total // limit)
  │         → MediaScanPenalty(objects=claimed,
  │                              duration=added_duration * (claimed // limit))
  │   apply_penalty(penalty)
  │     - Chaster add_time(session_id, duration)
  │     - si échec : restore_censored_count(claimed)
  │     - si succès : create_log "USER added time!"
  ▼
Boucle suivante
```

**Filtre des labels**

`MediaScanService.CENSORABLE_LABELS` contient uniquement :

| Valeur | Label |
| --- | --- |
| 2 | `Buttocks` |
| 4 | `FemaleBreast` |
| 6 | `FemaleGenitals` |
| 9 | `MaleGenitals` |
| 19 | `Anus` |
| 23 | `Nipple` |

Les variantes `Covered` (3, 5, 7, 8, 18, 22), les visages, mains, pieds, yeux, bouche, ventre, bras, silhouette **ne comptent pas**. Le `score` de détection est ignoré. Un scan contenant plusieurs objets compte **une seule fois**.

**Calcul de la pénalité**

Avec `limit_count = 100` et `added_duration = 600` :

| Scans cumulés | Claim | Durée ajoutée | Reste |
| --- | --- | --- | --- |
| 99 | 0 | 0 | 99 |
| 100 | 100 | 600 s | 0 |
| 250 | 200 | 1 200 s | 50 |
| 50 puis 60 | 100 | 600 s | 10 |

Le nom `objects` dans `MediaScanPenalty` désigne en réalité un **nombre d'images**, pas d'objets détectés.

**Mécaniques**

- Fenêtre fixe de **15 s** : la première image ouvre la fenêtre, les suivantes s'y ajoutent, la deadline n'est jamais repoussée.
- Un batch en cours de flush peut recevoir de nouveaux scans ; ils forment la fenêtre suivante.
- `seen_censored_objects` est persistant : un redémarrage ne perd pas les paliers déjà comptés.
- Le compteur n'est incrémenté en base qu'à la fin de la fenêtre. Une chute du processus dans les 15 s peut perdre les scans en mémoire.
- Le claim est atomique (`find_one_and_update` avec `$gte`) : deux flush concurrents ne peuvent pas réclamer le même palier.
- En cas d'échec Chaster, le compteur est restauré et le batch est retenté après 15 s.
- Sémaphores : 16 flush simultanés, 4 pénalités simultanées.
- Aucun cooldown, aucun plafond journalier, aucun poids par label.
- Le compteur `seen_censored_objects` n'est pas exposé dans l'API ni dans l'UI.

---

### 5.8 F8 — Suppression d'une session Chaster

**Fichiers :** `server/src/workers/webhook_inbox.py`, `server/src/domain/use_cases/session_lifecycle.py`.

```text
Chaster → webhook extension_session.deleted
  │ event_key = "extension_session.deleted:{sessionId}" (ou + updatedAt)
  ▼
handle_extension_session_deleted()
  │ revoke_session()
  │  1. charger la session
  │  2. si link_token :
  │       close_by_user_link_token(code=4004)
  │       queue.delete_for_token()
  │  3. watchers.close_session(code=4004)
  │  4. sessions.delete(session_id)
  ▼
Config, queue, connexion et watchers sont purgés
```

**Mécaniques**

- La suppression rend le `link_token` inutilisable : la lookup échoue à la reconnexion.
- Les sockets navigateur sont fermées avec `4004`, ce que le front traite comme une erreur permanente (pas de reconnexion).
- **PuryFi n'est pas déverrouillé/désactivé avant la purge.** Si le lock Chaster se termine alors que PuryFi était verrouillé par Puryfier, le lock PuryFi peut rester en place. C'est un choix à expliciter avant de changer les mécaniques de fin de session.
- `extension_session.created` et `extension_session.updated` sont stockés dans l'inbox mais **ignorés** par le dispatcher.

---

### 5.9 F9 — Statut temps réel dans l'iframe

**Fichiers :** `server/src/api/realtime.py`, `server/src/realtime/registry.py`, `server/src/realtime/watchers.py`, `front/src/hooks/usePuryfiRealtimeStatus.ts`.

```text
Front
  │ WS /ws/session/{mainToken}
  │   ou /ws/configuration/{configurationToken}
  ▼
watch_session()
  │ 1. Chaster auth → session_id
  │ 2. charger la session locale
  │ 3. accept + watchers.add()
  │ 4. envoyer le statut courant
  │ 5. demander un refresh du snapshot PuryFi
  │ 6. boucle : receive_text avec timeout 30 s
  │      timeout → send_json({ type: "ping" })
  ▼
ConnectionManager.publish_status()
  │ à chaque ready, stateChange, profil, add/remove/close
  ▼
watchers.broadcast(session_id, status)
```

**Payload de statut**

```json
{
  "type": "status",
  "is_online": true,
  "has_linked_plugin": true,
  "puryfi_version": "0.8.8.0",
  "puryfi_username": "…",
  "puryfi_support_tier": { "level": 2, "name": "…" },
  "puryfi_enabled": true,
  "puryfi_has_lock": true
}
```

**Mécaniques**

- `is_online` n'est `true` qu'après un `ready` accepté.
- `puryfi_enabled` et `puryfi_has_lock` ne sont présents que si les intents optionnels sont accordés et la connexion vivante.
- Le front reçoit le premier statut immédiatement, puis les mises à jour.
- Reconnexion front avec backoff exponentiel 1 s → 15 s, arrêt définitif sur `4004`.
- Heartbeat applicatif toutes les 30 s ; un watcher mort est retiré.
- Les watchers sont authentifiés **à chaque connexion** par un appel Chaster, pas par un cache.
- Aucun compteur de médias, aucun historique et aucune alerte ne transitent par ce canal.

---

### 5.10 F10 — File d'attente offline et drain

**Fichiers :** `server/src/infra/queue.py`, `server/src/workers/outbound.py`, `server/src/domain/use_cases/lock_events.py`.

```text
Producteur (webhook, config)
  │ queue.enqueue(link_token, msg_type, payload)
  ▼
queued_messages (Mongo, ordre created_at)
  │
  │ Déclencheurs de drain :
  │ - bootstrap après ready + intents
  │ - intentsGrant tardif
  │ - flush demandé par un webhook
  ▼
drain_queued_messages()
  │ link_puryfi()
  │ fetch()
  │ pour chaque commande :
  │   send_message()
  │   si erreur → return False (message conservé)
  │   sinon delete(command)
  ▼
True si toute la queue est drainée
```

**Mécaniques**

- Suppression **après** succès uniquement : un crash ne perd pas la commande.
- Ordre sémantique : `lockConfiguration` avant `enabled`, `enterLockPassword` avant `enabled=false`.
- Erreur `missingPluginIntents` : la commande reste en queue et l'app re-demande les intents.
- Toute autre erreur : la commande reste en queue, pas de re-request.
- Cap 100 par token : au-delà, le plus ancien message est supprimé. En cas de très gros backlog, cela peut casser une séquence (par exemple perdre `lockConfiguration` et garder `enabled`).
- TTL 7 jours.
- `link_puryfi` est appelé à chaque drain : le passage à `has_linked_plugin = true` est conditionnel et atomique, donc pas de double log/transition.
- Les commandes ne sont jamais envoyées avant `ready` + intents obligatoires.

---

### 5.11 F11 — Erreurs, timeouts et retries

| Mécanisme | Valeur | Comportement |
| --- | --- | --- |
| RPC PuryFi | 15 s | Timeout, future nettoyée, l'appelant reçoit une erreur |
| Handshake global | 60 s | Fermeture `1011` si dépassé |
| Attente intents | 30 s | Le drain échoue, la queue reste |
| Chaster HTTP | 3 tentatives | 408/429/5xx et erreurs transport, backoff 0,5 s → 5 s + jitter |
| Webhook HTTP | 202 immédiat | Le traitement est asynchrone |
| Webhook inbox | 5 tentatives | Backoff 5 s → 300 s, lease 300 s, TTL 7 j |
| Queue | TTL 7 j | Cap 100, suppression du plus ancien |
| Media scan flush | Retry 15 s | Compteur restauré si `add_time` échoue |
| Watcher heartbeat | 30 s | Ping applicatif |
| Watcher send | 5 s | Socket retirée si l'envoi échoue |
| Front HTTP | 30 s | Timeout axios |
| Front WS | 1 s → 15 s | Reconnexion avec backoff, stop sur 4004 |

---

## 6. Inventaire des fonctionnalités

### 6.1 Cœur

| # | Fonctionnalité | Statut | Implémentation |
| --- | --- | --- | --- |
| 1 | Verrouiller PuryFi au freeze Chaster | ✅ | `handle_lock_frozen` |
| 2 | Déverrouiller/désactiver PuryFi au unfreeze | ✅ | `handle_lock_unfrozen` |
| 3 | Ajouter du temps quand un média est censuré | ✅ | `MediaScanService` + `MediaScanBatcher` |
| 4 | File durable si PuryFi est offline | ✅ | `queued_messages` + `drain_queued_messages` |
| 5 | Ordre garanti des commandes lock/unlock | ✅ | Queue ordonnée + mailbox par connexion |
| 6 | Idempotence des webhooks Chaster | ✅ | `event_key` métier + index unique |
| 7 | Traitement webhook asynchrone | ✅ | Inbox + worker avec leases |
| 8 | Retry des échecs Chaster | ✅ | `request_chaster`, backoff |
| 9 | Reconnexion du plugin après coupure | ✅ | Le plugin se reconnecte ; l'ancienne socket est remplacée |

### 6.2 Liaison et sécurité

| # | Fonctionnalité | Statut | Implémentation |
| --- | --- | --- | --- |
| 10 | Générer un lien WebSocket PuryFi | ✅ | `create_link_token` |
| 11 | Réutiliser le lien existant | ✅ | `session.link_token` |
| 12 | Réserver le lien au wearer | ✅ | Contrôle de rôle |
| 13 | Afficher le mot de passe d'urgence au keyholder | ✅ | `ShowPuryfiPassword` |
| 14 | Masquer les secrets selon le rôle | ✅ | `_session_response` |
| 15 | Authentification Basic du webhook | ✅ | `verify_credentials`, fail-closed |
| 16 | Rotation/révocation du lien PuryFi | ⛔ | Absent |
| 17 | Chiffrement des secrets au repos | ⛔ | `SECRET_KEY` réservé, non utilisé |
| 18 | Nettoyage à la fin de session | 🟡 | Purge DB/sockets, mais pas de déverrouillage PuryFi |
| 19 | Redaction des tokens dans les logs | ✅ | `token_fingerprint`, `redact_path` |
| 20 | `Cache-Control: no-store` | ✅ | Middleware FastAPI |
| 21 | CORS allowlist | ✅ | `front_url` uniquement |

### 6.3 Configuration et UI

| # | Fonctionnalité | Statut | Implémentation |
| --- | --- | --- | --- |
| 22 | Activer/désactiver lock on freeze | ✅ | `GeneralConfigurationOptions` |
| 23 | Activer/désactiver unlock on unfreeze | ✅ | `GeneralConfigurationOptions` |
| 24 | Activer la pénalité médias | ✅ | `CensoredMediaOptions` |
| 25 | Régler le seuil de médias | ✅ | `limit_count` |
| 26 | Régler la durée ajoutée | ✅ | `added_duration` |
| 27 | Sauvegarde vers Chaster via l'iframe | ✅ | `postMessage` + PUT |
| 28 | Configuration sans lock actif | ✅ | `has_session = false` |
| 29 | Affichage lecture seule dans la session | ✅ | `SessionSettings` + `readOnly` |
| 30 | Affichage du profil PuryFi | ✅ | `PuryfiProfile` |
| 31 | Affichage de l'état enabled/lock | ✅ | Statut temps réel |
| 32 | Choix des labels censorables | ⛔ | Liste codée en dur |
| 33 | Poids par label / score minimum | ⛔ | Absent |
| 34 | Cooldown / plafond journalier | ⛔ | Absent |
| 35 | Progression « X/Y médias » | ⛔ | Compteur non exposé |
| 36 | Journal d'activité / audit | ⛔ | Absent |

### 6.4 Temps réel

| # | Fonctionnalité | Statut | Implémentation |
| --- | --- | --- | --- |
| 37 | Statut online/offline sans refresh | ✅ | Watcher WS + registry |
| 38 | Statut « not linked » vs « offline » | ✅ | `has_linked_plugin` + `is_online` |
| 39 | Mise à jour après reconnexion du plugin | ✅ | `publish_status` |
| 40 | Profil PuryFi en direct | ✅ | `stateChange` sur `user` |
| 41 | État enabled/lock en direct | ✅ | `stateChange` sur `enabled` / `lockConfiguration` |
| 42 | Heartbeat des watchers | ✅ | Ping 30 s |
| 43 | Reconnexion front avec backoff | ✅ | `usePuryfiRealtimeStatus` |
| 44 | Notifications d'événements (scans, pénalités) | ⛔ | Absent |

### 6.5 Robustesse et exploitation

| # | Fonctionnalité | Statut | Implémentation |
| --- | --- | --- | --- |
| 45 | Supervision des tâches de connexion | ✅ | `Connection._spawn`, `stop()` |
| 46 | Fermeture de l'ancienne socket | ✅ | `ConnectionManager.add` |
| 47 | Un seul handshake par `ready` | ✅ | `_ready_handled` |
| 48 | Drain non concurrent | ✅ | `_drain_lock`, `_send_lock`, mailbox |
| 49 | Claim atomique des paliers | ✅ | `find_one_and_update` |
| 50 | Restauration du compteur si échec | ✅ | `restore_censored_count` |
| 51 | Batching des scans | ✅ | Fenêtre 15 s |
| 52 | Backpressure des flush | ✅ | Sémaphores 16/4 |
| 53 | Health endpoints | ✅ | `/health`, `/healthz` |
| 54 | Multi-instance | ⛔ | Registry/watchers/batcher en mémoire |
| 55 | Métriques / traces | ⛔ | Absent |

### 6.6 Partiels / TODO

| Élément | État | Détail |
| --- | --- | --- |
| `extension_updated` | ⛔ no-op | Handler présent, aucune logique |
| `extension_session.created` | ⛔ ignoré | Stocké dans l'inbox, aucun dispatch |
| `extension_session.updated` | ⛔ ignoré | Stocké dans l'inbox, aucun dispatch |
| Reconciliation d'état PuryFi | ⛔ | `stateChange` met à jour le cache, n'applique rien |
| Reset du compteur | ⛔ | `reset_censored_count` existe mais n'est appelé nulle part |
| Incrément unitaire | ⛔ | `increment_censored_count` existe mais le service utilise `_by` |
| Compteur visible | ⛔ | Non exposé dans les DTO |
| Rotation du token | ⛔ | Aucun endpoint |
| Déverrouillage temporaire | ⛔ | Aucun endpoint/worker |
| Récupération d'urgence | ⛔ | `enterLockEmergencyServerToken` non utilisé |
| Test d'image | ⛔ | `scanStaticMedia` / `censorStaticMedia` non utilisés |
| Whitelist/blacklist PuryFi | ⛔ | `wblistConfiguration` non utilisé |

---

## 7. Catalogue des mécaniques

### 7.1 Règles métier

| Mécanique | Règle actuelle | Réglable ? | Point d'ancrage |
| --- | --- | --- | --- |
| Déclencheur freeze | Webhook `lock_frozen` uniquement | Non | `handle_lock_frozen` |
| Condition freeze | `config.lock_on_freeze == true` | Oui, booléen | `ChasterExtensionConfigSchema` |
| Mot de passe | Généré à chaque freeze, 16 octets URL-safe | Non | `secrets.token_urlsafe(16)` |
| Lock PuryFi | `lockConfiguration` avec mot de passe, `timer=null`, `timerPlus=null` | Partiellement | `handle_lock_frozen` |
| Activation | `enabled=true` après le lock | Non | `handle_lock_frozen` |
| Déclencheur unfreeze | Webhook `lock_unfrozen` | Non | `handle_lock_unfrozen` |
| Condition unfreeze | `config.unlock_on_unfreeze == true` | Oui, booléen | `ChasterExtensionConfigSchema` |
| Déverrouillage | `enterLockPassword` avec le mot de passe stocké | Non | `handle_lock_unfrozen` |
| Désactivation | `enabled=false` après le déverrouillage | Non | `handle_lock_unfrozen` |
| Conservation du mot de passe | Jamais effacé après unfreeze | Non | `session.lock_password` |
| Filtre censorable | 6 labels, score ignoré | Non | `CENSORABLE_LABELS` |
| Unité de comptage | 1 scan = 1 image, quel que soit le nombre d'objets | Non | `is_censorable` |
| Seuil | `limit_count`, 100 par défaut | Oui, 1–10 000 | `CensorPicsConfigSchema` |
| Durée | `added_duration`, 600 s par défaut | Oui, 1–604 800 | `CensorPicsConfigSchema` |
| Paliers multiples | `total // limit` paliers, une seule requête `add_time` | Non | `record_batch` |
| Fenêtre de batch | 15 s fixe, non repoussée | Non (constructeur) | `DEFAULT_WINDOW_SECONDS` |
| Cooldown | Aucun | — | — |
| Plafond journalier | Aucun | — | — |
| Log Chaster de pénalité | `USER added time!` + durée | Non | `apply_penalty` |
| Log Chaster freeze/unfreeze | Aucun | — | — |
| Compteur persistant | `seen_censored_objects` | — | `UserLockConfiguration` |

### 7.2 Mécaniques de transport et de fiabilité

| Mécanique | Règle actuelle | Réglable ? | Point d'ancrage |
| --- | --- | --- | --- |
| API PuryFi supportée | `[1.0.0, 2.0.0)` | Non | `MIN_API_VERSION`, `MAX_API_VERSION` |
| Ready | Acquitté avant tout autre message | Non | `_accept_ready` |
| Handshake | Une seule fois par connexion | Non | `_ready_handled` |
| Intents obligatoires | 4, dont `readUserState` | Non | `protocol.intents` |
| Intents optionnels | 2, état enabled/lock | Non | `protocol.optional_intents` |
| Gate d'envoi | `ready && intents_granted` | Non | `can_send_protected` |
| Ordre des envois | Mailbox unique + `_send_lock` | Non | `Connection` |
| Remplacement de socket | Nouvelle connexion gagne, ancienne `4001` | Non | `ConnectionManager.add` |
| Suppression queue | Après succès uniquement | Non | `drain_queued_messages` |
| Cap queue | 100 par token, drop oldest | Non | `MAX_QUEUED_PER_TOKEN` |
| TTL queue | 7 jours | Non | `QUEUE_TTL_SECONDS` |
| TTL inbox | 7 jours | Non | `INBOX_TTL_SECONDS` |
| Retry webhook | 5 tentatives, backoff exponentiel | Non | `WebhookInboxWorker` |
| Lease webhook | 300 s | Non | `lease_seconds` |
| Retry Chaster | 3 tentatives | Non | `CHASTER_MAX_ATTEMPTS` |
| Timeout RPC | 15 s | Non | `RPC_TIMEOUT_SECONDS` |
| Timeout handshake | 60 s | Non | `HANDSHAKE_TIMEOUT_SECONDS` |
| Timeout intents | 30 s | Non | `INTENTS_TIMEOUT_SECONDS` |
| Timeout watcher send | 5 s | Non | `WATCHER_SEND_TIMEOUT_SECONDS` |
| Heartbeat watcher | 30 s | Non | `WATCHER_HEARTBEAT_SECONDS` |
| Idempotence webhook | `action_log._id` / session+updatedAt | Non | `build_event_key` |
| Rôle par défaut | Deny (ni mot de passe ni token) | Non | `_session_response` |
| Cache-Control | no-store sur session/config | Non | `main.py` |

### 7.3 Valeurs codées en dur à connaître avant de changer une mécanique

| Valeur | Emplacement | Effet |
| --- | --- | --- |
| 15 s | `workers/media_scans.py` | Fenêtre de regroupement |
| 0,5 s | `workers/media_scans.py` | Poll du scheduler |
| 15 s | `workers/media_scans.py` | Retry après échec de pénalité |
| 16 / 4 | `workers/media_scans.py` | Concurrence flush / pénalités |
| 100 | `infra/queue.py` | Cap de la queue par token |
| 7 jours | `infra/documents/*.py` | TTL queue et inbox |
| 5 / 300 s / 5 s / 300 s | `workers/webhook_inbox.py` | Retries et lease |
| 3 / 0,5 s / 5 s | `infra/chaster.py` | Retry Chaster |
| 15 / 30 / 60 s | `realtime/connection.py` | Timeouts RPC / intents / handshake |
| 30 s / 5 s | `api/realtime.py`, `realtime/watchers.py` | Heartbeat / send |
| `[1.0.0, 2.0.0)` | `realtime/connection.py` | Compatibilité API |
| 6 labels | `domain/use_cases/media_scan.py` | Filtre censorable |
| 100 images / 600 s | `domain/entities.py` | Défauts de configuration |

---

## 8. Où changer quoi

Cette section est le mode d'emploi pour modifier les mécaniques sans casser les invariants.

### 8.1 Changer le modèle de pénalité

**Objectif typique :** poids par label, score minimum, cooldown, plafond journalier, comptage par objet plutôt que par image.

**Fichiers à modifier**

| Couche | Fichier | Changement |
| --- | --- | --- |
| Schéma | `server/src/domain/entities.py` | Ajouter `min_score`, `label_weights`, `cooldown_seconds`, `max_penalties_per_day`, éventuellement `count_mode` à `CensorPicsConfigSchema` |
| Filtrage | `server/src/domain/use_cases/media_scan.py` | Remplacer `is_censorable` booléen par un calcul de points |
| Batching | `server/src/workers/media_scans.py` | Le batch ne doit plus stocker seulement `count`, mais les objets/points/labels agrégés |
| Persistance | `server/src/infra/documents/user_lock_configuration.py` | Ajouter les compteurs journaliers / dernier timestamp de pénalité |
| Repository | `server/src/infra/repositories.py` | Ajouter des opérations atomiques de claim avec cooldown/plafond |
| DTO | `server/src/domain/entities.py` | Exposer éventuellement la progression |
| Front | `front/src/components/common/configuration/CensoredMediaOptions.tsx` | Matrice de labels, score, poids, cooldown, plafond |
| Types | `server/openapi.json`, `front/src/types/api.generated.ts` | Régénérer via `pnpm generate:api` |
| Tests | `server/tests/test_media_scan.py`, `front/src/components/common/configuration/CensoredMediaOptions.test.tsx` | Poids, score, cooldown, plafond, migration |

**Point clé :** aujourd'hui `record_nowait(session, objects)` reçoit déjà les objets, mais `_PendingBatch` ne stocke que `count` et `batch.session`. Pour des poids par label, il faut agréger au minimum :

```python
@dataclass
class _PendingBatch:
    session: LockSession
    points: int = 0
    images: int = 0
    labels: Counter[int] = field(default_factory=Counter)
    due_at: float | None = None
    flushing: bool = False
```

**Décision de conception à prendre :** le seuil `limit_count` doit-il rester un nombre d'images, ou devenir un nombre de points ? Le document `FEATURE_ROADMAP.md` propose des points ; il faut alors migrer les valeurs existantes (`poids = 1` pour tous les labels) pour conserver le comportement actuel.

**Attention :** si le cooldown ou le plafond journalier est ajouté, il doit être **persisté en base**. Un état uniquement en mémoire serait perdu au redémarrage et permettrait de contourner le plafond.

---

### 8.2 Changer la cadence de pénalité

| Mécanique | Où | Remarque |
| --- | --- | --- |
| Fenêtre de batch | `MediaScanBatcher(window_seconds=...)` | Passer par la configuration ou les settings, pas par une constante |
| Cooldown entre pénalités | `MediaScanService.record_batch` + repository | Nécessite un timestamp persistant |
| Plafond par jour | Repository + index/collection | Nécessite une clé de jour (UTC) |
| Pénalité immédiate | Supprimer le batch ou réduire la fenêtre | Attention à la charge Chaster : un scan = un appel HTTP |
| Pénalité par objet | `is_censorable` / `record_nowait` | Un scan avec 3 objets compterait 3 au lieu de 1 |
| Pénalité par label | `CENSORABLE_LABELS` + poids | Voir 8.1 |

**Contrainte :** ne jamais faire d'I/O dans `Connection.handle_message`. Le batcher existe précisément pour cela. Si la nouvelle mécanique a besoin d'une décision immédiate (par exemple un couperet), elle doit rester non bloquante et déléguer à un worker.

---

### 8.3 Changer le comportement freeze/unfreeze

| Objectif | Fichier | Modification |
| --- | --- | --- |
| Configurer un timer PuryFi au freeze | `handle_lock_frozen` | Remplacer `timer: None` / `timerPlus: None` par une valeur calculée |
| Choisir la durée du timer | `ChasterExtensionConfigSchema` | Ajouter `lock_timer_seconds` ou `timer_mode` |
| Utiliser `timerPlus` (pénalité native PuryFi) | `handle_lock_frozen` | Fournir `timesPerLabel` au lieu de `null` |
| Réutiliser le mot de passe | `handle_lock_frozen` | Ne régénérer que si absent, ou selon une politique |
| Faire expirer le mot de passe | `UserLockConfiguration` + worker | Ajouter `password_expires_at` |
| Verrouiller sans activer | `handle_lock_frozen` | Supprimer la seconde commande `enabled=true` |
| Déverrouiller sans désactiver | `handle_lock_unfrozen` | Supprimer `enabled=false` |
| Ne pas écraser un timer existant | `handle_lock_frozen` | Lire `lockConfiguration` avant d'écrire, ou utiliser un `setState` partiel |
| Ajouter un log Chaster | `handle_lock_frozen` / `handle_lock_unfrozen` | Appeler `chaster.create_log` |
| Rendre l'enchaînement idempotent | `_queue_and_flush` | La queue le fait déjà ; attention au cap 100 |

**Point clé :** `setState` sur `lockConfiguration` **remplace toute la valeur**. Si l'on veut préserver un timer existant, il faut d'abord le lire (avec `readLockConfigurationState`) puis renvoyer une valeur complète, ou changer la mécanique pour écrire un chemin plus fin (`lockConfiguration.password`).

**Point clé :** la séquence actuelle est correcte pour la convergence : si `lockConfiguration` réussit et `enabled` échoue, la queue ne contient plus que `enabled` et sera rejouée. Si l'on ajoute des commandes, il faut conserver cette propriété de reprise.

---

### 8.4 Ajouter un mode « Guard » / réconciliation

**État actuel**

- `Connection` s'abonne déjà à `user`, `enabled`, `lockConfiguration` (selon intents).
- `stateChange` met à jour le cache et publie le statut.
- Aucune comparaison avec un état attendu, aucune réapplication.

**Ce qu'il manque**

1. **Persister l'état Chaster attendu** : ajouter `chaster_frozen: bool | None` (ou `last_chaster_event`) dans `UserLockConfiguration`, mis à jour par `handle_lock_frozen` / `handle_lock_unfrozen`.
2. **Définir l'état PuryFi attendu** à partir de `chaster_frozen` + `lock_on_freeze` / `unlock_on_unfreeze`.
3. **Comparer** dans `_handle_puryfi_state_change` :
   - Chaster gelé + `lock_on_freeze` → PuryFi doit être `enabled=true` et avoir un lock.
   - Chaster dégelé + `unlock_on_unfreeze` → PuryFi doit être `enabled=false` et ne pas avoir de lock.
4. **Anti-boucle** : ignorer les `stateChange` qui correspondent à notre propre `setState` (fenêtre de debounce ou comparaison avec la dernière commande envoyée).
5. **Mode** : `notify` (statut/alerte) ou `strict` (réappliquer via `setState`).
6. **UI** : badge « Protégé », « Modifié manuellement », « Lock PuryFi absent ».

**Fichiers**

- `server/src/realtime/connection.py` : `_handle_puryfi_state_change`, `_load_puryfi_state`.
- `server/src/domain/use_cases/lock_events.py` : persister l'état Chaster.
- `server/src/domain/entities.py` + `infra/documents` : nouveau champ.
- `server/src/realtime/registry.py` : exposer le diagnostic.
- `server/src/domain/use_cases/media_scan.py` : rien, sauf si Guard doit aussi surveiller les scans.

**Attention :** aujourd'hui, l'application ne connaît pas l'état Chaster courant. Un Guard naïf ne peut pas distinguer « PuryFi désactivé manuellement alors que Chaster est gelé » de « Chaster dégelé ». Il faut d'abord persister cet état.

---

### 8.5 Changer la politique de liaison et de secrets

| Objectif | Fichier | Modification |
| --- | --- | --- |
| Rotation du token | `api/session.py`, `use_cases/session.py`, `repositories.py` | Endpoint `POST /link-token/rotate`, invalider l'ancien, fermer la socket |
| Révocation | `session_lifecycle.py` | Réutiliser `close_by_user_link_token` + suppression token |
| Hash du token en base | `UserLockConfiguration` | Stocker `link_token_hash` et une version chiffrée pour l'affichage |
| Chiffrement du mot de passe | `UserLockConfiguration` + `Settings.secret_key` | Chiffrer/déchiffrer dans le repository |
| Expiration du token | `UserLockConfiguration` + worker | Ajouter `link_token_expires_at` |
| Audit des accès | nouveau | Journaliser les connexions/déconnexions avec fingerprint |

**Contrainte :** le token est utilisé comme clé de lookup dans `get_by_link_token` et dans la queue. Une rotation doit être **atomique** : nouveau token en base, ancienne socket fermée, queue de l'ancien token supprimée ou migrée.

---

### 8.6 Ajouter des contrôles manuels / keyholder

| Fonctionnalité | Brique à ajouter | SDK |
| --- | --- | --- |
| Lock/Unlock manuel depuis la session | Endpoint + use case + bouton UI | `setState` |
| Test de connexion | Endpoint ou message WS | `getPluginManifest`, `getPluginConfiguration`, `getPendingPluginIntents` |
| Déverrouillage temporaire | Collection `temporary_unlocks` + worker + endpoints | `enterLockPassword`, `setState` |
| Récupération d'urgence | Formulaire keyholder + endpoint | `enterLockEmergencyServerToken` |
| Diagnostic des permissions | Carte UI + endpoint | `getPluginIntents`, `getPendingPluginIntents` |
| Test d'image | Upload + endpoint | `scanStaticMedia`, `censorStaticMedia` |

**Contrainte :** toute action manuelle doit passer par la **même mailbox/queue** que les webhooks, sinon deux commandes peuvent se croiser et produire un état incohérent. Les use cases existants (`_queue_and_flush`) sont le bon point d'entrée.

---

### 8.7 Changer la fin de session

**Comportement actuel**

```text
extension_session.deleted
  → fermer plugin
  → supprimer queue
  → fermer watchers
  → supprimer config
```

**Options à décider**

| Option | Effet |
| --- | --- |
| **A. Purge silencieuse** (actuel) | Rapide, mais PuryFi peut rester verrouillé |
| **B. Déverrouiller avant purge** | Envoyer `enterLockPassword` + `enabled=false` puis purger ; ajoute de la latence et des cas d'échec |
| **C. Laisser le lock PuryFi expirer** | Si PuryFi a son propre timer, il finit par se déverrouiller ; pas garanti |
| **D. Marquer la session terminée sans supprimer** | Permet un audit et une reprise, mais conserve des secrets |

Si l'on choisit B, il faut le faire **avant** `sessions.delete`, avec un timeout et un comportement de secours. Il faut aussi décider quoi faire si PuryFi est offline : envoyer quand même la commande en queue, puis supprimer la queue ? Cela n'aurait aucun sens. Une stratégie possible : tenter le déverrouillage si la connexion est live, sinon consigner l'état et purger.

---

### 8.8 Passer à plusieurs instances

Les objets suivants sont process-wide et doivent être externalisés :

| Objet | Problème | Solution |
| --- | --- | --- |
| `ConnectionManager` | Une socket connue d'un seul process | Redis Pub/Sub ou routage par session |
| `SessionWatcherManager` | Watchers locaux seulement | Redis / broker |
| `MediaScanBatcher` | Compteurs en mémoire par process | Agrégation par session dans Redis |
| `WebhookInboxWorker` | Lease Mongo déjà compatible multi-process | OK, mais `_recover_processing` doit être revu |
| Mailbox par connexion | Doit rester locale au process qui détient la socket | Routage des commandes vers ce process |

Tant que ce n'est pas fait, **forcer un seul worker uvicorn** et le documenter.

---

### 8.9 Checklist générique de modification

1. **Définir la règle métier** dans `domain/` (pas dans les routes).
2. **Étendre le schéma** `ChasterExtensionConfigSchema` si la règle est configurable.
3. **Migrer les documents existants** : les nouveaux champs doivent avoir des défauts compatibles.
4. **Mettre à jour le repository** avec des opérations atomiques (pas de `read-modify-write`).
5. **Respecter les gates** : `ready`, `intents_granted`, ordre de la queue.
6. **Ne pas bloquer `handle_message`** : toute I/O lente va dans un worker.
7. **Mettre à jour les DTO** et régénérer `server/openapi.json` + `front/src/types/api.generated.ts` (`pnpm generate:api`).
8. **Mettre à jour l'UI** et les tests de composants.
9. **Ajouter les tests de régression** : idempotence, retry, état partiel, redémarrage, concurrence.
10. **Vérifier les secrets** : jamais dans les logs, jamais retournés au mauvais rôle.
11. **Vérifier le comportement offline** : la commande doit rester en queue et être rejouable.
12. **Vérifier le comportement shutdown** : flush des compteurs, annulation des tâches, fermeture des sockets.

---

## 9. Invariants à préserver

Ces propriétés sont testées et structurent la fiabilité actuelle. Toute nouvelle mécanique doit les conserver ou les remplacer explicitement.

1. **Un seul écrivain par socket.** Tous les envois passent par la mailbox et `_send_lock`.
2. **Pas d'I/O dans la boucle de lecture WebSocket.** Les scans sont bufferisés ; les RPC sont attendus par des futures.
3. **Rien n'est envoyé avant `ready` + intents obligatoires.** La queue est la seule zone sûre.
4. **Une commande n'est supprimée qu'après un envoi réussi.** Un crash ne perd pas la commande.
5. **L'ordre des commandes est sémantique.** `lockConfiguration` avant `enabled`, `enterLockPassword` avant `enabled=false`.
6. **Idempotence métier, pas `requestId`.** Chaster change le `requestId` à chaque retry.
7. **Le claim de pénalité est atomique.** Deux flush ne peuvent pas réclamer le même palier.
8. **Le compteur est restauré si l'ajout de temps échoue.**
9. **Un nouveau `ready` ne relance pas le handshake.**
10. **Une nouvelle socket remplace l'ancienne et la ferme.**
11. **Le rôle par défaut est deny.** Ni mot de passe ni token pour un rôle inconnu.
12. **Les secrets ne sont jamais loggés en clair.**
13. **Les watchers sont heartbeatés et les sockets mortes sont retirées.**
14. **Le shutdown flush les compteurs et annule les tâches supervisées.**

---

## 10. Constats, limites et dettes

### 10.1 Constats importants

| # | Constat | Impact |
| --- | --- | --- |
| 1 | `readUserState` est obligatoire | Un utilisateur qui refuse le profil PuryFi bloque freeze/unfreeze |
| 2 | `readMediaProcesses` est obligatoire même si la pénalité est désactivée | Permission inutile demandée |
| 3 | Le lock PuryFi efface `timer` et `timerPlus` | Un timer PuryFi existant est perdu au freeze |
| 4 | La suppression de session ne déverrouille pas PuryFi | Risque de lock PuryFi orphelin |
| 5 | Le token de liaison est permanent | Pas de rotation en cas de fuite |
| 6 | Le mot de passe est stocké en clair | Risque si la base est compromise ; `SECRET_KEY` inutilisé |
| 7 | La config locale n'est pas rafraîchie depuis Chaster | Dérive possible si `extension_updated` ou une modification externe |
| 8 | `extension_updated` est un no-op | Aucune synchro de config par webhook |
| 9 | `extension_session.created/updated` sont ignorés | Métadonnées de session non maintenues par webhook |
| 10 | Le compteur de médias n'est pas exposé | Le joueur ne voit pas sa progression |
| 11 | Aucun cooldown/plafond | Risque de pénalités runaway |
| 12 | Aucun audit | Difficile d'expliquer un ajout de temps |
| 13 | Le batch perd jusqu'à 15 s de scans au crash | Compteur non persisté avant flush |
| 14 | Le cap de queue drop le plus ancien | Peut casser une séquence de lock/unlock |
| 15 | Mono-processus | Pas de scale horizontal |
| 16 | `enterLockPassword` : intent ambigu dans la doc SDK | À valider avec le runtime |
| 17 | `configurationChange` met à jour `self.configuration` mais pas `session.config` | Impact faible, mais incohérence de cache |
| 18 | `reset_censored_count` et `increment_censored_count` sont inutilisés | Dette / code mort |

### 10.2 Mécaniques absentes mais disponibles dans le SDK

| Primitive SDK | Usage actuel | Potentiel |
| --- | --- | --- |
| `getPluginManifest` | Non utilisé | Diagnostic version plugin |
| `getPluginConfiguration` | Non utilisé | Diagnostic config côté plugin |
| `getPendingPluginIntents` | Non utilisé | Diagnostic permissions en attente |
| `unsubscribeFromState` | Non utilisé | Nettoyage / changement dynamique d'abonnements |
| `unsubscribeFromStaticMediaScans` | Non utilisé | Désactiver les scans à chaud |
| `enterLockEmergencyServerToken` | Non utilisé | Récupération d'urgence |
| `scanStaticMedia` / `censorStaticMedia` | Non utilisé | Test d'image, prévisualisation |
| `timer` / `timerPlus` | Écrasés à `null` | Timer PuryFi natif, pénalité par label native |
| `wblistConfiguration` | Non utilisé | Whitelist/blacklist PuryFi |
| `subscribeToMediaCensorHooks` | Non utilisé | Censure personnalisée (risqué, latence) |

### 10.3 Dettes techniques

- `lock_events.py` ne crée aucun log Chaster pour freeze/unfreeze.
- `extension_updated` est un TODO explicite.
- `extension_session.created/updated` ne sont pas dispatchés.
- Le compteur de médias n'a pas de progression exposée.
- Le `SecretStr` de `SECRET_KEY` n'est pas exploité.
- `README` et `FEATURE_ROADMAP` mentionnent des fonctionnalités encore absentes (diagnostic, Guard, audit, rotation, unlock temporaire).
- `ARCHITECTURE_REVIEW.md` date d'une version antérieure ; certaines corrections ont été faites, mais il reste une bonne base de constats.

---

## 11. Décisions à prendre

Avant de modifier les mécaniques, il faut trancher ces points. Ils déterminent l'ampleur du changement.

### 11.1 Modèle de jeu

1. **Pénalité** : images, points, ou objets ? Le seuil doit-il être un nombre d'images ou un score ?
2. **Labels** : quels labels comptent ? Faut-il inclure les variantes `Covered` ? Faut-il un poids par label ?
3. **Score** : faut-il ignorer les détections sous un seuil de confiance ?
4. **Cooldown / plafond** : faut-il limiter les pénalités par jour ou par fenêtre ?
5. **Progression** : faut-il afficher le compteur et le prochain palier ?

### 11.2 Comportement du lock

6. **Timer PuryFi** : faut-il préserver, effacer ou configurer un timer au freeze ?
7. **TimerPlus** : faut-il utiliser la pénalité native PuryFi ou continuer à appeler Chaster ?
8. **Mot de passe** : doit-il être régénéré à chaque freeze, réutilisé, ou expirer ?
9. **Fin de session** : faut-il déverrouiller PuryFi avant la purge ?
10. **Guard** : mode notify ou strict ? Faut-il persister l'état Chaster ?

### 11.3 Permissions et sécurité

11. **Intents** : `readUserState` et `readMediaProcesses` doivent-ils rester obligatoires ?
12. **Token** : faut-il une rotation/révocation, et à quelle fréquence ?
13. **Secrets** : faut-il chiffrer le mot de passe et/ou le token au repos ?
14. **Audit** : faut-il journaliser les connexions, freeze/unfreeze et pénalités ?

### 11.4 Exploitation

15. **Multi-instance** : rester mono-processus ou introduire Redis ?
16. **Observabilité** : métriques, traces, healthchecks plus complets ?
17. **Tests de contrat** : exécuter les tests avec le runtime PuryFi de `purify-sdk/versions-built/` avant chaque changement de protocole ?

---

## Références principales

| Sujet | Fichier |
| --- | --- |
| Schéma de configuration | `server/src/domain/entities.py` |
| Freeze/unfreeze | `server/src/domain/use_cases/lock_events.py` |
| Pénalité médias | `server/src/domain/use_cases/media_scan.py` |
| Batching des scans | `server/src/workers/media_scans.py` |
| Handshake et acteur PuryFi | `server/src/realtime/connection.py` |
| Protocole PuryFi | `server/src/realtime/protocol.py` |
| Queue durable | `server/src/infra/queue.py` |
| Drain de queue | `server/src/workers/outbound.py` |
| Inbox webhook | `server/src/workers/webhook_inbox.py` |
| Idempotence | `server/src/domain/events.py` |
| Session lifecycle | `server/src/domain/use_cases/session_lifecycle.py` |
| Repositories | `server/src/infra/repositories.py` |
| Statut temps réel | `server/src/realtime/registry.py`, `server/src/api/realtime.py` |
| Watchers | `server/src/realtime/watchers.py` |
| UI session | `front/src/pages/Session.tsx` |
| UI configuration | `front/src/pages/Configuration.tsx` |
| SDK PuryFi | `purify-sdk/docs/README.md` |
| Roadmap existante | `FEATURE_ROADMAP.md` |
| Revue d'architecture | `ARCHITECTURE_REVIEW.md` |
