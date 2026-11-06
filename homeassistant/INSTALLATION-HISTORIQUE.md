# Installation de l’historique — Basket Live 0.5.0

## 1. Add-on

Appliquer le patch au dépôt 0.4.0, puis publier :

```zsh
cd ~/Dev/basket-live-addon && git add -A && git commit -m "Historique saison et statistiques Nanterre" && git push
```

Dans Home Assistant, rechercher les mises à jour de la boutique des modules complémentaires et installer **Basket Live 0.5.0**. Vérifier cette version dans le journal. Ne pas désinstaller l’add-on : son stockage `/data` contient l’état et les archives persistantes.

## 2. Ressource JavaScript

Copier `homeassistant/www/basket-historique-card.js` vers `/config/www/basket-historique-card.js`.

Dans Paramètres → Tableaux de bord → menu ⋮ → Ressources, ajouter :

- URL : `/local/basket-historique-card.js?v=1.0.0`
- Type : **Module JavaScript**

Conserver la ressource `basket-a-venir-card.js` existante. Recharger complètement la page ou le cache de l’application mobile après installation.

## 3. Dashboard

Dans l’éditeur de configuration brute du dashboard Basket, ajouter à la fin de la liste `views:` la vue `title: Historique` fournie dans `homeassistant/dashboard-basket.yaml`.

Si le dashboard n’a pas été personnalisé, son contenu complet peut être remplacé par le fichier fourni. L’onglet utilise le capteur `sensor.basket_live_resultats_saison` et la carte d’en-tête déjà présente. Un identifiant de capteur personnalisé peut être renseigné dans `capteur:`.

## 4. Package et recorder

Reporter les exclusions du bloc `recorder:` de `homeassistant/packages/basket.yaml` dans votre configuration. Si le package existant n’a pas été personnalisé, remplacer `/config/packages/basket.yaml` par le fichier fourni.

Si vous avez déjà un bloc `recorder:` ailleurs, fusionner dans ce bloc les exclusions suivantes, sans créer un second bloc :

```yaml
recorder:
  exclude:
    entities:
      - sensor.basket_live_lives_en_cours
      - sensor.basket_live_resultats_saison
    entity_globs:
      - sensor.basket_live_statistiques_*
```

Conserver les autres exclusions déjà présentes. Vérifier la configuration Home Assistant puis redémarrer Home Assistant pour appliquer les exclusions.

## 5. Vérifications

- Le capteur `sensor.basket_live_resultats_saison` apparaît via MQTT et l’onglet Historique affiche la saison 2026-2027.
- Un match de Nanterre se déplie et se referme ; les autres résultats restent des lignes simples.
- Les résultats déjà présents dans l’add-on sont archivés immédiatement. Les résultats plus anciens arrivent progressivement **les jours sans match suivi seulement**, après un calendrier du jour réussi. L’état de l’import est indiqué dans la carte.
- L’import ancien s’arrête à **65 requêtes totales sur 100**, préservant 35 requêtes pour la marge et la réserve essentielle. Aucun test ou rafraîchissement manuel n’est nécessaire pour lancer l’import.
- Les nouvelles statistiques Nanterre sont collectées une fois par ressource, à partir de 15 minutes après la fin confirmée, si le budget de fond le permet. Les statistiques historiques attendent également un jour libre.
- L’ouverture des accordéons, les changements de période et d’équipe ne consomment aucune requête REST.
- Une ressource absente ou une collecte échouée/interrompue est signalée ; aucun nouvel appel automatique n’est effectué pour cette ressource. Les corrections ultérieures du fournisseur ne sont pas rechargées.

Les archives résident dans `/data/archives/<saison>/` du stockage persistant de l’add-on et sont publiées en MQTT retenu. Conserver ce stockage dans vos sauvegardes Home Assistant. Les statistiques disponibles dépendent de la couverture du fournisseur pour chaque compétition et rencontre.
