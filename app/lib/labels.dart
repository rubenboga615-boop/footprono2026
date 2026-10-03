// Libellés français des marchés du moteur (« marché|ligne|sélection »).
import 'format.dart';

/// Marchés gratuits (le serveur fait foi : /me renvoie la liste à jour).
const defaultFreeMarkets = {'1X2', 'OU', 'BTTS'};

class MarketGroup {
  const MarketGroup(this.title, this.markets);
  final String title;
  final List<String> markets;
}

/// Ordre d'affichage des marchés, regroupés.
const marketGroups = [
  MarketGroup('Résultat', ['1X2', 'DC', 'DNB']),
  MarketGroup('Buts', [
    'OU',
    'BTTS',
    'TEAM_OU_HOME',
    'TEAM_OU_AWAY',
    'ODD_EVEN',
    'CLEAN_SHEET',
    'WIN_TO_NIL',
  ]),
  MarketGroup('Scores', ['CS', 'MARGIN']),
  MarketGroup('Handicaps', ['AH', 'EH']),
  MarketGroup('Combinés', ['1X2_OU', '1X2_BTTS', 'OU_BTTS']),
  MarketGroup('Mi-temps', ['HT_1X2', 'HT_OU', 'HT_BTTS', 'HTFT', 'HIGHEST_HALF']),
  MarketGroup('Corners', [
    'CORNERS_OU',
    'CORNERS_TEAM_OU_HOME',
    'CORNERS_TEAM_OU_AWAY',
    'CORNERS_1X2',
    'CORNERS_AH',
  ]),
  MarketGroup('Cartons', [
    'CARDS_OU',
    'CARDS_TEAM_OU_HOME',
    'CARDS_TEAM_OU_AWAY',
    'CARDS_1X2',
    'BOOKING_POINTS_OU',
  ]),
  MarketGroup('Tirs', ['SHOTS_OU', 'SHOTS_TEAM_OU_HOME', 'SHOTS_TEAM_OU_AWAY', 'SHOTS_1X2']),
  MarketGroup('Tirs cadrés', ['SOT_OU', 'SOT_TEAM_OU_HOME', 'SOT_TEAM_OU_AWAY', 'SOT_1X2']),
];

const _stats = {
  'CORNERS': ('corners', 'corner'),
  'CARDS': ('cartons', 'carton'),
  'SHOTS': ('tirs', 'tir'),
  'SOT': ('tirs cadrés', 'tir cadré'),
};

/// Titre d'un marché (« Plus/moins de buts »).
String marketTitle(String market, {String home = 'Domicile', String away = 'Extérieur'}) {
  switch (market) {
    case '1X2':
      return 'Résultat du match';
    case 'DC':
      return 'Double chance';
    case 'DNB':
      return 'Remboursé si match nul';
    case 'OU':
      return 'Plus/moins de buts';
    case 'BTTS':
      return 'Les deux équipes marquent';
    case 'TEAM_OU_HOME':
      return 'Buts de $home';
    case 'TEAM_OU_AWAY':
      return 'Buts de $away';
    case 'ODD_EVEN':
      return 'Total de buts pair ou impair';
    case 'CLEAN_SHEET':
      return 'Sans encaisser de but';
    case 'WIN_TO_NIL':
      return 'Victoire sans encaisser de but';
    case 'CS':
      return 'Score exact';
    case 'MARGIN':
      return 'Écart de buts';
    case 'AH':
      return 'Handicap asiatique';
    case 'EH':
      return 'Handicap européen';
    case '1X2_OU':
      return 'Résultat et plus/moins de buts';
    case '1X2_BTTS':
      return 'Résultat et les deux marquent';
    case 'OU_BTTS':
      return 'Plus/moins de buts et les deux marquent';
    case 'HT_1X2':
      return 'Résultat à la mi-temps';
    case 'HT_OU':
      return 'Buts en 1re mi-temps';
    case 'HT_BTTS':
      return 'Les deux marquent en 1re mi-temps';
    case 'HTFT':
      return 'Mi-temps / fin de match';
    case 'HIGHEST_HALF':
      return 'Mi-temps la plus prolifique';
    case 'BOOKING_POINTS_OU':
      return 'Points de cartons (jaune 10, rouge 25)';
  }
  for (final e in _stats.entries) {
    if (!market.startsWith('${e.key}_')) continue;
    final rest = market.substring(e.key.length + 1);
    final name = e.value.$1;
    return switch (rest) {
      'OU' => 'Total de $name',
      'TEAM_OU_HOME' => '${_cap(name)} de $home',
      'TEAM_OU_AWAY' => '${_cap(name)} de $away',
      '1X2' => 'Plus de $name',
      'AH' => 'Handicap $name',
      _ => market,
    };
  }
  return market;
}

