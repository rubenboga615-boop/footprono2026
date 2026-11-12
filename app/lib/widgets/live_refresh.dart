// Mise à jour seule pendant les matchs (retour du fondateur du 12/11/2026 : il fallait
// actualiser sans arrêt). Deux voies :
// - chaque relevé du serveur (toutes les minutes) arrive par le WebSocket déjà ouvert
//   (`AppState.liveFeed`) : l'écran se recharge aussitôt s'il montre un des matchs relevés ;
// - en secours (pas connecté, WebSocket coupé), rechargement toutes les 30 secondes tant
//   qu'un match est en cours ou commence dans les 10 minutes, application ouverte seulement.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../theme.dart';

class LiveRefresh extends StatefulWidget {
  const LiveRefresh({
    super.key,
    required this.active,
    required this.reload,
    required this.child,
    this.matchIds,
  });

  /// Un match montré est en cours ou commence bientôt.
  final bool active;
  final Future<void> Function() reload;

  /// Matchs montrés ; null : tout relevé recharge l'écran (liste des matchs).
  final Set<int>? matchIds;
  final Widget child;

  /// Intervalle du rechargement de secours (raccourci dans les tests).
  static Duration every = const Duration(seconds: 30);

  @override
  State<LiveRefresh> createState() => _LiveRefreshState();
}

class _LiveRefreshState extends State<LiveRefresh> {
  late final AppState _state = context.read<AppState>();
  Timer? _timer;

  /// Un relevé poussé vient de recharger l'écran : le prochain tour du secours est sauté.
  bool _fresh = false;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _state.liveFeed.addListener(_onFeed);
    _state.foreground.addListener(_onForeground);
    _arm();
  }

  @override
  void didUpdateWidget(LiveRefresh old) {
    super.didUpdateWidget(old);
    if (old.active != widget.active) _arm();
  }

  @override
  void dispose() {
    _timer?.cancel();
    _state.liveFeed.removeListener(_onFeed);
    _state.foreground.removeListener(_onForeground);
    super.dispose();
  }

  void _arm() {
    _timer?.cancel();
    _timer = null;
    if (!widget.active || !_state.foreground.value) return;
    _timer = Timer.periodic(LiveRefresh.every, (_) {
      if (_fresh) {
        _fresh = false;
      } else {
        _run();
      }
    });
  }

  void _onForeground() {
    _arm();
    // Retour dans l'application : les données ont pu vieillir, rechargées une fois.
    if (_state.foreground.value && widget.active) _run();
  }

  void _onFeed() {
    final feed = _state.liveFeed.value;
    if (feed == null || !_state.foreground.value) return;
    final ids = widget.matchIds;
    if (ids != null && !feed.matches.keys.any(ids.contains)) return;
    _fresh = true;
    _run();
  }

  Future<void> _run() async {
    if (_busy || !mounted) return;
    _busy = true;
    try {
      await widget.reload();
    } catch (_) {
    } finally {
      _busy = false;
    }
  }

  @override
  Widget build(BuildContext context) => widget.child;
}

/// « Mis à jour il y a 40 s » : âge du dernier relevé du direct, qui avance tout seul.
class UpdatedAgo extends StatefulWidget {
  const UpdatedAgo(this.at, {super.key, this.size = 11.5});
  final DateTime? at;
  final double size;

  /// « il y a 40 s », « il y a 3 min » ; vide sans heure.
  static String label(DateTime? at, DateTime now) {
    if (at == null) return '';
    final s = now.difference(at).inSeconds;
    if (s < 5) return 'Mis à jour à l\'instant';
    if (s < 60) return 'Mis à jour il y a $s s';
    return 'Mis à jour il y a ${s ~/ 60} min';
  }

  @override
  State<UpdatedAgo> createState() => _UpdatedAgoState();
}

class _UpdatedAgoState extends State<UpdatedAgo> {
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 5), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final text = UpdatedAgo.label(widget.at, MatchInfo.now());
    if (text.isEmpty) return const SizedBox.shrink();
    return Text(text, style: Fp.body(widget.size, color: Fp.muted));
  }
}
