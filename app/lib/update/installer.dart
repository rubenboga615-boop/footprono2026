import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;

import 'apk_download_stub.dart' if (dart.library.io) 'apk_download_io.dart';

/// Installation d'une nouvelle version hors Play Store : l'application télécharge l'APK
/// elle-même puis ouvre l'écran d'installation d'Android (une confirmation reste
/// obligatoire : Android ne laisse aucune application s'installer en silence).
abstract class ApkInstaller {
  Future<String> download(
    http.Client client,
    Uri url, {
    required int build,
    required String sha256,
    required void Function(double progress) onProgress,
  });

  /// Android 8 et plus : FootProba doit être autorisée à installer des applications.
  Future<bool> canInstall();

  /// Ouvre le réglage « Installer des applications inconnues » de FootProba.
  Future<void> openSettings();

  /// Ouvre l'écran d'installation d'Android pour l'APK téléchargé.
  Future<void> install(String path);
}

/// Implémentation Android (MainActivity.kt, canal « footprono/installer »).
class ChannelInstaller implements ApkInstaller {
  static const _channel = MethodChannel('footprono/installer');

  @override
  Future<String> download(
    http.Client client,
    Uri url, {
    required int build,
    required String sha256,
    required void Function(double progress) onProgress,
  }) async {
    final dir = await _channel.invokeMethod<String>('updatesDir');
    return downloadApk(client, url, dir: dir!, build: build, sha256Hex: sha256, onProgress: onProgress);
  }

  @override
  Future<bool> canInstall() async => await _channel.invokeMethod<bool>('canInstall') ?? false;

  @override
  Future<void> openSettings() => _channel.invokeMethod<void>('openSettings');

  @override
  Future<void> install(String path) => _channel.invokeMethod<void>('install', {'path': path});
}
