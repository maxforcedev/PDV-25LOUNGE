import 'package:core_pos/scanner/barcode_cooldown.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('requires absence before rearming the accepted barcode', () {
    var now = Duration.zero;
    final cooldown = BarcodeCooldown(now: () => now);

    expect(cooldown.accept('0012345678905'), isTrue);
    now = const Duration(milliseconds: 1900);
    expect(cooldown.accept('0012345678905'), isFalse);
    expect(cooldown.accept('7891234567890'), isTrue);
    now = const Duration(milliseconds: 2100);
    expect(cooldown.accept('0012345678905'), isFalse);
    now = const Duration(milliseconds: 2601);
    expect(cooldown.accept('0012345678905'), isTrue);
  });

  test('preserves leading zeros and starts cooldown for unknown barcodes too',
      () {
    var now = Duration.zero;
    final cooldown = BarcodeCooldown(now: () => now);

    expect(cooldown.accept(' 0012345678905 '), isTrue);
    expect(cooldown.accept('12345678905'), isTrue);
    expect(cooldown.accept('0012345678905'), isFalse);
  });

  test('does not treat camera processing time as barcode absence', () {
    var now = Duration.zero;
    final cooldown = BarcodeCooldown(now: () => now);

    expect(cooldown.accept('7891234567890'), isTrue);
    now = const Duration(seconds: 3);
    cooldown.keepBlocked('7891234567890');
    now = const Duration(milliseconds: 3400);
    expect(cooldown.accept('7891234567890'), isFalse);
    now = const Duration(milliseconds: 3901);
    expect(cooldown.accept('7891234567890'), isTrue);
  });
}
