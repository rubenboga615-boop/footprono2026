// « Mon plan de jeu » : copie de la maquette 30 du testeur (docs/maquettes/12-nouveau-visage).
// Budget de la semaine, limite de perte, mise maximale, rappel après une heure, pause. Le
// serveur applique ces limites au moment du pari (bookmaker/play_plan.py) ; une limite relevée
// ou retirée attend 24 h.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../format.dart';
import '../state/app_state.dart';
import '../widgets/common.dart';
import '../widgets/visage.dart';
import 'today_screen.dart' show fcfa;

/// Rappel « une heure dans l'appli » : allumé ou non (lu au démarrage, changé dans l'écran).
final playReminderOn = ValueNotifier<bool>(false);

class PlayPlanScreen extends StatefulWidget {
  const PlayPlanScreen({super.key});

  @override
  State<PlayPlanScreen> createState() => _PlayPlanScreenState();
}

class _PlayPlanScreenState extends State<PlayPlanScreen> {
  late final ApiClient api = context.read<AppState>().api;
  Json? plan;
  Object? error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final p = await api.get('/me/play-plan') as Json;
      if (!mounted) return;
      playReminderOn.value = p['reminder'] == true;
      setState(() {
        plan = p;
        error = null;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => error = e);
    }
  }

  Future<void> _save(Json body) async {
    try {
      final p = await api.put('/me/play-plan', body) as Json;
      if (!mounted) return;
      playReminderOn.value = p['reminder'] == true;
      setState(() => plan = p);
    } on ApiException catch (e) {
      if (mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = plan;
    if (p == null) {
      return VPage(
        children: [
          const VTopBar('Mon plan de jeu'),
          const SizedBox(height: 40),
          if (error != null)
            Text('Plan de jeu indisponible pour le moment.', textAlign: TextAlign.center, style: V.mu_(13))
          else
            const Center(child: CircularProgressIndicator()),
        ],
      );
    }
    final cur = context.read<AppState>().me?.currency ?? 'XOF';
    final week = p['week'] as Json;
    final staked = week['staked'] as int;
    final budget = p['weekly_budget'] as int?;
    final pending = (p['pending'] as Json?) ?? const {};
    final applies = parseDate(p['pending_applies_at'])?.toLocal();
    final pause = parseDate(p['pause_until'])?.toLocal();

    Widget limit(String key, String label) {
      final v = p[key] as int?;
      return GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () => _edit(key, label, v, cur),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(child: Text(label, style: V.t(13.5))),
                Text(v == null ? 'Aucune' : fcfa(v, cur), style: V.b(13.5, v == null ? V.mu : V.tx)),
              ],
            ),
            if (pending.containsKey(key) && applies != null)
              Padding(
                padding: const EdgeInsets.only(top: 3),
                child: Text(
                  '${pending[key] == null ? 'retirée' : 'passe à ${fcfa(pending[key] as int, cur)}'}'
                  ' le ${shortDate(applies)} à ${hourMinute(applies)}',
                  style: V.t(11.5, color: V.amber),
                ),
              ),
          ],
        ),
      );
    }

    return VPage(
      onRefresh: _load,
      children: [
        const VTopBar('Mon plan de jeu'),
        VCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const VKicker('Cette semaine'),
              const SizedBox(height: 6),
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        FittedBox(
                          fit: BoxFit.scaleDown,
                          alignment: Alignment.centerLeft,
                          child: Text(fcfa(staked, cur), style: V.big()),
                        ),
                        Text(
                          budget == null
                              ? 'misés depuis lundi · pas de budget fixé'
                              : 'misés sur ${fcfa(budget, cur)} prévus',
                          style: V.mu_(),
                        ),
                      ],
                    ),
                  ),
                  if (budget != null) ...[
                    const SizedBox(width: 10),
                    VRing(staked / budget, color: staked >= budget ? V.amber : V.vi),
                  ],
                ],
              ),
            ],
          ),
        ),
        if (pause != null)
          VCard(
            border: V.coral.withValues(alpha: 0.4),
            child: Row(
              children: [
                const VIc(VIcon.pause, color: V.coral),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Pause en cours : pas de pari avant le ${shortDate(pause)} à ${hourMinute(pause)}.',
                    style: V.t(13),
                  ),
                ),
              ],
            ),
          ),
        VCard(
          child: VList(
            children: [
              limit('weekly_budget', 'Budget par semaine'),
              limit('loss_limit', 'Arrêter si je perds plus de'),
              limit('max_stake', 'Mise maximale par pari'),
              Row(
                children: [
                  Expanded(child: Text('Rappel après 1 h dans l\'appli', style: V.t(13.5))),
                  VSwitch(
                    value: p['reminder'] == true,
                    label: 'Rappel après 1 h dans l\'appli',
                    onChanged: (v) => _save({'reminder': v}),
                  ),
                ],
              ),
            ],
          ),
        ),
        VCard(
          onTap: () => _pause(context),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Faire une pause', style: V.b()),
                    Text('Plus de paris pendant 24 h, 7 jours ou 30 jours', style: V.mu_()),
                  ],
                ),
              ),
              const RotatedBox(quarterTurns: 2, child: VIc(VIcon.back, size: 16, color: V.vi2)),
            ],
          ),
        ),
        const VInfo(
          'Ces limites ne se relèvent qu\'au bout de 24 h, pour éviter les décisions sous le coup d\'une perte.',
        ),
      ],
    );
  }

  Future<void> _edit(String key, String label, int? current, String cur) async {
    final result = await showModalBottomSheet<(bool, int?)>(
      context: context,
      isScrollControlled: true,
      backgroundColor: V.s1,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) => _AmountSheet(label: label, current: current, currency: cur),
    );
    if (result != null && result.$1) await _save({key: result.$2});
  }

  Future<void> _pause(BuildContext context) async {
    final days = await showModalBottomSheet<int>(
      context: context,
      backgroundColor: V.s1,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) => Padding(
        padding: const EdgeInsets.all(16),
        child: DefaultTextStyle(
          style: V.t(13.5),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Faire une pause', style: V.b(16)),
              const SizedBox(height: 4),
              Text('Une pause ne s\'annule pas avant la fin.', style: V.mu_(12)),
              for (final (d, label) in const [(1, '24 heures'), (7, '7 jours'), (30, '30 jours')])
                VBtn2(label, onTap: () => Navigator.pop(ctx, d)),
            ],
          ),
        ),
      ),
    );
    if (days == null) return;
    try {
      final p = await api.post('/me/play-plan/pause', {'days': days}) as Json;
      if (mounted) setState(() => plan = p);
    } on ApiException catch (e) {
      if (context.mounted) showError(context, e);
    }
  }
}