String _cap(String s) => s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);

String _plural(String line, String one, String many) {
  final v = double.tryParse(line) ?? 2;
  return v < 2 ? one : many;
}

String _side(String s, String home, String away) => switch (s) {
  'home' => home,
  'away' => away,
  'draw' => 'Nul',
  _ => s,
};

String _ou(String sel, String line, String one, String many) =>
    '${sel == 'over' ? 'Plus' : 'Moins'} de ${lineLabel(line)} ${_plural(line, one, many)}';

/// Libellé d'une sélection, avec le nom des équipes.
String selectionLabel(
  String market,
  String line,
  String sel, {
  String home = 'Domicile',
  String away = 'Extérieur',
}) {
  switch (market) {
    case '1X2':
      return sel == 'draw' ? 'Match nul' : 'Victoire ${_side(sel, home, away)}';
    case 'DC':
      return switch (sel) {
        '1X' => '$home ou nul',
        'X2' => 'Nul ou $away',
        '12' => '$home ou $away',
        _ => sel,
      };
    case 'DNB':
      return _side(sel, home, away);
    case 'OU':
      return _ou(sel, line, 'but', 'buts');
    case 'TEAM_OU_HOME':
    case 'TEAM_OU_AWAY':
      return _ou(sel, line, 'but', 'buts');
    case 'BTTS':
      return sel == 'yes' ? 'Oui, les deux marquent' : 'Non';
    case 'ODD_EVEN':
      return sel == 'even' ? 'Pair' : 'Impair';
    case 'CLEAN_SHEET':
      return switch (sel) {
        'home' => '$home n\'encaisse pas de but',
        'away' => '$away n\'encaisse pas de but',
        'home_no' => '$home encaisse au moins un but',
        'away_no' => '$away encaisse au moins un but',
        _ => sel,
      };
    case 'WIN_TO_NIL':
      return '${_side(sel, home, away)} gagne sans encaisser';
    case 'CS':
      return sel == 'other' ? 'Autre score' : sel;
    case 'MARGIN':
      if (sel == 'draw') return 'Match nul';
      final parts = sel.split('+');
      final n = int.tryParse(parts.last) ?? 1;
      final team = _side(parts.first, home, away);
      return n >= 4 ? '$team de 4 buts ou plus' : '$team de $n but${n > 1 ? 's' : ''}';
    case 'AH':
      // Ligne exprimée côté domicile ; l'extérieur a la ligne opposée.
      final v = double.tryParse(line) ?? 0;
      final l = sel == 'home' ? v : -v;
      return '${_side(sel, home, away)} (${lineLabel('$l', signed: true)})';
    case 'EH':
      final v = double.tryParse(line) ?? 0;
      final h = lineLabel('$v', signed: true);
      return switch (sel) {
        'home' => '$home ($h)',
        'away' => '$away (${lineLabel('${-v}', signed: true)})',
        _ => 'Nul avec handicap ($h)',
      };
    case '1X2_OU':
    case '1X2_BTTS':
    case 'OU_BTTS':
      final parts = sel.split('/');
      final a = parts.first;
      final b = parts.length > 1 ? parts[1] : '';
      final first = market == 'OU_BTTS'
          ? _ou(a, line, 'but', 'buts')
          : (a == 'draw' ? 'Nul' : 'Victoire ${_side(a, home, away)}');
      final second = switch (market) {
        '1X2_OU' => _ou(b, line, 'but', 'buts').toLowerCase(),
        _ => b == 'yes' ? 'les deux marquent' : 'pas les deux',
      };
      return '$first et $second';
    case 'HT_1X2':
      return sel == 'draw' ? 'Nul à la mi-temps' : '${_side(sel, home, away)} mène à la mi-temps';
    case 'HT_OU':
      return _ou(sel, line, 'but', 'buts');
    case 'HT_BTTS':
      return sel == 'yes' ? 'Oui' : 'Non';
    case 'HTFT':
      final parts = sel.split('/');
      return '${_side(parts.first, home, away)} / ${_side(parts.last, home, away)}';
    case 'HIGHEST_HALF':
      return switch (sel) {
        'first' => '1re mi-temps',
        'second' => '2e mi-temps',
        _ => 'Autant de buts',
      };
    case 'BOOKING_POINTS_OU':
      return _ou(sel, line, 'point', 'points');
  }
  for (final e in _stats.entries) {
    if (!market.startsWith('${e.key}_')) continue;
    final rest = market.substring(e.key.length + 1);
    final (many, one) = e.value;
    if (rest.contains('OU')) return _ou(sel, line, one, many);
    if (rest == '1X2') return sel == 'draw' ? 'Égalité' : _side(sel, home, away);
    if (rest == 'AH') {
      final v = double.tryParse(line) ?? 0;
      final l = sel == 'home' ? v : -v;
      return '${_side(sel, home, away)} (${lineLabel('$l', signed: true)})';
    }
  }
  return sel;
}

