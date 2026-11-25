import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../desktop/layout.dart';
import '../api/models.dart';
import '../format.dart';
import '../state/app_state.dart';
import 'create_screen.dart' show HomeTab;
import '../widgets/common.dart';
import '../widgets/visage.dart';
import 'daily_coupons_screen.dart';
import 'odds_alerts_screen.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  Key _key = UniqueKey();

  Future<void> _readAll() async {
    final state = context.read<AppState>();
    await guard(context, () => state.api.post('/me/notifications/read-all'));
    state.setUnread(0);
    setState(() => _key = UniqueKey());
  }

  /// « Tout effacer », après confirmation (revue du 07/11/2026 : rien ne s'effaçait).
  Future<void> _deleteAll() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Effacer toutes les notifications ?'),
        content: const Text('Elles disparaissent de ce téléphone et de ton compte.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Annuler')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Tout effacer')),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    final state = context.read<AppState>();
    await guard(context, () => state.api.delete('/me/notifications'));
    state.setUnread(0);
    setState(() => _key = UniqueKey());
  }

  /// « il y a 5 min », « il y a 3 h », « hier, 22:51 », « 12/10/2026 ».
  static String _ago(DateTime d) {
    final now = DateTime.now();
    final l = d.toLocal();
    final diff = now.difference(l);
    if (diff.inMinutes < 1) return 'à l\'instant';
    if (diff.inMinutes < 60) return 'il y a ${diff.inMinutes} min';
    if (_day(l) == _day(now)) return 'il y a ${diff.inHours} h';
    if (_day(l) == _day(now.subtract(const Duration(days: 1)))) return 'hier, ${hourMinute(l)}';
    return '${numericDate(l)}, ${hourMinute(l)}';
  }

  static DateTime _day(DateTime d) => DateTime(d.year, d.month, d.day);

  static String _group(DateTime d) {
    final now = DateTime.now();
    final day = _day(d.toLocal());
    if (day == _day(now)) return 'Aujourd\'hui';
    if (day == _day(now.subtract(const Duration(days: 1)))) return 'Hier';
    return longDate(day);
  }

  Future<void> _open(Json n) async {
    final state = context.read<AppState>();
    if (n['read_at'] == null) {
      await guard(context, () => state.api.post('/me/notifications/${n['id']}/read'));
      await state.refreshUnread();
      setState(() => _key = UniqueKey());
    }
    if (!mounted) return;
    // Coupons du jour : l'écran où copier les codes ; alerte : mes alertes ; matchs d'un
    // coupon : le suivi dans Mes paris.
    if (n['kind'] == 'daily_coupons') {
      await Navigator.of(context).push(MaterialPageRoute(builder: (_) => const DailyCouponsScreen()));
    } else if (n['kind'] == 'odds_alert') {
      await Navigator.of(context).push(MaterialPageRoute(builder: (_) => const OddsAlertsScreen()));
    } else if (_betKinds.contains(n['kind'])) {
      Navigator.of(context).popUntil((r) => r.isFirst);
      state.openTab(HomeTab.paris);
    }
  }

  Future<void> _delete(List<Json> list, List<Json> items) async {
    final state = context.read<AppState>();
    setState(() => list.removeWhere(items.contains));
    for (final n in items) {
      await guard(context, () => state.api.delete('/me/notifications/${n['id']}'));
    }
    await state.refreshUnread();
  }

  /// Maquette 24 : un pari = une carte, ses notifications en frise (la plus récente en bas).
  static List<List<Json>> _cards(List<Json> day) {
    final out = <List<Json>>[];
    final byBet = <Object, List<Json>>{};
    for (final n in day) {
      final bet = (n['data'] as Map?)?['bet_id'];
      if (bet != null && _betKinds.contains(n['kind'])) {
        final group = byBet[bet];
        if (group != null) {
          group.add(n);
          continue;
        }
        byBet[bet] = [n];
        out.add(byBet[bet]!);
      } else {
        out.add([n]);
      }
    }
    return out;
  }

  static VDotKind _dot(Json n) {
    final data = (n['data'] as Map?) ?? const {};
    return switch (n['kind']) {
      'bet_settled' when const {'won', 'partial'}.contains(data['outcome']) => VDotKind.green,
      'bet_settled' when data['outcome'] == 'lost' => VDotKind.red,
      _ => VDotKind.plain,
    };
  }

  @override
  Widget build(BuildContext context) {
    final state = context.read<AppState>();
    return Scaffold(
      backgroundColor: V.bg,
      body: SafeArea(
        child: Loader<List<Json>>(
          key: _key,
          load: () async => (await state.api.get('/me/notifications', {'limit': 100}) as List).cast<Json>(),
          builder: (context, list, reload) {
            final days = <String, List<Json>>{};
            for (final n in list) {
              days.putIfAbsent(_group(parseDate(n['created_at']) ?? DateTime.now()), () => []).add(n);
            }
            return RefreshIndicator(
              onRefresh: reload,
              child: ListView(
                padding: pagePadding(context, 16, 32, maxWidth: 640),
                children: [
                  const VTopBar('Notifications'),
                  if (list.isNotEmpty)
                    Row(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        VLink('Tout lire', onTap: _readAll),
                        const SizedBox(width: 16),
                        GestureDetector(
                          onTap: _deleteAll,
                          child: Text('Tout effacer', style: V.t(13.5, color: V.mu)),
                        ),
                      ],
                    ),
                  if (list.isEmpty)
                    VCard(
                      child: Text('Aucune notification.', style: V.t(13.5, color: V.mu)),
                    ),
                  for (final MapEntry(key: day, value: items) in days.entries) ...[
                    Padding(padding: const EdgeInsets.only(top: 16, left: 2), child: VKicker(day)),
                    for (final card in _cards(items))
                      Dismissible(
                        key: ValueKey('notification-${card.first['id']}'),
                        direction: DismissDirection.endToStart,
                        background: Container(
                          margin: const EdgeInsets.only(top: 12),
                          padding: const EdgeInsets.only(right: 20),
                          alignment: Alignment.centerRight,
                          decoration: BoxDecoration(
                            color: V.coralbg,
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: Text('Effacer', style: V.b(14, V.coral)),
                        ),
                        onDismissed: (_) => _delete(list, card),
                        child: card.length > 1 ? _betCard(card) : _single(card.first),
                      ),
                  ],
                  if (list.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 14),
                      child: Text(
                        'Glisse une notification vers la gauche pour l\'effacer.',
                        textAlign: TextAlign.center,
                        style: V.mu_(11.5),
                      ),
                    ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _time(DateTime when, bool unread) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Text(_ago(when), style: V.mu_(11.5)),
      if (unread) ...[const SizedBox(width: 6), const VDot(color: V.vi)],
    ],
  );

  Widget _single(Json n) {
    final when = parseDate(n['created_at']) ?? DateTime.now();
    final data = (n['data'] as Map?) ?? const {};
    final won = n['kind'] == 'bet_settled' && const {'won', 'partial'}.contains(data['outcome']);
    return VCard(
      onTap: () => _open(n),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(withoutEmoji('${n['title']}'), style: V.b(14.5)),
                const SizedBox(height: 2),
                Text(withoutEmoji('${n['body']}'), style: V.t(12.5, color: V.mu)),
              ],
            ),
          ),
          const SizedBox(width: 10),
          if (won && data['payout'] is num)
            VChip('+${thousands(data['payout'] as num)}', kind: VChipKind.up)
          else
            _time(when, n['read_at'] == null),
        ],
      ),
    );
  }

  Widget _betCard(List<Json> items) {
    final first = items.first;
    final latest = parseDate(first['created_at']) ?? DateTime.now();
    final unread = items.any((n) => n['read_at'] == null);
    final bet = (first['data'] as Map?)?['bet_id'];
    return VCard(
      onTap: () => _open(first),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(child: Text('Pari n° $bet', style: V.b(14.5))),
              _time(latest, unread),
            ],
          ),
          const SizedBox(height: 8),
          VTimeline(items: [for (final n in items.reversed) (withoutEmoji('${n['body']}'), _dot(n))]),
        ],
      ),
    );
  }
}

/// Notifications des matchs d'un coupon : touchées, elles ouvrent Mes paris.
const _betKinds = {'bet_kickoff', 'bet_live', 'bet_settled'};
