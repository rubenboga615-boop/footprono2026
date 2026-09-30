# Feuille de route

Ordre imposé par les dépendances : aucune phase ne démarre avant que la
précédente soit validée par ses critères (tests automatisés verts).

| Phase | Objet | Dépend de | Validée quand |
|---|---|---|---|
| **0 — Fondations** ✅ | Serveur d'API, config, logs, erreurs, PostgreSQL + migrations, Redis, Celery, métriques, CI, Docker, Termux | — | Lint, typage strict et tests d'intégration verts ; serveur, worker et beat réels opérationnels |
| **1 — Données** ✅ | Ingestion football-data + Understat, référentiel unique des équipes et compétitions, contrôles qualité, horodatage | 0 | Historique complet jusqu'à J-1 pour les 5 ligues, 100 % des équipes reconnues, rapports de qualité sans anomalie bloquante |
| **2 — Moteur** (terminée, voir `MOTEUR.md`) | Moteur de features unique, modèle de distribution de scores, marchés dérivés, calibration, backtest temporel | 1 | Bat le taux historique sur des saisons de test jamais vues, calibration validée, cohérence des marchés à 100 %, égalité train/service des vecteurs |
| **3 — Temps réel** | API-Football (calendrier, compositions, cotes), analyses (prédictions quotidiennes stockées et versionnées : faites en phase 2) | 2 | Vrais matchs du jour, prédictions traçables ; source en panne ⇒ erreur explicite |
| **4 — Métier** | Résultats, règlement automatique, bookmaker virtuel, coupons, montante, notifications (WebSocket, FCM) | 3 | Parcours pari → résultat → règlement → solde testé de bout en bout |
| **5 — Produit** | Comptes, rôles, abonnements, administration, application Flutter (web + APK), historique public de fiabilité | 4 | Tests de bout en bout de l'application verts |
| **6 — Production** | Serveur distant, sauvegardes, supervision, sécurité, paiement Mobile Money | 5 | Checklist production validée |

## Périmètre

- Compétitions : Premier League, La Liga, Bundesliga, Serie A, Ligue 1.
  Extension à d'autres ligues seulement après validation complète du moteur.
- La value n'est pas un objectif de la V1 : elle ne sera exposée que si un
  backtest la démontre.
