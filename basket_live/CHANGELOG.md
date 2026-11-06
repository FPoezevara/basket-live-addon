# Journal des versions

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
