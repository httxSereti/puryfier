# Roadmap fonctionnelle — Puryfier

> Propositions de fonctionnalités classées par valeur produit / effort.
> Base actuelle : verrouillage/déverrouillage PuryFi sur freeze/unfreeze Chaster,
> pénalité de temps sur médias censurés, statut temps réel, lien PuryFi.
>
> Date : 29 octobre 2026

---

## 1. Résumé

| Priorité | Fonctionnalité | SDK utilisé | Effort | Impact |
| --- | --- | --- | --- | --- |
| 1 | Pénalités pondérées par label | `staticMediaScan` | 4-6 j | ⭐⭐⭐⭐ |
| 2 | Diagnostic de liaison et permissions | `getPluginManifest`, `getPluginConfiguration`, `getPendingPluginIntents` | 2-3 j | ⭐⭐⭐⭐ |
| 3 | PuryFi Guard — surveillance et réconciliation d’état | `subscribeToState`, `stateChange`, `getState` | 5-8 j | ⭐⭐⭐⭐⭐ |
| 4 | Journal d’activité / audit | données existantes + `stateChange` | 4-6 j | ⭐⭐⭐ |
| 5 | Rotation / révocation du lien PuryFi | — | 2-3 j | ⭐⭐⭐ |
| 6 | Déverrouillage temporaire par le keyholder | `enterLockPassword`, `setState` | 5-7 j | ⭐⭐⭐⭐ |
| 7 | Récupération d’urgence | `enterLockEmergencyServerToken` | 2 j | ⭐⭐ |
| 8 | Test d’image dans la configuration | `scanStaticMedia`, `censorStaticMedia` | 8-12 j | ⭐⭐ |
| — | Hooks de censure personnalisée | `subscribeToMediaCensorHooks` | 8-12 j | ⭐ |

---

## 2. Fonctionnalités prioritaires

### 2.1 Pénalités pondérées par label

**Problème actuel**

Une image contenant au moins un objet censorable compte pour **1**, quel que soit le label. Une image avec des organes génitaux et une image avec un pectoral comptent pareil. Le seuil et le temps ajouté sont globaux.

**Proposition**

Utiliser les objets envoyés par PuryFi (`label`, `score`) pour calculer des **points** au lieu d’un simple compteur d’images :

```json
{
  "enabled": true,
  "limit_count": 10,
  "added_duration": 600,
  "min_score": 0.5,
  "label_weights": {
    "2": 1,
    "4": 1,
    "6": 2,
    "9": 2,
    "19": 2,
    "23": 1
  },
  "max_penalties_per_day": 5,
  "cooldown_seconds": 300
}
```

- `label_weights` : points par label PuryFi (`2 = Buttocks`, `4 = FemaleBreast`, `6 = FemaleGenitals`, `9 = MaleGenitals`, `19 = Anus`, `23 = Nipple`).
- `min_score` : ignore les détections peu fiables.
- `max_penalties_per_day` : évite les pénalités runaway.
- `cooldown_seconds` : évite qu’une même image scannée plusieurs fois déclenche plusieurs pénalités en rafale.
- Le seuil `limit_count` devient un seuil de **points**, pas d’images.

**Implémentation**

- Backend : étendre `CensorPicsConfigSchema` (`server/src/domain/entities.py`).
- `MediaScanBatcher` et `MediaScanService` : agréger des points au lieu d’un compteur booléen.
- Nouveau compteur/journal par label et par jour.
- Front : matrice de labels dans `CensoredMediaOptions.tsx`, avec noms lisibles, poids, score minimum, plafond et cooldown.
- Migration : poids par défaut = 1 pour tous les labels censorables, pour conserver le comportement actuel.
- Tests : labels, score sous le seuil, cooldown, plafond journalier, migration.

**SDK :** aucun nouvel intent. On utilise uniquement `staticMediaScan.objects[]`.

**Pourquoi c’est rentable :** c’est la fonctionnalité la plus directement liée au cœur du produit, sans nouvelle permission PuryFi.

---

### 2.2 Diagnostic de liaison et permissions

**Problème actuel**

L’utilisateur voit seulement « Online / Offline ». Si un intent manque, si la configuration PuryFi n’est pas celle attendue ou si le manifest est périmé, il n’a aucun diagnostic actionnable.

**Proposition**

Ajouter une carte « Connection health » avec :

- version PuryFi (`ready.version`) ;
- version du plugin (`manifest.version`) ;
- `instanceId` PuryFi ;
- intents accordés :
  - `readUserState` ✅ ;
  - `writeLockConfigurationState` ✅ ;
  - `writeEnabledState` ✅ ;
  - `readMediaProcesses` ✅ ;
- intents manquants ou en attente ;
- dernière connexion / dernière activité ;
- bouton **Request missing permissions**.

