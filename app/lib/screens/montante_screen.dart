import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../desktop/layout.dart';
import '../api/client.dart';
import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../main.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/maquette.dart';

String montanteStatus(String s) => switch (s) {
  'active' => 'En cours',
  'completed' => 'Réussie',
  'lost' => 'Perdue',
  'cashed_out' => 'Encaissée',
  _ => s,
};

Widget montanteTag(String s) => switch (s) {
  'completed' || 'cashed_out' => Tag.win(montanteStatus(s)),
  'lost' => Tag.loss(montanteStatus(s)),
  _ => Tag(montanteStatus(s)),
};

/// Milieu d'une fourchette, arrondi à 50 F : « 42 100 » (suivi de « environ »).
String _about(List? r) {
  if (r == null) return '—';
  final mid = ((r[0] as int) + (r[1] as int)) / 2;
  return thousands((mid / 50).round() * 50);
}

/// « 40 936 » ou « 40 936 à 43 275 ».
String _range(List? r, {String sep = ' à '}) {
  if (r == null) return '—';
  final lo = r[0] as int, hi = r[1] as int;
  return lo == hi ? thousands(lo) : '${thousands(lo)}$sep${thousands(hi)}';
}

/// Onglet Montante : la montante en cours, sinon la création d'une nouvelle ;
/// l'historique en dessous.
class MontanteListScreen extends StatefulWidget {
  const MontanteListScreen({super.key});

  @override
  State<MontanteListScreen> createState() => _MontanteListScreenState();
}

class _MontanteListScreenState extends State<MontanteListScreen> {
  Key _key = UniqueKey();
  bool creating = false;

  void _refresh() => setState(() {
    _key = UniqueKey();
    creating = false;
  });

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        bottom: false,
        child: Loader<List<Json>>(
          key: _key,
          load: () async => (await api.get('/montantes') as List).cast<Json>(),
          builder: (context, list, reload) {
            final active = list.where((m) => m['status'] == 'active').toList();
            final past = list.where((m) => m['status'] != 'active').toList();
            final current = active.isNotEmpty && !creating ? active.first : null;
            return RefreshIndicator(
              onRefresh: reload,
              child: ListView(
                padding: pagePadding(context, 26, 120, maxWidth: 1000),
                children: [
                  const OddsDownBanner(),
                  if (current != null)
                    MontanteView(montante: current, onChanged: _refresh)
                  else
                    _CreateMontante(onCreated: _refresh),
                  if (active.length > 1 || (creating && active.isNotEmpty)) ...[
                    const SectionTitle('Autres montantes en cours'),
                    for (final m in active.skip(creating ? 0 : 1)) _MontanteRow(m: m, onBack: _refresh),
                  ],
                  if (current != null) ...[
                    const SizedBox(height: 12),
                    OutlinedButton.icon(
                      onPressed: () => setState(() => creating = true),
                      icon: const Icon(Icons.add_rounded),
                      label: const Text('Nouvelle montante'),
                    ),
                  ],
                  if (past.isNotEmpty) ...[
                    const SectionTitle('Historique'),
                    for (final m in past) _MontanteRow(m: m, onBack: _refresh),
                  ],
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

class _MontanteRow extends StatelessWidget {
  const _MontanteRow({required this.m, required this.onBack});
  final Json m;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    final currency = m['currency'] as String;
    return GlassCard(
      margin: const EdgeInsets.only(bottom: 10),
      onTap: () async {
        await Navigator.of(context)
            .push(MaterialPageRoute(builder: (_) => MontanteDetailScreen(id: m['id'] as int)));
        onBack();
      },
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Montante n° ${m['id']}', style: Fp.title(15, weight: FontWeight.w600)),
                const SizedBox(height: 4),
                Text(
                  'Départ ${money(m['start_stake'] as int, currency)} · palier ${m['current_step']} '
                  'sur ${(m['steps'] as List).length}',
                  style: Fp.body(13, color: Fp.text2),
                ),
              ],
            ),
          ),
          montanteTag(m['status'] as String),
        ],
      ),
    );
  }
}

// --- Création ------------------------------------------------------------------

class _CreateMontante extends StatefulWidget {
  const _CreateMontante({required this.onCreated});
  final VoidCallback onCreated;

  @override
  State<_CreateMontante> createState() => _CreateMontanteState();
}

class _CreateMontanteState extends State<_CreateMontante> {
  final start = TextEditingController(text: thousands(5000));
  int count = 6;
  bool secureOn = false;
  int secure = 20;
  bool editRanges = false;
  bool busy = false;
  final ranges = List.generate(8, (i) => RangeValues(1.55 + 0.05 * i, 1.65 + 0.05 * i));

  /// Maquette N7 : trois choix de cotes ; plages de chaque palier en légère montée, de la
  /// première à la dernière (de, à, largeur d'une plage). Null : réglées palier par palier.
  static const presets = [(1.30, 1.45, 0.05), (1.55, 1.90, 0.10), (2.00, 2.50, 0.15)];
  int? preset = 1;

  void _apply() {
    final p = preset;
    if (p == null) return;
    final (a, b, w) = presets[p];
    final step = count > 1 ? (b - a - w) / (count - 1) : 0.0;
    double r2(double v) => (v * 100).round() / 100;
    for (var i = 0; i < count; i++) {
      ranges[i] = RangeValues(r2(a + step * i), r2(a + step * i + w));
    }
  }

  int get stake => int.tryParse(start.text.replaceAll(RegExp(r'\D'), '')) ?? 0;

  @override
  void dispose() {
    start.dispose();
    super.dispose();
  }

