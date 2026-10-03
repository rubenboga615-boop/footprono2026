import 'package:flutter/services.dart';

import 'write_png_stub.dart' if (dart.library.io) 'write_png_io.dart';

/// Partage d'une image vers WhatsApp, Facebook… (canal « footprono/share », MainActivity.kt).
class ShareBridge {
  static const _channel = MethodChannel('footprono/share');

  static Future<void> shareImage(Uint8List png, String text) async {
    final dir = await _channel.invokeMethod<String>('sharedDir');
    final path = await writePng(dir!, png);
    await _channel.invokeMethod<void>('shareImage', {'path': path, 'text': text});
  }
}
