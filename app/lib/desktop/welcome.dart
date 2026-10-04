import 'package:flutter/material.dart';

import '../theme.dart';

/// Version ordinateur, avant connexion : à gauche ce qu'est FootProba, à droite le formulaire.
class DesktopWelcome extends StatelessWidget {
  const DesktopWelcome({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Material(color: Colors.transparent, child: _layout());
  }

  Widget _layout() {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(
          child: Container(
            padding: const EdgeInsets.fromLTRB(64, 56, 64, 48),
            decoration: BoxDecoration(
              gradient: RadialGradient(
                center: const Alignment(-0.4, -0.4),
                radius: 1.1,
                colors: [Fp.accentAlpha(0.28), Colors.transparent],
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const FpLogo(size: 22),
                const Spacer(),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 520),
                  child: Text.rich(
                    TextSpan(
                      text: 'Des probabilités calibrées pour ',
                      style: Fp.title(42),
                      children: [
                        TextSpan(
                          text: 'cinq championnats',
                          style: Fp.title(42, color: Fp.accentLight),
                        ),
                        const TextSpan(text: '.'),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 18),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 460),
                  child: Text(
                    'Le moteur calcule ses chances sans regarder les cotes. Tu joues avec de l\'argent '
                    'fictif et tu vérifies toi-même s\'il a raison.',
                    style: Fp.body(16, color: Fp.text2, height: 1.5),
                  ),
                ),
                const Spacer(),
                Text(
                  'Premier League · Liga · Serie A · Bundesliga · Ligue 1',
                  style: Fp.body(13, color: Fp.text3, weight: FontWeight.w600),
                ),
              ],
            ),
          ),
        ),
        Container(
          width: 560,
          decoration: const BoxDecoration(
            color: Color(0x990A090E),
            border: Border(left: BorderSide(color: Fp.divider)),
          ),
          child: child,
        ),
      ],
    );
  }
}
