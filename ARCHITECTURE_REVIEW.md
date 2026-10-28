# Revue d'architecture — Puryfier

> Analyse du dépôt `puryfier` (version 0.3.0)
> Date : 2026-10-28
> Périmètre : backend FastAPI/Beanie, frontend React/Vite, tests, Docker, documentation.
> Méthode : lecture du code, vérification des index Beanie, exécution de la suite de tests, du linter et du build.

---

## Sommaire

1. [Verdict rapide](#1-verdict-rapide)
2. [Architecture actuelle](#2-architecture-actuelle)
3. [Points forts](#3-points-forts)
4. [Bugs et points faibles](#4-bugs-et-points-faibles)
5. [Features](#5-features)
6. [Architecture cible proposée](#6-architecture-cible-proposée)
7. [Plan de migration priorisé](#7-plan-de-migration-priorisé)
8. [Quick wins](#8-quick-wins-à-faire-tout-de-suite)
9. [Conclusion](#9-conclusion)

---

## 1. Verdict rapide

Puryfier est un **bon MVP**, avec une stack cohérente et une base front/back propre. J'ai vérifié l'état actuel :

- `pytest` : **52 tests passent**
- `ruff check` : OK
- `eslint` : OK
- `tsc + vite build` : OK (un warning Vite mineur sur `__dirname`)

Les vrais risques ne sont pas dans le style du code, mais dans **le pipeline webhook, le cycle de vie des secrets et l'état en mémoire**. Les trois points les plus critiques :

1. **La déduplication des webhooks Chaster est basée sur `requestId`, mais Chaster change ce `requestId` à chaque retry.** Elle ne protège donc pas contre les vrais retries.
2. **Les handlers webhook peuvent dépasser le timeout Chaster de 10 s** : le backend attend jusqu'à 15 s par RPC, et certains handlers en envoient deux à la suite.
3. **Les tokens et mots de passe ont un cycle de vie trop faible** : tokens loggés en clair, pas de révocation, pas de nettoyage à la fin d'une session, mot de passe stocké en clair.

À mon avis : **ne réécris pas tout**. Corrige d'abord les points P0 ci-dessous, puis extrais progressivement la logique métier des routes.

---

## 2. Architecture actuelle

```text
Chaster (iframe)
   │ hash: mainToken / partnerConfigurationToken
   ▼
React SPA
   │ GET/PUT /api/...          ┌──────────────┐
   ├──────────────────────────►│  FastAPI     │
   │                           │  routes      │
   │ WS /ws/session|config     │              │
   ▼                           │  services    │
Watchers ◄── ConnectionManager │  actions     │
   ▲                           └──────┬───────┘
   │                                  │ Beanie
   │                                  ▼
   │                               MongoDB
   │
Puryfi plugin ──WS /ws/{link_token}──► Connection(msgpack)
                                              ▲
Chaster webhooks ──POST───────────────────────┘
```

### Flux principaux

- **Page session/config** : le front récupère un token Chaster depuis le hash, appelle le backend, qui interroge Chaster, crée ou récupère un `UserLockConfiguration`, puis renvoie un DTO filtré selon le rôle.
- **Puryfi** : le plugin se connecte en WebSocket, le serveur fait le handshake `manifest` → `intents` → `getState` → `subscribeToStaticMediaScans`, puis traite les scans.
- **Webhooks** : auth Basic, déduplication par `requestId`, puis `lock_frozen` / `lock_unfrozen` envoient des RPC au plugin ou mettent en file d'attente.
- **Temps réel UI** : des sockets « watchers » écoutent les changements online/offline par session.

### Organisation du code

- `server/src/routes` : HTTP + une partie de la logique métier.
- `server/src/models` : documents Beanie **et** état runtime (`Connection`, `ConnectionManager`).
- `server/src/services` : appels Chaster et queue.
- `server/src/schemas` / `typings` : DTO internes et DTO Chaster.
- `front/src/pages`, `components`, `hooks`, `lib` : structuration simple et lisible.

---

## 3. Points forts

| Point | Détail |
|---|---|
| Stack adaptée | FastAPI + Beanie + MongoDB async, React 19 + Vite + TypeScript, Turborepo + pnpm + uv. |
| Monorepo propre | Séparation `front` / `server`, scripts centralisés, lockfiles présents. |
| Front lisible | Composants réutilisables, design system cohérent, skeletons, états d'erreur, responsive. |
| Bonne sécurité de base | Auth Basic en temps constant, CORS allowlist, masquage du mot de passe pour le wearer, pas de log des payloads sensibles. |
| Queue robuste | Cap par token, TTL MongoDB, suppression après envoi, ordre préservé. |
| Temps réel | Mise à jour online/offline sans refresh, reconnexion avec backoff. |
| Tests backend | 52 tests, dont des régressions sur les points sensibles (queue, RPC timeout, webhooks, media scan). |
| Déploiement documenté | Tunnel Cloudflare et Traefik, même origine pour `/api` et `/ws`, pas de CORS en production. |
| Expérience offline | Les messages sont mis en file si Puryfi n'est pas connecté. |

---

## 4. Bugs et points faibles

### 4.1 🔴 Critiques

| # | Localisation | Problème | Correction |
|---|---|---|---|
| 1 | `server/src/routes/webhooks/chaster.py:79-85` | **Déduplication par `requestId` seulement.** La doc Chaster dit explicitement que chaque tentative de retry a un **nouveau** `requestId` et un nouveau `sentAt`. Un retry de `lock_frozen` peut donc régénérer un mot de passe et remettre les messages en file. Le test `test_retried_lock_frozen...` réutilise le même `requestId`, ce qui masque le bug. | Clé d'idempotence métier : `event + data.actionLog._id` pour `action_log.created`, et `(event, sessionId, updatedAt)` pour les événements de session. Stocker cette clé dans une inbox unique, avec un état `pending/processing/done`. |
| 2 | `server/src/models/connection.py:57` + `lock_frozen.py:40-49` + `lock_unfrozen.py:45-55` | **Timeout webhook > timeout Chaster.** Chaster attend une réponse en 10 s. Le RPC timeout est de 15 s, et certains handlers font deux RPC séquentiels : jusqu'à 30 s. Chaster retente pendant que le premier traitement tourne encore. | Répondre `2xx` immédiatement après acceptation durable, puis traiter en worker. Sinon, réduire le timeout RPC à 3-5 s et rendre chaque handler idempotent. |
| 3 | `server/src/routes/webhooks/chaster.py:17-33` | **Échec ouvert si les credentials ne sont pas configurés.** Si `CHASTER_WEBHOOK_USER` et `CHASTER_WEBHOOK_PWD` sont vides, une requête avec `Authorization: Basic Og==` (user/pass vides) est acceptée. Vérifié. | Refuser le démarrage si l'un des deux est vide, ou répondre `503` plutôt que d'accepter. |
| 4 | `server/src/models/documents/user_lock_configuration.py:12-18` | **Les index Beanie ne sont pas créés.** Le type `Annotated[str, Indexed(unique=True)] &#124; None` place l'annotation dans l'`Optional` ; Beanie ne la détecte pas. Vérifié : `users_lock_configurations.index_information()` ne contient aucun index sur `session_id`, `lock_id` ni `link_token`. Conséquences : scans complets, aucune unicité, doublons possibles. | Déclarer les index dans `Settings.indexes`, avec un index partiel pour `link_token` (voir snippet ci-dessous). |
| 5 | `server/src/routes/extensions.py:34-49` et `configuration.py:45-60` | **Race `find_one` puis `insert`.** Deux requêtes simultanées peuvent créer deux configurations pour la même session. L'absence d'index unique aggrave le problème. | `update_one(..., upsert=True)` atomique + index unique sur `session_id`. Gérer `DuplicateKeyError` en relisant le document. |
| 6 | `server/src/routes/extensions.py:57-60` | **Mot de passe renvoyé pour tout rôle autre que `wearer`.** Le code fait `if role == "wearer": HIDDEN`, donc un rôle inconnu ou futur reçoit le mot de passe en clair. | Politique par défaut : `lock_password = ... if role == "keyholder" else None`. Ne jamais retourner le secret pour un autre rôle. |
| 7 | `server/src/routes/websocket.py:143`, `server/src/services/link.py:19` | **Tokens secrets dans les logs.** Le `link_token` est imprimé en clair. Les tokens Chaster sont aussi dans les URLs (`/api/session/{token}`, `/ws/session/{token}`), donc dans les access logs Uvicorn et potentiellement les erreurs remontées au front. | Logger une version masquée/hashée, filtrer les access logs, et éviter les tokens dans les URLs (auth WS par premier message ou ticket court). |
| 8 | `server/src/routes/websocket.py:154-169` + `connection.py:112-113` | **Tâches fire-and-forget non supervisées.** `initialize_plugin()` et `process_queued_messages()` ne sont ni suivies ni annulées à la déconnexion. Si les intents ne sont jamais accordés, `intents_granted_event.wait()` bloque indéfiniment. | Utiliser un `TaskGroup` ou un set de tâches, annuler dans `finally`, ajouter un timeout et un événement d'échec. |
| 9 | `server/src/models/connection_manager.py:23-25` | **Une nouvelle connexion remplace l'ancienne sans fermer l'ancienne.** Deux sockets peuvent rester actifs pour le même token ; l'ancienne continue de traiter des scans et peut recevoir des RPC. | Fermer l'ancienne socket, la retirer explicitement, et poser un verrou par token. |

### 4.2 🟠 Importants

| # | Localisation | Problème | Correction |
|---|---|---|---|
| 10 | `server/src/models/connection.py:109-113` | **Un `ready` multiple lance plusieurs handshakes et plusieurs drains de queue.** Chaque drain peut renvoyer les mêmes messages. | Flag `_ready_handled`, une seule tâche d'initialisation, drain idempotent. |
| 11 | `server/src/models/connection.py:125-151` | **Le traitement d'un scan fait des appels HTTP bloquants dans la boucle de réception.** `add_time_to_lock` et `create_custom_log` bloquent la lecture des RPC suivants et peuvent provoquer des timeouts. | Mettre les scans dans une file interne avec un worker par connexion. Ne jamais faire d'I/O longue dans `handle_message`. |
| 12 | Absence de handler `extension_session.deleted` | **Aucun nettoyage à la fin d'une session.** La configuration, le mot de passe, le token et les messages en file restent indéfiniment. Un ancien token reste valide et peut reconnecter un plugin après la fin du lock. | Traiter `extension_session.created/updated/deleted`, supprimer ou anonymiser les données, fermer la connexion et les watchers, révoquer le token. |
| 13 | `server/src/services/link.py:22-38` | **`save()` écrit tout le document** (risque de lost update avec un webhook concurrent) et **le log Chaster « linked Puryfi » est créé à chaque reconnexion**, pas seulement à la première liaison. | Mises à jour ciblées `$set`, et log uniquement si `has_linked_plugin` passe de `false` à `true` via une mise à jour conditionnelle. |
| 14 | `server/src/routes/configuration.py:86-128` | **Payload de configuration non validé.** `payload: dict`, puis `lock_config.config = data.get("config")` sans vérifier la forme. Si Chaster renvoie un `config` absent/null, erreur 500 après que Chaster a déjà sauvegardé. | Utiliser `ChasterExtensionConfigSchema` en entrée et en sortie, valider les bornes, et utiliser le payload validé comme source de vérité locale. |
| 15 | `server/src/models/connection.py:138-151` | **Le compteur de médias est remis à zéro avant de savoir si l'ajout de temps a réussi.** Si `add_time_to_lock` échoue, la pénalité est perdue. Le compteur est aussi perdu à chaque reconnexion. | Remettre à zéro seulement après succès, et persister le compteur par session. |
| 16 | `server/src/routes/webhooks/actions/lock_unfrozen.py:45-56` | **Le résultat de `setState(enabled=false)` est ignoré.** Le handler retourne `processed` même si le disable a échoué. | Vérifier chaque réponse et modéliser la transition comme une machine à états idempotente. |
| 17 | `server/src/routes/webhooks/actions/lock_frozen.py:40-49` | **Puryfi est activé avant que le mot de passe de lock soit configuré.** En cas d'échec du second message, on reste dans un état partiel. | Envoyer `lockConfiguration` d'abord, puis `enabled=true`. Rendre la séquence rejouable. |
| 18 | `server/src/utils/chaster_api.py:26-40`, `services/chaster.py:6-23` | **Pas de retry/backoff** sur les appels Chaster ; les erreurs 4xx/5xx sont peu exploitées. `str(e)` peut contenir l'URL avec le token dans la réponse d'erreur. | `tenacity` avec backoff, logs structurés, messages génériques côté client. |
| 19 | `server/src/models/connection.py:63,72-77` | `asyncio.get_event_loop()` est déprécié. Si `send_bytes` échoue, le `finally` n'est pas exécuté et la future reste dans `pending_requests`. | `asyncio.get_running_loop()` et englober l'envoi + l'attente dans le même `try/finally`. |
| 20 | `server/src/models/session_watchers.py:24-30` | **Broadcast séquentiel** : un watcher lent bloque tous les autres. Pas de heartbeat, donc une socket morte peut rester « online ». | `asyncio.gather` avec timeout, ping/pong, suppression des sockets mortes. |
| 21 | `server/src/routes/websocket.py:126-171` | `manager.add` publie `is_online=true` dès l'acceptation de la socket, avant le handshake Puryfi. Un client avec un token valide mais sans handshake apparaît en ligne. | Distinguer `connected` et `ready` ; ne publier `is_online` qu'après le handshake ou maintenir un flag `ready`. |

### 4.3 🟡 Frontend

| # | Localisation | Problème | Correction |
|---|---|---|---|
| 22 | `front/src/hooks/usePuryfiRealtimeStatus.ts:70-76` | Le statut reste `online` après une déconnexion du socket ; le backoff n'a pas de jitter. | Mettre le statut à `unknown/offline` à la fermeture, ajouter du jitter, limiter les retries, mettre en pause quand l'onglet est caché. |
| 23 | `front/src/components/ui/number-input.tsx:61-70` | Les valeurs invalides (0, négatif, décimal) sont propagées à chaque frappe avant le blur. | Valider/clamper immédiatement + validation serveur (`Field(ge=1)`). |
| 24 | `front/src/pages/Session.tsx:36-62` et `Configuration.tsx:58-129` | Duplication du fetching, du pattern `hasFetched`, de la gestion d'erreur et des appels `axios`. Pas de timeout ni d'`AbortController`. | Extraire `lib/api/*`, des hooks `useSession` / `useConfiguration`, et un client typé généré depuis l'OpenAPI. |
| 25 | `front/src/lib/clipboard.ts:16-29` | Si `document.execCommand` lève une exception, le `<textarea>` temporaire n'est pas retiré. | `try/finally` autour du fallback. |
| 26 | Global front | Pas de tests front, pas d'ErrorBoundary, pas de route 404, modal sans focus trap. | Vitest + Testing Library, ErrorBoundary, route `*`, focus trap/`aria-describedby`. |

### 4.4 🔵 Propreté / dette

- `print()` utilisé **55 fois** dans `server/src` : passer à `logging` structuré avec niveaux.
- `models/connection.py` mélange protocole msgpack, logique métier, persistance et appels Chaster : trop de responsabilités.
- `Connection.process_queued_messages` importe `manager` localement pour contourner un import circulaire : signe d'inversion de dépendance.
- `routes/configuration.py` contient deux branches presque identiques (`wearer` / `else`).
- `extension_updated.py` est un TODO qui retourne `processed` sans rien faire. La doc Chaster documente plutôt `extension_session.updated` ; il est probable que la synchro de configuration par webhook ne fonctionne pas.
- `puryfi_username` n'est jamais alimenté ; `getState user.username` est récupéré puis oublié.
- `manifest.version = "0.3.0"` est dupliqué avec `package.json` / `pyproject.toml`.
- `front/src/components/ui/empty.tsx` et la dépendance `iframe-resizer` (parent) semblent inutilisés.
- `wrangler` / `@cloudflare/vite-plugin` coexistent avec un déploiement Docker/nginx : deux stratégies de déploiement à clarifier.
- Les commentaires font référence à `REVIEW.md`, absent du dépôt.
- `.env.example` dit « Add ONE public hostname → http://front:80 », alors que `/api` et `/ws` doivent aller vers `server:8000` (comme expliqué dans le README). Suivre `.env.example` à la lettre casse l'API.
- `server/Dockerfile` n'a pas de `.dockerignore` dédié : le contexte `./server` copie `.venv`, `tests`, caches, etc.
- Conteneur serveur en `root`, pas de healthcheck, images `mongo:8` / `cloudflared:latest` non pinnées.
- Pas de CI (`.github` absent), pas de `pyright` exécuté, pas de `ruff format --check`.

### 4.5 Exemple de correction des index Beanie

```python
from pymongo import ASCENDING, IndexModel
from beanie import Document


class UserLockConfiguration(Document):
    session_id: str
    lock_id: str | None = None
    link_token: str | None = None
    # ...

    class Settings:
        name = "users_lock_configurations"
        indexes = [
            IndexModel([("session_id", ASCENDING)], unique=True),
            IndexModel([("lock_id", ASCENDING)]),
            IndexModel(
                [("link_token", ASCENDING)],
                unique=True,
                partialFilterExpression={"link_token": {"$type": "string"}},
            ),
        ]
```

> Pourquoi un index partiel : un index unique `sparse` indexe quand même un champ explicitement `null`. Comme Beanie sérialise `link_token=None` en `null`, il faut filtrer sur le type `string` pour autoriser plusieurs configurations non liées.

---

## 5. Features

### 5.1 Déjà là

- Lock automatique de Puryfi au freeze Chaster, avec génération d'un mot de passe d'urgence.
- Unlock + disable au unfreeze.
- Ajout de temps quand Puryfi censure des médias.
- File d'attente si Puryfi est offline.
- Statut temps réel online/offline dans l'iframe.
- Page de configuration complète avec sauvegarde vers Chaster.
- Génération du lien WebSocket Puryfi.
- UI adaptée aux rôles wearer/keyholder.
- Déploiement tunnel Cloudflare / Traefik.

### 5.2 Incomplet ou fragile

- `extension_updated` : TODO, probablement mauvais event.
- Pas de gestion de `extension_session.created/updated/deleted`.
- Pas de rotation/révocation du token Puryfi.
- Le compteur de médias n'est pas persistant.
- Le mot de passe d'urgence ne se met pas à jour dans l'UI après un freeze si la page est déjà ouverte.
- Pas d'état `ready` distinct de `connected`.
- Pas de support multi-instance.

### 5.3 Idées à forte valeur

| Feature | Intérêt | Effort |
|---|---|---|
| Bouton « Révoquer / régénérer le lien Puryfi » | Sécurité, en cas de fuite de token | Faible |
| Nettoyage automatique en fin de session | RGPD / secrets | Faible |
| Progression « X/Y médias censurés » persistée | UX et fiabilité | Moyen |
| Choix des labels considérés comme censurables | Personnalisation | Faible |
| Boutons manuels « Lock / Unlock / Tester la connexion » | Debug et contrôle | Faible |
| Activité en direct (scans, seuil, temps ajouté) | Transparence | Moyen |
| Affichage du username Puryfi et du last seen | Debug / confiance | Faible |
| i18n FR/EN | Accessibilité | Moyen |
| Métriques Prometheus + `/healthz` | Ops | Faible |
| Redis pub/sub + inbox distribuée | Scaling multi-instance | Élevé |

---

## 6. Architecture cible proposée

L'objectif n'est pas de tout réécrire, mais de séparer clairement **transport**, **métier**, **persistance** et **orchestration asynchrone**.

```text
apps/api/src/puryfier/
├── main.py
├── config.py                 # pydantic-settings, validation au démarrage
├── api/                      # routes HTTP/WS minces
│   ├── deps.py
│   ├── session.py
│   ├── configuration.py
│   ├── webhooks.py
│   └── realtime.py
├── domain/
│   ├── entities.py           # LockSession, PuryfiLink, ExtensionConfig
│   ├── ports.py              # Protocols: Repository, ChasterGateway, Inbox, Hub
│   └── use_cases/
│       ├── open_session.py
│       ├── update_configuration.py
│       ├── handle_lock_event.py
│       ├── link_puryfi.py
│       └── count_censored_media.py
├── infra/
│   ├── chaster.py            # httpx + retry + DTO typés
│   ├── mongo.py              # documents Beanie + repositories
│   └── logging.py
├── realtime/
│   ├── protocol.py           # codec msgpack + validation
│   ├── connection.py         # acteur par connexion + mailbox
│   ├── registry.py           # token/session -> connexion
│   └── watchers.py
└── workers/
    ├── webhook_inbox.py      # traitement durable des webhooks
    └── outbound.py           # drain de la queue
```

### 6.1 Les sept principes

1. **Webhook = accepter puis traiter.**
   - Vérifier l'auth, calculer une clé d'idempotence, insérer dans une collection `webhook_inbox`.
   - Répondre `200/202` en moins d'une seconde.
   - Un worker traite ensuite avec des leases, des retries et une DLQ.

2. **Clé d'idempotence métier, pas `requestId`.**

   ```python
   if event == "action_log.created":
       key = f"{event}:{data['actionLog']['_id']}"
   elif event.startswith("extension_session."):
       key = f"{event}:{data['session']['sessionId']}:{data['session'].get('updatedAt')}"
   ```

3. **Un acteur par connexion Puryfi.**
   - Une seule mailbox ordonnée par connexion.
   - Toutes les actions (webhook, queue, config) passent par cette mailbox.
   - Un seul worker envoie les messages, corrèle les `responseId`, applique les timeouts et publie les changements d'état.

4. **Le domaine ne connaît ni FastAPI, ni Beanie, ni msgpack.**
   - Les routes appellent des use cases.
   - Les use cases dépendent de ports (`Protocol`).
   - Les implémentations Mongo/Chaster/WebSocket sont dans `infra/` et `realtime/`.

5. **Settings validés au démarrage.**

   ```python
   class Settings(BaseSettings):
       chaster_developer_token: SecretStr
       chaster_webhook_user: SecretStr
       chaster_webhook_pwd: SecretStr
       database_url: str
       front_url: HttpUrl
       secret_key: SecretStr
   ```

   - Refuser de démarrer si un secret critique est vide.
   - Plus de `os.getenv()` dispersés ni de token capturé à l'import.

6. **Un modèle de données avec cycle de vie.**

   ```python
   class UserLockConfiguration(Document):
       session_id: str
       lock_id: str | None
       link_token_hash: str | None
       link_token_encrypted: str | None
       lock_password_encrypted: str | None
       has_linked_plugin: bool = False
       created_at: datetime
       updated_at: datetime
       ended_at: datetime | None

       class Settings:
           indexes = [
               IndexModel([("session_id", ASCENDING)], unique=True),
               IndexModel([("lock_id", ASCENDING)]),
               IndexModel(
                   [("link_token_hash", ASCENDING)],
                   unique=True,
                   partialFilterExpression={"link_token_hash": {"$type": "string"}},
               ),
           ]
   ```

   - Index partiel obligatoire : un index unique `sparse` indexe quand même les champs explicitement `null`, donc plusieurs configurations non liées seraient en conflit.
   - `link_token` : hash pour la recherche, version chiffrée pour l'affichage.
   - `lock_password` : chiffré avec une clé d'application.
   - `ended_at` + purge/TTL.

7. **Une abstraction de bus d'événements.**
   - Aujourd'hui : inbox Mongo + worker in-process.
   - Demain, si multi-instance : Redis Streams / PubSub pour router les événements et les statuts entre réplicas.
   - En l'état, `ConnectionManager` et `SessionWatcherManager` sont des singletons en mémoire : **l'application ne peut pas tourner avec plusieurs workers**. Il faut soit le documenter et forcer `--workers 1`, soit ajouter Redis.

### 6.2 Flux cible d'un webhook

```text
Chaster
  │ POST /webhooks
  ▼
Auth Basic (fail closed)
  │
  ▼
Calcul event_key + insert webhook_inbox (unique)
  │
  ├── doublon → 200 duplicate
  └── nouveau → 202 accepted
                    │
                    ▼
              Worker (lease + retry)
                    │
                    ▼
              Use case lock_frozen
                    │
                    ├── DB: update password (atomique)
                    └── Mailbox connexion Puryfi
                              │
                              ▼
                        Envoi msgpack sérialisé
```

### 6.3 Flux cible d'une connexion Puryfi

```text
WS /ws/{token}
  │ auth par hash de token
  ▼
Création d'un acteur Connection
  │
  ├── mailbox ordonnée (commandes webhook/queue/config)
  ├── handshake (manifest, intents, state)
  ├── RPC avec timeout court
  ├── heartbeat ping/pong
  └── publication des statuts aux watchers
```

---

## 7. Plan de migration priorisé

### P0 — 1 à 3 jours : sécurité et fiabilité immédiate

1. Refuser les credentials webhook vides (fail closed).
2. Dédupliquer par `event + actionLog._id` au lieu de `requestId`.
3. Répondre aux webhooks en `< 1 s` via une inbox durable, ou au minimum réduire les RPC à 3-5 s et rendre les handlers idempotents.
4. Corriger les index Beanie avec `Settings.indexes` + index partiel sur `link_token`.
5. Remplacer `find_one` + `insert` par un upsert atomique.
6. Masquer les tokens dans les logs et les messages d'erreur.
7. Politique par défaut : mot de passe uniquement pour `keyholder`.
8. Traiter `extension_session.deleted` : purge, révocation, fermeture des sockets.
9. `Cache-Control: no-store` sur les endpoints sensibles.

### P1 — 1 à 2 semaines : robustesse

1. Introduire l'acteur par connexion + mailbox ordonnée.
2. Superviser/annuler les tâches, ajouter les timeouts manquants.
3. Fermer l'ancienne connexion lors d'un remplacement.
4. Guard sur `ready`, heartbeat, état `connected` vs `ready`.
5. Persister le compteur de médias et ne le reset qu'après succès.
6. Valider la configuration côté serveur (`Field(ge=1, le=...)`).
7. Ajouter les retries Chaster avec backoff et logs structurés.
8. Tests : retry avec **nouveau** `requestId`, timeout webhook, deux sessions sans token, double `ready`, double connexion, config invalide.

### P2 — 2 à 4 semaines : architecture et qualité

1. Extraire `api/domain/infra/realtime/workers`.
2. Introduire `Settings`, DI via `app.state`, logging JSON.
3. Générer les types front depuis l'OpenAPI FastAPI.
4. Extraire un client API front + hooks + ErrorBoundary.
5. Ajouter Vitest/Testing Library et Playwright.
6. CI GitHub Actions : `ruff format --check`, `ruff check`, `pyright`, `pytest`, `eslint`, `tsc`, `vitest`, build Docker.
7. `/healthz`, healthchecks Docker, conteneur non-root, `.dockerignore`.
8. Nettoyer les dépendances mortes (`iframe-resizer`, `wrangler` si Docker uniquement).

### P3 — optionnel

- Redis Pub/Sub + inbox distribuée pour le multi-instance.
- Chiffrement des secrets avec rotation de clé.
- Métriques Prometheus, traces OpenTelemetry.
- i18n, notifications, audit log.

---

## 8. Quick wins à faire tout de suite

- [ ] `asyncio.get_event_loop()` → `asyncio.get_running_loop()`
- [ ] `try/finally` autour de `send_bytes` + attente RPC
- [ ] Flag `_ready_handled` dans `Connection`
- [ ] Fermer l'ancienne socket dans `ConnectionManager.add`
- [ ] Annuler les tâches dans le `finally` du endpoint WS
- [ ] Timeout sur `intents_granted_event.wait()`
- [ ] `lock_password` uniquement si `role == "keyholder"`
- [ ] Index `session_id` unique + index partiel `link_token`
- [ ] `Field(ge=1)` sur `limit_count` et `added_duration`
- [ ] Ne plus logger `user_token`
- [ ] `Cache-Control: no-store` sur session/config
- [ ] Ajouter `server/.dockerignore`
- [ ] Ajouter un `USER` non-root et un healthcheck
- [ ] Corriger `.env.example` (3 routes tunnel)
- [ ] Supprimer les références à `REVIEW.md` ou ajouter le fichier
- [ ] Passer les 55 `print` à `logging`
- [ ] Ajouter une ErrorBoundary et une route 404 côté front
- [ ] Mettre à jour le test de retry webhook pour utiliser un **nouveau** `requestId`

---

## 9. Conclusion

Le projet est **bien parti** : le front est soigné, le backend est lisible, les tests montrent une vraie culture des régressions, et la queue est déjà pensée pour l'offline. C'est un bon MVP auto-hébergé.

Les deux chantiers qui comptent vraiment sont :

1. **Le pipeline webhook** : idempotence métier, réponse rapide, traitement asynchrone durable.
2. **Le cycle de vie des secrets** : tokens, mots de passe, logs, révocation, nettoyage de session.

La priorité est donc :

```text
Sécurité webhook + idempotence
        ↓
Inbox durable + réponses rapides
        ↓
Cycle de vie des tokens/secrets
        ↓
Acteur par connexion + supervision des tâches
        ↓
Refactor progressif api/domain/infra
        ↓
Tests front + CI + observabilité
```

Une réécriture complète n'est pas nécessaire. Les correctifs P0 peuvent être faits sans changer l'architecture globale, puis le découpage `api/domain/infra` peut être introduit progressivement, route par route.
