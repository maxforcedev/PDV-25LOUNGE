import 'package:flutter/services.dart';

class ScannerBeep {
  static const _channel = MethodChannel('core_pos/scanner_beep');

  static Future<void> play() async {
    try {
      await _channel.invokeMethod<void>('play');
    } on PlatformException {
      // The scanner flow must not depend on the audible feedback channel.
    } on MissingPluginException {
      // Non-Android targets do not provide the POS hardware tone.
    }
  }
}
