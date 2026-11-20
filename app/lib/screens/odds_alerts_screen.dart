// « Mes alertes de cote » : copie de la maquette 29 du testeur (docs/maquettes/12-nouveau-visage).
// Une alerte sur une sélection (« préviens-moi quand la cote atteint 1,95 ») ou une alerte
// d'écart (« dès qu'un pari dépasse la cote de 8 points »). Le serveur vérifie après chaque
// relevé des cotes (bookmaker/odds_alerts.py) : au plus une alerte par match, jamais la nuit.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../widgets/common.dart';
import '../widgets/visage.dart';
import 'search_screen.dart';

String _pct(double p) => '${(p * 100).round()}$nbsp%';

class OddsAlertsScreen extends StatefulWidget {
  const OddsAlertsScreen({super.key});

  @override
  State<OddsAlertsScreen> createState() => _OddsAlertsScreenState();
}

class _OddsAlertsScreenState extends State<OddsAlertsScreen> {
  late final AppState state = context.read<AppState>();
  Json? data;
  bool failed = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final d = await state.api.get('/me/odds-alerts') as Json;
      if (mounted) {
        setState(() {
          data = d;
          failed = false;
        });
      }
    } on ApiException {
      if (mounted) setState(() => failed = true);
    }
  }

  Future<void> _run(Future<Object?> Function() action) async {
    try {
      await action();
      await _load();
    } on ApiException catch (e) {
      if (mounted) showError(context, e);
    }
  }

  Future<void> _create() async {
    final match = await Navigator.of(context)
        .push<MatchInfo>(MaterialPageRoute(builder: (_) => const SearchScreen(pickMatch: true)));
    if (match == null || !mounted) return;
    final created = await Navigator.of(context)
        .push<bool>(MaterialPageRoute(builder: (_) => AlertPickScreen(match: match)));
    if (created == true) await _load();
  }

  Future<void> _addHit(Json h) async {
    try {
      final id = h['match_id'] as int;
      final match = MatchInfo(await state.api.get('/matches/$id') as Json);
      final offers = [for (final o in await state.api.get('/matches/$id/offer') as List) Offer(o as Json)];
      final offer = offers
          .where(
            (o) => o.market == h['market'] && o.line == (h['line'] ?? '') && o.selection == h['selection'],
          )
          .firstOrNull;
      if (!mounted) return;
      final msg = offer == null ? 'Cette cote n\'est plus proposée.' : state.toggleCoupon(match, offer);
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text(msg)));
    } on ApiException catch (e) {
      if (mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = data;
    final children = <Widget>[
      VTopBar('Mes alertes de cote', action: VIcon.plus, actionLabel: 'Nouvelle alerte', onAction: _create),
    ];
    if (d == null) {
      children.add(const SizedBox(height: 40));
      children.add(
        failed
            ? Text('Alertes indisponibles pour le moment.', textAlign: TextAlign.center, style: V.mu_(13))
            : const Center(child: CircularProgressIndicator()),
      );
      return VPage(children: children);
    }
    final alerts = (d['alerts'] as List).cast<Json>();
    final gap = d['gap'] as Json?;
    final hits = (d['hits'] as List).cast<Json>();
    final gapValue = (gap?['min_gap'] as num?)?.toDouble() ?? 0.08;
    for (final a in alerts) {
      final engine = (a['engine'] as num?)?.toDouble();
      final now = a['odds'] as num?;
      final triggered = a['triggered_at'] != null;
      children.add(
        VCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('${a['home']} – ${a['away']}', style: V.b(15)),
                        Text(a['label'] as String, style: V.mu_(12.5)),
                      ],
                    ),
                  ),
                  if (triggered || a['open'] != true)
                    GestureDetector(
                      onTap: () => _run(() => state.api.delete('/me/odds-alerts/${a['id']}')),
                      child: Text(
                        'Retirer',
                        style: V.t(13, w: FontWeight.w600, color: V.vi2),
                      ),
                    )
                  else
                    VSwitch(
                      value: a['active'] == true,
                      label: 'Alerte active',
                      onChanged: (v) =>
                          _run(() => state.api.patch('/me/odds-alerts/${a['id']}', {'active': v})),
                    ),
                ],
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  _Fig('moteur', engine == null ? '—' : _pct(engine)),
                  _Fig('cote actuelle', now == null ? '—' : '${odds(now)} (${_pct(1 / now.toDouble())})'),
                  _Fig(triggered ? 'déclenchée à' : 'alerte à', '≥ ${odds(a['target_odds'])}'),
                ],
              ),
            ],
          ),
        ),
      );
    }
    // Maquette 29 : carte simple ; le seuil (5, 8 ou 10 points) se règle en la touchant.
    final gaps = (d['gaps'] as List).cast<num>();
    children.add(
      VCard(
        onTap: () async {
          final g = await showModalBottomSheet<num>(
            context: context,
            backgroundColor: V.s1,
            builder: (ctx) => SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 12),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text('Prévenir dès que le moteur dépasse la cote de', style: V.b(15)),
                    const SizedBox(height: 12),
                    VSeg(
                      bg: V.s2,
                      items: [for (final g in gaps) '${(g * 100).round()} points'],
                      selected: gaps.indexWhere((g) => (g - gapValue).abs() < 1e-6),
                      onSelect: (i) => Navigator.pop(ctx, gaps[i]),
                    ),
                  ],
                ),
              ),
            ),
          );
          if (g != null) {
            await _run(
              () => state.api.put('/me/odds-alerts/gap', {'min_gap': g, 'active': gap?['active'] ?? true}),
            );
          }
        },
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Tous les championnats', style: V.b(15)),
                  Text(
                    'dès qu\'un pari dépasse la cote de ${(gapValue * 100).round()} points',
                    style: V.mu_(12.5),
                  ),
                ],
              ),
            ),
            VSwitch(
              value: gap?['active'] == true,
              label: 'Alerte d\'écart',
              onChanged: (v) =>
                  _run(() => state.api.put('/me/odds-alerts/gap', {'min_gap': gapValue, 'active': v})),
            ),
          ],
        ),
      ),
    );
    for (final h in hits) {
      final at = parseDate(h['at'])?.toLocal();
      final engine = (h['engine'] as num).toDouble();
      final implied = (h['implied'] as num).toDouble();
      children.add(
        VCard(
          border: const Color(0xFF1D5A44),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'Déclenchée ${at == null ? '' : '${_today(at) ? '' : '${shortDate(at)} '}à ${hourMinute(at)}'}'
                    .toUpperCase(),
                style: V.t(10.5, w: FontWeight.w700, color: V.mint, ls: 0.8),
              ),
              const SizedBox(height: 4),
              Text('${h['home']} – ${h['away']} · ${lowerLabel(h['label'] as String)}', style: V.b(15)),
              const SizedBox(height: 6),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      h['from_odds'] == null
                          ? 'cote ${odds(h['odds'])} · moteur ${_pct(engine)}'
                          : 'cote ${odds(h['from_odds'])} → ${odds(h['odds'])}',
                      style: V.t(12.5, color: V.mu),
                    ),
                  ),
                  VGapChip(engine: engine, implied: implied),
                ],
              ),
              if (h['open'] == true) VBtn('Ajouter au coupon', height: 42, onTap: () => _addHit(h)),
            ],
          ),
        ),
      );
    }
    children.add(const VInfo('Au plus une alerte par match, jamais entre 23 h et 8 h.'));
    return VPage(onRefresh: _load, children: children);
  }

  static bool _today(DateTime d) {
    final n = DateTime.now();
    return d.year == n.year && d.month == n.month && d.day == n.day;
  }
}

