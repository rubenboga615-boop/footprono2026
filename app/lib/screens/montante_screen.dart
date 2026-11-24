import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../desktop/layout.dart';
import '../api/client.dart';
import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/visage.dart';
import '../widgets/engine_vs_odds.dart';
import '../widgets/common.dart';
import '../widgets/engine_compare.dart';
import '../widgets/maquette.dart';
import 'montante_stats_screen.dart';
import 'bookmaker_screen.dart' show selectionColor, selectionState;

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

/// « ≈ 84 000 F » : signe dessiné (la police de l'application n'a pas « ≈ »).
Widget _approx(String text, Color color) => Row(
  mainAxisSize: MainAxisSize.min,
  children: [
    IconTheme(
      data: IconThemeData(color: color),
      child: const VApprox(size: 10),
    ),
    const SizedBox(width: 4),
    Text(text, style: V.b(13.5, color)),
  ],
);

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
                  // Maquette M1 : bilan de mes montantes, gagnées et perdues ensemble.
                  const MontanteSummaryCard(),
                  if (current != null)
                    MontanteView(montante: current, onChanged: _refresh)
                  else
                    _CreateMontante(
                      onCreated: _refresh,
                      onBack: active.isEmpty ? null : () => setState(() => creating = false),
                    ),
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
  const _CreateMontante({required this.onCreated, this.onBack});
  final VoidCallback onCreated;

  /// Retour à la montante en cours (null : aucune montante en cours, pas de flèche).
  final VoidCallback? onBack;

  @override
  State<_CreateMontante> createState() => _CreateMontanteState();
}

class _CreateMontanteState extends State<_CreateMontante> {
  final start = TextEditingController(text: thousands(5000));
  int count = 6;
  bool secureOn = false;
  int secure = 20;
  bool busy = false;
  bool editRanges = false;
  final ranges = List.generate(8, (_) => const RangeValues(1.55, 1.65));

  /// Maquette 17 : trois choix de cote, la même plage à chaque palier.
  static const presets = [(1.30, 1.40), (1.55, 1.65), (1.80, 2.00)];
  int? preset = 1;

  /// Modèle d'origine (maquette N7), remis à la demande du fondateur (24/11/2026) : plages en
  /// légère montée de la première à la dernière (de, à, largeur d'une plage).
  static const ramps = [(1.30, 1.45, 0.05), (1.55, 1.90, 0.10), (2.00, 2.50, 0.15)];
  int? ramp;

