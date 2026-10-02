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
      phone = j['phone'] as String,
      displayName = j['display_name'] as String,
      country = j['country'] as String,
      currency = j['currency'] as String,
      role = j['role'] as String? ?? 'user',
      plan = Plan(j['plan'] as Json? ?? const {}),
      balance = (j['wallet'] as Json?)?['balance'] as int? ?? 0,
      lastRefill = parseDate((j['wallet'] as Json?)?['last_refill_at']);
  final int id;
  final String phone;
  final String displayName;
  final String country;
  final String currency;
  final String role;
  final Plan plan;
  final int balance;
  final DateTime? lastRefill;
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
  final int? liveHome;
  final int? liveAway;

  /// Arbitre désigné (API-Football, sinon football-data) ; absent des listes de matchs.
  final String? referee;

  static const _live = {'1H', 'HT', '2H', 'ET', 'BT', 'P', 'LIVE', 'INT'};
  static const _postponed = {'PST', 'CANC', 'ABD', 'SUSP', 'AWD', 'WO'};
  bool get isLive => _live.contains(apiStatus);
  bool get isFinished => status == 'finished';
  bool get isPostponed => _postponed.contains(apiStatus) || status == 'cancelled';

  /// « 21:00 », « En direct 63' », « Terminé », « Reporté ».
  String get when {
    if (isLive) return apiStatus == 'HT' ? 'Mi-temps' : 'En direct ${liveMinute ?? ''}\'';
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
      over25 = Prob(j['over_2_5'] as Json),
      btts = Prob(j['both_score'] as Json),
      xgHome = _d((j['expected_goals'] as Json)['home']),
      xgAway = _d((j['expected_goals'] as Json)['away']);
  final Prob home, draw, away, over25, btts;
  final double xgHome, xgAway;
}

class Upcoming {
  Upcoming(Json j)
    : match = MatchInfo(j['match'] as Json),
      summary = j['prediction'] == null ? null : Summary(j['prediction'] as Json);
  final MatchInfo match;
  final Summary? summary;
}

class Prediction {
  Prediction(Json j)
    : markets = [for (final m in j['markets'] as List) Prob(m as Json)],
      lockedMarkets = (j['locked_markets'] as List? ?? const []).cast<String>(),
      plan = j['plan'] as String? ?? 'free',
      xgHome = _d((j['expected_goals'] as Json)['home']),
      xgAway = _d((j['expected_goals'] as Json)['away']),
      counts = j['counts'] as Json?,
      context = j['context'] as Json?,
      engineVersion = j['engine_version'] as String,
      createdAt = parseDate(j['created_at']);
  final List<Prob> markets;
  final List<String> lockedMarkets;
  final String plan;
  final double xgHome, xgAway;
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
  /// plus ancienne que le dernier relevé de FootProno ([checkedAt]).
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
      kickoffAt = parseDate(j['kickoff_at']);
  final String homeTeam;
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