class _Fig extends StatelessWidget {
  const _Fig(this.label, this.value);
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Expanded(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: V.mu_(12.5)),
        Text(value, style: V.b(15)),
      ],
    ),
  );
}

/// Choix de la sélection d'un match, puis de la cote visée.
class AlertPickScreen extends StatelessWidget {
  const AlertPickScreen({super.key, required this.match});
  final MatchInfo match;

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    final m = match;
    return Scaffold(
      backgroundColor: V.bg,
      body: SafeArea(
        child: Loader<List<Offer>>(
          load: () async => [
            for (final o in await api.get('/matches/${m.id}/offer') as List) Offer(o as Json),
          ],
          builder: (context, offers, _) {
            final rows = offers.where((o) => o.modelProbability != null).toList();
            return VPage(
              children: [
                const VTopBar('Nouvelle alerte'),
                const SizedBox(height: 6),
                Text('${m.home.name} – ${m.away.name}', style: V.b(17)),
                Text('Choisis la sélection à surveiller.', style: V.mu_(12.5)),
                VCard(
                  child: rows.isEmpty
                      ? Text('Pas de cote récente pour ce match.', style: V.mu_(12.5))
                      : VList(
                          children: [
                            for (final o in rows)
                              GestureDetector(
                                behavior: HitTestBehavior.opaque,
                                onTap: () => _target(context, o),
                                child: Row(
                                  children: [
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            selectionLabel(
                                              o.market,
                                              o.line,
                                              o.selection,
                                              home: m.home.name,
                                              away: m.away.name,
                                            ),
                                            style: V.b(),
                                          ),
                                          Text(
                                            'moteur ${_pct(o.modelProbability!)} · cote ${_pct(1 / o.odds)}',
                                            style: V.mu_(),
                                          ),
                                        ],
                                      ),
                                    ),
                                    VOdd(odds(o.odds)),
                                  ],
                                ),
                              ),
                          ],
                        ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  Future<void> _target(BuildContext context, Offer o) async {
    final api = context.read<AppState>().api;
    // Cote visée proposée : celle où la cote donne 5 points de moins que le moteur, au moins
    // 0,05 au-dessus de l'actuelle.
    final p = o.modelProbability!;
    var target = ((1 / (p - 0.05).clamp(0.02, 0.99)) * 100).ceil() / 100;
    if (target < o.odds + 0.05) target = ((o.odds + 0.05) * 100).round() / 100;
    final chosen = await showModalBottomSheet<double>(
      context: context,
      backgroundColor: V.s1,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) => _TargetSheet(offer: o, initial: target),
    );
    if (chosen == null || !context.mounted) return;
    try {
      await api.post('/me/odds-alerts', {
        'match_id': match.id,
        'market': o.market,
        'line': o.line,
        'selection': o.selection,
        'target_odds': chosen.toStringAsFixed(2),
      });
      if (context.mounted) Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      if (context.mounted) showError(context, e);
    }
  }
}

class _TargetSheet extends StatefulWidget {
  const _TargetSheet({required this.offer, required this.initial});
  final Offer offer;
  final double initial;

  @override
  State<_TargetSheet> createState() => _TargetSheetState();
}

class _TargetSheetState extends State<_TargetSheet> {
  late double target = widget.initial;

  @override
  Widget build(BuildContext context) {
    final o = widget.offer;
    final min = ((o.odds + 0.01) * 100).round() / 100;
    Widget step(String label, double delta) => Expanded(
      child: VBtn2(
        label,
        onTap: () => setState(
          () => target = ((target + delta) * 100).round() / 100 < min
              ? min
              : ((target + delta) * 100).round() / 100,
        ),
      ),
    );
    return Padding(
      padding: const EdgeInsets.all(16),
      child: DefaultTextStyle(
        style: V.t(13.5),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Me prévenir quand la cote atteint', style: V.b(16)),
            const SizedBox(height: 4),
            Text(
              'Cote actuelle ${odds(o.odds)} (${_pct(1 / o.odds)}) · moteur ${_pct(o.modelProbability!)}',
              style: V.mu_(12),
            ),
            const SizedBox(height: 12),
            Center(child: Text('≥ ${odds(target)}', style: V.big())),
            Center(child: Text('la cote donnerait ${_pct(1 / target)}', style: V.mu_())),
            Row(children: [step('− 0,05', -0.05), const SizedBox(width: 8), step('+ 0,05', 0.05)]),
            VBtn('Créer l\'alerte', onTap: () => Navigator.pop(context, target)),
          ],
        ),
      ),
    );
  }
}
