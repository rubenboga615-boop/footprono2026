import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/client.dart';
import '../state/app_state.dart';
import '../screens/premium_screen.dart' show PremiumCard;
import '../theme.dart';

/// Charge une donnée et affiche chargement, erreur (avec « Réessayer ») ou contenu.
class Loader<T> extends StatefulWidget {
  const Loader({super.key, required this.load, required this.builder, this.errorHeader});
  final Future<T> Function() load;

  /// Gardé au-dessus du message d'erreur (maquette N16 : le titre de l'écran reste).
  final Widget? errorHeader;
  final Widget Function(BuildContext context, T data, Future<void> Function() reload) builder;

  @override
  State<Loader<T>> createState() => _LoaderState<T>();
}

class _LoaderState<T> extends State<Loader<T>> {
  late Future<T> _future = widget.load();
  // Dernières données reçues : gardées à l'écran pendant un rechargement (actualisation
  // automatique des paris en cours, tirer pour actualiser), au lieu d'une roue.
  T? _last;
  bool _hasLast = false;

  Future<void> _reload() async {
    final f = widget.load();
    // Bloc : une flèche renverrait le Future affecté, refusé par setState.
    setState(() {
      _future = f;
    });
    try {
      await f;
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<T>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState == ConnectionState.done && !snap.hasError) {
          _last = snap.data;
          _hasLast = true;
        }
        if (snap.connectionState != ConnectionState.done) {
          if (_hasLast) return widget.builder(context, _last as T, _reload);
          return const Center(
            child: Padding(padding: EdgeInsets.all(32), child: CircularProgressIndicator()),
          );
        }
        if (snap.hasError) {
          final panel = ErrorPanel(error: snap.error!, onRetry: _reload);
          final header = widget.errorHeader;
          if (header == null) return panel;
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 120),
            children: [header, const SizedBox(height: 80), panel],
          );
        }
        return widget.builder(context, snap.data as T, _reload);
      },
    );
  }
}

class ErrorPanel extends StatelessWidget {
  const ErrorPanel({super.key, required this.error, this.onRetry});
  final Object error;
  final VoidCallback? onRetry;

  // Maquette N16 : sans carte, icône rose, titre, phrase, « Réessayer » en pilule.
  @override
  Widget build(BuildContext context) {
    final api = error is ApiException ? error as ApiException : null;
    final (title, message) = switch (api) {
      ApiException(status: 0, code: 'network') => (
        'Pas de connexion',
        'Vérifie ta connexion internet. Tes paris et ton coupon sont gardés.',
      ),
      ApiException(status: 0, code: 'timeout') => ('FootProba ne répond pas', api.message),
      final e? => ('Un problème est survenu', e.message),
      null => ('Un problème est survenu', 'Erreur inattendue : $error'),
    };
    final offline = api?.status == 0;
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 40),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(offline ? Icons.wifi_off_rounded : Icons.error_outline_rounded, color: Fp.loss, size: 40),
            const SizedBox(height: 14),
            Text(title, textAlign: TextAlign.center, style: Fp.title(18)),
            const SizedBox(height: 6),
            Text(
              message,
              textAlign: TextAlign.center,
              style: Fp.body(14, color: Fp.muted, height: 1.4),
            ),
            if (onRetry != null) ...[
              const SizedBox(height: 18),
              SizedBox(
                width: 220,
                height: 52,
                child: FilledButton(
                  onPressed: onRetry,
                  style: FilledButton.styleFrom(
                    shape: const StadiumBorder(),
                    backgroundColor: Fp.accent,
                    foregroundColor: Colors.white,
                    textStyle: Fp.body(16, weight: FontWeight.w700),
                  ),
                  child: const Text('Réessayer'),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Bandeau « cotes indisponibles » (source des cotes coupée) : rien sinon.
class OddsDownBanner extends StatelessWidget {
  const OddsDownBanner({super.key});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<bool>(
      valueListenable: context.read<AppState>().oddsAvailable,
      builder: (context, available, _) => available
          ? const SizedBox.shrink()
          : Padding(
              padding: const EdgeInsets.only(bottom: 14),
              child: Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Fp.warning.withValues(alpha: 0.08),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Fp.warning.withValues(alpha: 0.25)),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.info_outline_rounded, size: 18, color: Fp.warning),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        'Cotes momentanément indisponibles : les paris, les coupons du jour et les '
                        'suggestions reprendront dès leur retour. Les probabilités du moteur restent '
                        'consultables.',
                        style: Fp.body(13, color: Fp.warning, height: 1.4),
                      ),
                    ),
                  ],
                ),
              ),
            ),
    );
  }
}

class EmptyState extends StatelessWidget {
  const EmptyState(this.text, {super.key, this.icon = Icons.inbox_rounded});
  final String text;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 40, horizontal: 24),
      child: Column(
        children: [
          Icon(icon, size: 36, color: Fp.text3),
          const SizedBox(height: 12),
          Text(
            text,
            textAlign: TextAlign.center,
            style: Fp.body(14, color: Fp.text2, height: 1.4),
          ),
        ],
      ),
    );
  }
}

class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key, this.trailing});
  final String text;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 20, 4, 10),
      child: Row(
        children: [
          Expanded(
            child: Text(
              text.toUpperCase(),
              style: Fp.body(12, color: Fp.text3, weight: FontWeight.w700).copyWith(letterSpacing: 1.1),
            ),
          ),
          ?trailing,
        ],
      ),
    );
  }
}

