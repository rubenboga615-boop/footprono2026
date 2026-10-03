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
  final start = TextEditingController(text: '5000');
  int count = 6;
  bool secureOn = false;
  int secure = 20;
  bool editRanges = false;
  bool busy = false;
  final ranges = List.generate(8, (i) => RangeValues(1.55 + 0.05 * i, 1.65 + 0.05 * i));

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
      showMessage('Montante lancée : choisis le pari du palier 1.');
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
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Expanded(child: TwoToneTitle('Ma', 'montante')),
            if (goal != null) _Goal(goal),
          ],
        ),
        const SizedBox(height: 16),
        GlassCard.section(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'Mise de départ',
                style: Fp.body(14, color: Fp.text2, weight: FontWeight.w600),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: start,
                keyboardType: TextInputType.number,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                onChanged: (_) => setState(() {}),
                style: Fp.title(24),
                decoration: InputDecoration(
                  suffixText: currencyLabel(currency),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(16),
                    borderSide: BorderSide(color: Fp.accentLine),
                  ),
                  fillColor: Fp.accentFaint,
                ),
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final v in const [1000, 5000, 10000, 25000])
                    FpChip(
                      thousands(v),
                      selected: stake == v,
                      onTap: () => setState(() => start.text = '$v'),
                    ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        GlassCard.section(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text('Plan · $count paliers', style: Fp.title(17, weight: FontWeight.w600)),
                  ),
                  GestureDetector(
                    onTap: () => setState(() => editRanges = !editRanges),
                    child: Text(
                      editRanges ? 'Terminé' : 'Modifier les plages',
                      style: Fp.body(14, color: Fp.accentLight, weight: FontWeight.w700),
                    ),
                  ),
                ],
              ),
              if (editRanges) ...[
                const SizedBox(height: 8),
                Text('Nombre de paliers : $count', style: Fp.body(13, color: Fp.text2)),
                Slider(
                  value: count.toDouble(),
                  min: 4,
                  max: 8,
                  divisions: 4,
                  label: '$count',
                  onChanged: (v) => setState(() => count = v.round()),
                ),
                for (var i = 0; i < count; i++) ...[
                  Text(
                    'Palier ${i + 1} : ${odds(ranges[i].start)} – ${odds(ranges[i].end)}',
                    style: Fp.body(13, weight: FontWeight.w600),
                  ),
                  RangeSlider(
                    values: ranges[i],
                    min: 1.2,
                    max: 3.0,
                    divisions: 36,
                    onChanged: (v) => setState(() => ranges[i] = v),
                  ),
                ],
              ] else ...[
                const SizedBox(height: 10),
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
              ],
              const SizedBox(height: 8),
              Text(
                'Tout pari dont la cote est dans la plage du palier convient. Les gains à venir dépendent '
                'des cotes réellement jouées.',
                style: Fp.body(13, color: Fp.text2, height: 1.4),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        _SecureCard(
          on: secureOn,
          pct: secure,
          onChanged: (v) => setState(() => secureOn = v),
          onPct: (v) => setState(() => secure = v),
        ),
        const SizedBox(height: 16),
        FilledButton(
          onPressed: busy || stake < 100 ? null : _create,
          child: const Text('Lancer la montante'),
        ),
      ],
    );
  }
}

