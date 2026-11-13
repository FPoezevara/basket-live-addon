# Journal des versions

## 0.8.2

- Tous les badges sont publiés pour chaque joueur, y compris ceux sans étoile (niveau 0), pour être affichés grisés par la carte Historique 1.4.2.
- « Duelliste » devient « Heartbreaker », avec un cœur brisé pour icône ; critère inchangé.

## 0.8.1

- Badges négatifs (Judas, Malchanceux/Malchanceuse, Chat noir) regroupés à la fin de la liste de chaque joueur. Aucune autre modification ; package et carte inchangés.

## 0.8.0

- Badges du concours de pronostics, calculés sur la saison à partir de l'historique, y compris les matchs déjà joués : Lucky Streak, Ultra Nanterrien(ne), Judas, Européen(ne), Chanceux/Chanceuse, Malchanceux/Malchanceuse, Assidu(e), Sans-faute, Duelliste, Âmes sœurs, Globe-trotter, Rouleau compresseur, Visionnaire, Chat noir. Cinq paliers chacun, une icône par badge.
- Badges publiés avec le classement (`sensor.basket_live_classement`, attribut `joueurs[].badges`), affichés sous le bilan de chaque joueur dans l'onglet Pronostics, avec une fiche détaillée au toucher. Étoiles rouges pour les badges négatifs.
- Notification à la personne qui gagne une nouvelle étoile, par une échéance persistante acquittée par Home Assistant ; plusieurs étoiles gagnées ensemble sont annoncées une seule fois. Le premier calcul après installation n'annonce rien.
- Visionnaire compte à partir de l'installation : le classement Élite des deux équipes est désormais figé à la fin de chaque match.
- Nouvelle option `joueuses` (accord au féminin). Carte Historique 1.4.0 et package Home Assistant à mettre à jour.

## 0.7.2

- Commande MQTT `corriger_prono` pour corriger a posteriori le pronostic d'un joueur sur un match terminé : points, résultats et classement recalculés, correction journalisée et sauvegardée. Aucun appel SportsAPI.

## 0.7.1

- Commande MQTT `rafraichir_classements` pour relancer une fois par jour les tableaux Élite et BCL dans la marge de quota.

## 0.7.0

- Onglet Classements avec la Betclic Élite complète et la poule de Nanterre en BCL. La ligne de Nanterre est mise en évidence dans chaque tableau.
- Découverte des saisons et classement quotidien via SportsAPI Pro V2. Les deux tableaux sont mis en cache et les mises à jour sont reportées si le compteur atteint 65 requêtes sur 100.
- Ressource Historique 1.3.0 et nouvelle vue YAML Classements.

## 0.6.0

- Corrige la colonne ÉVAL : `rating` n’est plus présenté comme une évaluation basket. Calcul local de l’EFF classique à partir des statistiques complètes ; note fournisseur conservée dans les détails, champs manquants indiqués par « — ».
- Matchs à venir sur sept jours calendaires, aujourd’hui inclus. J+2 à J+6 actualisés une fois par jour, au plus une requête/minute ; progression et attente d’une heure après échec persistées. Cinq appels de calendrier supplémentaires en routine, dans le budget existant.
- Résultats des sept derniers jours enrichis des choix, succès/échecs et points personnels.
- Historique : points « Ilona X - X Francis » colorés sur la ligne de métadonnées, drapeaux français/européens, traductions des tirs et fautes, retrait de la phrase d’attente d’import.
- Publication des pronostics attachés aux résultats depuis l’historique complet, indépendamment de la limite de 50 entrées de la tuile pronostics.
- Cartes à venir 1.3.0 et historique 1.1.0 ; dashboard et ressources à mettre à jour. Package fourni avec le correctif des droits Live d’Ilona.

## 0.5.1

- Commande MQTT `tester_archive_nanterre` pour tester un seul match historique terminé de Nanterre, y compris un jour de match.
- Réutilisation prioritaire du dernier résultat local ; sinon une seule page Nanterre et sélection d’une seule rencontre de la saison. Coût maximal de trois requêtes, plafond total de 65/100 conservé.
- Collecte uniquement des ressources en attente, progression persistante et absence de notifications ou de pronostics rétroactifs.
- Aucun changement des fichiers Home Assistant.

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
