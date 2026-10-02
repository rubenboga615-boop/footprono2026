import 'package:http/http.dart' as http;

/// Version web : pas d'APK à installer.
Future<String> downloadApk(
  http.Client client,
  Uri url, {
  required String dir,
  required int build,
  required String sha256Hex,
  required void Function(double progress) onProgress,
}) => throw UnsupportedError('mise à jour APK : Android seulement');
