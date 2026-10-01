# Principes du projet

Ces règles viennent directement des défauts mesurés dans l'ancien projet
(voir `AUDIT_ANCIEN_PROJET.md`). Toute contribution doit les respecter ; les
tests doivent les faire respecter automatiquement quand c'est possible.

## 1. Jamais de fausse donnée

Une source indisponible (API externe, base, modèle, cache) produit une **erreur
explicite**, journalisée, avec un état contrôlé — jamais une réponse fictive.

Interdit : faux matchs quand l'API est indisponible, fausses prédictions quand le
modèle manque, données de démonstration en production, cotes inventées,
notifications fictives côté client.

Toutes les erreurs HTTP partagent une enveloppe unique :
`{"error": {"code", "message", "request_id", "details?"}}`.

## 2. Un seul moteur de features

Le vecteur d'entrée d'un modèle est produit par **une seule implémentation**,
utilisée à l'identique par l'entraînement, le backtest et la production. Test
d'acceptation obligatoire : pour tout match historique, le vecteur calculé « en
production » à la date du match est identique à celui de l'entraînement.

## 3. Causalité temporelle stricte

Une prédiction faite à l'instant *t* n'utilise que des informations disponibles
à *t* : aucun résultat du match prédit, aucune statistique post-match, aucune
cote de clôture, aucune donnée d'un autre match, aucune normalisation ou
sélection de features calculée sur le futur. Chaque feature documente sa source
et son instant de disponibilité.

## 4. Le modèle est indépendant du marché

Le modèle « sportif » n'utilise **pas de cotes** en entrée. Les cotes réelles
pré-match (horodatées, du même match) servent à afficher la probabilité du
marché et, plus tard éventuellement, à calculer une value — toujours
séparément du modèle. Aucune « value » n'est affichée sans backtest démontrant
un résultat positif avec intervalle de confiance.

## 5. Des probabilités cohérentes

Tous les marchés d'un match (1X2, double chance, over/under, BTTS, clean sheet,
score exact) dérivent d'**une même distribution de scores**. Les marchés
mi-temps dérivent d'une distribution contrainte par le score final. Aucune
incohérence mathématique entre marchés n'est tolérée (testée automatiquement).

## 6. Des probabilités calibrées et surveillées

Un modèle n'est déployé que s'il bat une référence naïve (taux historique) sur
des saisons de test jamais vues et s'il est calibré. La calibration est
surveillée en continu sur les matchs joués.

## 7. Traçabilité et reproductibilité

Données brutes horodatées, artefacts de modèles versionnés, dépendances
verrouillées, chaque prédiction enregistrée avec la version du modèle et des
données qui l'ont produite.

## 8. Les calculs sensibles restent côté serveur

Cotes des paris virtuels, soldes, règlements, droits d'accès : toujours
calculés et vérifiés par le serveur, jamais acceptés tels quels du client.
