// Client de l'API FootProba (/api/v1). Les erreurs du serveur arrivent
// toujours sous la forme {"error": {"code", "message", "details"}} : le
// message (en français) est montré tel quel à l'utilisateur.
import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

class ApiException implements Exception {
  ApiException(this.status, this.code, this.message, [this.details]);
  final int status;
  final String code;
  final String message;
  final Object? details;

  bool get isUnauthorized => status == 401;
  bool get premiumRequired => code == 'premium_required';
  bool get oddsChanged => code == 'odds_changed';
  bool get outOfRange => details is Map && (details as Map)['code'] == 'out_of_range';

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({required this.baseUrl, this.token, http.Client? httpClient})
    : _http = httpClient ?? http.Client();

  String baseUrl;
  String? token;
  final http.Client _http;

  /// Client HTTP partagé (téléchargement de la mise à jour).
  http.Client get httpClient => _http;
  static const timeout = Duration(seconds: 20);

  Uri uri(String path, [Map<String, Object?>? query]) {
    final root = baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl;
    // Une liste devient un paramètre répété (?match_ids=1&match_ids=2).
    final params = <String, Object>{
      for (final e in (query ?? const {}).entries)
        if (e.value case final Iterable<Object?> v)
          e.key: [for (final x in v) '$x']
        else if (e.value != null)
          e.key: '${e.value}',
    };
    return Uri.parse('$root/api/v1$path').replace(queryParameters: params.isEmpty ? null : params);
  }

  /// Adresse du flux des notifications en direct (WebSocket).
  Uri notificationsSocket() {
    final u = uri('/ws', {'token': token});
    return u.replace(scheme: u.scheme == 'https' ? 'wss' : 'ws');
  }

  Map<String, String> get _headers => {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    if (token != null) 'Authorization': 'Bearer $token',
  };

  Future<dynamic> get(String path, [Map<String, Object?>? query]) =>
      _send(() => _http.get(uri(path, query), headers: _headers));

  Future<dynamic> post(String path, [Object? body]) =>
      _send(() => _http.post(uri(path), headers: _headers, body: jsonEncode(body ?? const {})));

  Future<dynamic> delete(String path) => _send(() => _http.delete(uri(path), headers: _headers));

  Future<dynamic> put(String path, [Object? body]) =>
      _send(() => _http.put(uri(path), headers: _headers, body: jsonEncode(body ?? const {})));

  Future<dynamic> _send(Future<http.Response> Function() request) async {
    final http.Response res;
    try {
      res = await request().timeout(timeout);
    } on TimeoutException {
      throw ApiException(0, 'timeout', 'Connexion trop lente. Réessaie dans un instant.');
    } catch (e) {
      throw ApiException(0, 'network', 'Impossible de joindre FootProba. Vérifie ta connexion internet.');
    }
    final text = utf8.decode(res.bodyBytes);
    dynamic data;
    if (text.isNotEmpty) {
      try {
        data = jsonDecode(text);
      } catch (_) {
        data = null;
      }
    }
    if (res.statusCode >= 200 && res.statusCode < 300) return data;
    final error = data is Map ? data['error'] : null;
    if (error is Map) {
      throw ApiException(
        res.statusCode,
        '${error['code'] ?? 'error'}',
        '${error['message'] ?? 'Erreur ${res.statusCode}'}',
        error['details'],
      );
    }
    throw ApiException(
      res.statusCode,
      'http_${res.statusCode}',
      'Un problème est survenu. Réessaie dans un instant.',
    );
  }
}