/// Saisie d'une limite (montant), ou « Retirer la limite ».
class _AmountSheet extends StatefulWidget {
  const _AmountSheet({required this.label, required this.current, required this.currency});
  final String label;
  final int? current;
  final String currency;

  @override
  State<_AmountSheet> createState() => _AmountSheetState();
}

class _AmountSheetState extends State<_AmountSheet> {
  late final ctrl = TextEditingController(text: widget.current?.toString() ?? '');

  @override
  void dispose() {
    ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final cur = widget.currency;
    return Padding(
      padding: EdgeInsets.fromLTRB(16, 16, 16, 16 + MediaQuery.viewInsetsOf(context).bottom),
      child: DefaultTextStyle(
        style: V.t(13.5),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(widget.label, style: V.b(16)),
            const SizedBox(height: 4),
            Text('Plus strict : tout de suite. Plus souple ou retiré : dans 24 h.', style: V.mu_(12)),
            const SizedBox(height: 12),
            TextField(
              controller: ctrl,
              autofocus: true,
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              style: V.b(20),
              decoration: InputDecoration(
                suffixText: cur == 'XOF' || cur == 'XAF' ? 'F' : cur,
                hintText: 'Montant',
                filled: true,
                fillColor: V.s2,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: BorderSide.none,
                ),
              ),
            ),
            VBtn(
              'Enregistrer',
              onTap: () {
                final v = int.tryParse(ctrl.text);
                if (v == null || v < 100) return;
                Navigator.pop(context, (true, v));
              },
            ),
            if (widget.current != null)
              VBtn2('Retirer la limite', onTap: () => Navigator.pop(context, (true, null))),
          ],
        ),
      ),
    );
  }
}

/// Rappel « tu es dans l'appli depuis une heure » (plan de jeu) : compte le temps passé
/// application ouverte, sans compter quand elle est en arrière-plan.
class PlayReminder extends StatefulWidget {
  const PlayReminder({super.key, required this.child});
  final Widget child;

  @override
  State<PlayReminder> createState() => _PlayReminderState();
}

class _PlayReminderState extends State<PlayReminder> with WidgetsBindingObserver {
  static const every = Duration(hours: 1);
  Timer? _timer;
  Duration _spent = Duration.zero;
  DateTime? _since;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    playReminderOn.addListener(_sync);
    final api = context.read<AppState>().api;
    api
        .get('/me/play-plan')
        .then((p) => playReminderOn.value = (p as Json)['reminder'] == true)
        .catchError((Object _) => false);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    playReminderOn.removeListener(_sync);
    _timer?.cancel();
    super.dispose();
  }

  void _sync() {
    _timer?.cancel();
    if (!playReminderOn.value) {
      _since = null;
      return;
    }
    _since = DateTime.now();
    _timer = Timer(every - _spent, _ring);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState s) {
    if (!playReminderOn.value) return;
    if (s == AppLifecycleState.resumed) {
      _sync();
    } else if (_since != null) {
      _spent += DateTime.now().difference(_since!);
      _since = null;
      _timer?.cancel();
    }
  }

  Future<void> _ring() async {
    _spent = Duration.zero;
    if (!mounted) return;
    final go = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: V.s1,
        title: Text('Une heure dans l\'appli', style: V.b(16)),
        content: Text(
          'Tu joues depuis une heure. C\'est peut-être le moment de faire une pause.',
          style: V.t(13.5),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Continuer')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Mon plan de jeu')),
        ],
      ),
    );
    if (go == true && mounted) {
      await Navigator.of(context).push(MaterialPageRoute(builder: (_) => const PlayPlanScreen()));
    }
    _sync();
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