/// Groupe repliable (« menu déroulant ») : titre, nombre d'éléments et flèche ; un
/// toucher ouvre ou ferme. L'état reste le même en changeant d'onglet (PageStorage).
class FoldSection extends StatefulWidget {
  const FoldSection({
    super.key,
    required this.id,
    required this.title,
    required this.count,
    required this.children,
    this.initiallyOpen = false,
  });

  /// Identifiant stable (onglet + groupe) pour retrouver l'état ouvert / fermé.
  final String id;
  final String title;
  final String count;
  final List<Widget> children;
  final bool initiallyOpen;

  @override
  State<FoldSection> createState() => _FoldSectionState();
}

class _FoldSectionState extends State<FoldSection> {
  late bool open =
      PageStorage.maybeOf(context)?.readState(context, identifier: widget.id) as bool? ??
      widget.initiallyOpen;

  void _toggle() {
    setState(() => open = !open);
    PageStorage.maybeOf(context)?.writeState(context, open, identifier: widget.id);
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: 10),
        Semantics(
          button: true,
          expanded: open,
          label: '${widget.title}, ${widget.count}',
          child: InkWell(
            onTap: _toggle,
            borderRadius: Fp.radius14,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(
                color: open ? Fp.accentSoft : Fp.fill,
                borderRadius: Fp.radius14,
                border: Border.all(color: open ? Fp.accentLine : Colors.transparent),
              ),
              child: ExcludeSemantics(
                child: Row(
                  children: [
                    Expanded(
                      child: Text(widget.title, style: Fp.title(15, weight: FontWeight.w600)),
                    ),
                    Text(widget.count, style: Fp.body(12, color: Fp.text3)),
                    const SizedBox(width: 8),
                    AnimatedRotation(
                      turns: open ? 0.5 : 0,
                      duration: const Duration(milliseconds: 180),
                      child: const Icon(Icons.expand_more_rounded, size: 22, color: Fp.text2),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
        if (open) ...[const SizedBox(height: 6), ...widget.children],
      ],
    );
  }
}

/// Encadré « réservé à Premium ».
class PremiumLock extends StatelessWidget {
  const PremiumLock({super.key, required this.text, this.markets = const []});
  final String text;
  final List<String> markets;

  // Maquettes N1-N3 : même cadre que les écrans verrouillés ; jamais d'impasse, le bouton
  // ouvre « Passer Premium » (essai du 07/11/2026).
  @override
  Widget build(BuildContext context) => PremiumCard(text: text);
}

/// Ligne « libellé … valeur ».
class KeyValue extends StatelessWidget {
  const KeyValue(this.label, this.value, {super.key, this.valueColor, this.bold = false});
  final String label;
  final String value;
  final Color? valueColor;
  final bool bold;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Text(label, style: Fp.body(14, color: Fp.text2)),
          ),
          const SizedBox(width: 12),
          // Valeur collée à droite, sur au plus la moitié de la ligne.
          Flexible(
            child: Align(
              alignment: Alignment.topRight,
              child: Text(
                value,
                textAlign: TextAlign.right,
                style: bold
                    ? Fp.title(15, color: valueColor ?? Fp.text)
                    : Fp.body(14, color: valueColor ?? Fp.text, weight: FontWeight.w600),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Montre l'erreur d'une action (message du serveur) sans planter l'écran.
Future<T?> guard<T>(
  BuildContext context,
  Future<T> Function() action, {
  void Function(ApiException e)? onError,
}) async {
  try {
    return await action();
  } on ApiException catch (e) {
    if (onError != null) {
      onError(e);
    } else if (context.mounted) {
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text(e.message), backgroundColor: const Color(0xFF3A1430)));
    }
    return null;
  }
}

/// Attente d'un calcul du moteur sur toute une période (coupon intelligent, suggestions) :
/// une roue, puis une explication qui change avec le temps, pour que le joueur sache que
/// rien n'est bloqué (essai réel du 06/11/2026 : 18 s avec « Recherche… » pour seul signe).
class SlowWait extends StatefulWidget {
  const SlowWait({super.key, this.what = 'les matchs de la période'});
  final String what;

  /// Message affiché après ``seconds`` secondes d'attente.
  static String message(int seconds, String what) {
    if (seconds >= 30) {
      return 'Le serveur est très occupé. Tu peux encore patienter un peu ou réessayer plus tard.';
    }
    if (seconds >= 12) return 'Encore quelques secondes : il y a beaucoup de matchs à étudier.';
    if (seconds >= 4) return 'Le moteur étudie $what…';
    return 'Recherche…';
  }

  @override
  State<SlowWait> createState() => _SlowWaitState();
}

class _SlowWaitState extends State<SlowWait> {
  int seconds = 0;
  Timer? timer;

  @override
  void initState() {
    super.initState();
    timer = Timer.periodic(const Duration(seconds: 1), (_) => setState(() => seconds++));
  }

  @override
  void dispose() {
    timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: Row(
          children: [
            const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2.2, color: Fp.accentLight),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                SlowWait.message(seconds, widget.what),
                style: Fp.body(13, color: Fp.text2, height: 1.4),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
