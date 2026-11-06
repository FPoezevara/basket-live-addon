# Basket Live

Add-on Home Assistant qui suit en direct les matchs de Nanterre 92 (toutes compétitions), de la Betclic Élite et des clubs français en coupe d'Europe, à partir de l'API SportsAPI Pro V2 (offre gratuite), et publie le tout dans Mosquitto par découverte MQTT.

L'add-on publie les données et conserve les choix de suivi personnels. Préférences automatiques, notifications, Live Activities et tableau de bord vivent dans Home Assistant.

## Fonctionnement

| Quand | Requête | Rôle |
|---|---|---|
| 0 h 05, et au démarrage | 2 calendriers (aujourd'hui, demain) | Sélection des matchs suivis |
| 12 h 05 et 17 h 05 | 1 calendrier | Horaires modifiés, reports |
| 15 min avant un match suivi | 1 instantané live | Scores et statuts en temps réel |
| 5 min après un « terminé » stable | 1 calendrier (pour toute la vague) | Confirmation du score final |
| Match attendu ou en cours sans données récentes, même avec WebSocket connecté | `/api/live` toutes les 5 min au plus | Rattrapage, partagé entre les matchs, soumis au quota |
| Rafraîchissement manuel | Calendriers et, si des matchs sont actifs, `/api/live` | Rattrapage immédiat (bouton limité à une fois toutes les 5 min) |
| Après 90 min et 10 min sans changement de score/statut | Calendrier V1, toutes les 10 min au plus par date UTC | Secours de fin indépendant de V2, deux résultats identiques espacés de `delai_fin` |
| WebSocket indisponible | `/api/live` toutes les 2 min | Mode secours |

Le statut « terminé » peut osciller en fin de match (observé sur Chalon - Kalev le 4 novembre 2026 : terminé, pause, terminé). Un match n'est déclaré fini qu'après `delai_fin` secondes de statut stable et confirmation par le calendrier, avec au plus trois tentatives avant de se fier aux seules données live.

Le WebSocket (connexion, abonnements et messages) ne consomme pas le quota REST et reste utilisable lorsque celui-ci est épuisé. Les vérifications V1 et V2 sont des requêtes REST et partagent le compteur local.

Le quota n'étant pas exposé par l'API, l'add-on compte ses requêtes par jour UTC et garde une réserve de 15 % pour les confirmations de fin.

## Contrat MQTT

Entités (appareil « Basket Live ») :

| Entité | État | Attributs |
|---|---|---|
| `sensor.basket_live_matchs_a_venir` | nombre de matchs aujourd'hui et demain | `matchs` |
| `sensor.basket_live_lives_en_cours` | nombre de lives (fin provisoire comprise) | `matchs` |
| `sensor.basket_live_suivis_francis` | nombre de choix manuels actifs de Francis | `joueur`, `choix` (identifiant → booléen) |
| `sensor.basket_live_suivis_ilona` | nombre de choix manuels actifs d’Ilona | `joueur`, `choix` (identifiant → booléen) |
| `sensor.basket_live_resultats` | nombre de résultats sur `historique_jours` | `matchs` |
| `sensor.basket_live_requetes_du_jour` | requêtes consommées | |
| `sensor.basket_live_dernier_calendrier` | horodatage | |
| `binary_sensor.basket_live_websocket` | connexion | |
| `button.basket_live_rafraichir_le_calendrier` | | |

Événements, non retenus, sur `basket_live/evenement` : `{"type": …, "match": {…}, "suivis": […], "exclus": […], "ts": …}`. Les destinataires sont capturés au moment de l’événement, avant le nettoyage des choix en fin de match.

| Type | Quand |
|---|---|
| `debut` | entre-deux |
| `maj` | changement de score, au plus un par `intervalle_push` et par match |
| `periode` | changement de quart-temps, pause, mi-temps, prolongation |
| `fin_provisoire` | premier statut « terminé » |
| `reprise` | « terminé » annulé par le statisticien |
| `statut` | report, annulation |
| `suivi_actif` / `suivi_arrete` | choix personnel modifié ; champ `personne` pour le destinataire concerné |
| `fin` | fin confirmée ; `tardif: true` si rattrapée plus de 4 h après l'entre-deux |

Champs utiles d'un match : `categorie` (`nanterre`, `elite`, `europe`), `titre`, `tournoi`, `score`, `resume`, `court` (« NAN 81-78 LMS »), `quarts_dom`, `quarts_ext`, `statut`, `chrono`, `temps_restant` (s), `horloge` (le chrono tourne), `debut`.

Dans les événements, le chrono est extrapolé à l'instant de l'envoi ; dans les attributs des capteurs, il est celui de la dernière donnée reçue, pour ne pas écrire dans le recorder à chaque seconde.

## Installation

1. Paramètres, Modules complémentaires, Boutique, menu ⋮, Dépôts : ajouter `https://github.com/FPoezevara/basket-live-addon`.
2. Installer « Basket Live », renseigner la clé API dans Configuration, démarrer.
3. Vérifier dans le journal : `Calendrier du … : N matchs suivis` et `Connecté à MQTT`.

## Concours de pronostics

Pour chaque match à venir et chaque joueur (option `joueurs`), l'add-on publie un menu `select` (« jeu. 18:15 · Efes - Paris », options `—`, équipe à domicile, équipe à l'extérieur ; attributs `joueur`, `debut`, `points_en_jeu`). Le menu disparaît à l'entre-deux, ce qui fige le pronostic. À la fin confirmée, un bon pronostic rapporte 3 points pour Nanterre en Betclic Élite, 2 pour Nanterre dans une autre compétition ou pour un match d'Élite sans Nanterre, 1 pour les autres.

