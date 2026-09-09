import 'dart:async';

import 'package:core_pos/bootstrap/bootstrap_models.dart';
import 'package:core_pos/core/app_controller.dart';
import 'package:core_pos/network/pos_api.dart';
import 'package:core_pos/pairing/pairing_models.dart';
import 'package:core_pos/sales/quick_sale_page.dart';
import 'package:core_pos/sales/sale_models.dart';
import 'package:core_pos/storage/secret_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const product = QuickSaleProduct(
    id: 1,
    name: 'Coca',
    internalCode: 'COCA',
    price: '10.00',
    favorite: false,
    emitsTicket: false,
    modifierGroups: [],
  );

  AppController controller(_QuickSaleApi api) {
    final controller = AppController(
      api: api,
      secrets: _MemorySecretStore(),
      device: const DeviceDescriptor(
        name: 'Test',
        type: 'POS',
        appVersion: '1.0.0',
        osVersion: 'test',
        model: 'test',
      ),
    );
    controller.bootstrapSnapshot = const BootstrapSnapshot(
      companyName: 'Empresa',
      branchName: 'Filial',
      deviceName: 'Test',
      operatorName: 'Operador',
      release: ReleaseInfo(
        currentVersion: '1.0.0',
        latestVersion: '1.0.0',
        minimumSupportedVersion: '1.0.0',
        updateAvailable: false,
        updateRequired: false,
      ),
      modules: [],
    );
    return controller;
  }

  Future<void> open(WidgetTester tester, _QuickSaleApi api) async {
    await tester.binding.setSurfaceSize(const Size(1200, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
        MaterialApp(home: QuickSalePage(controller: controller(api))));
    await tester.pumpAndSettle();
  }

  testWidgets(
      'third unavailable mutation is removed without changing prior items',
      (tester) async {
    const products = [
      product,
      QuickSaleProduct(
        id: 2,
        name: 'Guarana',
        internalCode: 'GUARANA',
        price: '8.00',
        favorite: false,
        emitsTicket: false,
        modifierGroups: [],
      ),
      QuickSaleProduct(
        id: 3,
        name: 'Agua',
        internalCode: 'AGUA',
        price: '5.00',
        favorite: false,
        emitsTicket: false,
        modifierGroups: [],
      ),
    ];
    final api = _QuickSaleApi(
      (items) async => QuickSaleStockAvailability(
        available: items.length <= 2,
        enforced: true,
        shortages: const [
          {'available_quantity': '2'}
        ],
      ),
      catalog: products,
    );
    await open(tester, api);

    await tester.tap(find.text('Coca').first);
    await tester.tap(find.text('Guarana').first);
    await tester.tap(find.text('Agua').first);
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pumpAndSettle();

    expect(find.text('Qtd. 1'), findsNWidgets(2));
    expect(find.text('Coca'), findsNWidgets(2));
    expect(find.text('Guarana'), findsNWidgets(2));
    expect(find.text('Agua'), findsOneWidget);
    expect(
        find.textContaining('não possui estoque suficiente'), findsOneWidget);
    expect(api.previewCalls, 1);
  });

  testWidgets('invalid edit in the middle retains independent later items',
      (tester) async {
    const products = [
      product,
      QuickSaleProduct(
        id: 2,
        name: 'Guarana',
        internalCode: 'GUARANA',
        price: '8.00',
        favorite: false,
        emitsTicket: false,
        modifierGroups: [],
      ),
      QuickSaleProduct(
        id: 3,
        name: 'Agua',
        internalCode: 'AGUA',
        price: '5.00',
        favorite: false,
        emitsTicket: false,
        modifierGroups: [],
      ),
      QuickSaleProduct(
        id: 4,
        name: 'Suco',
        internalCode: 'SUCO',
        price: '7.00',
        favorite: false,
        emitsTicket: false,
        modifierGroups: [],
      ),
    ];
    final api = _QuickSaleApi(
      (items) async {
        final guarana = items.singleWhere(
          (item) => item['product'] == 2,
          orElse: () => const {},
        );
        return QuickSaleStockAvailability(
          available: guarana['quantity'] != '2',
          enforced: true,
          shortages: const [
            {'available_quantity': '1'}
          ],
        );
      },
      catalog: products,
    );
    await open(tester, api);

    for (final name in ['Coca', 'Guarana', 'Agua', 'Suco']) {
      await tester.tap(find.text(name).first);
    }
    await tester.pumpAndSettle();

    await tester.tap(find.text('Guarana').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.add_circle_outline));
    await tester.tap(find.text('SALVAR'));
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pumpAndSettle();

    expect(find.text('Qtd. 1'), findsNWidgets(4));
    expect(find.text('Qtd. 2'), findsNothing);
    expect(find.text('Agua'), findsNWidgets(2));
    expect(find.text('Suco'), findsNWidgets(2));
    expect(
        find.textContaining('não possui estoque suficiente'), findsOneWidget);
  });

  testWidgets('non-enforced availability never rolls back an optimistic tap',
      (tester) async {
    final api = _QuickSaleApi((_) async => const QuickSaleStockAvailability(
          available: true,
          enforced: false,
          shortages: [
            {'available_quantity': '0'}
          ],
        ));
    await open(tester, api);

    await tester.tap(find.text('Coca').first);
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pumpAndSettle();

    expect(find.text('Qtd. 1'), findsOneWidget);
  });

  testWidgets('a stale shortage response cannot replace a newer cart',
      (tester) async {
    final first = Completer<QuickSaleStockAvailability>();
    var calls = 0;
    final api = _QuickSaleApi((_) {
      calls++;
      if (calls == 1) return first.future;
      return Future.value(const QuickSaleStockAvailability(
        available: true,
        enforced: true,
        shortages: [],
      ));
    });
    await open(tester, api);

    await tester.tap(find.text('Coca').first);
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.text('Coca').first);
    await tester.pump(const Duration(milliseconds: 100));
    first.complete(const QuickSaleStockAvailability(
      available: false,
      enforced: true,
      shortages: [
        {'available_quantity': '0'}
      ],
    ));
    await tester.pumpAndSettle();

    expect(find.text('Qtd. 2'), findsOneWidget);
  });
}

