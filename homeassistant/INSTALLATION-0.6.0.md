# Installation de Basket Live 0.6.0

1. Appliquer `basket-live-0.6.0.patch` au dépôt 0.5.1, puis publier :

   ```zsh
   cd ~/Dev/basket-live-addon && git add -A && git commit -m "Semaine et statistiques corrigées" && git push
   ```

2. Installer la mise à jour **0.6.0** de l’add-on dans Home Assistant, sans le désinstaller. Conserver son stockage persistant contenant les archives et pronostics.
3. Copier les deux fichiers JavaScript du ZIP dans `/config/www/` : `basket-a-venir-card.js` et `basket-historique-card.js`.
4. Modifier les deux ressources existantes des tableaux de bord, de type **Module JavaScript**, vers `/local/basket-a-venir-card.js?v=1.3.0` et `/local/basket-historique-card.js?v=1.1.0`. Remplacer les URL existantes, sans ajouter de doublons. Recharger complètement le dashboard ou le cache de l’application mobile.
5. Remplacer le contenu du dashboard par `homeassistant/dashboard-basket.yaml`, ou reporter le titre « Les 7 prochains jours » et le contenu Markdown enrichi de la carte « Résultats des 7 derniers jours » si votre dashboard a été personnalisé.
6. Le package fourni conserve le correctif Live d’Ilona. S’il est déjà installé, aucun nouvel envoi du package ni redémarrage de Home Assistant n’est nécessaire pour cette évolution. Si vous le remplacez, conserver vos personnalisations et les exclusions recorder existantes, vérifier la configuration puis redémarrer Home Assistant.

## Vérification

- Attendre environ cinq minutes pour la première récupération de J+2 à J+6. Seuls les jours comportant des matchs suivis apparaissent dans la carte.
- Aujourd’hui et demain gardent leurs actualisations ; les cinq jours supplémentaires ne sont récupérés qu’une fois par jour local. La routine de calendrier passe de 4 à 9 requêtes/jour ; les rattrapages, fins et opérations manuelles restent comptés séparément dans le même quota de 100.
- Ouvrir JL Bourg - Nanterre dans Historique : la colonne ÉVAL utilise l’EFF classique calculée depuis le cache, avec « — » si les statistiques nécessaires manquent. La note 7,7 du fournisseur reste dans les indicateurs détaillés sous « Note fournisseur ». Aucun téléchargement des statistiques n’est nécessaire pour corriger l’affichage.
- Vérifier les points verts/orange dans l’historique et les résultats des pronostics sous les matchs récents. « — » signifie qu’aucun pronostic résolu n’a été enregistré ; les anciennes importations ne reçoivent pas de points rétroactifs.
- Vérifier les drapeaux, les libellés français et la disparition de la phrase d’attente d’import.

Les vérifications automatisées portent sur la logique et le rendu HTML simulé ; l’affichage final et les modèles Markdown restent à confirmer dans votre Home Assistant.
