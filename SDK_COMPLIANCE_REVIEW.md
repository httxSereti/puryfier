# Revue de conformité — Puryfier × SDK PuryFi

> Analyse de la codebase `puryfier` par rapport au SDK `@pury-fi/plugin-sdk`
> et au runtime PuryFi 0.8.8.0.
>
> Date : 29 octobre 2026
> Périmètre : `server/` (implémentation du plugin), `purify-sdk/` (SDK de référence), `front/` (hors protocole PuryFi).

---

## 1. Verdict

**La codebase suit désormais le SDK et le runtime PuryFi pour le sous-ensemble de fonctionnalités qu’elle implémente.**

Les écarts identifiés lors de la première revue ont été corrigés dans l’état actuel du dépôt :

- les commandes de lock passent par la queue durable et attendent `ready` + intents ;
- les erreurs sont lues avec la bonne clé (`error`), avec fallback sur `name` ;
- `lockConfiguration` est envoyé avec les trois champs requis ;
- `ready.apiVersion` est validé sur la plage `[1.0.0, 2.0.0)` ;
- les scans média ne bloquent plus la boucle de lecture WebSocket.

Il reste uniquement des points mineurs ou des fonctionnalités SDK volontairement non utilisées.

Le SDK n’est pas une dépendance du serveur : `purify-sdk/` est un clone Git séparé, ignoré par le dépôt principal (`.gitignore:5`) et absent du workspace pnpm (`pnpm-workspace.yaml`). Le serveur Python réimplémente le protocole ; la conformité est vérifiée par des tests de contrat, pas par un import du SDK.

---

## 2. Baseline et méthode

| Élément | Version / commit |
| --- | --- |
| SDK local | `purify-sdk/`, commit `0252d1b` |
| SDK npm | `@pury-fi/plugin-sdk@1.0.0` |
| Runtime PuryFi de référence | 0.8.8.0 (`purify-sdk/versions-built/puryfi-firefox-0.8.8.0-an+fx.xpi`) |
| Tests serveur | 189 tests passent (`pytest -q`) |
| Tests de contrat runtime | 11/11 passent (`pnpm test:runtime`) |

### Méthode de vérification

La vérification combine une analyse statique et une exécution dynamique du code réellement livré dans l’XPI :

1. Sélection du dernier XPI dans `purify-sdk/versions-built/` (`0.8.8.0`).
2. Extraction de `background/background.bundle.js`.
3. Extraction du module webpack `./dist/background/plugin-handler.js`, qui contient le vrai `handleMessage` de PuryFi.
4. Exécution de ce module dans Node avec un état d’extension simulé :
   - `PluginIntents` et `StateAccess` sont chargés depuis le SDK réellement embarqué dans l’XPI ;
   - les réponses, la sémantique de `setState` et les permissions d’intents sont testées sur le code livré.
5. Instanciation de la vraie classe de connexion PuryFi pour vérifier :
   - le contenu de la frame `ready` ;
   - l’ignorance des messages plugin avant `isReady`.
6. Comparaison avec le paquet npm `@pury-fi/plugin-sdk@1.0.0` et avec le clone local `purify-sdk/`.

Limite : l’extension n’est pas lancée dans Firefox/Chromium et le handler est exécuté avec des dépendances mockées. Ce n’est donc pas un test d’intégration navigateur complet, mais c’est bien le code du runtime 0.8.8.0 qui est exécuté pour les handlers testés.

---

## 3. Matrice de conformité

