import 'package:flutter/material.dart';

import '../api/client.dart';
import '../theme.dart';

/// Charge une donnée et affiche chargement, erreur (avec « Réessayer ») ou contenu.
class Loader<T> extends StatefulWidget {
  const Loader({super.key, required this.load, required this.builder});
  final Future<T> Function() load;
  final Widget Function(BuildContext context, T data, Future<void> Function() reload) builder;

  @override
  State<Loader<T>> createState() => _LoaderState<T>();
}

class _LoaderState<T> extends State<Loader<T>> {
  late Future<T> _future = widget.load();

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
        if (snap.connectionState != ConnectionState.done) {
          return const Center(
            child: Padding(padding: EdgeInsets.all(32), child: CircularProgressIndicator()),
          );
        }
        if (snap.hasError) {
          return ErrorPanel(error: snap.error!, onRetry: _reload);
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

  @override
  Widget build(BuildContext context) {
    final message = error is ApiException ? (error as ApiException).message : 'Erreur inattendue : $error';
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: GlassCard(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.cloud_off_rounded, color: Fp.loss, size: 32),
              const SizedBox(height: 12),
              Text(
                message,
                textAlign: TextAlign.center,
                style: Fp.body(14, color: Fp.text2, height: 1.4),
              ),
              if (onRetry != null) ...[
                const SizedBox(height: 16),
                OutlinedButton(onPressed: onRetry, child: const Text('Réessayer')),
              ],
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

/// Encadré « réservé à Premium ».
class PremiumLock extends StatelessWidget {
  const PremiumLock({super.key, required this.text, this.markets = const []});
  final String text;
  final List<String> markets;

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      highlight: true,
      child: Row(
        children: [
          const Icon(Icons.lock_rounded, color: Fp.accentLight),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Premium', style: Fp.title(15, color: Fp.accentLight)),
                const SizedBox(height: 4),
                Text(text, style: Fp.body(13, color: Fp.text2, height: 1.4)),
              ],
            ),
          ),
        ],
      ),
    );
  }
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