class _Goal extends StatelessWidget {
  const _Goal(this.range);
  final List range;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Text('Objectif', style: Fp.body(12, color: Fp.text2)),
        Text('${_range(range)} F', style: Fp.body(13, weight: FontWeight.w700)),
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
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 10, 12),
      decoration: BoxDecoration(
        color: Fp.fill,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Fp.line12),
      ),
      child: Column(
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Sécuriser $pct % de chaque gain', style: Fp.body(16, weight: FontWeight.w700)),
                    const SizedBox(height: 2),
                    Text(
                      onChanged == null
                          ? 'Fixé au lancement de la montante'
                          : 'Mis de côté au lieu d\'être remisé',
                      style: Fp.body(13, color: Fp.text2),
                    ),
                  ],
                ),
              ),
              // Montante lancée : réglage figé, affiché sans interrupteur inactif.
              if (onChanged != null)
                Switch(value: on, onChanged: onChanged)
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
      ),
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
                    if (r.oddsRange != null)
                      Text('plage ${r.oddsRange}', style: Fp.body(10.5, color: Fp.text3)),
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
    this.oddsRange,
  });
  final int number;
  final _StepState state;
  final String stake;
  final String odds;
  final String? oddsRange;
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
              children: [
                Text(odds, style: Fp.body(14, weight: FontWeight.w600)),
                if (oddsRange != null) Text(oddsRange!, style: Fp.body(11, color: Fp.text2)),
              ],
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

  @override
  void initState() {
    super.initState();
    _loadBet();
  }

  Json? get _current {
    final m = widget.montante;
    return (m['steps'] as List).cast<Json>().where((s) => s['number'] == m['current_step']).firstOrNull;
  }

  Future<void> _loadBet() async {
    final id = _current?['bet_id'];
    if (id == null) return;
    try {
      final b = Bet(await context.read<AppState>().api.get('/bets/$id') as Json);
      if (mounted) setState(() => currentBet = b);
    } on ApiException {
      // le tableau reste lisible sans le détail du pari
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

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (widget.back) ...[
              SquareButton(
                icon: Icons.arrow_back_rounded,
                tooltip: 'Retour',
                onTap: () => Navigator.of(context).maybePop(),
              ),
              const SizedBox(width: 14),
            ],
            const Expanded(child: TwoToneTitle('Ma', 'montante')),
            if (goal != null) _Goal(goal) else montanteTag(m['status'] as String),
          ],
        ),
        const SizedBox(height: 16),
        GlassCard.section(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      'Plan · ${steps.length} paliers',
                      style: Fp.title(17, weight: FontWeight.w600),
                    ),
                  ),
                  Text(
                    'départ ${money(m['start_stake'] as int, currency)}',
                    style: Fp.body(13, color: Fp.text2),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              ..._plan(context, [
                for (final s in steps)
                  _PlanRow(
                    number: s['number'] as int,
                    state: stateOf(s),
                    stake: s['stake'] != null
                        ? thousands(s['stake'] as int)
                        : _range(s['stake_range'] as List?, sep: '\nà '),
                    odds: s['odds'] != null
                        ? odds(s['odds'])
                        : '${odds(s['odds_min'])}–${odds(s['odds_max'])}',
                    oddsRange: s['odds'] != null ? '${odds(s['odds_min'])}–${odds(s['odds_max'])}' : null,
                    gain: s['payout'] != null
                        ? thousands(s['payout'] as int)
                        : s['potential_payout'] != null
                        ? thousands(s['potential_payout'] as int)
                        : _range(s['payout_range'] as List?, sep: '\nà '),
                  ),
              ]),
              const SizedBox(height: 4),
              Text(
                'Tout pari dont la cote est dans la plage du palier convient. Les gains à venir dépendent '
                'des cotes réellement jouées.',
                style: Fp.body(13, color: Fp.text2, height: 1.4),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        GlassCard.section(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: _Figure('Encaissable maintenant', '${thousands(m['cashable'] as int)} F', Fp.text),
              ),
              Expanded(
                child: _Figure('Chance d\'aller au bout · modèle', pct(m['chance_by_model']), Fp.accentLight),
              ),
              Expanded(child: _Figure('Selon les cotes', pct(m['chance_by_odds']), Fp.textSoft)),
            ],
          ),
        ),
        if (active && current != null) ...[
          const SizedBox(height: 12),
          GlassCard.section(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    Text(
                      'Palier ${current['number']} · ${waiting ? 'pari à choisir' : 'pari choisi'}',
                      style: Fp.body(14, color: Fp.text2, weight: FontWeight.w600),
                    ),
                    if (bet != null && bet.selections.every((s) => s.modelProbability != null)) ...[
                      const SizedBox(width: 8),
                      Tag(
                        'Modèle ${percent(bet.selections.fold<double>(1, (p, s) => p * s.modelProbability!))}',
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 8),
                if (waiting)
                  Text(
                    'Mise imposée ${money(current['stake'] as int, currency)}, '
                    'cote entre ${odds(current['odds_min'])} et ${odds(current['odds_max'])}.',
                    style: Fp.body(14, color: Fp.textStrong, height: 1.4),
                  )
                else if (bet != null) ...[
                  for (final s in bet.selections)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 4),
                      child: Text(
                        '${s.homeTeam} – ${s.awayTeam} · '
                        '${fullLabel(s.market, s.line, s.selection, home: s.homeTeam, away: s.awayTeam)}',
                        style: Fp.body(15, weight: FontWeight.w700),
                      ),
                    ),
                  const SizedBox(height: 8),
                  _InfoBox(
                    ok: current['out_of_range'] != true,
                    text:
                        'Cote ${odds(bet.totalOdds)} : '
                        '${current['out_of_range'] == true ? 'hors de la plage (confirmé)' : 'dans la plage'} '
                        '${odds(current['odds_min'])}–${odds(current['odds_max'])}. Gain de ce palier : '
                        '${money(bet.potentialPayout, bet.currency)}.',
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: 12),
          _SecureCard(on: (m['secure_pct'] as int) > 0, pct: m['secure_pct'] as int),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  style: OutlinedButton.styleFrom(minimumSize: const Size(0, 52)),
                  onPressed: _cashOut,
                  child: FittedBox(child: Text('Encaisser ${thousands(m['cashable'] as int)} F')),
                ),
              ),
              if (waiting) ...[
                const SizedBox(width: 10),
                Expanded(
                  child: FilledButton(onPressed: _suggestions, child: const Text('Choisir le pari')),
                ),
              ],
            ],
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
        ] else if (!active) ...[
          const SizedBox(height: 12),
          GlassCard.section(
            child: KeyValue(
              m['status'] == 'lost' ? 'Résultat' : 'Encaissé',
              m['status'] == 'lost' ? 'montante perdue' : money(m['cashable'] as int, currency),
              bold: true,
              valueColor: m['status'] == 'lost' ? Fp.lossText : Fp.win,
            ),
          ),
        ],
      ],
    );
  }
}

