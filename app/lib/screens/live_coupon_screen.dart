// Coupon en direct (maquettes D9 à D11 validées le 13/11/2026) : propositions du moteur
// pendant trois fenêtres de chaque match (pause → 50e, 60e-63e, 75e-78e), une sélection par
// match, combinés de plusieurs matchs. Étude du 13/11/2026 sur 13 347 matchs : chances
// justes à ces trois moments. Aucune notification : le joueur vient les chercher.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../desktop/layout.dart';
import '../format.dart';
import '../labels.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'premium_screen.dart';

const liveProfiles = ['Sûr', 'Équilibré', 'Audacieux'];

class LiveCouponScreen extends StatefulWidget {
  const LiveCouponScreen({super.key});

  @override
  State<LiveCouponScreen> createState() => _LiveCouponScreenState();
}

class _LiveCouponScreenState extends State<LiveCouponScreen> {
  late final AppState _state = context.read<AppState>();
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _state.loadLiveCoupons();
    // Les fenêtres s'ouvrent et se ferment à la minute : relu toutes les 30 s, écran ouvert.
    _timer = Timer.periodic(const Duration(seconds: 30), (_) {
      if (_state.foreground.value) _state.loadLiveCoupons();
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: ValueListenableBuilder<LiveCoupons?>(
          valueListenable: _state.liveCoupons,
          builder: (context, lc, _) => RefreshIndicator(
            onRefresh: _state.loadLiveCoupons,
            child: ListView(
              padding: pagePadding(context, 16, 40, maxWidth: 720),
              children: [
                Row(
                  children: [
                    BackChevron(onTap: () => Navigator.of(context).maybePop()),
                    const SizedBox(width: 4),
                    Flexible(
                      child: Text('Coupon en direct', style: Fp.title(22), overflow: TextOverflow.ellipsis),
                    ),
                    if (lc?.trial ?? true) ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: const Color(0xFF1F1709),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          'En test',
                          style: Fp.body(11, weight: FontWeight.w700, color: Fp.warning),
                        ),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 12),
                _Info(
                  lc?.indicative ?? true
                      ? 'Cotes indicatives, relevées en direct chez un autre bookmaker : vérifie-les dans '
                            '1xBet avant de parier. Si tu viens de perdre, fais une pause.'
                      : 'Cotes 1xBet en direct : elles bougent vite, vérifie-les avant de parier. Si tu '
                            'viens de perdre, fais une pause.',
                ),
                if (lc == null)
                  const Padding(
                    padding: EdgeInsets.all(32),
                    child: Center(child: CircularProgressIndicator()),
                  )
                else if (lc.nothingWorthIt)
                  const EmptyState(
                    'Aucun coupon intéressant pendant cette fenêtre : le moteur ne trouve pas de cote '
                    'assez généreuse.\nC\'est normal : il ne propose que si sa chance dépasse celle de la '
                    'cote d\'au moins 3 points.',
                    icon: Icons.hourglass_empty_rounded,
                  )
                else if (!lc.open)
                  const EmptyState(
                    'Aucun match ouvert en ce moment.\nLe coupon en direct s\'ouvre à la pause (jusqu\'à la '
                    '50e), de la 60e à la 63e et de la 75e à la 78e.',
                    icon: Icons.sensors_rounded,
                  )
                else ...[
                  const SizedBox(height: 14),
                  Text(
                    'Combinés du moteur · ${lc.matches.length} match${lc.matches.length > 1 ? 's' : ''} '
                    'ouvert${lc.matches.length > 1 ? 's' : ''}',
                    style: Fp.body(13, color: Fp.muted, weight: FontWeight.w700),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      for (final (i, p) in liveProfiles.indexed) ...[
                        if (i > 0) const SizedBox(width: 6),
                        Expanded(
                          child: _ProfileTile(
                            profile: p,
                            combo: lc.combos[p],
                            indicative: lc.indicative,
                            onTap: () => _open(context, lc, p),
                          ),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Par match',
                    style: Fp.body(13, color: Fp.muted, weight: FontWeight.w700),
                  ),
                  for (final m in lc.matches) _MatchRow(match: m, indicative: lc.indicative),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _open(BuildContext context, LiveCoupons lc, String profile) {
    final combo = lc.combos[profile];
    if (combo == null) return;
    if (combo.locked) {
      openPremium(context);
      return;
    }
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Fp.card,
      builder: (sheet) => _ComboSheet(profile: profile, combo: combo, coupons: lc),
    );
  }
}

String _moment(LiveCouponMatch m) => m.apiStatus == 'HT' ? 'MT' : "${m.minute ?? ''}'";

String _oddsText(Object v, bool indicative) => indicative ? '≈ ${odds(v)}' : odds(v);

class _Info extends StatelessWidget {
  const _Info(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
    decoration: BoxDecoration(
      color: Fp.fill6,
      borderRadius: BorderRadius.circular(14),
      border: Border.all(color: Fp.line12),
    ),
    child: Text(text, style: Fp.body(12.5, color: Fp.textSoft, height: 1.45)),
  );
}

class _ProfileTile extends StatelessWidget {
  const _ProfileTile({
    required this.profile,
    required this.combo,
    required this.indicative,
    required this.onTap,
  });
  final String profile;
  final LiveCombo? combo;
  final bool indicative;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final c = combo;
    final first = profile == liveProfiles.first;
    return Material(
      color: first ? Fp.cardHigh : Fp.card,
      borderRadius: BorderRadius.circular(14),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: c == null ? null : onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 4),
          decoration: first
              ? BoxDecoration(
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: Fp.accent2, width: 1.5),
                )
              : null,
          child: Column(
            children: [
              Text(
                c == null ? profile : '$profile · ${c.size}',
                style: Fp.body(12, color: Fp.muted),
                textAlign: TextAlign.center,
              ),
              Text(
                c == null ? '—' : chancePercent(c.probability),
                style: Fp.body(16, weight: FontWeight.w800),
              ),
              Text(
                c == null ? 'rien à proposer' : 'cote ${_oddsText(c.odds, indicative)}',
                style: Fp.body(12, color: Fp.muted),
              ),
              if (c != null && c.locked) Text('Premium', style: Fp.body(11, color: Fp.warning)),
              if (c != null && !c.locked && c.belowOdds)
                Text('moteur < cote', style: Fp.body(11, color: Fp.warning)),
            ],
          ),
        ),
      ),
    );
  }
}

class _MatchRow extends StatelessWidget {
  const _MatchRow({required this.match, required this.indicative});
  final LiveCouponMatch match;
  final bool indicative;

  @override
  Widget build(BuildContext context) {
    final m = match;
    final sure = m.picks['Sûr'];
    final left = m.apiStatus == 'HT' ? null : m.closesAt - (m.minute ?? m.closesAt);
    return Container(
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      decoration: BoxDecoration(color: Fp.card, borderRadius: BorderRadius.circular(18)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '${m.home} ${m.score.isNotEmpty ? m.score[0] ?? 0 : 0}-'
                  '${m.score.length > 1 ? m.score[1] ?? 0 : 0} ${m.away}',
                  style: Fp.body(14.5, weight: FontWeight.w700),
                ),
              ),
              Text(
                m.apiStatus == 'HT' ? '● Mi-temps' : '● ${m.minute}\'',
                style: Fp.body(
                  12.5,
                  color: m.apiStatus == 'HT' ? Fp.warning : Fp.win,
                  weight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Row(
            children: [
              Expanded(
                child: Text(
                  sure == null
                      ? 'Pas de proposition Sûr pour ce match'
                      : 'Sûr : ${selectionLabel(sure.market, sure.line, sure.selection, home: m.home, away: m.away).toLowerCase()}'
                            ' · ${chancePercent(sure.probability)} · ${_oddsText(sure.odds, indicative)}',
                  style: Fp.body(12.5, color: Fp.muted),
                ),
              ),
              Text(
                left == null || left > 3 ? 'jusqu\'à la ${m.closesAt}e' : 'encore $left min',
                style: Fp.body(12, color: Fp.warning),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ComboSheet extends StatelessWidget {
  const _ComboSheet({required this.profile, required this.combo, required this.coupons});
  final String profile;
  final LiveCombo combo;
  final LiveCoupons coupons;

  @override
  Widget build(BuildContext context) {
    final state = context.read<AppState>();
    final byId = {for (final m in coupons.matches) m.id: m};
    final ind = coupons.indicative;
    final tenths = (combo.probability * 10).round();
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(18, 16, 18, 18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              '$profile · ${combo.size == 1 ? '1 match' : 'combiné de ${combo.size} matchs'}',
              style: Fp.title(17),
            ),
            Container(
              margin: const EdgeInsets.only(top: 12),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFF12301F),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: const Color(0xFF1F5B3A)),
              ),
              child: Text(
                'Chance selon le moteur : ${chancePercent(combo.probability)} · environ $tenths sur 10.\n'
                'Calculée avec le score et la minute de chaque match. Vérifiée sur 13 347 matchs passés.',
                style: Fp.body(13, color: const Color(0xFFC9F5D9), height: 1.4),
              ),
            ),
            for (final s in combo.selections)
              if (byId[s.matchId] case final m?)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              '${m.home} – ${m.away} · ${_moment(m)}',
                              style: Fp.body(12, color: Fp.muted),
                            ),
                            Text(
                              selectionLabel(s.market, s.line, s.selection, home: m.home, away: m.away),
                              style: Fp.body(14.5, weight: FontWeight.w700),
                            ),
                            Text(
                              'moteur ${chancePercent(s.probability)} · selon la cote '
                              '${chancePercent(1 / (double.tryParse(s.odds) ?? 1))}',
                              style: Fp.body(12, color: s.belowOdds ? Fp.warning : Fp.muted),
                            ),
                          ],
                        ),
                      ),
                      Text(
                        _oddsText(s.odds, ind),
                        style: Fp.body(16, weight: FontWeight.w800, color: ind ? Fp.warning : Fp.text),
                      ),
                    ],
                  ),
                ),
            if (combo.belowOdds)
              Container(
                margin: const EdgeInsets.only(top: 12),
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: const Color(0xFF1F1709),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: const Color(0xFF6B4F1D)),
                ),
                child: Text(
                  'Le moteur est moins confiant que la cote : ${chancePercent(combo.probability)} contre '
                  '${chancePercent(1 / combo.odds)} selon la cote. Un joueur prudent attend la prochaine '
                  'proposition.',
                  style: Fp.body(12.5, color: Fp.warning, height: 1.4),
                ),
              ),
            if (ind)
              Container(
                margin: const EdgeInsets.only(top: 12),
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: const Color(0xFF1F1709),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: const Color(0xFF6B4F1D)),
                ),
                child: Text(
                  'Cotes indicatives : relevées chez un autre bookmaker, elles peuvent différer de 1xBet de '
                  'quelques centièmes. Vérifie la cote dans 1xBet avant de parier.',
                  style: Fp.body(12.5, color: Fp.warning, height: 1.4),
                ),
              ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: Text(
                    ind ? 'Cote indicative du combiné' : 'Cote du combiné (1xBet)',
                    style: Fp.body(13, color: Fp.muted),
                  ),
                ),
                Text(_oddsText(combo.odds, ind), style: Fp.body(15, weight: FontWeight.w800)),
              ],
            ),
            const SizedBox(height: 14),
            FilledButton(
              onPressed: () {
                final msg = state.addLiveSelections(combo.selections, byId);
                Navigator.pop(context);
                showMessage(msg);
                if (msg == 'Ajouté au coupon') {
                  Navigator.of(context).popUntil((r) => r.isFirst);
                  state.openTab(1);
                }
              },
              style: FilledButton.styleFrom(
                minimumSize: const Size.fromHeight(50),
                shape: const StadiumBorder(),
                backgroundColor: Fp.accent,
              ),
              child: const Text('Ajouter à mon coupon'),
            ),
            const SizedBox(height: 10),
            Text(
              'Dans 1xBet : Direct → Football → chaque match, puis la sélection ci-dessus. '
              'Argent fictif dans FootProba ; ce n\'est pas un conseil de pari.',
              style: Fp.body(12, color: Fp.muted, height: 1.4),
            ),
          ],
        ),
      ),
    );
  }
}
