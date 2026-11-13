import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:footprono/state/app_state.dart';

class _CodeError implements Exception {
  _CodeError(this.code);
  final String code;
}

void main() {
  test("connexion Google : le code de l'échec est gardé pour l'aide", () {
    expect(googleErrorCode(_CodeError('internal-error')), 'internal-error');
    expect(googleErrorCode(TimeoutException('lent')), 'TimeoutException');
    expect(googleErrorCode(_CodeError('')), '_CodeError');
  });
}
