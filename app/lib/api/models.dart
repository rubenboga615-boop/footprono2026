// Données de l'API, lues à partir du JSON.
import '../format.dart';

typedef Json = Map<String, dynamic>;

double _d(Object? v) => v is num ? v.toDouble() : double.tryParse('$v') ?? 0;
double? _dn(Object? v) => v == null ? null : _d(v);

class Plan {
  Plan(Json j)
    : name = j['name'] as String? ?? 'free',
      premiumUntil = parseDate(j['premium_until']),
      daysLeft = j['days_left'] as int? ?? 0,
      freeMarkets = {...(j['free_markets'] as List? ?? const []).cast<String>()},
      price = j['premium_price'] as int? ?? 2000,
      priceCurrency = j['premium_currency'] as String? ?? 'XOF';
  final String name;
  final DateTime? premiumUntil;
  final int daysLeft;
  final Set<String> freeMarkets;
  final int price;
  final String priceCurrency;
  bool get premium => name == 'premium';
}

class Me {
  Me(Json j)
    : id = j['id'] as int,
      phone = j['phone'] as String?,
      email = j['email'] as String?,
      googleLinked = j['google_linked'] as bool? ?? false,
      hasPassword = j['has_password'] as bool? ?? true,
      displayName = j['display_name'] as String,
      country = j['country'] as String,
      currency = j['currency'] as String,
      role = j['role'] as String? ?? 'user',
      plan = Plan(j['plan'] as Json? ?? const {}),
      balance = (j['wallet'] as Json?)?['balance'] as int? ?? 0,
      lastRefill = parseDate((j['wallet'] as Json?)?['last_refill_at']),
      dailyCouponsNotifications = j['daily_coupons_notifications'] as bool? ?? true,
      betaAvailable = j['beta_available'] as bool? ?? false,
      betaSharing = j['beta_sharing'] as bool? ?? false,
      betaTester = j['beta_tester'] as int?;
  final int id;

  /// Vide pour un compte créé avec Google.
  final String? phone;
  final String? email;
  final bool googleLinked;

  /// Faux pour un compte créé avec Google (pas de connexion par numéro).
  final bool hasPassword;
  final String displayName;
  final String country;
  final String currency;
  final String role;
  final Plan plan;
  final int balance;
  final DateTime? lastRefill;

  /// Notification quotidienne « coupons du jour disponibles ».
  final bool dailyCouponsNotifications;

  /// Mode bêta : proposé pendant la période de test ; partage choisi par le joueur
  /// (« Testeur n° [betaTester] », sans nom ni numéro).
  final bool betaAvailable;
  final bool betaSharing;
  final int? betaTester;
  bool get isAdmin => role == 'admin';
}

/// Relevés du direct reçus (WebSocket, ou GET /live/feed sans WebSocket), cumulés : pour
/// chaque match, son dernier relevé (statut, minute, score, buts, cartons rouges, chances).
/// Les écrans se mettent à jour à partir d'eux, sans rien recharger (retour du 12/11/2026).
class LiveFeed {
  LiveFeed(Json j)
    : at = DateTime.tryParse('${j['at']}'),
      matches = {for (final m in (j['matches'] as List? ?? const []).cast<Json>()) m['id'] as int: m};
  LiveFeed._(this.at, this.matches);
  final DateTime? at;
  final Map<int, Json> matches;

  /// Ce relevé ajouté aux précédents ; un match déjà relevé plus récemment est gardé.
  LiveFeed merge(LiveFeed newer) {
    final out = {...matches};
    newer.matches.forEach((id, m) {
      final old = out[id];
      final a = parseDate(old?['updated_at']), b = parseDate(m['updated_at']);
      if (old == null || a == null || b == null || !b.isBefore(a)) out[id] = m;
    });
    return LiveFeed._(newer.at ?? at, out);
  }

  /// Chances du moment d'un match relevé, au format de GET /live/chances ; null si aucune
  /// (pas publiées, carton rouge…).
  Json? chancesOf(int id) {
    final m = matches[id];
    final c = m?['chances'];
    if (m == null || c is! Map || c.isEmpty) return null;
    return {'minute': m['minute'], 'extra': m['extra'], 'markets': c};
  }
}

class Team {
  Team(Json j) : id = j['id'] as int, name = j['name'] as String;
  final int id;
  final String name;
  String get code => teamCode(name);
}