| Aspect | SDK / runtime PuryFi | Implémentation Puryfier | Statut |
| --- | --- | --- | --- |
| Transport | msgpack sur WebSocket | `server/src/realtime/protocol.py` | ✅ |
| Enveloppe RPC | `{type, payload, responseId}` | `server/src/realtime/connection.py` | ✅ |
| Enveloppe réponse | `{payload, responseId}` sans `type` | `connection.py` | ✅ |
| Corrélation des réponses | via `responseId` | `connection.py` | ✅ |
| `ready` | version, `apiVersion`, `instanceId` | métadonnées conservées | ✅ |
| Compatibilité API | `[1.0.0, 2.0.0)` | `_accept_ready()` + tests | ✅ |
| `setPluginManifest` | 5 champs nullables | manifest complet | ✅ |
| `setPluginConfiguration` | configuration utilisateur | envoyé, `configurationChange` géré | ✅ |
| `getPluginManifest` / `getPluginConfiguration` | disponibles | non utilisés | ✅ sous-ensemble |
| `requestPluginIntents` | requête + `intentsGrant` | implémenté | ✅ |
| `getPendingPluginIntents` | disponible | non utilisé | ✅ sous-ensemble |
| `getState` | chemins d’état | `user.username` uniquement | ✅ sous-ensemble |
| `setState` | `enabled`, `lockConfiguration` | payload complet | ✅ |
| `subscribeToState` / `stateChange` | disponible | non utilisé | ✅ sous-ensemble |
| `subscribeToStaticMediaScans` | requis `readMediaProcesses` | implémenté | ✅ |
| `staticMediaScan` | `{objects}` | traité sans I/O bloquante | ✅ |
| `scanStaticMedia` / `censorStaticMedia` | disponible | non utilisé | ✅ sous-ensemble |
| Media censor hooks | disponible dans 0.8.8.0 | non utilisé | ✅ sous-ensemble |
| `enterLockPassword` | requis `writeLockConfigurationState` | implémenté | ✅ |
| `enterLockEmergencyServerToken` | disponible | non utilisé | ✅ sous-ensemble |
| Erreurs RPC | `error` (runtime) / `name` (SDK) | les deux acceptés | ✅ |
| Erreur `ready` | `name` (`incompatibleApiVersion`) | `name` utilisé | ✅ |
| Readiness / intents | messages protégés après grant | queue durable + garde | ✅ |

---

## 4. Corrections apportées depuis la première revue

### 4.1 Readiness et intents

**Avant :** les handlers de lock envoyaient directement sur une connexion acceptée mais pas encore `ready` ou sans intents, ce qui pouvait perdre la commande.

**Maintenant :**

- `_queue_and_flush()` persiste toujours les commandes avant toute tentative de livraison (`server/src/domain/use_cases/lock_events.py:21-61`).
- La livraison n’est tentée que si `connection.ready` et `connection.intents_granted` sont vrais (`lock_events.py:47-55`).
- `PuryfiConnection` expose explicitement `ready`, `intents_granted` et `flush_queue()` (`server/src/domain/ports.py:106-128`).
- `flush_queue()` vérifie `can_send_protected` et sérialise les drains avec `_drain_lock` (`server/src/realtime/connection.py:130-133`, `:572-608`).
- `intentsGrant` déclenche un drain immédiat (`connection.py:361-372`).
- Les handlers retournent `*_queued_not_ready` au lieu de prétendre que la commande a été appliquée (`lock_events.py:125-132`, `:188-195`).

Tests associés : `server/tests/test_lock_frozen.py`, `server/tests/test_lock_unfrozen.py`.

### 4.2 Clé d’erreur

**Avant :** `outbound.py` lisait `res.get("name")`, alors que PuryFi 0.8.8.0 renvoie `{ "type": "error", "error": "missingPluginIntents", ... }`.

**Maintenant :**

- `_error_name()` lit `error` puis `name` (`server/src/workers/outbound.py:13-24`).
- `MISSING_INTENTS_ERRORS` accepte `missingPluginIntents` et `missingIntents` (`outbound.py:13`).
- Les erreurs `ConnectionError` / `TimeoutError` sont gérées sans perdre la queue (`outbound.py:73-103`).

Tests associés : `server/tests/test_connection.py:597-620`.

### 4.3 `lockConfiguration`

**Avant :** le serveur n’envoyait que `password`, ce qui effaçait `timer` et `timerPlus` dans PuryFi.

**Maintenant :**

```python
"value": {
    "password": {"secret": generated_password},
    "timer": None,
    "timerPlus": None,
}
```

Référence : `server/src/domain/use_cases/lock_events.py:100-116`.

Le payload correspond au `WriteOnlyValue<"lockConfiguration">` du SDK et au comportement réel du runtime 0.8.8.0, qui remplace l’objet complet.