| Entité | État | Attributs |
|---|---|---|
| `sensor.basket_live_pronostics` | matchs terminés pronostiqués de la saison | `matchs` : en cours (pronostics révélés) puis terminés, 50 au plus |
| `sensor.basket_live_classement` | joueur en tête, ou « Égalité » | `saison`, `joueurs` (`nom`, `points`, `bons`, `pronos`) |

Saison du 1er juillet au 30 juin. Les pronostics de l'autre ne sont cachés que sur le tableau de bord : HA n'a pas de droits par entité.

## Côté Home Assistant

`homeassistant/packages/basket.yaml` (préférences, lives, résultats, sélecteurs) et `homeassistant/dashboard-basket.yaml` (tableau de bord) sont la référence versionnée de ce qui est installé dans `/homeassistant`.

## Tests

```bash
pip install aiohttp aiomqtt pytest pytest-timeout amqtt
python -m pytest tests
```

`tests/test_integration.py` rejoue une fin de match contre un faux serveur SportsAPI Pro et un vrai broker MQTT (amqtt).

## Fin de match bloquée en V2

La V2 peut continuer à publier un ancien score et un statut « en cours » après la fin réelle.
À partir de 90 minutes après l'horaire prévu et de 10 minutes sans changement de score/statut, l'add-on vérifie aussi les résultats V1 par date UTC, au plus toutes les 10 minutes. Une confirmation déjà engagée est revérifiée même si la V2 se remet à changer.
Il exige une correspondance unique des deux équipes et de l'horaire (15 minutes de tolérance),
un statut V1 explicitement terminé et un score final inchangé sur deux lectures séparées
par `delai_fin`. Le nom des équipes doit correspondre après normalisation ; une ambiguïté,
un match absent ou une erreur réseau ne constitue pas une preuve de fin.
La confirmation publie le score final, retire le match des lives, calcule les pronostics et émet
l'événement `fin` avec l'identifiant V2 habituel. Le package existant affiche alors le résultat
sur le téléphone et ferme la notification après son délai de 30 minutes.
Les sources externes et le quota REST restent nécessaires à cette vérification ; aucun score
final ni aucune fin ne sont inventés si les deux API sont indisponibles ou inexploitables.

Le budget REST est partagé : avec `quota_jour: 100`, les appels de fond peuvent utiliser
les 85 premières requêtes. Les 15 restantes sont réservées aux confirmations de fin.
Une recherche V1 initiale est un appel de fond ; la seconde lecture confirmant un résultat
V1 déjà trouvé est essentielle. Il n'existe aucun sous-plafond quotidien par endpoint.
Un instantané V2 contient tous les matchs en cours ; un calendrier V1 couvre tous les matchs
de la même date. Le nombre de matchs n'est donc pas limité par le nombre d'instantanés.
Le coût est réservé et sauvegardé dans `etat.json` avant chaque appel HTTP, y compris pour
une requête qui échoue ensuite. Un redémarrage ne recharge pas le budget quotidien.
Un quota épuisé est journalisé : le WebSocket continue, mais les nouvelles vérifications
REST doivent attendre le renouvellement du quota. Les appels effectués hors de l'add-on
avec la même clé ne figurent pas dans ce compteur local ; un HTTP 429 bloque tous les
nouveaux appels REST de l'add-on jusqu'au lendemain UTC.

## Boutons Live personnels (0.3.0)

La carte `basket-a-venir-card` 1.2.0 affiche les matchs à venir et en cours, avec un bouton Live
à droite de l'heure et de la compétition : texte et contour blancs au repos, orange si le suivi
est actif. Un appui active, le suivant désactive. Chaque compte HA utilise la correspondance
`joueurs` déjà configurée pour les pronostics : Francis et Ilona ont chacun leurs choix, et peuvent
suivre plusieurs matchs en parallèle. Un compte absent de cette correspondance ne peut pas agir
sur les boutons. Cette personnalisation d'affichage n'introduit pas de droits d'accès par entité HA.

La préférence « Live des matchs de Nanterre » active les boutons Nanterre par défaut. Une action
sur un bouton est une dérogation personnelle pour cette seule rencontre, sans modifier la préférence
automatique ni le choix des autres rencontres. Les pronostics sont indépendants du suivi live.

Les commandes `basket_live/suivi/<joueur>/<id>/set` portent `ON` ou `OFF`, QoS 1, sans rétention.
L'add-on valide le joueur et le match, sauvegarde le choix avant son accusé MQTT et publie les
capteurs `sensor.basket_live_suivis_<joueur>`. L'attribut `choix` contient un booléen par identifiant :
`true` pour suivre, `false` pour exclure ce match du suivi automatique, absence pour appliquer la
préférence automatique. Le nombre de choix n'est pas limité par la longueur d'un état HA.
Aucune requête SportsAPI n'est nécessaire pour un changement de sélection.

Un choix fait en cours de match démarre immédiatement le live. L'arrêt ferme uniquement la
notification de ce match pour cette personne. À la fin, l'événement contient les destinataires
avant leur nettoyage, puis les notifications suivent le délai de fermeture existant de 30 minutes.
Les deux anciens `input_text.basket_suivi_<joueur>_id` restent seulement pour migrer le choix
unique existant ; ils sont vidés après confirmation, sans écraser un choix déjà fait avec les boutons.
Les listes déroulantes et leurs anciennes automatisations sont supprimées.

Installation : voir [homeassistant/INSTALLATION-LIVE.md](homeassistant/INSTALLATION-LIVE.md).
Tests de la carte : `node --test tests/test_card_live.cjs`.