class _QuickSaleApi implements PosApi {
  _QuickSaleApi(this.availability, {List<QuickSaleProduct>? catalog})
      : catalog = catalog ??
            const [
              QuickSaleProduct(
                id: 1,
                name: 'Coca',
                internalCode: 'COCA',
                price: '10.00',
                favorite: false,
                emitsTicket: false,
                modifierGroups: [],
              )
            ];
  final Future<QuickSaleStockAvailability> Function(List<Map<String, dynamic>>)
      availability;
  final List<QuickSaleProduct> catalog;
  var previewCalls = 0;

  @override
  Future<List<QuickSaleProduct>> quickSaleCatalog(
          {String? search, int? categoryId, bool favorites = false}) async =>
      catalog;

  @override
  Future<QuickSaleCheckoutOptions> quickSaleCheckoutOptions() async =>
      const QuickSaleCheckoutOptions(
        paymentMethods: [
          QuickSalePaymentMethod(id: 1, code: 'cash', name: 'Dinheiro')
        ],
        cashSessions: [QuickSaleCashSession(id: 1, registerName: 'Caixa')],
        cashBindingMode: 'FLEXIBLE',
        cashRequired: true,
        fixedCashAvailable: true,
      );

  @override
  Future<QuickSaleStockAvailability> quickSaleStockAvailability(
          {required List<Map<String, dynamic>> items}) =>
      availability(List<Map<String, dynamic>>.from(items));

  @override
  Future<QuickSalePreview> quickSalePreview(
      {required List<Map<String, dynamic>> items,
      required Map<String, dynamic> discount,
      required bool serviceFeeWaived}) async {
    previewCalls++;
    return const QuickSalePreview(
      items: [],
      subtotal: '0.00',
      promotionDiscountTotal: '0.00',
      itemDiscountTotal: '0.00',
      discount: '0.00',
      serviceFeeRate: '0.00',
      serviceFeeAmount: '0.00',
      total: '0.00',
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _MemorySecretStore implements SecretStore {
  @override
  Future<void> clearDeviceCredential() async {}
  @override
  Future<void> clearOperatorSession() async {}
  @override
  Future<String?> readDeviceCredential() async => null;
  @override
  Future<String?> readOperatorSession() async => null;
  @override
  Future<void> writeDeviceCredential(String credential) async {}
  @override
  Future<void> writeOperatorSession(String token) async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
