import 'package:core_pos/sales/sale_presentation.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('formats operational quantities for Brazilian presentation', () {
    expect(formatQuantity('1.000'), '1');
    expect(formatQuantity('1.500'), '1,5');
    expect(formatQuantity('0.500'), '0,5');
    expect(formatQuantity('1.250'), '1,25');
  });

  test('keeps API quantities canonical', () {
    expect(formatQuantityForApi(1.5), '1.5');
    expect(formatQuantityForApi(1), '1');
  });
}
