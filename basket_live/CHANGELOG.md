# Journal des versions

## 0.5.0

- Nouvel onglet Historique : résultats de toute la saison courante, distincts des sept derniers jours, avec filtre Nanterre et regroupement par mois.
- Accordéons réservés aux matchs de Nanterre : comparaison des équipes par période, feuille de match des deux équipes et tous les indicateurs joueurs fournis.
- Collecte unique de `statistics` et `lineups`, à partir de 15 minutes après la fin confirmée, avec réservation durable avant appel. Cache JSON persistant par saison et match ; aucun appel à l’ouverture des accordéons.
- Import progressif des résultats anciens et de leurs statistiques uniquement les jours sans match suivi, après vérification du calendrier, avec plafond partagé de 65 sur 100 et au plus une requête par minute.
- Pagination et progression persistées, saisons découvertes via l’API, conservation des résultats suivis face aux pages V2 anciennes et absence de notifications/pronostics rétroactifs.
- Nouveaux capteurs MQTT de saison et de statistiques par match, exclus du recorder. Mettre à jour l’add-on, le package, le dashboard et ajouter la nouvelle ressource JavaScript.

## 0.4.0

- Remplacement de l'attente de 30 minutes dans Home Assistant par des échéances persistées dans l'add-on et publiées en MQTT retenu. Home Assistant reprend les fermetures échues au démarrage et à chaque minute ; acquittement uniquement après traitement.
- Reconstitution des fermetures manquantes pour les résultats de l'état 0.3.0, sans remettre à zéro leur délai.
- Rappel personnel deux heures avant les matchs sans pronostic : un groupe par personne et horaire, regroupant toutes les compétitions suivies. Les rappels traités ne sont pas recréés après redémarrage.
- Suppression ou mise à jour des rappels encore en attente après un pronostic, report ou changement d'horaire ; rattrapage après une interruption uniquement avant le début du match.
- Tags stables pour remplacer une éventuelle retransmission et priorité des rappels sur le nettoyage d'anciens lives.
- Sauvegarde immédiate des pronostics et des acquittements. Aucun appel REST SportsAPI supplémentaire.
- Mise à jour du package Home Assistant requise ; carte JavaScript et dashboard inchangés.

## 0.3.0

- Boutons Live blancs/orange dans la carte Aujourd'hui et demain (carte 1.2.0), avec choix indépendants pour Francis et Ilona et plusieurs matchs simultanés.
- Choix conservés dans l'état de l'add-on et publiés sur deux capteurs personnels ; aucun appel supplémentaire à SportsAPI et aucune limite liée à un champ texte de 255 caractères.
- Les matchs commencés restent dans la carte pour pouvoir démarrer ou arrêter leur suivi ; les pronostics conservent leur fonctionnement.
- Les choix prennent effet immédiatement en cours de match. Une désactivation ne ferme que la notification de la personne et du match concernés.
- La préférence automatique Live Nanterre reste active par défaut, avec possibilité de déroger pour un match précis.
- Migration du choix unique antérieur après confirmation MQTT ; nettoyage des choix à la fin du match et capture des destinataires avant ce nettoyage.
- Mettre à jour le package, le dashboard et la ressource JavaScript en même temps que l'add-on.

## 0.2.3

- Les connexions WebSocket ne consomment plus le quota REST et restent possibles lorsque ce quota est épuisé.
- Vérification indépendante des fins via V1 pour les matchs non terminés depuis au moins 90 minutes et sans changement depuis 10 minutes : une requête par date UTC toutes les 10 minutes au plus, partagée entre les matchs et comptée dans le quota REST essentiel.
- Budget REST partagé sans sous-plafonds par endpoint : appels de fond dans les 85 premières requêtes, confirmations de fin dans la réserve des 15 dernières. Compteurs sauvegardés avant chaque appel et remis à zéro à minuit UTC.
- Un statut V1 terminé, une correspondance unique des équipes et de l'horaire, et deux scores finaux identiques espacés de `delai_fin` sont nécessaires. Une absence de résultat ou une panne ne termine jamais un match.
- Conservation des identifiants V2 pour le dashboard, les événements, les pronostics et les Live Activities ; les fins confirmées utilisent le circuit de notification existant.
- Les quarts V2 incomplets ne sont pas présentés comme des détails définitifs lors d'une confirmation V1.

- Publication MQTT : une nouvelle valeur arrivée pendant l’envoi de la précédente reste en attente, notamment pour le passage de « en cours » à « terminé ».

## 0.2.2

- Rattrapage des matchs sans données récentes par un instantané live, même si le WebSocket reste connecté (une requête partagée toutes les 5 min au plus, dans la limite du quota).
- Le rafraîchissement manuel du calendrier récupère aussi les scores si des matchs sont actifs.
- Les mises à jour portant un horodatage source ancien ne sont plus considérées comme fraîches ; les messages antérieurs à un horodatage déjà reçu sont ignorés.
- Journalisation des instantanés live et des rattrapages ; protection contre les requêtes live simultanées.

## 0.2.1

- Nouveau barème des pronostics : 3 points pour Nanterre en Betclic Élite, 2 pour Nanterre dans une autre compétition et pour un match d'Élite sans Nanterre, 1 pour les autres.

## 0.2.0

- Concours de pronostics : un menu par match à venir et par joueur, fermé à l'entre-deux.
- Points à la fin confirmée : 2 pour un match de Nanterre, 1 pour les autres.
- Nouveaux capteurs `sensor.basket_live_pronostics` (historique de la saison) et `sensor.basket_live_classement`.
- Nouvelle option `joueurs` (par défaut : francis, ilona).

## 0.1.3

- « Nanterre 92 » raccourci en « Nanterre » dans les lives.

## 0.1.2

- Barre de progression sur le temps réglementaire : 25 % par quart-temps, pleine en prolongation.
- « JL Bourg » affiché « Bourg-en-Bresse ».

## 0.1.1

- Noms d'équipes et de compétitions raccourcis, statut court (QT1…QT4), temps joué publiés pour la Live Activity.

## 0.1.0

- Première version : calendrier, WebSocket temps réel, confirmation des fins de match, découverte MQTT.
