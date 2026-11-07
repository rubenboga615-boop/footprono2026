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

class Team {
  Team(Json j) : id = j['id'] as int, name = j['name'] as String;
  final int id;
  final String name;
  String get code => teamCode(name);
}

class MatchInfo {
  MatchInfo(Json j)
    : id = j['id'] as int,
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
      referee = (j['api_referee'] ?? j['referee']) as String?;
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
