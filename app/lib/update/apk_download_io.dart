import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;

/// Télécharge l'APK dans [dir] en vérifiant son empreinte SHA-256 (celle publiée par le serveur) :
/// un fichier incomplet ou altéré n'est jamais proposé à l'installation.
Future<String> downloadApk(
  http.Client client,
  Uri url, {
  required String dir,
  required int build,
  required String sha256Hex,
  required void Function(double progress) onProgress,
}) async {
  final folder = Directory(dir);
  if (folder.existsSync()) {
    for (final old in folder.listSync()) {
      if (old is File) old.deleteSync();
    }
  } else {
    folder.createSync(recursive: true);
  }
  final file = File('$dir/footprono-$build.apk');
  final response = await client.send(http.Request('GET', url));
  if (response.statusCode != 200) {
    throw HttpException('téléchargement refusé (${response.statusCode})', uri: url);
  }
  final total = response.contentLength ?? 0;
  final digest = _DigestSink();
  final hasher = sha256.startChunkedConversion(digest);
  final out = file.openWrite();
  var received = 0;
  try {
    await for (final chunk in response.stream) {
      out.add(chunk);
      hasher.add(chunk);
      received += chunk.length;
      if (total > 0) onProgress(received / total);
    }
  } finally {
    await out.close();
  }
  hasher.close();
  if (digest.value.toString() != sha256Hex.toLowerCase()) {
    file.deleteSync();
    throw const FileSystemException('fichier téléchargé incomplet ou altéré');
  }
  return file.path;
}

class _DigestSink implements Sink<Digest> {
  late Digest value;
  @override
  void add(Digest data) => value = data;
  @override
  void close() {}
}