  Future<void> _create() async {
    final api = context.read<AppState>().api;
    setState(() => busy = true);
    try {
      await api.post('/montantes', {
        'start_stake': stake,
        'secure_pct': secureOn ? secure : 0,
        'steps': [
          for (final r in ranges.take(count))
            {'odds_min': r.start.toStringAsFixed(2), 'odds_max': r.end.toStringAsFixed(2)},
        ],
      });
      // Pas de message en bas de l'écran : il cachait la carte « Suggestions du moteur » du
      // palier 1, justement celle à toucher (essai réel du 06/11/2026). L'écran du plan suffit.
      widget.onCreated();
    } on ApiException catch (e) {
      showMessage(e.message, error: true);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final currency = context.read<AppState>().me?.currency ?? 'XOF';
    final pct = secureOn ? secure : 0;
    // Aperçu au franc près (même calcul que le serveur) : minimum et maximum.
    final rows = <(int, int, int, int)>[]; // mise min, max, gain min, max
    var lo = stake, hi = stake;
    for (final r in ranges.take(count)) {
      final gLo = (lo * r.start).floor(), gHi = (hi * r.end).floor();
      rows.add((lo, hi, gLo, gHi));
      lo = (gLo * (100 - pct) / 100).floor();
      hi = (gHi * (100 - pct) / 100).floor();
    }
    final goal = rows.isEmpty ? null : [rows.last.$3, rows.last.$4];
    // Chance d'aller au bout selon les cotes, marge du bookmaker comprise (même calcul que le
    // serveur : produit des 1/cote au milieu de chaque plage).
    var chance = 1.0;
    for (final r in ranges.take(count)) {
      chance *= 2 / (r.start + r.end);
    }
    // Ordinateur : la place ne manque pas, le plan (escalier) reste affiché.
    final desktop = DesktopScope.of(context);
    final showPlan = editRanges || desktop;
    Widget label(String text) => Padding(
      padding: const EdgeInsets.only(top: 14, bottom: 8),
      child: Text(
        text,
        style: Fp.body(13, color: Fp.muted, weight: FontWeight.w600),
      ),
    );
    Widget kv(String k, String v, {Color color = Fp.text}) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Expanded(
            child: Text(k, style: Fp.body(13.5, color: Fp.muted)),
          ),
          Text(
            v,
            style: Fp.body(15, weight: FontWeight.w700, color: color),
          ),
        ],
      ),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Maquette N7 (07/11/2026).
        const MTitle('Nouvelle', 'montante', 26),
        const SizedBox(height: 6),
        Text(
          'Tu remises tout le gain de chaque palier sur le suivant. Un pari perdu arrête la montante.',
          style: Fp.body(14, color: Fp.muted, height: 1.4),
        ),
        label('Mise de départ (argent fictif)'),
        TextField(
          controller: start,
          keyboardType: TextInputType.number,
          // « 5 000 » comme la maquette : chiffres groupés pendant la saisie.
          inputFormatters: [
            FilteringTextInputFormatter.digitsOnly,
            TextInputFormatter.withFunction((_, v) {
              final text = v.text.isEmpty ? '' : thousands(int.parse(v.text));
              return TextEditingValue(
                text: text,
                selection: TextSelection.collapsed(offset: text.length),
              );
            }),
          ],
          onChanged: (_) => setState(() {}),
          style: Fp.title(22),
          decoration: InputDecoration(
            suffixText: currencyLabel(currency),
            suffixStyle: Fp.body(13, color: Fp.muted),
            filled: true,
            fillColor: Fp.background,
            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(16),
              borderSide: const BorderSide(color: Fp.line),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(16),
              borderSide: const BorderSide(color: Fp.accent2, width: 1.5),
            ),
          ),
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final v in const [1000, 5000, 10000, 25000])
              MChip(
                thousands(v),
                selected: stake == v,
                onTap: () => setState(() => start.text = thousands(v)),
              ),
          ],
        ),
        label('Nombre de paliers'),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (var n = 4; n <= 8; n++)
              MChip(
                '$n',
                selected: count == n,
                onTap: () => setState(() {
                  count = n;
                  _apply();
                }),
              ),
          ],
        ),
        label('Cote de chaque palier'),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final (i, (a, b, _)) in presets.indexed)
              MChip(
                '${odds(a)}–${odds(b)}',
                selected: preset == i,
                onTap: () => setState(() {
                  preset = i;
                  _apply();
                }),
              ),
          ],
        ),
        const SizedBox(height: 4),
        if (!desktop)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton(
              onPressed: () => setState(() => editRanges = !editRanges),
              style: TextButton.styleFrom(padding: EdgeInsets.zero, foregroundColor: Fp.lilac),
              child: Text(
                editRanges ? 'Masquer le plan' : 'Voir le plan palier par palier ›',
                style: Fp.body(13, weight: FontWeight.w600, color: Fp.lilac),
              ),
            ),
          ),
        if (showPlan)
          MCard(
            margin: const EdgeInsets.only(top: 4),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                ..._plan(context, [
                  for (final (i, r) in rows.indexed)
                    _PlanRow(
                      number: i + 1,
                      state: _StepState.future,
                      stake: r.$1 == r.$2 ? thousands(r.$1) : '${thousands(r.$1)}\nà ${thousands(r.$2)}',
                      odds: '${odds(ranges[i].start)}–${odds(ranges[i].end)}',
                      gain: r.$3 == r.$4 ? thousands(r.$3) : '${thousands(r.$3)}\nà ${thousands(r.$4)}',
                    ),
                ]),
                const SizedBox(height: 4),
                Text('Régler la plage d\'un palier', style: Fp.body(13, color: Fp.muted)),
                for (var i = 0; i < count; i++) ...[
                  const SizedBox(height: 6),
                  Text(
                    'Palier ${i + 1} : ${odds(ranges[i].start)} – ${odds(ranges[i].end)}',
                    style: Fp.body(13, weight: FontWeight.w600),
                  ),
                  RangeSlider(
                    values: ranges[i],
                    min: 1.2,
                    max: 3.0,
                    onChanged: (v) => setState(() {
                      ranges[i] = RangeValues((v.start * 20).round() / 20, (v.end * 20).round() / 20);
                      preset = null;
                    }),
                  ),
                ],
                Text(
                  'Tout pari dont la cote est dans la plage du palier convient. Les gains à venir dépendent '
                  'des cotes réellement jouées.',
                  style: Fp.body(12.5, color: Fp.muted, height: 1.4),
                ),
              ],
            ),
          ),
        MCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (goal != null)
                kv('Objectif', goal[0] == goal[1] ? '${_range(goal)} F' : '${_about(goal)} F environ'),
              kv('Chance d\'aller au bout', _outOf100(chance).toLowerCase(), color: Fp.warning),
              const SizedBox(height: 4),
              _SecureCard(
                on: secureOn,
                pct: secure,
                onChanged: (v) => setState(() => secureOn = v),
                onPct: (v) => setState(() => secure = v),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        MButton('Lancer la montante', busy: busy, onPressed: busy || stake < 100 ? null : _create),
      ],
    );
  }
}

