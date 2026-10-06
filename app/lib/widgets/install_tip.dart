import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../platform/device.dart';
import '../theme.dart';

/// iPhone dans Safari : comment installer FootProba sur l'écran d'accueil (plein écran,
/// icône comme une application). Masquable ; rien ailleurs (Android, ordinateur).
class InstallTip extends StatefulWidget {
  const InstallTip({super.key, this.margin = EdgeInsets.zero});
  final EdgeInsets margin;

  static const _hiddenKey = 'install_tip_hidden';

  @override
  State<InstallTip> createState() => _InstallTipState();
}

class _InstallTipState extends State<InstallTip> {
  bool show = false;

  @override
  void initState() {
    super.initState();
    if (iosBrowserNotInstalled) _load();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    if (mounted && prefs.getBool(InstallTip._hiddenKey) != true) setState(() => show = true);
  }

  Future<void> _hide() async {
    setState(() => show = false);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(InstallTip._hiddenKey, true);
  }

  @override
  Widget build(BuildContext context) {
    if (!show) return const SizedBox.shrink();
    return Padding(
      padding: widget.margin,
      child: GlassCard(
        highlight: true,
        padding: const EdgeInsets.fromLTRB(14, 12, 4, 12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Padding(
              padding: EdgeInsets.only(top: 2),
              child: Icon(Icons.add_to_home_screen_rounded, color: Fp.accentLight, size: 22),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Installe FootProba sur ton iPhone', style: Fp.title(14.5)),
                  const SizedBox(height: 6),
                  Text.rich(
                    TextSpan(
                      style: Fp.body(13, color: Fp.textSoft, height: 1.45),
                      children: const [
                        TextSpan(text: 'Dans Safari, touche '),
                        WidgetSpan(
                          alignment: PlaceholderAlignment.middle,
                          child: Icon(Icons.ios_share_rounded, size: 17, color: Fp.accentLight),
                        ),
                        TextSpan(text: ' Partager, puis « Sur l\'écran d\'accueil ». '),
                        TextSpan(text: 'FootProba s\'ouvrira en plein écran, comme une application.'),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            IconButton(
              tooltip: 'Masquer',
              onPressed: _hide,
              icon: const Icon(Icons.close_rounded, size: 18, color: Fp.text3),
            ),
          ],
        ),
      ),
    );
  }
}
