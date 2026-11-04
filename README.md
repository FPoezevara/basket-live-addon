# Basket Live

Add-on Home Assistant qui suit en direct les matchs de Nanterre 92 (toutes compétitions), de la Betclic Élite et des clubs français en coupe d'Europe, à partir de l'API SportsAPI Pro V2 (offre gratuite), et publie le tout dans Mosquitto par découverte MQTT.

L'add-on ne fait que les données. Préférences, notifications, Live Activities et tableau de bord vivent dans Home Assistant.

## Fonctionnement

| Quand | Requête | Rôle |
|---|---|---|
| 0 h 05, et au démarrage | 2 calendriers (aujourd'hui, demain) | Sélection des matchs suivis |
| 12 h 05 et 17 h 05 | 1 calendrier | Horaires modifiés, reports |
| 15 min avant un match suivi | 1 connexion WebSocket + 1 instantané live | Scores et statuts en temps réel |
| 5 min après un « terminé » stable | 1 calendrier (pour toute la vague) | Confirmation du score final |
| WebSocket indisponible | `/api/live` toutes les 2 min | Mode secours |

Le statut « terminé » peut osciller en fin de match (observé sur Chalon - Kalev le 4 novembre 2026 : terminé, pause, terminé). Un match n'est déclaré fini qu'après `delai_fin` secondes de statut stable et confirmation par le calendrier, avec au plus trois tentatives avant de se fier aux seules données live.

Le quota n'étant pas exposé par l'API, l'add-on compte ses requêtes par jour UTC et garde une réserve de 15 % pour les confirmations de fin.

## Contrat MQTT

Entités (appareil « Basket Live ») :

| Entité | État | Attributs |
|---|---|---|
| `sensor.basket_live_matchs_a_venir` | nombre de matchs aujourd'hui et demain | `matchs` |
| `sensor.basket_live_lives_en_cours` | nombre de lives (fin provisoire comprise) | `matchs` |
| `sensor.basket_live_resultats` | nombre de résultats sur `historique_jours` | `matchs` |
| `sensor.basket_live_requetes_du_jour` | requêtes consommées | |
| `sensor.basket_live_dernier_calendrier` | horodatage | |
| `binary_sensor.basket_live_websocket` | connexion | |
| `button.basket_live_rafraichir_le_calendrier` | | |

Événements, non retenus, sur `basket_live/evenement` : `{"type": …, "match": {…}, "ts": …}`.

| Type | Quand |
|---|---|
| `debut` | entre-deux |
| `maj` | changement de score, au plus un par `intervalle_push` et par match |
| `periode` | changement de quart-temps, pause, mi-temps, prolongation |
| `fin_provisoire` | premier statut « terminé » |
| `reprise` | « terminé » annulé par le statisticien |
| `statut` | report, annulation |
| `fin` | fin confirmée ; `tardif: true` si rattrapée plus de 4 h après l'entre-deux |

Champs utiles d'un match : `categorie` (`nanterre`, `elite`, `europe`), `titre`, `tournoi`, `score`, `resume`, `court` (« NAN 81-78 LMS »), `quarts_dom`, `quarts_ext`, `statut`, `chrono`, `temps_restant` (s), `horloge` (le chrono tourne), `debut`.

Dans les événements, le chrono est extrapolé à l'instant de l'envoi ; dans les attributs des capteurs, il est celui de la dernière donnée reçue, pour ne pas écrire dans le recorder à chaque seconde.

## Installation

1. Paramètres, Modules complémentaires, Boutique, menu ⋮, Dépôts : ajouter `https://github.com/FPoezevara/basket-live-addon`.
2. Installer « Basket Live », renseigner la clé API dans Configuration, démarrer.
3. Vérifier dans le journal : `Calendrier du … : N matchs suivis` et `Connecté à MQTT`.

## Tests

```bash
pip install aiohttp aiomqtt pytest pytest-timeout amqtt
python -m pytest tests
```

`tests/test_integration.py` rejoue une fin de match contre un faux serveur SportsAPI Pro et un vrai broker MQTT (amqtt).
