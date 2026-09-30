// Formats français : « 150 582 F CFA », « 41 % », « 1,85 », « Sam. 10 oct. ».

const nbsp = '\u00A0';

String currencyLabel(String code) => switch (code) {
  'XOF' || 'XAF' => 'F${nbsp}CFA',
  _ => code,
};

/// Entier avec espaces insécables entre les milliers : 150582 → « 150 582 ».
String thousands(num value) {
  final negative = value < 0;
  final digits = value.abs().floor().toString();
  final out = StringBuffer();
  for (var i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) out.write(nbsp);
    out.write(digits[i]);
  }
  return '${negative ? '−' : ''}$out';
}

String money(num value, [String currency = 'XOF']) => '${thousands(value)}$nbsp${currencyLabel(currency)}';

/// Montant signé d'un mouvement : « +5 000 F CFA ».
String signedMoney(num value, [String currency = 'XOF']) =>
    '${value > 0 ? '+' : ''}${money(value, currency)}';

/// Probabilité 0-1 → « 41 % » (« < 1 % » pour les très petites).
String percent(double p, {int decimals = 0}) {
  final v = p * 100;
  if (v > 0 && v < 1 && decimals == 0) return '<${nbsp}1$nbsp%';
  return '${v.toStringAsFixed(decimals).replaceAll('.', ',')}$nbsp%';
}

/// Cote ou nombre décimal à la française : 1.850 → « 1,85 ».
String decimal(Object? value, {int max = 2}) {
  final d = value is num ? value.toDouble() : double.tryParse('$value') ?? 0;
  var s = d.toStringAsFixed(max);
  if (s.contains('.')) {
    s = s.replaceFirst(RegExp(r'0+$'), '');
    if (s.endsWith('.')) s = '${s}0';
  }
  return s.replaceAll('.', ',');
}

/// Cote à deux décimales : « 1,60 ».
String odds(Object? value) {
  final d = value is num ? value.toDouble() : double.tryParse('$value') ?? 0;
  return d.toStringAsFixed(2).replaceAll('.', ',');
}

/// Ligne d'un marché : « 2.5 » → « 2,5 », « -0.25 » → « −0,25 ».
String lineLabel(String line, {bool signed = false}) {
  final v = double.tryParse(line);
  if (v == null) return line;
  final body = decimal(v.abs());
  if (v < 0) return '−$body';
  return signed && v > 0 ? '+$body' : body;
}

const _days = ['Lun.', 'Mar.', 'Mer.', 'Jeu.', 'Ven.', 'Sam.', 'Dim.'];
const _daysLong = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'];
const _months = [
  'janv.',
  'févr.',
  'mars',
  'avr.',
  'mai',
  'juin',
  'juil.',
  'août',
  'sept.',
  'oct.',
  'nov.',
  'déc.',
];
const _monthsLong = [
  'janvier',
  'février',
  'mars',
  'avril',
  'mai',
  'juin',
  'juillet',
  'août',
  'septembre',
  'octobre',
  'novembre',
  'décembre',
];

/// « Sam. 10 oct. »
String shortDate(DateTime d) => '${_days[d.weekday - 1]} ${d.day} ${_months[d.month - 1]}';

/// « Samedi 10 octobre »
String longDate(DateTime d) => '${_daysLong[d.weekday - 1]} ${d.day} ${_monthsLong[d.month - 1]}';

/// « 10/10/2026 »
String numericDate(DateTime d) =>
    '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')}/${d.year}';

/// « 21:00 »
String hourMinute(DateTime d) =>
    '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';

/// « 10/10/2026 à 21:00 » (heure locale du téléphone).
String dateTime(DateTime d) {
  final l = d.toLocal();
  return '${numericDate(l)} à ${hourMinute(l)}';
}

DateTime? parseDate(Object? v) => v == null ? null : DateTime.tryParse('$v');

/// Code court d'une équipe à partir de son nom : « Manchester United » → « MUN ».
String teamCode(String name) {
  final words = name.replaceAll(RegExp(r"[^A-Za-zÀ-ÿ ]"), ' ').split(' ').where((w) => w.length > 1).toList();
  if (words.isEmpty) return name.substring(0, name.length.clamp(0, 3)).toUpperCase();
  final main = words.first;
  final code = words.length == 1
      ? main.substring(0, main.length.clamp(0, 3))
      : main.substring(0, 1) + words[1].substring(0, words[1].length.clamp(0, 2));
  return code.toUpperCase();
}
