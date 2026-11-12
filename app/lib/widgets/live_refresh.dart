// Mise à jour seule pendant les matchs (retour du fondateur du 12/11/2026).
// Chaque relevé du serveur (chaque minute) arrive par le WebSocket déjà ouvert, ou, sans
// WebSocket, par GET /live/feed toutes les 30 s (AppState.watchLive) ; la liste et l'écran
// d'un match se mettent à jour à partir de ce relevé (AppState.liveFeed, MatchInfo.withFeed),
// sans recharger la liste ni l'analyse (158 requêtes en 8 minutes pour un joueur avant).

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Tant que [active] (un match montré est en cours ou proche), l'écran suit les relevés.
class LiveWatch extends StatefulWidget {
  const LiveWatch({super.key, required this.active, required this.child});
  final bool active;
  final Widget child;

  @override
  State<LiveWatch> createState() => _LiveWatchState();
}

class _LiveWatchState extends State<LiveWatch> {
  late final AppState _state = context.read<AppState>();
  bool _on = false;

  void _set(bool on) {
    if (on == _on) return;
    _on = on;
    _state.watchLive(on);
  }

  @override
  void initState() {
    super.initState();
    _set(widget.active);
  }

  @override
  void didUpdateWidget(LiveWatch old) {
    super.didUpdateWidget(old);
    _set(widget.active);
  }

  @override
  void dispose() {
    _set(false);
    super.dispose();
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