**Implémentation**

- À la connexion, appeler :
  - `getPluginManifest` ;
  - `getPluginConfiguration` ;
  - `getPluginIntents` ;
  - `getPendingPluginIntents`.
- Stocker ces informations dans `Connection` et les exposer dans le statut temps réel.
- Ajouter un endpoint ou un message WebSocket pour re-demander les intents manquants :
  `requestPluginIntents`.
- Front : carte de diagnostic sur `Configuration.tsx` et/ou `Session.tsx`.
- Régénérer `server/openapi.json` et `front/src/types/api.generated.ts` si le DTO change.

**SDK :** `getPluginManifest`, `getPluginConfiguration`, `getPendingPluginIntents` — aucun intent supplémentaire pour les lectures.

**Effort :** 2-3 jours.

**Impact :** réduit fortement le support (« pourquoi PuryFi est offline ? », « pourquoi les scans ne remontent pas ? »).

---

### 2.3 PuryFi Guard — surveillance et réconciliation d’état

**Problème actuel**

Puryfier pousse son état vers PuryFi quand Chaster déclenche un événement, mais il ne sait pas si l’utilisateur a **désactivé PuryFi manuellement** ou supprimé son lock PuryFi pendant que le lock Chaster est encore gelé.

**Proposition**

Un mode optionnel « PuryFi Guard » :

1. Au handshake, lire l’état actuel :
   - `enabled` ;
   - `lockConfiguration` (sans le secret du mot de passe, qui est no-read).
2. S’abonner aux changements :
   - `subscribeToState` sur `enabled` ;
   - `subscribeToState` sur `lockConfiguration`.
3. Recevoir `stateChange` et comparer à l’état attendu :
   - Chaster gelé + `lock_on_freeze` → PuryFi doit être activé et avoir un lock.
   - Chaster dégelé + `unlock_on_unfreeze` → PuryFi doit être désactivé.
4. Selon la configuration :
   - **notify** : journaliser et notifier le keyholder ;
   - **strict** : réappliquer l’état avec `setState`.

**Implémentation**

- Ajouter les intents `readEnabledState` et `readLockConfigurationState` (uniquement si Guard est activé, pour limiter les permissions).
- Ajouter un handler `stateChange` dans `Connection.handle_message`.
- Stocker l’état attendu et le dernier état observé.
- Ajouter un debounce/anti-boucle : ne pas réappliquer immédiatement un `stateChange` causé par notre propre `setState`.
- Ajouter un statut UI : « Protégé », « Modifié manuellement », « Lock PuryFi absent ».
- Tests : désactivation manuelle, suppression du lock, réconciliation, anti-boucle.

**SDK :** `subscribeToState`, `unsubscribeFromState`, `stateChange`, `getState` ; intents `readEnabledState`, `readLockConfigurationState`.

**Effort :** 5-8 jours.

**Risque :** ne pas transformer Puryfier en « police » qui empêche l’utilisateur de reprendre la main. Prévoir un mode notify par défaut et un mode strict explicite.

**Impact :** très forte valeur pour l’intégrité du lock Chaster.

---

### 2.4 Journal d’activité / audit

**Problème actuel**

Le keyholder voit le temps ajouté, mais pas l’historique : combien d’images, quels labels, quand, pourquoi, avec quelle version de PuryFi.

**Proposition**

Un journal par session :

- connexion / déconnexion PuryFi ;
- freeze / unfreeze Chaster ;
- lock PuryFi appliqué / échec ;
- lot de médias censurés : nombre d’images, labels, points, temps ajouté ;
- changements de permissions ;
- erreurs de livraison de queue.

**Implémentation**

- Collection MongoDB `session_events` avec TTL (30/90 jours).
- Endpoint paginé `GET /api/session/{main_token}/events`.
- Affichage timeline dans `Session.tsx`.
- Ne jamais stocker d’image, d’URL ni de secret ; uniquement des compteurs et labels.
- Tests : pagination, TTL, absence de fuite de secrets.

**SDK :** données déjà disponibles via `staticMediaScan` et `ready` ; `stateChange` si Guard est activé.

**Effort :** 4-6 jours.

**Impact :** confiance, transparence, support.

---

### 2.5 Rotation / révocation du lien PuryFi

**Problème actuel**

Le `link_token` PuryFi est permanent. S’il fuite, il n’y a pas de rotation ni de révocation directe.

**Proposition**

- Bouton « Régénérer le lien PuryFi ».
- Fermeture de la connexion active et invalidation de l’ancien token.
- Affichage de la date de création / dernière utilisation.
- Confirmation explicite : PuryFi devra être re-lié avec la nouvelle URL.

**Implémentation**