class MatchInfo {
  MatchInfo(Json j)
    : json = j,
      id = j['id'] as int,
      competition = j['competition'] as String,
      date = DateTime.parse(j['match_date'] as String),
      kickoffAt = parseDate(j['kickoff_at']),
      status = j['status'] as String,
      apiStatus = j['api_status'] as String?,
      home = Team(j['home_team'] as Json),
      away = Team(j['away_team'] as Json),
      homeGoals = j['home_goals'] as int?,
      awayGoals = j['away_goals'] as int?,
      liveMinute = j['live_minute'] as int?,
      liveExtra = j['live_extra'] as int?,
      liveHome = j['live_home_goals'] as int?,
      liveAway = j['live_away_goals'] as int?,
      liveUpdatedAt = parseDate(j['live_updated_at']),
      referee = (j['api_referee'] ?? j['referee']) as String?;

  /// Données reçues, pour en faire une copie mise à jour par un relevé (``withFeed``).
  final Json json;
  final int id;
  final String competition;
  final DateTime date;
  final DateTime? kickoffAt;
  final String status;
  final String? apiStatus;
  final Team home;
  final Team away;
  final int? homeGoals;
  final int? awayGoals;
  final int? liveMinute;

  /// Temps additionnel en cours : 90+4 → 4.
  final int? liveExtra;
  final int? liveHome;
  final int? liveAway;

  /// Heure du dernier relevé du direct (« mis à jour il y a 40 s »).
  final DateTime? liveUpdatedAt;

  /// Arbitre désigné (API-Football, sinon football-data) ; absent des listes de matchs.
  final String? referee;

  static const _live = {'1H', 'HT', '2H', 'ET', 'BT', 'P', 'LIVE', 'INT'};
  static const _postponed = {'PST', 'CANC', 'ABD', 'SUSP', 'AWD', 'WO'};
  bool get isLive => _live.contains(apiStatus);
  bool get isFinished => status == 'finished';
  bool get isPostponed => _postponed.contains(apiStatus) || status == 'cancelled';

  /// Commencé (en cours ou fini) : plus de pari possible. L'heure suffit, le relevé du
  /// direct passant toutes les 2 minutes (essai du 07/11/2026 : cote ajoutée à la 78e).
  bool get started =>
      isLive || isFinished || (kickoffAt != null && !isPostponed && !now().isBefore(kickoffAt!));

  /// Ce match avec son dernier relevé du direct, s'il est plus récent que les données
  /// chargées : minute, score, statut et heure changent sans rien recharger.
  MatchInfo withFeed(LiveFeed? feed) {
    final f = feed?.matches[id];
    if (f == null) return this;
    final at = parseDate(f['updated_at']);
    final mine = liveUpdatedAt;
    if (at == null || (mine != null && at.isBefore(mine))) return this;
    final finished = f['status'] == 'finished';
    return MatchInfo({
      ...json,
      'status': f['status'] ?? status,
      'api_status': f['api_status'],
      'live_minute': f['minute'],
      'live_extra': f['extra'],
      'live_home_goals': f['home'],
      'live_away_goals': f['away'],
      'live_updated_at': f['updated_at'],
      if (f['kickoff_at'] != null) 'kickoff_at': f['kickoff_at'],
      if (finished) 'home_goals': f['home'],
      if (finished) 'away_goals': f['away'],
    });
  }

  Duration? get _late {
    final k = kickoffAt;
    if (k == null || isLive || isFinished || isPostponed) return null;
    final late = now().difference(k);
    return late.isNegative ? null : late;
  }

  /// Heure du coup d'envoi passée de moins de 10 minutes, pas encore commencé chez
  /// API-Football : « Coup d'envoi imminent » (retour du fondateur du 12/11/2026).
  bool get awaitingKickoff {
    final late = _late;
    return late != null && late < const Duration(minutes: 10);
  }

  /// Plus de 10 minutes après l'heure prévue, toujours pas commencé (Guinée – Érythrée le
  /// 12/11/2026 : 16:00 selon API-Football, 17:00 ailleurs) : « Coup d'envoi retardé (heure à
  /// confirmer) » pendant 3 heures au plus. Les paris restent fermés.
  bool get kickoffDelayed {
    final late = _late;
    return late != null && late >= const Duration(minutes: 10) && late < const Duration(hours: 3);
  }

  /// En cours, ou coup d'envoi dans les 10 minutes (ou passé et attendu) : l'écran suit les
  /// relevés du direct.
  bool get liveSoon {
    final k = kickoffAt;
    if (isLive || awaitingKickoff || kickoffDelayed) return true;
    if (k == null || isFinished || isPostponed) return false;
    final wait = k.difference(now());
    return !wait.isNegative && wait <= const Duration(minutes: 10);
  }