/// Libellé complet pour un coupon ou un pari : « Plus/moins de buts · Plus de 2,5 buts ».
String fullLabel(
  String market,
  String line,
  String sel, {
  String home = 'Domicile',
  String away = 'Extérieur',
}) {
  final s = selectionLabel(market, line, sel, home: home, away: away);
  if (market == '1X2' || market == 'DC') return s;
  return '${marketTitle(market, home: home, away: away)} · $s';
}

/// Libellés des états d'un pari ou d'une sélection.
String betStatusLabel(String status, String? outcome) {
  if (status == 'open') return 'En cours';
  if (status == 'void') return 'Remboursé';
  return switch (outcome) {
    'won' => 'Gagné',
    'lost' => 'Perdu',
    'void' || 'push' => 'Remboursé',
    'partial' => 'Partiellement gagné',
    _ => outcome ?? status,
  };
}

String resultLabel(String result) => switch (result) {
  'win' || 'won' => 'Gagné',
  'partial' => 'Partiellement gagné',
  'lost' => 'Perdu',
  'half_win' => 'Demi-gagné',
  'push' => 'Remboursé',
  'half_loss' => 'Demi-perdu',
  'loss' => 'Perdu',
  'pending' || 'open' => 'En attente',
  'void' => 'Annulé',
  _ => result,
};

const competitionNames = {
  'EPL': 'Premier League',
  'LALIGA': 'Liga',
  'LA_LIGA': 'Liga',
  'BUNDESLIGA': 'Bundesliga',
  'SERIE_A': 'Serie A',
  'LIGUE_1': 'Ligue 1',
  'POR': 'Liga Portugal',
  'BEL': 'Pro League belge',
  'NED': 'Eredivisie',
  'GRE': 'Super League grecque',
  'TUR': 'Süper Lig',
  'SCO': 'Premiership écossaise',
};

String competitionName(String code) => competitionNames[code.toUpperCase()] ?? code;

const _selectionOrder = [
  'home',
  'draw',
  'away',
  '1X',
  'X2',
  '12',
  'over',
  'under',
  'yes',
  'no',
  'home_no',
  'away_no',
  'odd',
  'even',
  'first',
  'second',
  'equal',
];

/// Ordre d'affichage : ligne croissante, puis domicile / nul / extérieur, plus / moins…
int compareSelections(String lineA, String selA, String lineB, String selB) {
  final la = double.tryParse(lineA) ?? 0, lb = double.tryParse(lineB) ?? 0;
  if (la != lb) return la.compareTo(lb);
  int rank(String s) {
    final i = _selectionOrder.indexOf(s.split('/').first);
    return i < 0 ? 99 : i;
  }

  final r = rank(selA).compareTo(rank(selB));
  return r != 0 ? r : selA.compareTo(selB);
}

// --- Explications en français simple (handicaps, remboursé si nul) -------------

String _goals(int n) => n == 1 ? '1 but' : '$n buts';

