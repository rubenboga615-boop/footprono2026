import 'dart:js_interop';

@JS('navigator.userAgent')
external String get _userAgent;

@JS('navigator.standalone')
external bool? get _standalone;

@JS('window.matchMedia')
external _MediaQueryList _matchMedia(String query);

extension type _MediaQueryList._(JSObject _) implements JSObject {
  external bool get matches;
}

/// iPhone ou iPad dans Safari, pas encore ajouté à l'écran d'accueil : on explique
/// comment installer FootProba (Apple ne permet pas de proposer l'installation).
bool get iosBrowserNotInstalled {
  try {
    final ua = _userAgent;
    final ios = ua.contains('iPhone') || ua.contains('iPad') || ua.contains('iPod');
    if (!ios) return false;
    final installed = (_standalone ?? false) || _matchMedia('(display-mode: standalone)').matches;
    return !installed;
  } catch (_) {
    return false;
  }
}