class _SecureCard extends StatelessWidget {
  const _SecureCard({required this.on, required this.pct, this.onChanged, this.onPct});
  final bool on;
  final int pct;
  final ValueChanged<bool>? onChanged;
  final ValueChanged<int>? onPct;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Sécuriser $pct % de chaque gain', style: Fp.body(15, weight: FontWeight.w700)),
                  const SizedBox(height: 2),
                  Text(
                    onChanged == null
                        ? 'Fixé au lancement de la montante'
                        : 'Mis de côté au lieu d\'être remisé',
                    style: Fp.body(13, color: Fp.muted),
                  ),
                ],
              ),
            ),
            // Montante lancée : réglage figé, affiché sans interrupteur inactif.
            if (onChanged != null)
              SizedBox(
                width: 46,
                height: 28,
                child: FittedBox(
                  child: Switch(
                    value: on,
                    onChanged: onChanged,
                    activeTrackColor: Fp.accent,
                    activeThumbColor: Colors.white,
                    inactiveTrackColor: const Color(0xFF3A3550),
                    inactiveThumbColor: Colors.white,
                    trackOutlineColor: const WidgetStatePropertyAll(Colors.transparent),
                  ),
                ),
              )
            else
              on ? const Tag.win('Activé') : const Tag('Désactivé', color: Fp.textSoft),
          ],
        ),
        if (on && onPct != null)
          Slider(
            value: pct.toDouble(),
            min: 5,
            max: 90,
            divisions: 17,
            label: '$pct %',
            onChanged: (v) => onPct!(v.round()),
          ),
      ],
    );
  }
}

// --- Tableau ----------------------------------------------------------------------

enum _StepState { won, lost, current, future }

/// Plan d'une montante : tableau sur téléphone, escalier sur ordinateur.
List<Widget> _plan(BuildContext context, List<_PlanRow> rows) =>
    DesktopScope.of(context) ? [_Stairs(rows)] : [const _TableHeader(), ...rows];

/// Version ordinateur : chaque palier est une marche, plus haute à mesure que le gain grandit.
/// Palier gagné en vert, perdu en rose, en cours en violet.
class _Stairs extends StatelessWidget {
  const _Stairs(this.rows);
  final List<_PlanRow> rows;

  @override
  Widget build(BuildContext context) {
    final n = rows.length;
    return Padding(
      padding: const EdgeInsets.only(top: 6, bottom: 4),
      child: SizedBox(
        height: 300,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            for (final (i, r) in rows.indexed) ...[
              if (i > 0) const SizedBox(width: 10),
              Expanded(child: _Step(r, height: 165 + 135 * (n == 1 ? 1 : i / (n - 1)))),
            ],
          ],
        ),
      ),
    );
  }
}

class _Step extends StatelessWidget {
  const _Step(this.r, {required this.height});
  final _PlanRow r;
  final double height;