/// Écart précis : « Villarreal perd de 2 buts », « match nul »…
String _margin(String team, int d) => switch (d) {
  0 => 'match nul',
  1 => '$team gagne d\'un but',
  -1 => '$team perd d\'un but',
  > 0 => '$team gagne de ${_goals(d)}',
  _ => '$team perd de ${_goals(-d)}',
};

/// Écart d'au moins k buts pour l'équipe (k peut être négatif).
String _atLeast(String team, int k) {
  if (k >= 2) return '$team gagne de ${_goals(k)} ou plus';
  if (k == 1) return '$team gagne';
  if (k == 0) return '$team gagne ou fait match nul';
  if (k == -1) return '$team gagne, fait match nul ou perd d\'un seul but';
  return '$team ne perd pas de ${_goals(-k + 1)} ou plus';
}

/// Résultat d'un handicap asiatique h pour l'équipe, selon l'écart d (buts de l'équipe − adversaire).
String _ahResult(double h, int d) {
  double part(double x) => x > 0 ? 1 : (x == 0 ? 0.5 : 0); // 1 gagné, 0,5 remboursé, 0 perdu
  final quarter = ((h * 4).round() % 2).abs() == 1;
  final v = quarter ? (part(d + h - 0.25) + part(d + h + 0.25)) / 2 : part(d + h);
  return switch (v) {
    1.0 => 'win',
    0.75 => 'half_win',
    0.5 => 'push',
    0.25 => 'half_loss',
    _ => 'loss',
  };
}

/// Une phrase qui dit quand la sélection est gagnée ; null si le libellé suffit.
String? explainSelection(
  String market,
  String line,
  String sel, {
  String home = 'Domicile',
  String away = 'Extérieur',
}) {
  final v = double.tryParse(line) ?? 0;
  if (market == 'DNB') {
    return 'Gagné si ${_side(sel, home, away)} gagne. Match nul : mise remboursée.';
  }
  if (market == 'EH') {
    // Handicap européen : la ligne s'ajoute au score du domicile, 3 issues, jamais de remboursement.
    final eh = v.round();
    if (sel == 'draw') return 'Gagné seulement si ${_margin(home, -eh)}.';
    final team = sel == 'home' ? home : away;
    final k = sel == 'home' ? 1 - eh : 1 + eh;
    return 'Gagné si ${_atLeast(team, k)}. Sinon perdu.';
  }
  if (market != 'AH') return null;
  final team = sel == 'home' ? home : away;
  final h = sel == 'home' ? v : -v; // handicap de l'équipe choisie
  final out = <String>[];
  int? winFrom;
  for (var d = -8; d <= 8; d++) {
    if (_ahResult(h, d) == 'win') {
      winFrom = d;
      break;
    }
  }
  if (winFrom != null) out.add('Gagné si ${_atLeast(team, winFrom)}.');
  for (var d = -8; d <= 8; d++) {
    final r = _ahResult(h, d);
    final text = switch (r) {
      'half_win' => 'moitié gagnée, moitié remboursée',
      'push' => 'mise remboursée',
      'half_loss' => 'moitié perdue, moitié remboursée',
      _ => null,
    };
    if (text != null) {
      final m = _margin(team, d);
      out.add('${m[0].toUpperCase()}${m.substring(1)} : $text.');
    }
  }
  out.add('Sinon perdu.');
  return out.join(' ');
}

/// Comment lire un marché (affiché sous son titre), pour ceux qui ne le connaissent pas.
String? marketHelp(String market) => switch (market) {
  'AH' =>
    'Handicap asiatique : on ajoute le chiffre au score de l\'équipe. « +1,5 » = on lui '
        'donne 1,5 but d\'avance ; « −1,5 » = elle doit gagner de 2 buts ou plus. Les lignes en '
        ',25 et ,75 partagent la mise en deux paris (moitié gagnée ou remboursée possible).',
  'EH' =>
    'Handicap européen : on ajoute le chiffre au score de l\'équipe, avec 3 issues '
        '(équipe, nul, adversaire). Jamais de remboursement.',
  'DNB' => 'Remboursé si nul : tu gagnes si l\'équipe gagne, ta mise est rendue en cas de match nul.',
  _ => null,
};
