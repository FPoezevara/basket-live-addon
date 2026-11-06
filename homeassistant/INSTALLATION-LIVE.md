# Installer les boutons Live

Cette fonctionnalité nécessite l'add-on **0.3.0**, la carte **1.2.0** et le package mis à jour.
Le dashboard conserve la correspondance des comptes Francis/Ilona déjà utilisée pour les pronostics.

1. Appliquer le patch au dépôt du Mac, puis commit et push sur GitHub.
2. Dans Home Assistant, rechercher les mises à jour puis installer Basket Live 0.3.0.
3. Copier `homeassistant/packages/basket.yaml` vers `/homeassistant/packages/basket.yaml`.
4. Copier `homeassistant/www/basket-a-venir-card.js` vers `/homeassistant/www/basket-a-venir-card.js`.
5. Dans l'éditeur de configuration brute du dashboard Basket, utiliser le fichier
   `homeassistant/dashboard-basket.yaml`. Il retire les deux listes déroulantes ; les autres cartes restent identiques.
   Si le dashboard installé a des personnalisations supplémentaires, retirer uniquement les lignes
   `input_select.basket_suivi_francis` et `input_select.basket_suivi_ilona` des cartes « Mes notifications ».
6. Modifier **la ressource existante** de la carte en `/local/basket-a-venir-card.js?v=1.2.0`, type module JavaScript.
   Ne pas créer un deuxième chargement de la même carte.
7. Vérifier la configuration Home Assistant puis redémarrer Home Assistant pour charger les nouveaux scripts
   et supprimer les anciens sélecteurs/automatisations. Recharger le dashboard (et l'application mobile si nécessaire).

Les capteurs `sensor.basket_live_suivis_francis` et `sensor.basket_live_suivis_ilona` doivent être disponibles.
Un bouton blanc signifie suivi inactif ; un bouton orange signifie suivi actif pour le compte connecté.
Il est possible d'en activer plusieurs. Les matchs commencés restent affichés et désactivables.
Le choix unique antérieur est migré automatiquement quand les capteurs et le match sont disponibles.

La préférence « Live Nanterre » est conservée. Un bouton permet de déroger à cette préférence pour un match,
sans désactiver le suivi automatique des prochains matchs. Les pronostics et le quota REST ne changent pas.
