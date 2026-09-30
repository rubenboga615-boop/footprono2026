# Données (phase 1)

## Sources

| Source | Apporte | Fait foi pour | Accès |
|---|---|---|---|
| [football-data.co.uk](https://www.football-data.co.uk) | Résultats, mi-temps, tirs, corners, fautes, cartons, arbitre, cotes 1X2 et plus/moins 2,5 | Résultats et statistiques de match | CSV `mmz4281/<saison>/<division>.csv` |
| [Understat](https://understat.com) | xG, npxG, PPDA, deep, xPts ; calendrier des matchs à venir | Statistiques avancées | JSON `getLeagueData/<ligue>/<année>` |
| [API-Football](https://www.api-football.com) | Statistiques par équipe et **par mi-temps** : tirs (cadrés, contrés, surface), corners, fautes, hors-jeu, possession, cartons, arrêts, passes, xG | Statistiques par période (2024-25 et après) | `/fixtures` puis `/fixtures/statistics?half=true` (clé `FP_API_FOOTBALL_KEY`) |

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

## API-Football (statistiques par période)

- **Couverture vérifiée** sur les fichiers du collecteur de l'ancien projet
  (18 ligues, 2016 → 2026) : statistiques par période pour 98 à 100 % des
  matchs à partir de 2024-25. Avant 2024, API-Football fournit le match complet
  seulement (vérifié sur un match de 2016) : `ingest.sh api-football --seasons 2016-2023`.
- **Conventions vérifiées contre football-data** (5 ligues-saisons) : un
  compteur absent vaut 0 (cartons rouges « vides » = 0 dans 99,9 % des cas) ;
  une mesure absente (possession, passes, xG) reste inconnue ; les fautes ne
  sont jamais fournies par mi-temps. Accord avec football-data : corners 96 à
  99,9 %, tirs cadrés 96 à 99,9 %, cartons jaunes 91 à 99 % ; 1re + 2e mi-temps
  = match complet dans 99,85 % des cas.
- **xG API-Football ≠ xG Understat** : corrélation 0,86 à 0,90 mais plus bas
  d'environ 0,14 par équipe. Ils sont stockés séparément, jamais mélangés.
- **Rattachement** : par affiche dans la saison, date (±3 jours) et score
  concordants. Les barrages (équipe de division inférieure, ou affiche en
  double à une autre date) sont ignorés et comptés. Un nom d'équipe inconnu
  qui joue toute la saison rejette le fichier. Les noms API-Football (169, dont
  4 équipes orthographiées de deux façons selon les saisons) sont dans le
  référentiel, dérivés automatiquement en appariant les matchs à football-data.
- **Téléchargement** : seuls les matchs terminés de la saison régulière sans
  statistiques en base sont demandés. Budget par fichier (`FP_API_FOOTBALL_BUDGET`,
  1 500) et petite réserve quotidienne de sécurité
  (`FP_API_FOOTBALL_MIN_REMAINING`, 200 ; elle était de 3 100 tant que
  l'ancien archiveur de cotes partageait la clé) ; fenêtre d'une minute respectée.
  Une clé refusée arrête tout sans relance ; clé absente = source signalée
  indisponible.
- **Calendrier à venir** (phase 3) : la liste de la saison, déjà téléchargée
  pour les statistiques, sert aussi aux matchs non joués, sans requête de
  plus : coup d'envoi exact en UTC (`kickoff_at`), statut API-Football
  (`api_status` : NS à venir, PST reporté, CANC annulé…) et arbitre désigné.
  Un match à venir prend la date d'API-Football (reports, horaires télévisés),
  sauf s'il est reporté sans nouvelle date ; Understat ne l'écrase plus
  ensuite. Un match reporté, annulé ou arrêté n'est pas prédit.
- **Cotes des matchs à venir** (`footprono-ingest odds`, tâche `collect_odds`
  à 07:30 et 16:30 UTC) : bookmakers de `FP_ODDS_BOOKMAKERS` (défaut 1xBet,
  Bet365, Pinnacle ; Pinnacle sert de référence interne et n'est pas
  affiché). Table `bookmaker_odds` : chaque cote gardée telle que publiée
  (nom du pari, libellé), une ligne ajoutée seulement quand la cote change,
  historique jamais écrasé ; réponse brute archivée. Traduction vers les
  marchés du moteur à la lecture (`map_bet`) pour les paris dont le sens est
  certain ; le handicap asiatique attend une vérification sur cotes réelles.
  Un bookmaker absent du service est signalé, jamais remplacé en silence.
  Coût : 2 requêtes par championnat et par bookmaker environ (≈ 30 par relevé).
- **Suivi en direct** (`footprono-ingest live`, tâche `follow_live` toutes les
  2 minutes) : pour les matchs dans leur fenêtre (coup d'envoi − 5 min à
  + 3 h 30), une requête `/fixtures?ids=` (20 matchs par requête) met à jour
  statut, minute et score (`live_*`). Dès la fin : score final et mi-temps
  enregistrés comme **provisoires** (`result_source = api_football`), puis
  `/fixtures/statistics?half=true` (corners, cartons, tirs par période),
  redemandées jusqu'à 8 h après le coup d'envoi si pas encore publiées.
  Aucune requête sans match en cours. Le lendemain, football-data confirme
  (`result_source = football_data`) ; un score provisoire différent est
  signalé dans le rapport d'ingestion puis remplacé, et une ligne
  football-data sans résultat ne remet jamais « à venir » un match joué.
- **Compositions et blessés** (table `match_team_sheets`, dernière version
  conservée telle que publiée) : les compositions arrivent avec la réponse du
  suivi en direct (matchs de l'heure qui vient, un passage toutes les
  10 minutes tant qu'elles manquent), les blessés et suspendus avec la tâche
  des cotes (`/injuries`, 1 requête par championnat pour aujourd'hui et
  demain). **Affichage seulement** : le moteur ne s'en sert pas tant qu'un
  modèle de la valeur des joueurs n'a pas prouvé son apport en backtest.
  API : `GET /matches/{id}/team-sheets`.
- API-Football ne dépend que de football-data pour la saison : il se charge
  après lui (ordre de `all` et de la tâche quotidienne).

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
| Stats API-Football (ou découpage par mi-temps) pour moins de 98 % des matchs joués, saisons 2024+ | avertissement |
| 1re + 2e mi-temps ≠ match complet (corners, jaunes) pour plus de 1 % des lignes | avertissement |
| Corners API-Football = football-data pour moins de 95 % des matchs | avertissement |

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
| Rennes - PSG le 23/08/2026, Ligue 1 2026-27 | Rennes 2-2 PSG | PSG 0-0 Rennes | **Résolu** : API-Football donne aussi Rennes 2-2 PSG (2-0 à la mi-temps) ; Understat est en erreur |

Contradictions relevées par API-Football (statistiques de ces matchs non chargées) :

| Match | football-data | API-Football | Explication |
|---|---|---|---|
| Bastia - Lyon, Ligue 1 2016-17 | 0-3 | 0-0 | Match arrêté à la mi-temps (incidents), perdu sur tapis vert |
| Hellas Verona - Roma, Serie A 2020-21 | 0-0 | 3-0 | Perdu sur tapis vert par la Roma ; ici football-data garde le score joué |
| Union Berlin - Bochum, Bundesliga 2024-25 | 0-2 | 1-1 | Perdu sur tapis vert (score officiel ≠ score joué) |

football-data ne suit donc pas une convention unique pour les matchs sur tapis
vert. À traiter en phase 2 : ces 4 matchs (avec Sassuolo - Pescara) doivent
être exclus de l'apprentissage des buts, leurs statistiques ne décrivant pas le
score retenu.

## Validation du téléchargement réel (téléphone, 29/09/2026)

`ingest.sh all` sur Termux : 110 fichiers sur 110 téléchargés et chargés
(football-data et Understat, 5 ligues, 2016-17 → 2026-27). Qualité : 0 erreur,
2 avertissements — Ligue 1 2019-20 (saison arrêtée, déclarée) et Ligue 1
2026-27 (xG pour 97,8 % des matchs joués : le match Rennes - PSG en conflit
entre sources n'a pas de xG rattachés, voir ci-dessus).

## Points à confirmer

- ~~Hypothèse~~ **Vérifié (29/09/2026)** : l'absence de statistiques API-Football
  avant 2024-25 dans les fichiers du collecteur venait du paramètre `half=true`.
  Hull - Leicester (13/08/2016, fixture 17696) : réponse vide avec `half=true`,
  statistiques du match complet sans. Le téléchargement de FootProno demande les
  saisons antérieures à 2024 sans `half` : match complet seulement, pas de
  découpage par mi-temps.

- Convention des colonnes de cotes football-data (moment exact de collecte
  des cotes « pré-match ») et fuseau horaire de l'heure de coup d'envoi.

## Commandes

```bash
footprono-ingest all                                   # téléchargement 2016 → saison en cours
footprono-ingest all --seasons 2026                    # saison en cours seulement
footprono-ingest football-data --from-dir <dossier>    # import local : <dossier>/<2425>/<E0>.csv
footprono-ingest understat --from-dir <dossier>        # import local : <dossier>/<2024>/<EPL>/{matches,team_matches}.csv
footprono-ingest api-football                          # téléchargement 2024 → saison en cours (clé requise)
footprono-ingest api-football --from-dir <dossier>     # fichiers du collecteur : <dossier>/<39>/<2024>.json
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
| `GET /api/v1/matches/{id}` | Détail : statistiques, xG, statistiques par équipe et par mi-temps, cotes |
| `GET /api/v1/ingestion/runs`, `/ingestion/runs/{id}` | Journal des ingestions et rapports |
| `GET /api/v1/data/quality` | Contrôles de qualité recalculés |

Les routes d'ingestion seront réservées aux administrateurs à l'arrivée des
comptes (phase 5).