  @override
  Widget build(BuildContext context) {
    final (fill, border, accent) = switch (r.state) {
      _StepState.won => (Fp.win.withValues(alpha: 0.14), Fp.win.withValues(alpha: 0.45), Fp.win),
      _StepState.lost => (Fp.loss.withValues(alpha: 0.14), Fp.loss.withValues(alpha: 0.45), Fp.lossText),
      _StepState.current => (Fp.accentAlpha(0.28), Fp.accentLight, Fp.accentLight),
      _StepState.future => (Fp.fill, Fp.line10, Fp.textSoft),
    };
    final status = switch (r.state) {
      _StepState.won => 'Gagné',
      _StepState.lost => 'Perdu',
      _StepState.current => 'En cours',
      _StepState.future => '',
    };
    return Container(
      height: height,
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
      decoration: BoxDecoration(
        color: fill,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(12), bottom: Radius.circular(4)),
        border: Border.all(color: border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'PALIER ${r.number}',
            style: Fp.body(10.5, color: Fp.text3, weight: FontWeight.w700),
          ),
          if (status.isNotEmpty)
            Text(
              status,
              style: Fp.body(11.5, color: accent, weight: FontWeight.w700),
            ),
          // Bas de la marche : réduit plutôt que coupé si la marche est étroite.
          Expanded(
            child: Align(
              alignment: Alignment.bottomLeft,
              child: FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.bottomLeft,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'gain',
                      style: Fp.body(10.5, color: Fp.text3, weight: FontWeight.w600),
                    ),
                    FittedBox(
                      fit: BoxFit.scaleDown,
                      alignment: Alignment.centerLeft,
                      child: Text(r.gain, style: Fp.title(15, color: accent).copyWith(height: 1.2)),
                    ),
                    const SizedBox(height: 6),
                    Text('mise ${r.stake}', style: Fp.body(11, color: Fp.text2, height: 1.3)),
                    Text('cote ${r.odds}', style: Fp.body(11, color: Fp.text2)),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _TableHeader extends StatelessWidget {
  const _TableHeader();

  @override
  Widget build(BuildContext context) {
    final style = Fp.body(11, color: Fp.text2, weight: FontWeight.w700).copyWith(letterSpacing: 1);
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 0, 14, 8),
      child: Row(
        children: [
          SizedBox(width: 44, child: Text('PALIER', style: style)),
          const SizedBox(width: 8),
          Expanded(flex: 5, child: Text('MISE', style: style)),
          Expanded(flex: 5, child: Text('COTE', style: style)),
          Expanded(
            flex: 5,
            child: Text('GAIN', textAlign: TextAlign.right, style: style),
          ),
        ],
      ),
    );
  }
}

class _PlanRow extends StatelessWidget {
  const _PlanRow({
    required this.number,
    required this.state,
    required this.stake,
    required this.odds,
    required this.gain,
  });
  final int number;
  final _StepState state;
  final String stake;
  final String odds;
  final String gain;

  @override
  Widget build(BuildContext context) {
    final current = state == _StepState.current;
    Widget square(Color? fill, Widget child, {Color? border}) => Container(
      width: 32,
      height: 32,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: fill,
        borderRadius: BorderRadius.circular(8),
        border: border != null ? Border.all(color: border) : null,
      ),
      child: child,
    );
    final badge = switch (state) {
      _StepState.won => square(Fp.win, const Icon(Icons.check_rounded, size: 20, color: Color(0xFF052E1C))),
      _StepState.lost => square(Fp.loss, const Icon(Icons.close_rounded, size: 20, color: Color(0xFF3B0A24))),
      _StepState.current => square(Fp.accent, Text('$number', style: Fp.title(15, color: Colors.white))),
      _StepState.future => square(
        null,
        Text('$number', style: Fp.title(15, color: Fp.textSoft)),
        border: const Color(0x40FFFFFF),
      ),
    };
    final gainColor = switch (state) {
      _StepState.current => Fp.accentLight,
      _StepState.lost => Fp.lossText,
      _StepState.future when gain.contains('\n') => Fp.accentLight,
      _ => Fp.text,
    };
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: current ? Fp.accentSoft : Fp.fill,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: current ? Fp.accentLine : Fp.line10),
      ),
      child: Row(
        children: [
          SizedBox(
            width: 44,
            child: Align(alignment: Alignment.centerLeft, child: badge),
          ),
          const SizedBox(width: 8),
          Expanded(
            flex: 5,
            child: Text(stake, style: Fp.body(14, weight: FontWeight.w600, height: 1.25)),
          ),
          Expanded(
            flex: 5,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [Text(odds, style: Fp.body(14, weight: FontWeight.w600))],
            ),
          ),
          Expanded(
            flex: 5,
            child: Text(
              gain,
              textAlign: TextAlign.right,
              style: Fp.body(14, weight: FontWeight.w700, height: 1.25, color: gainColor),
            ),
          ),
        ],
      ),
    );
  }
}

// --- Montante en cours ou terminée ----------------------------------------------

class MontanteView extends StatefulWidget {
  const MontanteView({super.key, required this.montante, required this.onChanged, this.back = false});
  final Json montante;
  final VoidCallback onChanged;
  final bool back;

  @override
  State<MontanteView> createState() => _MontanteViewState();
}

class _MontanteViewState extends State<MontanteView> {
  Bet? currentBet;
  final Map<int, Bet> bets = {}; // pari de chaque palier joué (libellé de la liste)

  @override
  void initState() {
    super.initState();
    _loadBets();
  }

  Json? get _current {
    final m = widget.montante;
    return (m['steps'] as List).cast<Json>().where((s) => s['number'] == m['current_step']).firstOrNull;
  }

  Future<void> _loadBets() async {
    final api = context.read<AppState>().api;
    for (final s in (widget.montante['steps'] as List).cast<Json>()) {
      final id = s['bet_id'] as int?;
      if (id == null) continue;
      try {
        final b = Bet(await api.get('/bets/$id') as Json);
        if (!mounted) return;
        setState(() {
          bets[id] = b;
          if (id == _current?['bet_id']) currentBet = b;
        });
      } on ApiException {
        // la liste reste lisible sans le détail du pari
      }
    }
  }

