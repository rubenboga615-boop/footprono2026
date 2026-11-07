// Mode bêta (période de test) : le joueur volontaire partage, sans nom ni numéro, les
// temps de chargement et les erreurs des écrans, et les actions du Coupon intelligent.
// Éteint : rien n'est gardé ni envoyé. Les envois sont groupés (au plus une fois par
// minute, ou dès 20 événements) et une panne d'envoi ne gêne jamais le joueur.
import 'dart:async';

import '../api/client.dart';

class BetaReporter {
  BetaReporter(this.api, {DateTime Function()? clock}) : _clock = clock ?? DateTime.now;

  final ApiClient api;
  final DateTime Function() _clock;
  static const path = '/me/beta/events';
  static const batch = 20;
  static const every = Duration(minutes: 1);
  static const maxBuffer = 200;

  /// Écrans dont le temps de chargement est suivi (les erreurs le sont partout).
  static const watched = [
    '/smart-coupon',
    '/smart-coupons/day',
    '/montantes',
    '/reliability',
    '/matches/',
    '/predictions/upcoming',
    '/bets',
  ];

  final List<Map<String, Object?>> _buffer = [];
  DateTime? _lastSent;
  bool _sending = false;
  bool _enabled = false;

  bool get enabled => _enabled;
  set enabled(bool on) {
    _enabled = on;
    if (!on) _buffer.clear();
  }

  /// Événements en attente d'envoi (tests).
  List<Map<String, Object?>> get pending => List.unmodifiable(_buffer);

  /// Appelé par ``ApiClient`` après chaque requête.
  void observe(String requestPath, Duration elapsed, ApiException? error) {
    if (!_enabled) return;
    final p = requestPath.split('?').first;
    if (p == path) return;
    final ms = elapsed.inMilliseconds;
    if (error != null) {
      // Réponses normales du serveur (cote changée, Premium requis…) : pas des pannes.
      final broken = error.status == 0 || error.status >= 500;
      if (!broken) return;
      _add({
        'kind': error.code == 'timeout' ? 'slow' : 'error',
        'path': p,
        'duration_ms': ms,
        'detail': error.status == 0 ? error.code : 'http_${error.status}',
      });
      return;
    }
    if (!watched.any((w) => p == w || p.startsWith(w.endsWith('/') ? w : '$w/'))) return;
    _add({'kind': ms >= 20000 ? 'slow' : 'timing', 'path': p, 'duration_ms': ms});
  }

  /// Action du joueur (``coupon_compose``, ``coupon_add``).
  void action(String name) {
    if (_enabled) _add({'kind': 'action', 'path': name});
  }

  void _add(Map<String, Object?> e) {
    // Heure de l'action (l'envoi est groupé : sans elle, l'ordre des actions était perdu).
    _buffer.add({...e, 'at': _clock().toUtc().toIso8601String()});
    if (_buffer.length > maxBuffer) _buffer.removeAt(0);
    final last = _lastSent;
    if (_buffer.length >= batch || last == null || _clock().difference(last) >= every) {
      unawaited(flush());
    }
  }

  /// Envoie les événements en attente (aussi quand l'application passe en arrière-plan).
  Future<void> flush() async {
    if (!_enabled || _sending || _buffer.isEmpty || api.token == null) return;
    _sending = true;
    _lastSent = _clock();
    final sent = _buffer.take(50).toList();
    _buffer.removeRange(0, sent.length);
    try {
      await api.post(path, {'events': sent});
    } catch (_) {
      // Serveur injoignable : renvoyés au prochain envoi (dans la limite du tampon).
      if (_enabled) _buffer.insertAll(0, sent.take(maxBuffer - _buffer.length));
    } finally {
      _sending = false;
    }
  }
}