  /// Change à chaque relevé du direct : les parties de l'écran qui lisent leurs propres
  /// données (onglet En direct, chances) se rechargent alors.
  String get liveKey => '$apiStatus|$liveMinute|$liveExtra|$liveHome|$liveAway|$liveUpdatedAt|$status';

  /// Heure utilisée pour savoir si un match a commencé (fixée dans les tests).
  static DateTime Function() now = DateTime.now;

  /// Minute du direct : « 63' », « 45+2' », « MT », « Prol. 105' », « Tirs au but ».
  String get clock {
    final m = liveMinute == null ? '' : '$liveMinute${(liveExtra ?? 0) > 0 ? '+$liveExtra' : ''}\'';
    return switch (apiStatus) {
      'HT' => 'MT',
      'ET' => 'Prol. $m',
      'BT' => 'Pause prol.',
      'P' => 'Tirs au but',
      'INT' => 'Interrompu',
      _ => m,
    };
  }

  /// « 21:00 », « En direct 63' », « Terminé », « Reporté ».
  String get when {
    if (isLive) {
      return switch (apiStatus) {
        'HT' => 'Mi-temps',
        'ET' || 'BT' || 'P' || 'INT' => clock,
        _ => 'En direct $clock',
      };
    }
    if (isFinished) return 'Terminé';
    if (isPostponed) return 'Reporté';
    if (awaitingKickoff) return 'Coup d\'envoi imminent';
    if (kickoffDelayed) return 'Coup d\'envoi retardé';
    return kickoffAt != null ? hourMinute(kickoffAt!.toLocal()) : 'Heure à confirmer';
  }

  String? get score {
    if (isFinished && homeGoals != null) return '$homeGoals - $awayGoals';
    if (isLive && liveHome != null) return '$liveHome - $liveAway';
    return null;
  }
}

/// Buts attendus d'un côté ; null quand le pronostic n'en donne pas.
double? _xg(Json j, String side) => switch (j['expected_goals']) {
  final Json e => _d(e[side]),
  _ => null,
};

/// Probabilité d'une sélection selon le moteur.
class Prob {
  Prob(Json j)
    : market = j['market'] as String,
      line = j['line'] as String? ?? '',
      selection = j['selection'] as String,
      probability = _d(j['probability']),
      push = _d(j['push']),
      fairOdds = _dn(j['fair_odds']);
  final String market;
  final String line;
  final String selection;
  final double probability;
  final double push;
  final double? fairOdds;
  String get key => '$market|$line|$selection';
}

class Summary {
  Summary(Json j)
    : home = Prob(j['home'] as Json),
      draw = Prob(j['draw'] as Json),
      away = Prob(j['away'] as Json),
      over25 = j['over_2_5'] == null ? null : Prob(j['over_2_5'] as Json),
      btts = j['both_score'] == null ? null : Prob(j['both_score'] as Json),
      xgHome = _xg(j, 'home'),
      xgAway = _xg(j, 'away');
  final Prob home, draw, away;

  /// Absent pour les coupes d'Europe (plus/moins 2,5 buts non publié).
  final Prob? over25;

  /// Absent quand le moteur ne donne pas d'avis (championnats de niveau 2).
  final Prob? btts;

  /// Absents pour les anciens pronostics de coupe (sans modèle des buts).
  final double? xgHome, xgAway;
}

class Upcoming {
  Upcoming(Json j)
    : match = MatchInfo(j['match'] as Json),
      summary = j['prediction'] == null ? null : Summary(j['prediction'] as Json);

  /// Match sans prédiction (en direct, version ordinateur).
  Upcoming.of(this.match) : summary = null;

  /// Même prédiction, match du moment (score et minute du direct).
  Upcoming.withMatch(Upcoming u, this.match) : summary = u.summary;
  final MatchInfo match;
  final Summary? summary;
}

class Prediction {
  Prediction(Json j)
    : markets = [for (final m in j['markets'] as List) Prob(m as Json)],
      lockedMarkets = (j['locked_markets'] as List? ?? const []).cast<String>(),
      plan = j['plan'] as String? ?? 'free',
      xgHome = _xg(j, 'home'),
      xgAway = _xg(j, 'away'),
      counts = j['counts'] as Json?,
      context = j['context'] as Json?,
      engineVersion = j['engine_version'] as String,
      createdAt = parseDate(j['created_at']);
  final List<Prob> markets;
  final List<String> lockedMarkets;
  final String plan;
  final double? xgHome, xgAway;
  final Json? counts;
  final Json? context;
  final String engineVersion;
  final DateTime? createdAt;
}

