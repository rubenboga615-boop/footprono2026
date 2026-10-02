import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:footprono/update/apk_download_io.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  final apk = utf8.encode('faux APK ' * 1000);
  final client = MockClient((_) async => http.Response.bytes(apk, 200));
  late Directory dir;
  setUp(() => dir = Directory.systemTemp.createTempSync('fp-update'));
  tearDown(() => dir.deleteSync(recursive: true));

  test('APK complet : empreinte vérifiée, anciens fichiers effacés', () async {
    File('${dir.path}/footprono-45.apk').writeAsStringSync('ancien');
    final progress = <double>[];
    final path = await downloadApk(
      client,
      Uri.parse('http://serveur/api/v1/app/download'),
      dir: dir.path,
      build: 46,
      sha256Hex: sha256.convert(apk).toString(),
      onProgress: progress.add,
    );
    expect(File(path).readAsBytesSync(), apk);
    expect(dir.listSync().map((f) => f.path.split('/').last), ['footprono-46.apk']);
    expect(progress.last, 1.0);
  });

  test('empreinte différente : fichier supprimé, rien à installer', () async {
    await expectLater(
      downloadApk(
        client,
        Uri.parse('http://serveur/api/v1/app/download'),
        dir: dir.path,
        build: 46,
        sha256Hex: 'f' * 64,
        onProgress: (_) {},
      ),
      throwsA(isA<FileSystemException>()),
    );
    expect(dir.listSync(), isEmpty);
  });

  test('serveur en erreur : exception', () async {
    final down = MockClient((_) async => http.Response('', 404));
    await expectLater(
      downloadApk(
        down,
        Uri.parse('http://serveur/api/v1/app/download'),
        dir: dir.path,
        build: 46,
        sha256Hex: 'f' * 64,
        onProgress: (_) {},
      ),
      throwsA(isA<HttpException>()),
    );
  });
}
