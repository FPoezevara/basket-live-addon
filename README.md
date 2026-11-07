# Basket Live

Add-on Home Assistant qui suit en direct les matchs de Nanterre 92 (toutes compétitions), de la Betclic Élite et des clubs français en coupe d'Europe, à partir de l'API SportsAPI Pro V2 (offre gratuite), et publie le tout dans Mosquitto par découverte MQTT.

L'add-on publie les données et conserve les choix de suivi personnels. Préférences automatiques, notifications, Live Activities et tableau de bord vivent dans Home Assistant.

## Fonctionnement

| Quand | Requête | Rôle |
|---|---|---|
| 0 h 05, et au démarrage | 2 calendriers (aujourd'hui, demain) | Sélection des matchs suivis |
| J+2 à J+6, une fois par jour local | 5 calendriers au total, espacés d’au moins 1 minute | Horizon aujourd’hui + six jours ; progression conservée après redémarrage |
| 12 h 05 et 17 h 05 | 1 calendrier | Horaires modifiés, reports |
| 15 min avant un match suivi | 1 instantané live | Scores et statuts en temps réel |
| 5 min après un « terminé » stable | 1 calendrier (pour toute la vague) | Confirmation du score final |
| Match attendu ou en cours sans données récentes, même avec WebSocket connecté | `/api/live` toutes les 5 min au plus | Rattrapage, partagé entre les matchs, soumis au quota |
| Rafraîchissement manuel | Calendriers et, si des matchs sont actifs, `/api/live` | Rattrapage immédiat (bouton limité à une fois toutes les 5 min) |
| Après 90 min et 10 min sans changement de score/statut | Calendrier V1, toutes les 10 min au plus par date UTC | Secours de fin indépendant de V2, deux résultats identiques espacés de `delai_fin` |
| 15 min après la fin confirmée d’un match de Nanterre | 1 appel `statistics` + 1 appel `lineups` | Collecte unique, cache permanent de saison |
| Journée sans match suivi, calendrier du jour vérifié | Pages de résultats et statistiques historiques, au plus 1 appel/minute | Import progressif, arrêté à 65 requêtes totales sur 100 |
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
| `sensor.basket_live_notifications` | nombre de tâches en attente, échéances futures comprises | `echeances` |
| `sensor.basket_live_suivis_francis` | nombre de choix manuels actifs de Francis | `joueur`, `choix` (identifiant → booléen) |
| `sensor.basket_live_suivis_ilona` | nombre de choix manuels actifs d’Ilona | `joueur`, `choix` (identifiant → booléen) |
| `sensor.basket_live_resultats` | nombre de résultats sur `historique_jours` | `matchs` |
| `sensor.basket_live_resultats_saison` | nombre de résultats de la saison | `saison`, `matchs`, `import` |
| `sensor.basket_live_statistiques_<matchId>` | nombre de ressources enregistrées (0 à 2) | `statistics`, `lineups`, réponses brutes conservées |
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

## Historique de saison et feuilles de match

L’onglet **Historique** conserve tous les résultats des compétitions suivies pour la saison courante (2026-2027 actuellement), indépendamment de la tuile des sept derniers jours. La saison suit le découpage existant des pronostics : du 1er juillet au 30 juin. Les fichiers des saisons précédentes restent conservés.

Seules les rencontres de Nanterre se déplient : comparaison des équipes par période, scores par quart-temps, feuille de match des deux équipes et indicateurs détaillés pour chaque joueur. Les zéros sont conservés ; les données absentes sont indiquées par un tiret. Les indicateurs supplémentaires fournis par l’API sont également affichés. Le tableau des joueurs défile horizontalement sur téléphone.

Les deux ressources V2 `/api/match/{matchId}/statistics` et `/api/match/{matchId}/lineups` sont demandées une seule fois chacune après la fin confirmée de Nanterre, à partir de 15 minutes après confirmation, avec au moins une minute entre les collectes. Les réponses brutes sont enregistrées sous `/data/archives/<saison>/statistiques/<matchId>.json`. L’index et la progression de l’import sont enregistrés dans `/data/archives/<saison>/index.json`. Ces fichiers utilisent le stockage persistant de l’add-on. Cliquer dans l’accordéon consulte uniquement les données MQTT locales, sans appel REST, y compris pour plusieurs utilisateurs simultanés.

Les résultats antérieurs à l’installation sont importés progressivement depuis les pages de résultats de Nanterre (toutes compétitions) et des tournois configurés (Élite et clubs français en Europe). Cet import et la collecte des statistiques anciennes attendent une journée sans match suivi, après vérification réussie du calendrier du jour. Avec le quota de 100, ils s’arrêtent dès que le compteur total atteint 65 : 20 requêtes de marge supplémentaires et 15 réservées aux opérations essentielles. Ils reprennent un autre jour libre ; l’historique peut donc rester partiel quelque temps. Les nouvelles statistiques après-match restent dans le budget de fond existant de 85 requêtes ; aucun quota additionnel n’est créé.

La réservation de chaque collecte est persistée avant l’appel. Une erreur ou une interruption incertaine ne provoque aucun nouvel essai automatique de cette ressource ; la carte l’indique. Cette règle garantit une seule tentative par ressource et par match, même après redémarrage, mais ne récupère pas les corrections publiées plus tard par le fournisseur. Les importations anciennes ne déclenchent ni notification de fin, ni attribution rétroactive de points de pronostics.

Installation détaillée : [Historique 0.5.0](homeassistant/INSTALLATION-HISTORIQUE.md). Ajouter la ressource JavaScript **module** `/local/basket-historique-card.js?v=1.0.0`, puis l’onglet prévu dans le dashboard. Les gros attributs des archives sont exclus du recorder par le package fourni ; les fichiers de l’add-on restent leur stockage durable.

### Tester un seul match historique

À partir de 0.5.1, publier `tester_archive_nanterre` sur `basket_live/commande`, sans rétention, sélectionne le match terminé de Nanterre le plus récent déjà archivé. Si aucun n’existe, une seule page de résultats Nanterre est demandée et seul son match terminé le plus récent de la saison est ajouté. Le test collecte uniquement ses ressources encore en attente, même un jour de match, à raison d’un appel par minute. Il ne déclenche aucune notification ni modification de pronostics.

Coût maximal de la commande : **3 requêtes** (une page et deux ressources), ou 0 à 2 si le match est déjà archivé. Le test exige que ce coût maximal tienne dans le plafond de 65 requêtes totales sur 100 ; il ne réessaie pas les ressources déjà enregistrées, indisponibles ou interrompues. Le match sélectionné et sa progression survivent à un redémarrage. Les imports automatiques existants conservent leur propre calendrier.

Dans Outils de développement → Actions, exécuter :

```yaml
action: mqtt.publish
data:
  topic: basket_live/commande
  payload: tester_archive_nanterre
  qos: 1
  retain: false
```

Consulter le journal `Test archive Nanterre sélectionné`, puis les deux lignes `Archive Nanterre <id> : statistics/lineups enregistre`. Attendre environ deux à quatre minutes et ouvrir la rencontre dans l’onglet Historique. Un double envoi réutilise le cache ; il ne recharge pas les statistiques.

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
l'événement `fin` avec l'identifiant V2 habituel. Le package affiche alors le résultat sur le téléphone. La fermeture 30 minutes après la fin confirmée repose sur une échéance persistante, reprise même après redémarrage.
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

La carte `basket-a-venir-card` 1.3.0 affiche les matchs à venir et en cours, avec un bouton Live
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
avant leur nettoyage, puis les notifications suivent une échéance persistante de fermeture 30 minutes après la fin confirmée.
Les deux anciens `input_text.basket_suivi_<joueur>_id` restent seulement pour migrer le choix
unique existant ; ils sont vidés après confirmation, sans écraser un choix déjà fait avec les boutons.
Les listes déroulantes et leurs anciennes automatisations sont supprimées.

Installation : voir [homeassistant/INSTALLATION-LIVE.md](homeassistant/INSTALLATION-LIVE.md).
Tests de la carte : `node --test tests/test_card_live.cjs`.

## Échéances persistantes et rappels de pronostics (0.4.0)

Chaque résultat confirmé programme une fermeture par personne à `termine_ts + 1800` dans
`etat.json`. Le nouveau capteur `sensor.basket_live_notifications` publie les tâches en MQTT
retenu. Home Assistant les relit au démarrage, à chaque changement de la file et toutes les
minutes. Une tâche échue est traitée puis acquittée sur `basket_live/notification/ack` avec
`{"cle": "..."}` (QoS 1, sans rétention). Les acquittements sont sauvegardés immédiatement.
Un redémarrage ne décale donc pas l'échéance. La mise à jour reprend aussi les fermetures
oubliées pour les résultats présents dans l'ancien état. Les notifications mobiles restent
soumises au fonctionnement normal de l'application compagnon et du téléphone.

Les rappels sont préparés à partir de deux heures avant le début, indépendamment du suivi Live.
Pour chaque joueur, les rencontres de toutes les compétitions au même horaire affiché (minute)
forment un seul groupe. Le groupe contient uniquement ses matchs sans pronostic. Exemple :
Roanne - Saint-Quentin et Cholet - Paris à 18 h donnent à 16 h un seul rappel pour Francis,
avec uniquement les rencontres qu'il n'a pas pronostiquées ; Ilona a son propre groupe.
Le rappel ouvre l'onglet Direct, où se trouvent les boutons de pronostic.

La préparation utilise l'état local des pronostics, sans requête SportsAPI. Home Assistant
revérifie les menus avant l'envoi. Tant qu'un rappel n'est pas acquitté, son contenu est mis
à jour si un pronostic est fait et il est annulé s'il ne reste aucun match. Un changement
d'horaire crée un groupe correspondant au nouvel horaire ; les rencontres reportées ou
annulées sont exclues. Une fois acquitté, un groupe personne/horaire n'est pas renvoyé,
même si un autre match est découvert au même horaire ou si un pronostic est annulé ensuite.

Si Home Assistant ou l'add-on est indisponible à H-2, un rappel est rattrapé au retour,
uniquement avant le début du match. Un tag stable par horaire permet à une retransmission
éventuelle de remplacer la notification existante. En cas d'erreur d'envoi, la tâche reste
à traiter ; un acquittement signifie que l'action Home Assistant a réussi, pas qu'une personne
a lu la notification. Le protocole évite les doublons usuels ; il ne peut pas rendre atomiques
l'envoi à un téléphone et la sauvegarde de son acquittement lors d'une coupure entre les deux.

Voir [homeassistant/INSTALLATION-NOTIFICATIONS.md](homeassistant/INSTALLATION-NOTIFICATIONS.md).

## Évolutions 0.6.0 : semaine, évaluations et pronostics

La carte des matchs à venir couvre **aujourd’hui et les six jours suivants**. Aujourd’hui et demain gardent leur cadence d’actualisation ; les cinq autres journées sont récupérées une fois par jour local et espacées d’au moins une minute. Les calendriers de routine passent ainsi de 4 à 9 requêtes par jour, hors redémarrage, rafraîchissements manuels et rattrapages. Tous les appels restent dans le compteur existant et la réserve essentielle est préservée. Une récupération lointaine échouée attend une heure avant un nouvel essai ; cette attente et les journées déjà récupérées sont persistées. Le remplissage initial des cinq jours supplémentaires prend environ cinq minutes.

La colonne ÉVAL de l’historique présentait à tort `rating`, une note fournisseur. Elle affiche désormais l’**EFF classique calculée** : points + rebonds + passes + interceptions + contres − tirs ratés − lancers francs ratés − balles perdues. Cette mesure est distincte du PIR d’EuroLeague. Le calcul utilise exclusivement les statistiques déjà en cache ; s’il manque un champ nécessaire ou si les tirs sont incohérents, la valeur reste « — ». Les valeurs négatives et les zéros sont conservés. La note `rating` reste consultable sous « Note fournisseur » dans les indicateurs détaillés.

Les résultats récents affichent sous chaque match le choix et les points de chaque personne. L’historique affiche à droite de la première ligne **Ilona X - X Francis**, en vert pour un pronostic gagné, en orange pour un pronostic perdu, et « — » neutre en l’absence de pronostic enregistré. Les données proviennent de l’historique complet persistant des pronostics, et non de la tuile limitée à 50 entrées. Un résultat ancien importé ne crée jamais de points rétroactifs. Drapeaux et traductions des tirs/fautes complètent l’affichage ; la phrase d’attente d’import est supprimée.

Installer le dashboard mis à jour et les deux ressources **module** : `/local/basket-a-venir-card.js?v=1.3.0` et `/local/basket-historique-card.js?v=1.1.0`. Le package fourni conserve le correctif des boutons Live pour Ilona. Guide : [Installation 0.6.0](homeassistant/INSTALLATION-0.6.0.md).