  /// Plages de chaque palier selon le choix ; aucun choix : réglées palier par palier.
  void _apply() {
    double r2(double v) => (v * 100).round() / 100;
    if (preset case final p?) {
      final (lo, hi) = presets[p];
      for (var i = 0; i < ranges.length; i++) {
        ranges[i] = RangeValues(lo, hi);
      }
    } else if (ramp case final p?) {
      final (a, b, w) = ramps[p];
      final step = count > 1 ? (b - a - w) / (count - 1) : 0.0;
      for (var i = 0; i < count; i++) {
        ranges[i] = RangeValues(r2(a + step * i), r2(a + step * i + w));
      }
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
    // Si tout passe : à la cote du milieu de chaque plage, arrondi (le gain exact dépend des
    // cotes réellement jouées ; minimum et maximum dans le plan, sur ordinateur).
    var middle = stake.toDouble();
    for (final r in ranges.take(count)) {
      middle = middle * (r.start + r.end) / 2 * (100 - pct) / 100;
    }
    final step = middle >= 10000 ? 1000 : 100;
    final atMiddle = (middle / step).round() * step;
    // Ordinateur : la place ne manque pas, le plan (escalier) et la sécurisation restent affichés.
    final desktop = DesktopScope.of(context);
    final showPlan = editRanges || desktop;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Maquette 17 : titre, mise de départ, nombre de paliers et cote par palier en sélecteurs,
        // puis le résumé honnête (si tout passe, chance d'aller au bout, si un palier rate).
        VTopBar('Nouvelle montante', back: widget.onBack != null, onBack: widget.onBack),
        VCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const VKicker('Mise de départ'),
              VSeg(
                bg: V.s1,
                items: [
                  for (final v in const [2000, 5000, 10000]) thousands(v),
                  const [2000, 5000, 10000].contains(stake) ? 'Autre' : thousands(stake),
                ],
                selected: switch (stake) {
                  2000 => 0,
                  5000 => 1,
                  10000 => 2,
                  _ => 3,
                },
                onSelect: (i) => i < 3
                    ? setState(() => start.text = thousands(const [2000, 5000, 10000][i]))
                    : _otherStake(context.read<AppState>().me?.currency ?? 'XOF'),
              ),
              const SizedBox(height: 12),
              const VKicker('Nombre de paliers'),
              VSeg(
                bg: V.s1,
                items: const ['3', '4', '6', '8'],
                selected: const [3, 4, 6, 8].indexOf(count),
                onSelect: (i) => setState(() {
                  count = const [3, 4, 6, 8][i];
                  _apply();
                }),
              ),
              const SizedBox(height: 12),
              const VKicker('Cote par palier'),
              VSeg(
                bg: V.s1,
                items: [for (final (a, b) in presets) '${odds(a)}–${odds(b)}'],
                selected: preset ?? -1,
                onSelect: (i) => setState(() {
                  preset = i;
                  ramp = null;
                  _apply();
                }),
              ),
              const SizedBox(height: 8),
              // Modèle d'origine : cotes qui montent un peu à chaque palier.
              Text('ou en montée, palier après palier', style: V.mu_(12)),
              const SizedBox(height: 4),
              VSeg(
                bg: V.s1,
                items: [for (final (a, b, _) in ramps) '${odds(a)}→${odds(b)}'],
                selected: ramp ?? -1,
                onSelect: (i) => setState(() {
                  ramp = i;
                  preset = null;
                  _apply();
                }),
              ),
            ],
          ),
        ),
        VCard(
          child: VList(
            children: [
              if (goal != null)
                Row(
                  children: [
                    const Expanded(child: Text('Si tout passe')),
                    _approx('${thousands(atMiddle)} F', V.mint),
                  ],
                ),
              Row(
                children: [
                  const Expanded(child: Text('Chance d\'aller au bout')),
                  _approx(percent(chance, decimals: chance < 0.01 ? 1 : 0), V.tx),
                ],
              ),
              Row(
                children: [
                  const Expanded(child: Text('Si un palier rate')),
                  Text('−${thousands(stake)} F', style: V.b(13.5, V.coral)),
                ],
              ),
            ],
          ),
        ),
        if (!desktop)
          Align(
            alignment: Alignment.centerLeft,
            child: VLink(
              editRanges ? 'Masquer le plan' : 'Voir le plan palier par palier ›',
              onTap: () => setState(() => editRanges = !editRanges),
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
                      ramp = null;
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
        VCard(
          child: _SecureCard(
            on: secureOn,
            pct: secure,
            onChanged: (v) => setState(() => secureOn = v),
            onPct: (v) => setState(() => secure = v),
          ),
        ),
        VBtn(busy ? 'Création…' : 'Créer la montante', onTap: busy || stake < 100 ? null : _create),
      ],
    );
  }

  /// « Autre » : une mise de départ au choix.
  Future<void> _otherStake(String currency) async {
    final ctrl = TextEditingController(text: '$stake');
    final v = await showDialog<int>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: V.s1,
        title: Text('Mise de départ', style: V.b(16)),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          keyboardType: TextInputType.number,
          inputFormatters: [FilteringTextInputFormatter.digitsOnly],
          decoration: InputDecoration(suffixText: currencyLabel(currency)),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Annuler')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, int.tryParse(ctrl.text)),
            child: const Text('Valider'),
          ),
        ],
      ),
    );
    if (v != null && v > 0 && mounted) setState(() => start.text = thousands(v));
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
                    inactiveTrackColor: const Color(0xFF2E3A55),
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
    final steps = (m['steps'] as List).cast<Json>();
    final active = m['status'] == 'active';
    final current = _current;
    final waiting = active && current != null && current['bet_id'] == null;
    final bet = currentBet;

    _StepState stateOf(Json s) {
      final r = s['result'] as String? ?? 'pending';
      if (r == 'won' || r == 'partial') return _StepState.won;
      if (r == 'lost') return _StepState.lost;
      if (active && s['number'] == m['current_step']) return _StepState.current;
      return _StepState.future;
    }

    String pct(Object? v) => v == null ? '—' : percent((v as num).toDouble(), decimals: 1);
    final stakeNow = current?['stake'] as int? ?? m['cashable'] as int;

    String betLabel(Bet b) => switch (b.selections) {
      // Maquette 15 : « Brest – Nantes, +1,5 but », « Lens ou nul » (l'équipe suffit).
      [final x] => switch (lowerLabel(
        selectionLabel(x.market, x.line, x.selection, home: x.homeTeam, away: x.awayTeam),
      ).replaceFirst(RegExp(r'^plus de '), '+').replaceFirst(RegExp(r'^moins de '), '−')) {
        final l when l.contains(x.homeTeam) || l.contains(x.awayTeam) => l,
        final l => '${x.homeTeam} – ${x.awayTeam}, $l',
      },
      final l => 'Combiné de ${l.length} matchs',
    };

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            if (widget.back) ...[
              BackChevron(onTap: () => Navigator.of(context).maybePop()),
              const SizedBox(width: 4),
            ],
            Expanded(
              child: Text.rich(
                const TextSpan(
                  children: [
                    TextSpan(text: 'Ma '),
                    TextSpan(
                      text: 'montante',
                      style: TextStyle(color: V.vi2),
                    ),
                  ],
                ),
                style: V.t(24, w: FontWeight.w800, ls: -0.4),
              ),
            ),
            if (!active) ...[montanteTag(m['status'] as String), const SizedBox(width: 6)],
            VChip('n° ${m['id']}', kind: VChipKind.vi),
          ],
        ),
        // Maquette 15 : palier et plage, la mise en jeu, puis si ça passe / si j'arrête / si ça rate.
        VCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              VKicker(
                'Palier ${m['current_step']} sur ${steps.length}'
                '${current != null && active ? ' · plage ${odds(current['odds_min'])}–${odds(current['odds_max'])}' : ''}',
              ),
              Text(
                active
                    ? '${thousands(stakeNow)} F'
                    : m['status'] == 'lost'
                    ? 'perdue'
                    : '${thousands(m['cashable'] as int)} F',
                style: V.big(!active && m['status'] == 'lost' ? V.coral : V.tx),
              ),
              Text(active ? 'en jeu' : 'encaissé', style: V.mu_()),
              if (active && current != null) _Outcomes(montante: m, current: current),
            ],
          ),
        ),
        // Maquette M3 : ce qui est en jeu au palier en cours, en clair. Le joueur décide :
        // l'application ne dit jamais « continue » ni « arrête ».
        // Paliers en pastilles (vert gagné, violet en cours), puis le détail de chaque palier.
        VCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Wrap(
                spacing: 4,
                runSpacing: 4,
                children: [
                  for (final s in steps)
                    switch (stateOf(s)) {
                      _StepState.won => VChip(
                        '${s['number']}',
                        kind: VChipKind.up,
                        after: const VIc(VIcon.check, size: 12, stroke: 2.4),
                      ),
                      _StepState.lost => VChip('${s['number']}', kind: VChipKind.dn),
                      _StepState.current => VChip('${s['number']}', kind: VChipKind.vi),
                      _ => VChip('${s['number']}', kind: VChipKind.eq),
                    },
                ],
              ),
              // Maquette 15 : les paliers déjà joués, « Palier 1 · Brest – Nantes, +1,5 but » et la cote.
              if (steps.where((s) => s['bet_id'] != null || s['odds'] != null).toList() case final played
                  when played.isNotEmpty) ...[
                const SizedBox(height: 4),
                VList(
                  children: [
                    for (final s in played)
                      Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Palier ${s['number']}${switch (bets[s['bet_id']]) {
                                    final b? => ' · ${betLabel(b)}',
                                    _ => '',
                                  }}',
                                  style: V.t(13.5),
                                ),
                                // Pari du palier pas encore réglé : sa date ou « en direct ».
                                for (final x in bets[s['bet_id']]?.selections ?? const <BetSel>[])
                                  if (x.result == 'pending')
                                    Text(selectionState(x), style: V.t(11.5, color: selectionColor(x))),
                              ],
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(odds(s['odds'] ?? bets[s['bet_id']]?.totalOdds), style: V.mu_(12.5)),
                        ],
                      ),
                  ],
                ),
              ],
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
                  '${money(bet.potentialPayout, bet.currency)}.'
                  '${current['engine'] is int ? ' Proposé par le moteur ${current['engine']}.' : ''}',
            ),
          ],
          if (waiting) ...[VBtn('Voir les paris proposés', onTap: _suggestions)],
          VBtn2('Encaisser ${thousands(m['cashable'] as int)} F et arrêter', onTap: _cashOut),
        ],
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
  late final Future<(Json, Map<int, MatchInfo>)> _loading = _load(context.read<AppState>());

  /// Mode comparaison (maquette K4) : les suggestions du moteur 2, sous celles du moteur 1.
  Json? data2;

  Future<(Json, Map<int, MatchInfo>)> _load(AppState state) async {
    final api = state.api;
    final url = '/montantes/$montanteId/suggestions';
    final second = state.compareEngines
        ? api
              .get('$url?engine=2', null, ApiClient.slowTimeout)
              .then<Object?>((v) => v, onError: (Object _) => null)
        : null;
    final data = await api.get(url, null, ApiClient.slowTimeout) as Json;
    final other = await second;
    data2 = other is Json ? other : null;
    final ids = <int>{
      for (final d in [data, ?data2])
        for (final s in d['suggestions'] as List)
          for (final sel in s['selections'] as List) sel['match_id'] as int,
    }.toList();
    final infos = await Future.wait([for (final id in ids) api.get('/matches/$id')]);
    return (data, {for (final (i, id) in ids.indexed) id: MatchInfo(infos[i] as Json)});
  }

  Future<void> _play(BuildContext context, Json suggestion, Json data, {int? engine}) async {
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
        'from_suggestion': true, // suivi des montantes (M2)
        'engine': ?engine, // comparaison des moteurs (K4) : le palier garde le nom du moteur
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
            if (err is ApiException && err.montanteFinished) {
              return ListView(
                padding: padding,
                children: [
                  header,
                  EmptyState(
                    'Cette montante est terminée : plus de pari possible pour elle. Lance-en une '
                    'nouvelle depuis l\'onglet Montante.',
                    icon: Icons.flag_rounded,
                  ),
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.add_rounded),
                    label: const Text('Créer une nouvelle montante'),
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
                      color: Fp.warningBg,
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: Fp.warningLine),
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
                else if (!allBelow || showAnyway) ...[
                  if (data2 != null) ...[
                    const SizedBox(height: 12),
                    const Align(alignment: Alignment.centerLeft, child: EngineTag(1)),
                  ],
                  const SizedBox(height: 8),
                  MCard(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
                    child: Column(
                      children: [
                        for (final (i, s) in list.indexed) ...[
                          if (i > 0) const Divider(height: 1, thickness: 1, color: Fp.divider),
                          _SuggestionCard(
                            s: s,
                            matches: matches,
                            onPlay: () => _play(context, s, data, engine: data2 == null ? null : 1),
                          ),
                        ],
                      ],
                    ),
                  ),
                ],
                if (data2 case final d2?) ..._engine2(context, d2, data, matches),
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

extension on _SuggestionsScreenState {
  /// Maquette K4 : les suggestions du moteur 2 pour le même palier, marquées « MOTEUR 2 ».
  List<Widget> _engine2(BuildContext context, Json d2, Json data, Map<int, MatchInfo> matches) {
    final list = (d2['suggestions'] as List).cast<Json>();
    return [
      const SizedBox(height: 16),
      const Align(alignment: Alignment.centerLeft, child: EngineTag(2)),
      const SizedBox(height: 8),
      if (list.isEmpty)
        Text(
          'Le moteur 2 n\'a aucun pari avec une cote réelle dans cette plage pour l\'instant.',
          style: Fp.body(13, color: Fp.text2, height: 1.4),
        )
      else
        MCard(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
          child: Column(
            children: [
              for (final (i, s) in list.indexed) ...[
                if (i > 0) const Divider(height: 1, thickness: 1, color: Fp.divider),
                _SuggestionCard(s: s, matches: matches, onPlay: () => _play(context, s, data, engine: 2)),
              ],
            ],
          ),
        ),
      const SizedBox(height: 6),
      Text(
        'Moteur 2 : les paris les mieux payés (prix proche de la cote juste selon la cote de référence) '
        'd\'abord, puis la cote la plus basse.',
        style: Fp.body(12, color: Fp.text2, height: 1.4),
      ),
    ];
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
                  Wrap(
                    spacing: 8,
                    runSpacing: 4,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      Text(
                        'moteur ${percent(model)} · selon la cote ${percent(implied, decimals: 1)}',
                        style: Fp.body(13, color: Fp.muted),
                      ),
                      GapBadge(
                        engine: model,
                        implied: implied,
                        nation: sels.any((x) => isNation(matches[x['match_id']]?.competition)),
                      ),
                    ],
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

/// Si ça passe, si j'arrête, si ça rate (maquette 15).
class _Outcomes extends StatelessWidget {
  const _Outcomes({required this.montante, required this.current});
  final Json montante;
  final Json current;

  @override
  Widget build(BuildContext context) {
    final m = montante;
    final cashable = (m['cashable'] as num? ?? 0).toInt();
    final stake = (current['stake'] as num? ?? 0).toInt();
    // Pari du palier placé : gain exact. Sinon : à la cote du milieu de la plage, arrondi à la centaine.
    final placed = (current['potential_payout'] as num?)?.toInt();
    final middle = (double.parse('${current['odds_min']}') + double.parse('${current['odds_max']}')) / 2;
    final payout = placed ?? stake + ((stake * middle - stake) / 100).round() * 100;
    Widget box(String label, String value, Color color) => Expanded(
      child: VCard2(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: V.mu_()),
            FittedBox(
              fit: BoxFit.scaleDown,
              child: Text(value, style: V.b(13.5, color)),
            ),
          ],
        ),
      ),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: 10),
        Row(
          children: [
            box('Si ça passe', '+${thousands(payout - stake)}', V.mint),
            const SizedBox(width: 6),
            box('Si j\'arrête', thousands(cashable), V.tx),
            const SizedBox(width: 6),
            box('Si ça rate', '−${thousands(stake)}', V.coral),
          ],
        ),
      ],
    );
  }
}
