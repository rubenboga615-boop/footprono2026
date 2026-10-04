import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../format.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'daily_coupons_screen.dart';

class AdminScreen extends StatefulWidget {
  const AdminScreen({super.key});

  @override
  State<AdminScreen> createState() => _AdminScreenState();
}

class _AdminScreenState extends State<AdminScreen> {
  final search = TextEditingController();
  String query = '';

  @override
  void dispose() {
    search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(18, 16, 18, 32),
          children: [
            const BackHeader('Adminis', 'tration', joined: true),
            const SizedBox(height: 16),
            Loader<Json>(
              load: () async => await api.get('/admin/stats') as Json,
              builder: (context, s, _) => GlassCard.main(
                child: Column(
                  children: [
                    KeyValue('Comptes', '${s['users']} (${s['active_users']} actifs)'),
                    KeyValue('Premium', '${s['premium']}'),
                    KeyValue('… dont essai gratuit', '${s['premium_trial']}'),
                    KeyValue('… dont activés / payés', '${s['premium_paid_or_granted']}'),
                    KeyValue('Nouveaux comptes (7 j)', '${s['new_users_7d']}'),
                    KeyValue('Paris (7 j)', '${s['bets_7d']}'),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 10),
            GlassCard.section(
              highlight: true,
              onTap: () =>
                  Navigator.of(context)
                      .push(MaterialPageRoute(builder: (_) => const AdminDailyCodesScreen())),
              child: Row(
                children: [
                  const Icon(Icons.qr_code_2_rounded, color: Fp.accentLight),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      'Codes 1xBet des coupons du jour',
                      style: Fp.title(14, weight: FontWeight.w600),
                    ),
                  ),
                  const Icon(Icons.chevron_right_rounded, color: Fp.text3),
                ],
              ),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: search,
              textInputAction: TextInputAction.search,
              onSubmitted: (v) => setState(() => query = v.trim()),
              decoration: InputDecoration(
                labelText: 'Chercher un compte (nom ou numéro)',
                suffixIcon: IconButton(
                  icon: const Icon(Icons.search_rounded),
                  onPressed: () => setState(() => query = search.text.trim()),
                ),
              ),
            ),
            const SizedBox(height: 12),
            Loader<List<Json>>(
              key: ValueKey(query),
              load: () async =>
                  (await api.get('/admin/users', {'q': query.isEmpty ? null : query}) as List).cast<Json>(),
              builder: (context, users, reload) => Column(
                children: [
                  if (users.isEmpty) const EmptyState('Aucun compte trouvé.'),
                  for (final u in users)
                    GlassCard(
                      margin: const EdgeInsets.only(bottom: 8),
                      onTap: () async {
                        await Navigator.of(context)
                            .push(MaterialPageRoute(builder: (_) => AdminUserScreen(id: u['id'] as int)));
                        await reload();
                      },
                      child: Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text('${u['display_name']}', style: Fp.body(14, weight: FontWeight.w700)),
                                Text('${u['phone']} · ${u['country']}', style: Fp.body(12, color: Fp.text2)),
                              ],
                            ),
                          ),
                          if (u['is_active'] != true) const Tag('Désactivé', color: Fp.loss),
                          const SizedBox(width: 6),
                          Tag(
                            u['plan'] == 'premium' ? 'Premium' : 'Gratuit',
                            color: u['plan'] == 'premium' ? Fp.win : Fp.text2,
                          ),
                        ],
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class AdminUserScreen extends StatefulWidget {
  const AdminUserScreen({super.key, required this.id});
  final int id;

  @override
  State<AdminUserScreen> createState() => _AdminUserScreenState();
}

class _AdminUserScreenState extends State<AdminUserScreen> {
  Key _key = UniqueKey();

  static const _kinds = {
    'trial': 'Essai à l\'inscription',
    'admin_grant': 'Activé par l\'administrateur',
    'admin_revoke': 'Retiré par l\'administrateur',
    'payment': 'Paiement',
  };

  Future<void> _grant() async {
    final days = TextEditingController(text: '30');
    final note = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Activer Premium'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: days,
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: const InputDecoration(
                labelText: 'Nombre de jours',
                helperText: 'Ajoutés à la période en cours',
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: note,
              decoration: const InputDecoration(labelText: 'Note (ex. paiement reçu)'),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Annuler')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Activer')),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    final api = context.read<AppState>().api;
    await guard(
      context,
      () => api.post('/admin/users/${widget.id}/premium', {
        'days': int.tryParse(days.text) ?? 30,
        'note': note.text.trim().isEmpty ? null : note.text.trim(),
      }),
    );
    setState(() => _key = UniqueKey());
  }

  Future<void> _post(String path, Object body) async {
    final api = context.read<AppState>().api;
    await guard(context, () => api.post(path, body));
    setState(() => _key = UniqueKey());
  }

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Loader<Json>(
          key: _key,
          load: () async => await api.get('/admin/users/${widget.id}') as Json,
          builder: (context, d, _) {
            final u = d['user'] as Json;
            final events = (d['subscription_events'] as List).cast<Json>();
            final until = parseDate(u['premium_until']);
            final premium = u['plan'] == 'premium';
            return ListView(
              padding: const EdgeInsets.fromLTRB(18, 16, 18, 32),
              children: [
                const BackHeader('Compte', 'utilisateur'),
                const SizedBox(height: 16),
                GlassCard.main(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${u['display_name']}', style: Fp.title(20)),
                      Text(
                        '${u['phone']} · ${u['country']} · ${u['role']}',
                        style: Fp.body(13, color: Fp.text2),
                      ),
                      const SizedBox(height: 10),
                      KeyValue(
                        'Formule',
                        premium ? 'Premium' : 'Gratuite',
                        valueColor: premium ? Fp.win : null,
                      ),
                      if (until != null)
                        KeyValue(premium ? 'Premium jusqu\'au' : 'Premium terminé le', dateTime(until)),
                      KeyValue('Compte', u['is_active'] == true ? 'actif' : 'désactivé'),
                      KeyValue('Inscrit le', dateTime(DateTime.parse(u['created_at'] as String))),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                FilledButton.icon(
                  onPressed: _grant,
                  icon: const Icon(Icons.workspace_premium_rounded),
                  label: const Text('Activer Premium'),
                ),
                const SizedBox(height: 8),
                if (premium)
                  OutlinedButton(
                    onPressed: () => _post('/admin/users/${widget.id}/premium/revoke', {}),
                    child: const Text('Retirer Premium'),
                  ),
                const SizedBox(height: 8),
                OutlinedButton(
                  onPressed: () =>
                      _post('/admin/users/${widget.id}/active', {'active': u['is_active'] != true}),
                  child: Text(u['is_active'] == true ? 'Désactiver le compte' : 'Réactiver le compte'),
                ),
                const SectionTitle('Historique de l\'abonnement'),
                for (final e in events)
                  GlassCard(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          _kinds[e['kind']] ?? '${e['kind']}',
                          style: Fp.body(13, weight: FontWeight.w700),
                        ),
                        Text(
                          '${dateTime(DateTime.parse(e['created_at'] as String))}'
                          '${(e['days'] as int) > 0 ? ' · ${e['days']} jours' : ''}'
                          ' · jusqu\'au ${numericDate(DateTime.parse(e['premium_until'] as String).toLocal())}',
                          style: Fp.body(12, color: Fp.text2),
                        ),
                        if (e['note'] != null) Text('${e['note']}', style: Fp.body(12, color: Fp.text3)),
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
}