  Future<void> _cashOut() async {
    final m = widget.montante;
    final api = context.read<AppState>().api;
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Encaisser'),
        content: Text(
          'Arrêter la montante et garder ${money(m['cashable'] as int, m['currency'] as String)} ?',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Annuler')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Encaisser')),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    final done = await guard(context, () => api.post('/montantes/${m['id']}/cash-out'));
    if (done != null) {
      showMessage('Montante encaissée.');
      widget.onChanged();
    }
  }

  Future<void> _suggestions() async {
    await Navigator.of(context)
        .push(MaterialPageRoute(builder: (_) => SuggestionsScreen(montanteId: widget.montante['id'] as int)));
    widget.onChanged();
  }

  @override
  Widget build(BuildContext context) {
    final m = widget.montante;
    final currency = m['currency'] as String;
    final steps = (m['steps'] as List).cast<Json>();
    final active = m['status'] == 'active';
    final current = _current;
    final waiting = active && current != null && current['bet_id'] == null;
    final bet = currentBet;
    final goal = m['final_payout_range'] as List?;

    _StepState stateOf(Json s) {
      final r = s['result'] as String? ?? 'pending';
      if (r == 'won' || r == 'partial') return _StepState.won;
      if (r == 'lost') return _StepState.lost;
      if (active && s['number'] == m['current_step']) return _StepState.current;
      return _StepState.future;
    }

    String pct(Object? v) => v == null ? '—' : percent((v as num).toDouble(), decimals: 1);
    final won = steps.where((s) => stateOf(s) == _StepState.won).length;
    final stakeNow = current?['stake'] as int? ?? m['cashable'] as int;

    String betLabel(Bet b) => b.selections.length == 1
        ? fullLabel(
            b.selections.single.market,
            b.selections.single.line,
            b.selections.single.selection,
            home: b.selections.single.homeTeam,
            away: b.selections.single.awayTeam,
          )
        : 'Combiné de ${b.selections.length} matchs';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            if (widget.back) ...[
              BackChevron(onTap: () => Navigator.of(context).maybePop()),
              const SizedBox(width: 4),
            ],
            const Expanded(child: MTitle('Ma', 'montante', 26)),
            if (!active) montanteTag(m['status'] as String),
          ],
        ),
        const SizedBox(height: 12),
        // Maquette v2 : où en est la montante, d'un coup d'œil.
        GlassCard.section(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          active ? 'Mise actuelle' : (m['status'] == 'lost' ? 'Résultat' : 'Encaissé'),
                          style: Fp.body(12, color: Fp.muted),
                        ),
                        Text(
                          active
                              ? '${thousands(stakeNow)} F'
                              : m['status'] == 'lost'
                              ? 'perdue'
                              : '${thousands(m['cashable'] as int)} F',
                          style: Fp.body(
                            30,
                            weight: FontWeight.w800,
                            color: !active && m['status'] == 'lost' ? Fp.lossText : Fp.text,
                          ),
                        ),
                      ],
                    ),
                  ),
                  if (goal != null)
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text('Objectif', style: Fp.body(12, color: Fp.muted)),
                        Text(
                          goal[0] == goal[1] ? '${_range(goal)} F' : '${_about(goal)} F environ',
                          style: Fp.body(18, weight: FontWeight.w700),
                        ),
                        if (goal[0] != goal[1])
                          Text(
                            'entre ${_range(goal, sep: ' et ')} F',
                            style: Fp.body(11, color: Fp.text3),
                          ),
                      ],
                    ),
                ],
              ),
              const SizedBox(height: 12),
              // Maquette C2 : barre fine, violet sur #241E3D. Sans sa propre annonce : le texte
              // « Palier 1 sur 6 » dessous la dit (sinon toute la page devenait une « barre de
              // progression » pour le lecteur d'écran, et ses boutons disparaissaient).
              ExcludeSemantics(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(3),
                  child: LinearProgressIndicator(
                    value: steps.isEmpty ? 0 : (active ? (m['current_step'] as int) : won) / steps.length,
                    minHeight: 6,
                    backgroundColor: Fp.line10,
                    color: Fp.accent,
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Palier ${m['current_step']} sur ${steps.length} · départ '
                '${money(m['start_stake'] as int, currency)} (argent fictif)',
                style: Fp.body(12, color: Fp.muted),
              ),
              // Le chiffre qui compte pour le joueur, en haut (maquette C2 : encadré ambre).
              if ((m['chance_by_odds'] ?? m['chance_by_model']) case final num chance when active)
                Container(
                  margin: const EdgeInsets.only(top: 10),
                  padding: const EdgeInsets.fromLTRB(12, 11, 12, 11),
                  decoration: BoxDecoration(
                    color: const Color(0xFF1F1709),
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: const Color(0xFF6B4F1D)),
                  ),
                  child: Text.rich(
                    TextSpan(
                      children: [
                        TextSpan(
                          text: 'Chance d\'aller au bout : ${_outOf100(chance.toDouble()).toLowerCase()}',
                          style: const TextStyle(fontWeight: FontWeight.w700),
                        ),
                        TextSpan(
                          text:
                              ' (${percent(chance.toDouble(), decimals: 1)} '
                              '${m['chance_by_odds'] != null ? 'selon les cotes' : 'selon le moteur'}). La plupart '
                              'des montantes s\'arrêtent avant le dernier palier.',
                        ),
                      ],
                    ),
                    style: Fp.body(13, color: Fp.warning, height: 1.4),
                  ),
                ),
            ],
          ),
        ),
        if (active) ...[
          const SizedBox(height: 12),
          GlassCard.section(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('C\'est quoi, une montante ?', style: Fp.body(14, weight: FontWeight.w700)),
                const SizedBox(height: 6),
                Text(
                  'Tu mises ${money(m['start_stake'] as int, currency)}. Si tu gagnes, tu remises tout le gain '
                  'au palier suivant. Un seul pari perdu et la montante s\'arrête : tout ce qui a été misé '
                  'est perdu. Tu peux encaisser à tout moment.',
                  style: Fp.body(13, color: Fp.muted, height: 1.4),
                ),
              ],
            ),
          ),
        ],
        const SizedBox(height: 12),
        GlassCard.section(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 4),
          child: Column(
            children: [
              for (final s in steps)
                _StepLine(
                  number: s['number'] as int,
                  state: stateOf(s),
                  title: switch (bets[s['bet_id']]) {
                    final b? => '${betLabel(b)} · ${odds(b.totalOdds)}',
                    _ => s['odds'] != null ? 'Cote ${odds(s['odds'])}' : 'À choisir',
                  },
                  detail: s['stake'] != null
                      ? '${thousands(s['stake'] as int)} → '
                            '${s['payout'] != null
                                ? thousands(s['payout'] as int)
                                : s['potential_payout'] != null
                                ? thousands(s['potential_payout'] as int)
                                : _range(s['payout_range'] as List?)} F'
                      : '${_about(s['stake_range'] as List?)} → ${_about(s['payout_range'] as List?)} F environ',
                  range: '${odds(s['odds_min'])}–${odds(s['odds_max'])}',
                ),
            ],
          ),
        ),
        // Ordinateur : l'escalier des paliers sous la liste.
        if (DesktopScope.of(context)) ...[
          const SizedBox(height: 12),
          GlassCard.section(
            child: _Stairs([
              for (final s in steps)
                _PlanRow(
                  number: s['number'] as int,
                  state: stateOf(s),
                  stake: s['stake'] != null
                      ? thousands(s['stake'] as int)
                      : _range(s['stake_range'] as List?, sep: '\nà '),
                  odds: s['odds'] != null ? odds(s['odds']) : '${odds(s['odds_min'])}–${odds(s['odds_max'])}',
                  gain: s['payout'] != null
                      ? thousands(s['payout'] as int)
                      : s['potential_payout'] != null
                      ? thousands(s['potential_payout'] as int)
                      : _range(s['payout_range'] as List?, sep: '\nà '),
                ),
            ]),
          ),
        ],
        const SizedBox(height: 6),
        Text(
          'Tout pari dont la cote est dans la plage du palier convient.',
          style: Fp.body(12, color: Fp.text2),
        ),
        // Montante terminée : la chance annoncée au départ (en cours : dans l'encadré du haut).
        if (!active && (m['chance_by_model'] != null || m['chance_by_odds'] != null))
          Text(
            [
              if (m['chance_by_model'] != null) '${pct(m['chance_by_model'])} selon le moteur',
              if (m['chance_by_odds'] != null) '${pct(m['chance_by_odds'])} selon les cotes',
            ].join(', ').replaceFirst(RegExp(r'^'), 'Chance d\'aller au bout : '),
            style: Fp.body(12, color: Fp.text2),
          ),
        if (active && current != null) ...[
          if (!waiting && bet != null) ...[
            const SizedBox(height: 12),
            _InfoBox(
              ok: current['out_of_range'] != true,
              text:
                  'Palier ${current['number']} : cote ${odds(bet.totalOdds)}, '
                  '${current['out_of_range'] == true ? 'hors de la plage (confirmé)' : 'dans la plage'} '
                  '${odds(current['odds_min'])}–${odds(current['odds_max'])}. Gain de ce palier : '
                  '${money(bet.potentialPayout, bet.currency)}.',
            ),
          ],
          if (waiting) ...[
            const SizedBox(height: 12),
            Semantics(
              button: true,
              label: 'Choisir le pari',
              child: Material(
                color: Colors.transparent,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(16),
                  side: const BorderSide(color: Color(0x8CA78BFA)),
                ),
                clipBehavior: Clip.antiAlias,
                child: InkWell(
                  onTap: _suggestions,
                  child: Ink(
                    color: Fp.accentAlpha(0.12),
                    padding: const EdgeInsets.fromLTRB(14, 12, 12, 12),
                    child: Row(
                      children: [
                        const Icon(Icons.star_outline_rounded, size: 18, color: Color(0xFFE4D8FD)),
                        const SizedBox(width: 10),
                        Expanded(
                          child: ExcludeSemantics(
                            child: Text.rich(
                              TextSpan(
                                style: Fp.body(13, color: Fp.textStrong, height: 1.4),
                                children: [
                                  TextSpan(
                                    text: 'Suggestions du moteur',
                                    style: Fp.body(13, weight: FontWeight.w800),
                                  ),
                                  TextSpan(
                                    text:
                                        ' pour le palier ${current['number']} (mise '
                                        '${money(current['stake'] as int, currency)}, cote '
                                        '${odds(current['odds_min'])} à ${odds(current['odds_max'])}), selon les '
                                        'mêmes règles que le Coupon intelligent.',
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                        const Icon(Icons.chevron_right_rounded, color: Color(0xFFC9B2F8)),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
          const SizedBox(height: 12),
          MCard(
            margin: EdgeInsets.zero,
            child: _SecureCard(on: (m['secure_pct'] as int) > 0, pct: m['secure_pct'] as int),
          ),
          const SizedBox(height: 14),
          OutlinedButton(
            style: OutlinedButton.styleFrom(minimumSize: const Size(0, 52)),
            onPressed: _cashOut,
            child: FittedBox(child: Text('Arrêter et garder ${thousands(m['cashable'] as int)} F')),
          ),
          if (waiting)
            TextButton(
              onPressed: () {
                Navigator.of(context).popUntil((r) => r.isFirst);
                HomeShellState.of(context)?.go(0);
                showMessage('Choisis 1 à 3 sélections, puis « Utiliser pour le palier » dans le coupon.');
              },
              child: const Text('Composer moi-même depuis les matchs'),
            ),
        ],
      ],
    );
  }
}

/// Un palier (maquette v2) : numéro coloré selon l'état, pari et gains, état à droite.
class _StepLine extends StatelessWidget {
  const _StepLine({
    required this.number,
    required this.state,
    required this.title,
    required this.detail,
    required this.range,
  });
  final int number;
  final _StepState state;
  final String title;
  final String detail;

  /// Plage de cote du palier (« 1,55–1,65 »).
  final String range;

  @override
  Widget build(BuildContext context) {
    // Maquette C2 : numéro dans une étiquette (encadré violet pour le palier en cours),
    // étiquette d'état à droite (verte, rose ou violette).
    const green = (Color(0xFF12301F), Fp.win), pink = (Color(0xFF3A1620), Fp.loss);
    final (status, tag) = switch (state) {
      _StepState.won => ('Gagné', green),
      _StepState.lost => ('Perdu', pink),
      _StepState.current => ('En cours', (Fp.cardHigh, Fp.lilac)),
      _StepState.future => ('', (Fp.cardHigh, Fp.lilac)),
    };
    final digit = switch (state) {
      _StepState.won => green,
      _StepState.lost => pink,
      _ => (Fp.cardHigh, Fp.lilac),
    };
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 13),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: Fp.line10)),
      ),
      child: Row(
        children: [
          Container(
            width: 30,
            padding: const EdgeInsets.symmetric(vertical: 4),
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: digit.$1,
              borderRadius: BorderRadius.circular(8),
              border: state == _StepState.current ? Border.all(color: Fp.accent2, width: 1.5) : null,
            ),
            child: Text(
              '$number',
              style: Fp.body(11, weight: FontWeight.w700, color: digit.$2),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: Fp.body(14, weight: FontWeight.w700)),
                Text('$detail · plage $range', style: Fp.body(12, color: Fp.muted)),
              ],
            ),
          ),
          if (status.isNotEmpty) ...[
            const SizedBox(width: 8),
            Tag(status, color: tag.$2, background: tag.$1),
          ],
        ],
      ),
    );
  }
}

