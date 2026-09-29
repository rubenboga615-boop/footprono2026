# Données (phase 1)

## Sources

| Source | Apporte | Fait foi pour | Accès |
|---|---|---|---|
| [football-data.co.uk](https://www.football-data.co.uk) | Résultats, mi-temps, tirs, corners, fautes, cartons, arbitre, cotes 1X2 et plus/moins 2,5 | Résultats et statistiques de match | CSV `mmz4281/<saison>/<division>.csv` |
| [Understat](https://understat.com) | xG, npxG, PPDA, deep, xPts ; calendrier des matchs à venir | Statistiques avancées | JSON `getLeagueData/<ligue>/<année>` |

Saisons couvertes : 2016-17 → saison en cours, pour Premier League, La Liga,
Serie A, Bundesliga et Ligue 1.

## Règles d'ingestion

- **Référentiel unique** (`ingestion/reference/teams.csv`) : 165 équipes, chacune
  avec son nom dans chaque source. Un nom inconnu **rejette tout le fichier**
  avec une erreur explicite : aucun match n'est rattaché à une mauvaise équipe
  ni ignoré en silence.
- **Fichiers bruts archivés** tels quels sous `FP_RAW_DATA_DIR`, nommés par
  empreinte SHA-256 et enregistrés dans `raw_files` : chaque match, cote ou
  statistique renvoie au fichier exact dont il provient.
- **football-data fait foi** pour les résultats. Understat complète (xG, matchs
  à venir) sans jamais écraser un résultat de football-data.
- **Contradictions entre sources signalées, jamais fusionnées** :
  - score différent → football-data conservé, écart consigné dans le rapport ;
  - rencontre Understat qui chevauche (±1 jour) un match football-data d'une
    des deux équipes (domicile/extérieur inversés, date) → non insérée, xG non
    rattachés ; si Understat était passé avant, sa rencontre est supprimée au
    passage de football-data.
- **Cotes** stockées en format long : bookmaker × marché × ligne × moment
  (`pre` avant match, `close` clôture) × sélection. Bookmakers conservés :
  B365, PS (Pinnacle), BFE, Max, Avg, BbMx, BbAv. Marchés : 1X2 et plus/moins
  2,5. Les autres (handicap asiatique, autres bookmakers) restent dans les
  fichiers bruts. Une cote ≤ 1 est rejetée et signalée.
- **Saisons arrêtées** (`INTERRUPTED_SEASONS`) : Ligue 1 2019-20 (COVID-19).
  Ses matchs non joués ont le statut `cancelled`, jamais « à venir ».
- **Idempotence** : relancer une ingestion ne crée aucun doublon.
- **Une source indisponible** donne le statut `unavailable` pour le fichier et
  `partial` pour l'exécution ; aucune donnée de remplacement n'est produite.
  Après 3 échecs consécutifs (réseau, blocage, page HTML au lieu des données),
  les fichiers restants de cette source ne sont pas tentés et le rapport le dit.
  Un fichier absent (404) ne compte pas comme un échec de la source.
- **Téléchargement** : identité de navigateur et adresses reprises de l'ancien
  téléchargeur (qui fonctionnait depuis le téléphone), pause de 1,5 s entre deux
  requêtes, 4 tentatives par fichier. La progression s'affiche fichier par fichier.

## Contrôles de qualité

Lancés après chaque ingestion (`footprono-ingest quality`, `GET /api/v1/data/quality`).

| Contrôle | Gravité |
|---|---|
| Nombre d'équipes ≠ 18 ou 20 | erreur |
| Plus de matchs que n × (n − 1) | erreur |
| Saison terminée incomplète (hors saison arrêtée déclarée) | erreur |
| Équipe sans (n − 1) matchs à domicile et à l'extérieur | erreur |
| Une équipe avec deux matchs à ±1 jour (doublon entre sources) | erreur |
| Score mi-temps > score final | erreur |
| Match annulé hors saison arrêtée | erreur |
| Match passé toujours « à venir » | erreur (saison terminée) / avertissement (saison en cours) |
| xG pour moins de 98 % des matchs joués | avertissement |
| Cotes B365 avant match pour moins de 98 % des matchs joués | avertissement |
| Marge B365 1X2 hors [1,00 ; 1,25] | avertissement |

## Résultat de l'import des données fournies (vérifié)

Import complet : 18 188 matchs joués, 1 501 à venir, 101 annulés ; 637 378
cotes ; 36 288 lignes de statistiques avancées ; 0 erreur de qualité.

Avertissements restants, tous expliqués :

- saison en cours : xG disponibles pour 78 à 87 % des matchs joués, car
  l'export Understat fourni s'arrête au 18/09/2026 alors que football-data va
  jusqu'au 20/09/2026 ;
- Ligue 1 2019-20 : 279/380 matchs joués (saison arrêtée, exception déclarée).

Contradictions entre sources relevées (conservées dans le rapport d'ingestion) :

| Match | football-data | Understat | Explication |
|---|---|---|---|
| Sassuolo - Pescara, Serie A 2016-17 | 0-3 | 2-1 | Match perdu sur tapis vert (score officiel ≠ score joué) |
| Union Berlin - Bochum, Bundesliga 2024-25 | 0-2 | 1-1 | Match perdu sur tapis vert (score officiel ≠ score joué) |
| Rennes - PSG le 23/08/2026, Ligue 1 2026-27 | Rennes 2-2 PSG | PSG 0-0 Rennes | À confirmer : sources contradictoires sur le lieu et le score |

À traiter en phase 2 : les deux matchs sur tapis vert ont des xG
correspondant au score joué et non au score officiel ; le moteur devra les
exclure de l'entraînement ou les traiter à part.

## Validation du téléchargement réel (téléphone, 29/09/2026)

`ingest.sh all` sur Termux : 110 fichiers sur 110 téléchargés et chargés
(football-data et Understat, 5 ligues, 2016-17 → 2026-27). Qualité : 0 erreur,
2 avertissements — Ligue 1 2019-20 (saison arrêtée, déclarée) et Ligue 1
2026-27 (xG pour 97,8 % des matchs joués : le match Rennes - PSG en conflit
entre sources n'a pas de xG rattachés, voir ci-dessus).

## Points à confirmer

- Convention des colonnes de cotes football-data (moment exact de collecte
  des cotes « pré-match ») et fuseau horaire de l'heure de coup d'envoi.

## Commandes

```bash
footprono-ingest all                                   # téléchargement 2016 → saison en cours
footprono-ingest all --seasons 2026                    # saison en cours seulement
footprono-ingest football-data --from-dir <dossier>    # import local : <dossier>/<2425>/<E0>.csv
footprono-ingest understat --from-dir <dossier>        # import local : <dossier>/<2024>/<EPL>/{matches,team_matches}.csv
footprono-ingest quality                               # contrôles seuls
footprono-ingest --json all ...                        # rapport complet en JSON
```

Code de sortie : 0 si tout est bon (avertissements compris), 1 sinon.

La tâche Celery `footprono.ingest_current_season` télécharge la saison en cours
chaque jour à 06:15 UTC (planifiée par `beat`).

## API de lecture

| Route | Contenu |
|---|---|
| `GET /api/v1/competitions` | Compétitions et saisons disponibles (matchs, matchs joués) |
| `GET /api/v1/competitions/{code}/seasons/{année}/teams` | Équipes d'une saison |
| `GET /api/v1/teams/{id}` | Équipe |
| `GET /api/v1/matches` | Matchs filtrés (`competition`, `season`, `team_id`, `status`, `date_from`, `date_to`), paginés (`limit` ≤ 500, `offset`) |
| `GET /api/v1/matches/{id}` | Détail : statistiques, xG, cotes |
| `GET /api/v1/ingestion/runs`, `/ingestion/runs/{id}` | Journal des ingestions et rapports |
| `GET /api/v1/data/quality` | Contrôles de qualité recalculés |

Les routes d'ingestion seront réservées aux administrateurs à l'arrivée des
comptes (phase 5).
