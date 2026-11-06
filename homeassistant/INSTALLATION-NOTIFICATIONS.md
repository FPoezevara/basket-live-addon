# Installer les échéances persistantes et les rappels

Prérequis : Basket Live 0.3.0 et son package installés.

1. Appliquer le patch 0.4.0 au dépôt du Mac, puis commit et push sur GitHub.
2. Dans Home Assistant, rechercher les mises à jour et installer Basket Live 0.4.0.
3. Copier le nouveau `homeassistant/packages/basket.yaml` vers `/homeassistant/packages/basket.yaml`.
4. Vérifier la configuration puis redémarrer Home Assistant. Le nouveau package remplace l'ancienne
   automatisation d'attente de 30 minutes ; ne pas garder une copie de cette ancienne automatisation.
5. Vérifier que `sensor.basket_live_notifications` est disponible. Son attribut `echeances` contient
   les fermetures prévues et les rappels en attente, pas les rappels déjà acquittés.

La carte JavaScript et le dashboard ne changent pas : rien à recopier pour ces deux fichiers.

Les fermetures échues seront reprises automatiquement, y compris pour les résultats conservés
avant la mise à jour. Home Assistant contrôle les échéances chaque minute ; la fermeture peut
survenir jusqu'à une minute après l'heure prévue, hors délais réseau et téléphone.

Francis et Ilona reçoivent chacun leurs rappels selon leurs pronostics. À 16 h, les matchs sans
pronostic qui commencent à 18 h sont regroupés dans une seule notification personnelle.
Un appui ouvre l'onglet Direct pour pronostiquer. Aucun rappel n'est envoyé après le début.
Les rappels et les fermetures ne consomment aucune requête supplémentaire dans le quota SportsAPI.