class _Figure extends StatelessWidget {
  const _Figure(this.label, this.value, this.color);
  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          label,
          textAlign: TextAlign.center,
          style: Fp.body(12, color: Fp.text2, height: 1.3),
        ),
        const SizedBox(height: 6),
        Text(
          value,
          textAlign: TextAlign.center,
          style: Fp.title(19, color: color),
        ),
      ],
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

class SuggestionsScreen extends StatelessWidget {
  const SuggestionsScreen({super.key, required this.montanteId});
  final int montanteId;

  Future<(Json, Map<int, MatchInfo>)> _load(ApiClient api) async {
    final data = await api.get('/montantes/$montanteId/suggestions') as Json;
    final ids = <int>{
      for (final s in data['suggestions'] as List)
        for (final sel in s['selections'] as List) sel['match_id'] as int,
    };
    final matches = <int, MatchInfo>{};
    for (final id in ids) {
      matches[id] = MatchInfo(await api.get('/matches/$id') as Json);
    }
    return (data, matches);
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
    final state = context.read<AppState>();
    const padding = EdgeInsets.fromLTRB(18, 16, 18, 32);
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: FutureBuilder<(Json, Map<int, MatchInfo>)>(
          future: _load(state.api),
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
                  Center(child: CircularProgressIndicator()),
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
            return ListView(
              padding: padding,
              children: [
                Padding(
                  padding: const EdgeInsets.only(bottom: 16),
                  child: BackHeader('Pari du', 'palier ${data['step']}'),
                ),
                GlassCard(
                  child: Row(
                    children: [
                      Expanded(child: _Figure('Mise', '${thousands(stake)} F', Fp.text)),
                      Expanded(child: _Figure('Plage de cote', '${odds(lo)}–${odds(hi)}', Fp.accentLight)),
                      Expanded(
                        child: _Figure(
                          'Gain',
                          '${thousands((stake * lo).floor())} à ${thousands((stake * hi).floor())}',
                          Fp.text,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 18),
                Row(
                  children: [
                    Text('Suggestions', style: Fp.title(17, weight: FontWeight.w600)),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        'classées par probabilité du modèle',
                        textAlign: TextAlign.right,
                        style: Fp.body(12, color: Fp.text2),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                if (list.isEmpty)
                  const EmptyState(
                    'Aucun pari avec une cote réelle dans cette plage pour l\'instant.',
                    icon: Icons.search_off_rounded,
                  ),
                for (final (i, s) in list.indexed)
                  _SuggestionCard(
                    rank: i + 1,
                    s: s,
                    matches: matches,
                    primary: i == 0,
                    onPlay: () => _play(context, s, data),
                  ),
                const SizedBox(height: 8),
                Text(
                  'Modèle : chances estimées par notre moteur. Selon la cote : chances que donne le '
                  'bookmaker. Quand les deux ne sont pas d\'accord, la cote a le plus souvent raison '
                  '(vérifié sur 7 000 matchs) : un écart n\'est pas une bonne affaire. Rien n\'est joué '
                  'sans ta validation.',
                  style: Fp.body(12, color: Fp.text3, height: 1.4),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _SuggestionCard extends StatelessWidget {
  const _SuggestionCard({
    required this.rank,
    required this.s,
    required this.matches,
    required this.primary,
    required this.onPlay,
  });
  final int rank;
  final Json s;
  final Map<int, MatchInfo> matches;
  final bool primary;
  final VoidCallback onPlay;

  @override
  Widget build(BuildContext context) {
    final sels = (s['selections'] as List).cast<Json>();
    final kind = sels.length == 1 ? 'SIMPLE' : 'COMBINÉ DE ${sels.length}';
    return GlassCard.section(
      margin: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '$rank. $kind',
                  style: Fp.body(14, color: Fp.text2, weight: FontWeight.w700).copyWith(letterSpacing: 1),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          for (final sel in sels)
            Builder(
              builder: (context) {
                final m = matches[sel['match_id']];
                final home = m?.home.name ?? 'Domicile';
                final away = m?.away.name ?? 'Extérieur';
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              // Libellé complet : « Buts de Stuttgart · Moins de 2,5 buts »,
                              // jamais « Moins de 2,5 buts » seul (ambigu pour un total d'équipe).
                              fullLabel(
                                sel['market'] as String,
                                (sel['line'] ?? '') as String,
                                sel['selection'] as String,
                                home: home,
                                away: away,
                              ),
                              style: Fp.body(15, weight: FontWeight.w700),
                            ),
                            Text(
                              '$home – $away${m != null ? ' · ${shortDate(m.date)} ${m.when}' : ''}',
                              style: Fp.body(13, color: Fp.text2),
                            ),
                            if (explainSelection(
                                  sel['market'] as String,
                                  (sel['line'] ?? '') as String,
                                  sel['selection'] as String,
                                  home: home,
                                  away: away,
                                )
                                case final e?)
                              Padding(
                                padding: const EdgeInsets.only(top: 3),
                                child: Text(e, style: Fp.body(12, color: Fp.accentLight, height: 1.35)),
                              ),
                          ],
                        ),
                      ),
                      Text(odds(sel['odds']), style: Fp.body(14, weight: FontWeight.w600)),
                    ],
                  ),
                );
              },
            ),
          const Divider(height: 24),
          Row(
            children: [
              Expanded(child: _Small('Cote totale', odds(s['total_odds']), Fp.text)),
              Expanded(
                child: _Small('Modèle', percent((s['model_probability'] as num).toDouble()), Fp.accentLight),
              ),
              Expanded(
                child: _Small(
                  'Selon la cote',
                  percent((s['implied_probability'] as num).toDouble(), decimals: 1),
                  Fp.text2,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          primary
              ? FilledButton(onPressed: onPlay, child: const Text('Choisir ce pari'))
              : OutlinedButton(onPressed: onPlay, child: const Text('Choisir ce pari')),
        ],
      ),
    );
  }
}

class _Small extends StatelessWidget {
  const _Small(this.label, this.value, this.color);
  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: Fp.body(12, color: Fp.text2)),
        const SizedBox(height: 2),
        Text(value, style: Fp.title(17, color: color)),
      ],
    );
  }
}