Tests associés : `server/tests/test_lock_frozen.py:79-88`, `server/tests/test_websocket.py:363-...`.

### 4.4 Version d’API

**Avant :** `ready` était toujours acquitté `ok`, sans lire `apiVersion`.

**Maintenant :**

- `_parse_api_version()` impose le format `x.y.z` (`connection.py:27-35`).
- `_accept_ready()` valide `[1.0.0, 2.0.0)` (`connection.py:398-435`).
- En cas d’incompatibilité, la réponse utilise `name: "incompatibleApiVersion"`, comme attendu par le runtime pour `ready`.
- Les métadonnées `version`, `apiVersion` et `instanceId` sont conservées pour le diagnostic.
- La réponse `ready` est envoyée **avant** le démarrage du bootstrap (`connection.py:390-396`).

Tests associés : `server/tests/test_connection.py:301-399`, `server/tests/test_websocket.py:146-164`.

### 4.5 Scans média non bloquants

**Avant :** `handle_message()` attendait les appels Chaster de `MediaScanService.record()`, ce qui bloquait la lecture des réponses RPC.

**Maintenant :**

- `staticMediaScan` appelle uniquement `MediaScanSink.record_nowait()` (`connection.py:374-388`).
- `MediaScanBatcher` agrège les scans par session et flushe par lots (`server/src/workers/media_scans.py`).
- Le batcher est injecté par le conteneur et le endpoint WebSocket (`server/src/container.py`, `server/src/api/realtime.py`).

Tests associés : `server/tests/test_media_scan.py`.

### 4.6 Enum des labels aligné sur le SDK

**Avant :** `PuryfiObjectLabel` s’arrêtait à `Hand = 25`, alors que le SDK expose aussi `Silhouette = 26` (`purify-sdk/src/core/object.ts:28`).

**Maintenant :**

- `PuryfiObjectLabel.Silhouette = 26` est présent (`server/src/domain/entities.py:42`).
- `PuryfiObjectLabel.get_name(26)` retourne `"Silhouette"` au lieu de `None`.
- Le label reste absent de `CENSORABLE_LABELS` : il ne déclenche donc aucun compte de média censuré.

Tests associés : `server/tests/test_entities.py`.

### 4.7 Version du manifest dérivée du projet

**Avant :** `manifest["version"]` était codé en dur dans `protocol.py` et devait être synchronisé manuellement avec la version du projet lors des releases.

**Maintenant :**

- `server/src/version.py` lit la version depuis `server/pyproject.toml`, source unique pour le serveur, avec repli sur les métadonnées du paquet installé.
- `server/src/realtime/protocol.py` construit le manifest avec `__version__`.
- Un test vérifie que `manifest["version"]` correspond bien à `pyproject.toml`.

Tests associés : `server/tests/test_protocol.py`.

---

## 5. Vérification dynamique du runtime 0.8.8.0

Commande :

```bash
node server/scripts/puryfi_runtime_contract.mjs
# ou
pnpm test:runtime
```

Résultat observé :

```text
PuryFi runtime: 0.8.8.0
[PASS] getState user.username retourne la valeur d'état
[PASS] setPluginManifest valide le manifest et le restitue
[PASS] setPluginConfiguration accepte une configuration vide
[PASS] erreur d'intent manquant utilise la clé 'error'
[PASS] enterLockPassword sans intent utilise aussi 'error'
[PASS] setState lockConfiguration partiel efface timer/timerPlus
[PASS] setState lockConfiguration complet conserve timer/timerPlus
[PASS] enterLockPassword valide le secret et supprime le lock
[PASS] subscribeToStaticMediaScans exige readMediaProcesses
[PASS] ready est envoyé avec apiVersion 1.0.0
[PASS] les messages du plugin sont ignorés avant isReady

Résultat: 11/11 tests passés
```

Points confirmés sur PuryFi 0.8.8.0 :

