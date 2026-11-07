// Logo d'un club (image d'API-Football gardée par le serveur FootProba) ; sans logo, ses
// initiales dans un rond violet, comme dans les maquettes du 07/11/2026.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../theme.dart';

class TeamLogo extends StatelessWidget {
  const TeamLogo(this.team, {super.key, this.size = 24});
  final Team team;
  final double size;

  /// Désactivé dans les tests (aucune image à télécharger).
  static bool enabled = true;

  @override
  Widget build(BuildContext context) {
    final initials = _Initials(team.name, size);
    if (!enabled) return initials;
    final url = context.read<AppState>().api.uri('/teams/${team.id}/logo').toString();
    return SizedBox(
      width: size,
      height: size,
      child: Image.network(
        url,
        width: size,
        height: size,
        fit: BoxFit.contain,
        // Logo net même sur les écrans très denses, sans charger plus que nécessaire.
        cacheWidth: (size * MediaQuery.devicePixelRatioOf(context)).round(),
        errorBuilder: (_, _, _) => initials,
        frameBuilder: (_, child, frame, sync) => sync || frame != null ? child : initials,
        semanticLabel: 'Logo ${team.name}',
      ),
    );
  }
}

class _Initials extends StatelessWidget {
  const _Initials(this.name, this.size);
  final String name;
  final double size;

  @override
  Widget build(BuildContext context) {
    final letter = name.trim().isEmpty ? '?' : name.trim()[0].toUpperCase();
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: const BoxDecoration(shape: BoxShape.circle, color: Fp.cardHigh),
      child: Text(
        letter,
        style: Fp.body(size * 0.46, weight: FontWeight.w700, color: Fp.lilac),
      ),
    );
  }
}