class _InfoBox extends StatelessWidget {
  const _InfoBox({required this.ok, required this.text});
  final bool ok;
  final String text;

  @override
  Widget build(BuildContext context) {
    final color = ok ? Fp.win : Fp.warning;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(ok ? Icons.check_rounded : Icons.info_outline_rounded, size: 18, color: color),
          const SizedBox(width: 10),
          Expanded(
            child: Text(text, style: Fp.body(14, color: color, height: 1.35)),
          ),
        ],
      ),
    );
  }
}

class MontanteDetailScreen extends StatefulWidget {
  const MontanteDetailScreen({super.key, required this.id});
  final int id;

  @override
  State<MontanteDetailScreen> createState() => _MontanteDetailScreenState();
}

class _MontanteDetailScreenState extends State<MontanteDetailScreen> {
  Key _key = UniqueKey();

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Loader<Json>(
          key: _key,
          load: () async => await api.get('/montantes/${widget.id}') as Json,
          builder: (context, m, reload) => RefreshIndicator(
            onRefresh: reload,
            child: ListView(
              padding: pagePadding(context, 16, 32),
              children: [
                MontanteView(montante: m, back: true, onChanged: () => setState(() => _key = UniqueKey())),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// --- Pari du palier : suggestions ----------------------------------------------

class SuggestionsScreen extends StatefulWidget {
  const SuggestionsScreen({super.key, required this.montanteId});
  final int montanteId;

  @override
  State<SuggestionsScreen> createState() => _SuggestionsScreenState();
}

class _SuggestionsScreenState extends State<SuggestionsScreen> {
  int get montanteId => widget.montanteId;
  bool showAnyway = false;

  /// Demandé une seule fois : le calcul étudie toute la période (plusieurs secondes).
  late final Future<(Json, Map<int, MatchInfo>)> _loading = _load(context.read<AppState>().api);

  Future<(Json, Map<int, MatchInfo>)> _load(ApiClient api) async {
    final data = await api.get('/montantes/$montanteId/suggestions', null, ApiClient.slowTimeout) as Json;
    final ids = <int>{
      for (final s in data['suggestions'] as List)
        for (final sel in s['selections'] as List) sel['match_id'] as int,
    }.toList();
    final infos = await Future.wait([for (final id in ids) api.get('/matches/$id')]);
    return (data, {for (final (i, id) in ids.indexed) id: MatchInfo(infos[i] as Json)});
  }

  Future<void> _play(BuildContext context, Json suggestion, Json data) async {
    final state = context.read<AppState>();
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Jouer le palier ${data['step']}'),
        content: Text(
          'Cote ${decimal(suggestion['total_odds'], max: 3)}, mise '
          '${money(data['stake'] as int, state.me?.currency ?? 'XOF')}.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Annuler')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Jouer')),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    final done = await guard(
      context,
      () => state.api.post('/montantes/$montanteId/bet', {
        'selections': [
          for (final s in suggestion['selections'] as List)
            {
              'match_id': s['match_id'],
              'market': s['market'],
              'line': s['line'] ?? '',
              'selection': s['selection'],
              'odds': '${s['odds']}',
            },
        ],
      }),
    );
    if (done != null && context.mounted) {
      showMessage('Palier ${data['step']} joué.');
      await state.refreshMe();
      if (context.mounted) Navigator.pop(context);
    }
  }

  @override
  Widget build(BuildContext context) {
    const padding = EdgeInsets.fromLTRB(18, 16, 18, 32);
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: FutureBuilder<(Json, Map<int, MatchInfo>)>(
          future: _loading,
          builder: (context, snap) {
            const header = Padding(
              padding: EdgeInsets.only(bottom: 16),
              child: BackHeader('Pari du', 'palier'),
            );
            if (snap.connectionState != ConnectionState.done) {
              return ListView(
                padding: padding,
                children: const [
                  header,
                  SlowWait(what: 'les matchs des prochains jours'),
                ],
              );
            }
            final err = snap.error;
            if (err is ApiException && err.premiumRequired) {
              return ListView(
                padding: padding,
                children: const [
                  header,
                  PremiumLock(
                    text:
                        'Les suggestions de pari pour la montante sont incluses dans Premium. '
                        'Tu peux composer le pari toi-même depuis les matchs.',
                  ),
                ],
              );
            }
            if (err != null) return ErrorPanel(error: err);
            final (data, matches) = snap.data!;
            final list = (data['suggestions'] as List).cast<Json>();
            final stake = data['stake'] as int;
            final lo = double.parse('${data['odds_min']}'), hi = double.parse('${data['odds_max']}');
            final allBelow = list.isNotEmpty && list.every((s) => s['engine_below_odds'] == true);
            return ListView(
              padding: padding,
              children: [
                // Maquette N8 : titre, mise et plage en une ligne, puis une liste compacte.
                BackHeader('Suggestions pour le', 'palier ${data['step']}'),
                const SizedBox(height: 8),
                Text(
                  'Mise ${thousands(stake)} F · cote ${odds(lo)} à ${odds(hi)} · gain '
                  '${thousands((stake * lo).floor())} à ${thousands((stake * hi).floor())} F · la cote la plus '
                  'basse d\'abord',
                  style: Fp.body(13.5, color: Fp.muted, height: 1.4),
                ),
                // Rapport du 09/11/2026 (trêve internationale) : quand le moteur juge chaque
                // suggestion moins probable que la cote ne le dit, le dire avant tout.
                if (allBelow) ...[
                  Container(
                    margin: const EdgeInsets.only(top: 12),
                    padding: const EdgeInsets.fromLTRB(12, 11, 12, 11),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1F1709),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: const Color(0xFF6B4F1D)),
                    ),
                    child: Text(
                      'Rien de bon pour ce palier aujourd\'hui : pour chaque pari de la plage, le moteur '
                      'est moins confiant que la cote. Un joueur prudent attend d\'autres matchs ; ta '
                      'montante ne bouge pas tant que tu ne joues pas.',
                      style: Fp.body(13.5, color: Fp.warning, height: 1.4),
                    ),
                  ),
                  if (!showAnyway)
                    Align(
                      alignment: Alignment.centerLeft,
                      child: TextButton(
                        onPressed: () => setState(() => showAnyway = true),
                        child: Text('Voir quand même les ${list.length} paris ›'),
                      ),
                    ),
                ],
                if (list.isEmpty)
                  const EmptyState(
                    'Aucun pari avec une cote réelle dans cette plage pour l\'instant. Les matchs déjà pris '
                    'par tes autres montantes en cours sont écartés : ton risque reste réparti.',
                    icon: Icons.search_off_rounded,
                  )
                else if (!allBelow || showAnyway)
                  MCard(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
                    child: Column(
                      children: [
                        for (final (i, s) in list.indexed) ...[
                          if (i > 0) const Divider(height: 1, thickness: 1, color: Fp.divider),
                          _SuggestionCard(s: s, matches: matches, onPlay: () => _play(context, s, data)),
                        ],
                      ],
                    ),
                  ),
                const SizedBox(height: 12),
                Text(
                  'Le moteur n\'est pas plus fort que le bookmaker : une suggestion n\'est pas un conseil de '
                  'pari. Quand les deux ne sont pas d\'accord, la cote a le plus souvent raison (vérifié sur '
                  '7 000 matchs). Rien n\'est joué sans ta validation.',
                  style: Fp.body(12.5, color: Fp.muted, height: 1.4),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

/// Une suggestion (maquette N8) : chaque sélection en gras, le match, l'heure et la chance du
/// moteur ; la cote dans une case violette, à toucher pour jouer le palier.
class _SuggestionCard extends StatelessWidget {
  const _SuggestionCard({required this.s, required this.matches, required this.onPlay});
  final Json s;
  final Map<int, MatchInfo> matches;
  final VoidCallback onPlay;

  @override
  Widget build(BuildContext context) {
    final sels = (s['selections'] as List).cast<Json>();
    final model = (s['model_probability'] as num).toDouble();
    final implied = (s['implied_probability'] as num).toDouble();
    return InkWell(
      onTap: onPlay,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (sels.length > 1)
                    Text(
                      'Combiné de ${sels.length}',
                      style: Fp.body(12, color: Fp.muted, weight: FontWeight.w600),
                    ),
                  for (final sel in sels)
                    Builder(
                      builder: (context) {
                        final m = matches[sel['match_id']];
                        final home = m?.home.name ?? 'Domicile';
                        final away = m?.away.name ?? 'Extérieur';
                        final market = sel['market'] as String, line = (sel['line'] ?? '') as String;
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 2),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              // Libellé complet : « Buts de Stuttgart · Moins de 2,5 buts »,
                              // jamais « Moins de 2,5 buts » seul (ambigu pour un total d'équipe).
                              Text(
                                fullLabel(market, line, sel['selection'] as String, home: home, away: away),
                                style: Fp.body(15, weight: FontWeight.w700),
                              ),
                              Text(
                                [
                                  '$home – $away',
                                  if (m != null) '${shortDate(m.date)} ${m.when}',
                                  if (sels.length > 1) 'cote ${odds(sel['odds'])}',
                                ].join(' · '),
                                style: Fp.body(13, color: Fp.muted),
                              ),
                              if (explainSelection(
                                    market,
                                    line,
                                    sel['selection'] as String,
                                    home: home,
                                    away: away,
                                  )
                                  case final e?)
                                Text(e, style: Fp.body(12, color: Fp.lilac, height: 1.35)),
                            ],
                          ),
                        );
                      },
                    ),
                  Text(
                    'moteur ${percent(model)} · selon la cote ${percent(implied, decimals: 1)}',
                    style: Fp.body(13, color: Fp.muted),
                  ),
                  // Décision du 07/11/2026 : gardée mais expliquée (et montrée après les autres).
                  if (s['engine_below_odds'] == true)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text(
                        'Le moteur est moins confiant que le bookmaker sur ce pari.',
                        style: Fp.body(12.5, color: Fp.warning, height: 1.4),
                      ),
                    ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            Semantics(
              button: true,
              label: 'Choisir ce pari, cote ${odds(s['total_odds'])}',
              excludeSemantics: true,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: Fp.cardHigh,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: Fp.accent2, width: 1.5),
                ),
                child: Text(
                  odds(s['total_odds']),
                  style: Fp.body(16, weight: FontWeight.w800, color: Fp.lilac),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// « environ 4 montantes sur 100 » (« moins d'une sur 100 » sous 1 %).
String _outOf100(double p) {
  final n = (p * 100).round();
  if (p < 0.005) return 'Moins d\'une sur 100';
  return 'Environ ${n < 1 ? 1 : n} sur 100';
}