- Endpoint `POST /api/session/{main_token}/link-token/rotate`.
- `MongoLockSessionRepository.rotate_link_token`.
- `ConnectionManager.close_by_user_link_token` pour fermer l’ancienne socket.
- Front : bouton dans `PuryfiConnection` / `LinkTokenModal`.

**Effort :** 2-3 jours.

**Impact :** sécurité.

---

### 2.6 Déverrouillage temporaire par le keyholder

**Problème actuel**

Le keyholder ne peut pas autoriser une courte pause PuryFi sans déverrouiller complètement Chaster.

**Proposition**

- Le keyholder choisit une durée (5 min, 15 min, 1 h).
- Puryfier déverrouille PuryFi (`enterLockPassword`) et le désactive.
- À expiration, Puryfier re-verrouille et réactive PuryFi.
- Le timer doit survivre à un redémarrage du serveur (stockage MongoDB + worker).
- Audit et limite de durée.

**Implémentation**

- Collection `temporary_unlocks` avec `expires_at`.
- Worker périodique pour re-lock.
- Endpoints keyholder-only : créer / annuler / lister.
- Front : bouton + countdown.
- Tests : expiration, redémarrage, annulation, double exécution.

**SDK :** `enterLockPassword`, `setState enabled/lockConfiguration`.

**Effort :** 5-7 jours.

**Impact :** gameplay/contrôle ; fonctionnalité différenciante.

---

## 3. Fonctionnalités optionnelles

### 3.1 Récupération d’urgence

- Formulaire keyholder pour saisir un `emergencyServerToken`.
- Appel `enterLockEmergencyServerToken`.
- Audit, rate-limit, ne jamais logger le token.
- Utile si le mot de passe stocké est perdu ou si le lock PuryFi a été modifié hors Puryfier.
- **Effort :** 2 jours.
- **Risque :** sécurité ; à réserver au keyholder et à documenter.

### 3.2 Test d’image dans la configuration

- Upload d’une image de test.
- `scanStaticMedia` pour afficher les labels détectés et les points qui seraient comptés.
- `censorStaticMedia` pour prévisualiser la censure.
- **Effort :** 8-12 jours (transport binaire, endpoint, UI, privacy).
- **Intérêt :** pédagogique, mais pas essentiel au lock.

### 3.3 Affichage du profil PuryFi

- Stocker `user.username` et `user.supportTier` (déjà récupérés via `getState user.username`).
- Afficher un badge « PuryFi : pseudo » dans la session.
- **Effort :** 1 jour.
- **Intérêt :** confiance/identification.

---

## 4. À éviter pour l’instant

### 4.1 Hooks de censure personnalisée

`subscribeToMediaCensorHooks` / `mediaCensorHookRequest` permettent de modifier chaque image avant/après la censure PuryFi. C’est séduisant, mais :

- PuryFi attend la réponse du plugin pendant la navigation ;
- un serveur distant ajoute de la latence sur chaque image ;
- les images peuvent être nombreuses et volumineuses ;
- une panne Puryfier dégraderait la censure PuryFi elle-même.

À réserver à un plugin local ou à un usage très spécifique (watermark, censure custom). Pas prioritaire pour Puryfier.

### 4.2 `scanStaticMedia` / `censorStaticMedia` comme cœur de produit

PuryFi fait déjà l’inférence côté navigateur. Dupliquer le scan côté serveur ajoute de la charge, de la latence et des dépendances image/ML sans bénéfice direct pour le lock Chaster.

---

## 5. Ordre recommandé

### Étape 1 — Quick wins (1 semaine)

1. Diagnostic de liaison et permissions.
2. Affichage du profil PuryFi / dernière activité.
3. Rotation du lien PuryFi.

### Étape 2 — Cœur gameplay (1-2 semaines)

4. Pénalités pondérées par label.
5. Plafond journalier + cooldown.

### Étape 3 — Intégrité et confiance (1-2 semaines)

6. PuryFi Guard (notify puis strict).
7. Journal d’activité.

### Étape 4 — Contrôle avancé (2 semaines)

8. Déverrouillage temporaire keyholder.
9. Récupération d’urgence.

### Plus tard

10. Test d’image.
11. Hooks de censure personnalisée, uniquement si un besoin local émerge.

---

## 6. Critères de succès

- Aucun nouveau intent sans justification produit claire.
- Toute fonctionnalité qui ajoute un intent doit être optionnelle et expliquer pourquoi.
- Les fonctionnalités de contrôle (Guard, unlock temporaire) doivent avoir un mode « notify » avant le mode « enforce ».
- Les secrets (mot de passe, token d’urgence, link token) ne doivent jamais apparaître dans les logs ou les événements d’audit.
- Chaque fonctionnalité doit avoir des tests de contrat avec le runtime PuryFi de `purify-sdk/versions-built/`.
