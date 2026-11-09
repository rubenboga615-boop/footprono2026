import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../desktop/layout.dart';
import '../api/models.dart';
import '../format.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'daily_coupons_screen.dart';

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

  static IconData _icon(String kind) {
    if (kind == 'daily_coupons') return Icons.today_rounded;
    if (kind.startsWith('montante')) return Icons.stairs_rounded;
    if (kind.startsWith('premium')) return Icons.workspace_premium_outlined;
    if (kind == 'bet_corrected') return Icons.edit_note_rounded;
    if (kind == 'announcement') return Icons.campaign_outlined;
    if (kind == 'wallet_credit') return Icons.account_balance_wallet_outlined;
    if (kind.startsWith('bet')) return Icons.confirmation_number_outlined;
    return Icons.notifications_none_rounded;
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

  @override
  Widget build(BuildContext context) {
    final state = context.read<AppState>();
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Loader<List<Json>>(
          key: _key,
          load: () async => (await state.api.get('/me/notifications', {'limit': 100}) as List).cast<Json>(),
          builder: (context, list, reload) {
            final children = <Widget>[];
            String? last;
            for (final n in list) {
              final when = parseDate(n['created_at']) ?? DateTime.now();
              final g = _group(when);
              if (g != last) {
                children.add(SectionTitle(g));
                last = g;
              }
              final unread = n['read_at'] == null;
              children.add(
                // Glisser vers la gauche : effacée.
                Dismissible(
                  key: ValueKey('notification-${n['id']}'),
                  direction: DismissDirection.endToStart,
                  background: Container(
                    margin: const EdgeInsets.only(bottom: 12),
                    padding: const EdgeInsets.only(right: 20),
                    alignment: Alignment.centerRight,
                    decoration: BoxDecoration(
                      color: Fp.loss.withValues(alpha: 0.35),
                      borderRadius: BorderRadius.circular(18),
                    ),
                    child: Text('Effacer', style: Fp.body(14, weight: FontWeight.w700)),
                  ),
                  onDismissed: (_) async {
                    setState(() => list.remove(n));
                    await guard(context, () => state.api.delete('/me/notifications/${n['id']}'));
                    await state.refreshUnread();
                  },
                  child: GlassCard(
                    margin: const EdgeInsets.only(bottom: 12),
                    onTap: !unread && n['kind'] != 'daily_coupons'
                        ? null
                        : () async {
                            if (unread) {
                              await guard(context, () => state.api.post('/me/notifications/${n['id']}/read'));
                              await state.refreshUnread();
                              setState(() => _key = UniqueKey());
                            }
                            // Coupons du jour : ouvrir l'écran où copier les codes.
                            if (n['kind'] == 'daily_coupons' && context.mounted) {
                              await Navigator.of(context)
                                  .push(MaterialPageRoute(builder: (_) => const DailyCouponsScreen()));
                            }
                          },
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        IconSquare(_icon('${n['kind']}'), size: 40, iconSize: 20, radius: 12),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Expanded(
                                    child: Text('${n['title']}', style: Fp.body(16, weight: FontWeight.w700)),
                                  ),
                                  const SizedBox(width: 8),
                                  Text(_ago(when), style: Fp.body(12, color: Fp.text2)),
                                  if (unread) ...[
                                    const SizedBox(width: 8),
                                    const Padding(
                                      padding: EdgeInsets.only(top: 4),
                                      child: CircleAvatar(radius: 4, backgroundColor: Fp.accent),
                                    ),
                                  ],
                                ],
                              ),
                              const SizedBox(height: 4),
                              Text('${n['body']}', style: Fp.body(14, color: Fp.textStrong, height: 1.4)),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              );
            }
            return RefreshIndicator(
              onRefresh: reload,
              child: ListView(
                padding: pagePadding(context, 16, 32),
                children: [
                  const BackHeader('Notifications', '', joined: true),
                  const SizedBox(height: 10),
                  // Sous le titre (maquette U : à côté, les boutons chevauchaient le titre).
                  if (list.isNotEmpty) ...[
                    Row(
                      children: [
                        OutlinedButton(onPressed: _readAll, child: const Text('Tout lire')),
                        const SizedBox(width: 8),
                        OutlinedButton(onPressed: _deleteAll, child: const Text('Tout effacer')),
                      ],
                    ),
                    const SizedBox(height: 10),
                  ],
                  if (list.isEmpty)
                    const EmptyState('Aucune notification.', icon: Icons.notifications_none_rounded)
                  else
                    Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: Text(
                        'Glisse une notification vers la gauche pour l\'effacer.',
                        style: Fp.body(12.5, color: Fp.muted),
                      ),
                    ),
                  ...children,
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}
