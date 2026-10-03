import 'dart:io';
import 'dart:typed_data';

/// Écrit l'image dans [dir] (dossier partagé avec les autres applications) et renvoie son chemin.
Future<String> writePng(String dir, Uint8List bytes) async {
  final folder = Directory(dir);
  if (!folder.existsSync()) folder.createSync(recursive: true);
  for (final old in folder.listSync()) {
    if (old is File) old.deleteSync();
  }
  final file = File('$dir/coupon-${DateTime.now().millisecondsSinceEpoch}.png');
  await file.writeAsBytes(bytes);
  return file.path;
}