- les erreurs utilisent `error`, pas `name` ;
- `missingPluginIntents` est bien la valeur renvoyée ;
- un `setState` partiel sur `lockConfiguration` efface `timer` et `timerPlus` ;
- un payload complet les conserve ;
- `ready` est envoyé avec `apiVersion: "1.0.0"` et un `responseId` ;
- les messages du plugin sont ignorés tant que PuryFi n’a pas `isReady = true`.

---

## 6. Points résiduels

### 6.1 Configuration du plugin non persistée entre reconnexions

`Connection.configuration` démarre à `{}` et est renvoyé dans `setPluginConfiguration` à chaque connexion (`connection.py:77`, `:492-495`). Puryfier n’expose aucun champ de configuration PuryFi aujourd’hui, donc c’est sans impact. Si des champs sont ajoutés plus tard, il faudra persister la configuration reçue via `configurationChange`.

### 6.2 Ordre `enabled` → `lockConfiguration`

`lock_events.py:100-116` envoie `enabled=true` avant `lockConfiguration`. La queue garantit la livraison ordonnée et la reprise, mais si `lockConfiguration` échoue durablement, PuryFi peut rester activé sans nouveau lock. Ce n’est pas une non-conformité SDK ; c’est un risque produit à décider explicitement.

### 6.3 Timeout d’accord des intents

`initialize_plugin()` attend au maximum 30 s l’accord manuel des intents (`connection.py:110`, `:531-534`). Au-delà, le handshake est abandonné et la socket fermée. À surveiller si l’UX PuryFi demande une validation humaine lente.

### 6.4 Fonctionnalités SDK non implémentées

Non utilisées, donc sans impact sur les fonctionnalités actuelles :

- `getPluginManifest`, `getPluginConfiguration`, `getPendingPluginIntents` ;
- `subscribeToState`, `unsubscribeFromState`, `stateChange` ;
- `scanStaticMedia`, `censorStaticMedia` ;
- `subscribeToMediaCensorHooks`, `unsubscribeFromMediaCensorHooks`, `mediaCensorHookRequest` ;
- `enterLockEmergencyServerToken`.

---

## 7. Tests

### 7.1 Tests serveur

```text
189 passed
```

Les tests couvrent maintenant :

- la validation de `ready.apiVersion` et les réponses `incompatibleApiVersion` ;
- les erreurs `missingPluginIntents` avec `error` et `name` ;
- le payload complet de `lockConfiguration` ;
- la mise en queue avant `ready` / avant `intentsGrant` ;
- le traitement par lots des scans média ;
- les variantes d’erreur et les timeouts de drain ;
- l’alignement de `PuryfiObjectLabel` sur le SDK, dont `Silhouette = 26` ;
- la version du manifest dérivée de `pyproject.toml`.

### 7.2 Tests de contrat runtime

`server/scripts/puryfi_runtime_contract.mjs` exécute le vrai handler de PuryFi 0.8.8.0 avec un état d’extension simulé. Voir la section 5.

Limite : le harness dépend de `purify-sdk/versions-built/`, dossier ignoré par Git. Il est donc prévu pour une vérification locale/CI avec le XPI fourni, pas pour un build Docker de production.

---

## 8. Recommandations

1. Si des champs de configuration PuryFi sont ajoutés, persister `Connection.configuration` entre reconnexions.
2. Décider explicitement de l’ordre `enabled` / `lockConfiguration` et du comportement en cas d’échec partiel.
3. Revoir le timeout de 30 s pour l’accord manuel des intents.
4. Exécuter `pnpm test:runtime` dans la CI lorsque le XPI de référence est disponible.

---

## 9. Conclusion

Dans son état actuel, Puryfier est **compatible avec le SDK PuryFi et avec le runtime 0.8.8.0** pour les fonctionnalités qu’il utilise :

- handshake et version d’API ;
- manifest et configuration ;
- intents et permissions ;
- lecture/écriture d’état ;
- verrouillage/déverrouillage par mot de passe ;
- abonnement et traitement des scans média.

Les anciens points critiques — readiness, clé d’erreur, payload `lockConfiguration` partiel, absence de contrôle de version et blocage de la boucle de lecture — sont corrigés et couverts par des tests.

Il ne reste que des points mineurs de maintenance et des fonctionnalités SDK optionnelles non utilisées.
