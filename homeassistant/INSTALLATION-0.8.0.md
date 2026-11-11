# Installation 0.8.0 : badges du concours

1. Mettre à jour l'add-on Basket Live en 0.8.0 (Modules complémentaires, Boutique, Rechercher des mises à jour). Vérifier dans sa configuration la nouvelle option `joueuses` (par défaut `ilona`).
2. Copier `homeassistant/packages/basket.yaml` vers `/homeassistant/packages/basket.yaml`, puis redémarrer Home Assistant (nouveau script `basket_badge_annoncer`, nouvelle branche `badge` dans `basket_notification_executer`).
3. Copier `homeassistant/www/basket-historique-card.js` vers `/homeassistant/www/`, puis passer la ressource à `/local/basket-historique-card.js?v=1.4.0` (Paramètres, Tableaux de bord, Ressources).
4. Vérifier : journal de l'add-on sans erreur, attribut `joueurs[0].badges` présent dans `sensor.basket_live_classement`, badges visibles sous les bilans de l'onglet Pronostics. Aucune notification n'est envoyée pour les étoiles déjà acquises.
