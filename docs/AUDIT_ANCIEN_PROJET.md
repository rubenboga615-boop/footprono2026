# Audit de l'ancien projet (FootProno v19) — conclusions

Audit en lecture seule réalisé le 29/09/2026 sur l'archive
`footprono_project_v19_complet.zip` et les fichiers fournis séparément
(`data.zip`, `scraper.zip`, inventaire API-Football, couverture des ligues).
L'ancien code n'est **pas** repris : ce document conserve les enseignements.

Légende : **[V]** vérifié par exécution ou mesure · **[D]** déduit ·
**[C]** à confirmer.

## Constats principaux

1. **Aucun environnement documenté ne faisait tourner le produit** [V].
   Artefacts produits avec des versions incompatibles entre elles : données
   `.pkl` exigeant numpy 2, `requirements.txt` épinglant numpy 1.26, 198 modèles
   sous scikit-learn 1.8, 2 modèles EPL sérialisés avec une autre version.
2. **Écart train/service massif** [V]. Sur 750 matchs historiques reconstruits
   avec la fonction de production : 2 features sur 290 identiques au vecteur
   d'entraînement, 67 % des valeurs différentes (décalage d'un match, Elo
   périmé, features par terrain absentes à 85 %, constantes codées en dur).
3. **Cotes d'autres matchs injectées en production** [V]. Pour un même
   PSG-OM, P(OM ou nul) variait de 7 % à 93 % selon les seules cotes injectées.
4. **Cotes de clôture utilisées comme features** (Pinnacle `PSC*`) [D] : fuite
   temporelle pour une prédiction publiée avant le match. Ces colonnes
   disparaissent en 2025-26 (0 % de couverture) [V].
5. **Modèles livrés sans valeur prédictive** [V]. Sur la saison 2025-26 (jamais
   vue à l'entraînement), les 18 marchés binaires faisaient tous moins bien
   qu'une prédiction constante ; 1X2 pire que l'uniforme (log-loss 1,12–1,24
   contre 1,099). Modèles non calibrés et biaisés par `scale_pos_weight`.
6. **Marchés incohérents** [V] : |DC 1X − (P(H)+P(D))| = 12 points en moyenne,
   BTTS > Over 1.5 dans 23 % des cas, Over non monotones dans 46 % des cas.
7. **Données de démonstration servies comme réelles** [V] : faux matchs en cas
   d'échec de l'API, fausses notifications et faux abonnés dans le frontend hors
   ligne, cote des paris fournie par le client.

## Expérience contrôlée sur les cotes [V]

Même algorithme (LightGBM sans repondération), mêmes données (5 ligues),
tests hors échantillon 2024 et 2025. Log-loss 1X2 :

| Variante | 2024 | 2025 |
|---|---|---|
| Marché B365 pré-match (marge retirée) | 0,965 | 0,979 |
| Modèle sans cotes | 0,979 | 0,992 |
| Modèle avec cotes pré-match | 0,967 | 0,981 |
| Modèle avec cotes de clôture | 0,966 | — |
| Modèle avec cotes d'un autre match | 1,125 | 1,122 |
| Modèle avec cotes, cotes absentes | 1,086 | 1,080 |
| Uniforme | 1,099 | 1,099 |

- Avec cotes, le modèle reproduit le marché (50 à 67 % du gain d'importance
  vient des cotes) et s'effondre au niveau du hasard sans elles.
- Sans cotes, le modèle est propre et robuste mais moins précis que le marché.
- Backtest du modèle sans cotes contre les cotes B365 pré-match (edge > 5 %) :
  ROI −12,9 % en 2024 et −10,9 % en 2025, cote prise meilleure que la clôture
  dans moins de 50 % des cas. **Aucune value démontrée.**
- BTTS : quasiment aucun signal au-delà du taux de base, quelle que soit la
  variante.

## Décisions qui en découlent

Voir `PRINCIPES.md` : moteur de features unique, causalité temporelle stricte,
modèle sans cotes, distribution de scores unique, calibration obligatoire,
aucune fausse donnée, calculs sensibles côté serveur.

## Ressources réutilisables (à revalider)

- Données brutes football-data (18 divisions, jusqu'à 2026-27) et Understat
  (5 ligues, 2016–2026).
- Scripts de téléchargement `download_football_data` et `download_understat`.
- Inventaire de l'abonnement API-Football (plan Pro, 7 500 requêtes/jour ;
  historique de cotes limité à la saison en cours).

## Points restés à confirmer [C]

- Définition exacte et horaire de collecte des colonnes de cotes football-data
  (site inaccessible depuis l'environnement d'audit).
- Identifiants de marchés (`bet_id`) d'API-Football.
- Résultat d'un backtest de value avec la meilleure cote du marché.
