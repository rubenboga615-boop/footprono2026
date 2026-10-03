import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../desktop/layout.dart';
import '../api/models.dart';
import '../format.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';

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

  static IconData _icon(String kind) {
    if (kind.startsWith('montante')) return Icons.stairs_rounded;
    if (kind.startsWith('premium')) return Icons.workspace_premium_outlined;
    if (kind == 'bet_corrected') return Icons.edit_note_rounded;
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
                GlassCard(
                  margin: const EdgeInsets.only(bottom: 12),
                  onTap: !unread
                      ? null
                      : () async {
                          await guard(context, () => state.api.post('/me/notifications/${n['id']}/read'));
                          await state.refreshUnread();
                          setState(() => _key = UniqueKey());
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
              );
            }
            return RefreshIndicator(
              onRefresh: reload,
              child: ListView(
                padding: pagePadding(context, 16, 32),
                children: [
                  BackHeader(
                    'Notifi',
                    'cations',
                    joined: true,
                    trailing: TextButton(onPressed: _readAll, child: const Text('Tout lire')),
                  ),
                  const SizedBox(height: 8),
                  if (list.isEmpty)
                    const EmptyState('Aucune notification.', icon: Icons.notifications_none_rounded),
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
