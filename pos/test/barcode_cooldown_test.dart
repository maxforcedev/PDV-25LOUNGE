import 'package:core_pos/scanner/barcode_cooldown.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('applies the cooldown only to the accepted barcode', () {
    var now = Duration.zero;
    final cooldown = BarcodeCooldown(now: () => now);

    expect(cooldown.accept('0012345678905'), isTrue);
    now = const Duration(milliseconds: 1900);
    expect(cooldown.accept('0012345678905'), isFalse);
    expect(cooldown.accept('7891234567890'), isTrue);
    now = const Duration(seconds: 2);
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
}