/// Sélection jouable : cote réelle récente et probabilité du moteur.
class Offer {
  Offer(Json j)
    : market = j['market'] as String,
      line = j['line'] as String? ?? '',
      selection = j['selection'] as String,
      odds = _d(j['odds']),
      oddsText = '${j['odds']}',
      bookmaker = j['bookmaker'] as String,
      fetchedAt = parseDate(j['fetched_at']),
      modelProbability = _dn(j['model_probability']),
      openingOdds = _dn(j['opening_odds']),
      openedAt = parseDate(j['opened_at']),
      sourceUpdatedAt = parseDate(j['source_updated_at']),
      checkedAt = parseDate(j['checked_at']);
  final String market;
  final String line;
  final String selection;
  final double odds;
  final String oddsText;
  final String bookmaker;
  final DateTime? fetchedAt;
  final double? modelProbability;

  /// Première cote relevée pour cette sélection chez ce bookmaker.
  final double? openingOdds;
  final DateTime? openedAt;

  /// Dernière mise à jour de la cote chez la source (API-Football) ; peut être bien
  /// plus ancienne que le dernier relevé de FootProba ([checkedAt]).
  final DateTime? sourceUpdatedAt;
  final DateTime? checkedAt;
  bool get moved => openingOdds != null && (openingOdds! - odds).abs() >= 0.005;
  String get key => '$market|$line|$selection';
}

class BetSel {
  BetSel(Json j)
    : matchId = j['match_id'] as int,
      market = j['market'] as String,
      line = j['line'] as String? ?? '',
      selection = j['selection'] as String,
      odds = _d(j['odds']),
      bookmaker = j['bookmaker'] as String? ?? '',
      modelProbability = _dn(j['model_probability']),
      result = j['result'] as String? ?? 'pending',
      homeTeam = j['home_team'] as String? ?? 'Domicile',
      awayTeam = j['away_team'] as String? ?? 'Extérieur',
      kickoffAt = parseDate(j['kickoff_at']),
      state = j['state'] as String? ?? 'upcoming',
      minute = j['minute'] as int?,
      extra = j['extra'] as int?,
      now = j['now'] as String?,
      score = (j['score'] as List?)?.cast<int?>(),
      count = (j['count'] as List?)?.cast<int>(),
      countLabel = j['count_label'] as String?;
  final String homeTeam;

  /// Marché de comptage terminé : corners (cartons, tirs) domicile et extérieur, et leur nom.
  final List<int>? count;
  final String? countLabel;

  /// Suivi du match : upcoming, live (minute, score), finished (résultat bientôt noté), settled.
  final String state;
  final int? minute;

  /// Temps additionnel (« 90+4' »).
  final int? extra;

  /// En direct : résultat si le match s'arrêtait maintenant (win, loss, push, half_win…).
  final String? now;
  final List<int?>? score;
  final String awayTeam;
  final DateTime? kickoffAt;
  final int matchId;
  final String market;
  final String line;
  final String selection;
  final double odds;
  final String bookmaker;
  final double? modelProbability;
  final String result;
}

class Bet {
  Bet(Json j)
    : id = j['id'] as int,
      kind = j['kind'] as String,
      stake = j['stake'] as int,
      currency = j['currency'] as String,
      totalOdds = _d(j['total_odds']),
      potentialPayout = j['potential_payout'] as int,
      status = j['status'] as String,
      outcome = j['outcome'] as String?,
      payout = j['payout'] as int?,
      placedAt = parseDate(j['placed_at']),
      montanteStepId = j['montante_step_id'] as int?,
      selections = [for (final s in j['selections'] as List) BetSel(s as Json)];
  final int id;
  final String kind;
  final int stake;
  final String currency;
  final double totalOdds;
  final int potentialPayout;
  final String status;
  final String? outcome;
  final int? payout;
  final DateTime? placedAt;
  final int? montanteStepId;
  final List<BetSel> selections;
}

/// Une ligne du coupon (sélection choisie par l'utilisateur, pas encore jouée).
class CouponItem {
  CouponItem({required this.match, required this.offer});
  final MatchInfo match;
  final Offer offer;
  Json toJson() => {
    'match_id': match.id,
    'market': offer.market,
    'line': offer.line,
    'selection': offer.selection,
    'odds': offer.oddsText,
  };
}
