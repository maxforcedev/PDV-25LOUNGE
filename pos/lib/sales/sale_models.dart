import 'package:flutter/foundation.dart';

import '../cash/cash_models.dart';
import '../printing/models.dart';

class QuickSaleDiscountIntent {
  const QuickSaleDiscountIntent({
    this.type = 'amount',
    this.value = '0.00',
  });

  final String type;
  final String value;

  factory QuickSaleDiscountIntent.fromJson(Map<String, dynamic> json) =>
      QuickSaleDiscountIntent(
        type: json['type'] as String? ?? 'amount',
        value: json['value'] as String? ?? '0.00',
      );

  bool get isZero => double.tryParse(value.replaceAll(',', '.')) == 0;
  bool get isPercentage => type == 'percentage';

  QuickSaleDiscountIntent copyWith({String? type, String? value}) =>
      QuickSaleDiscountIntent(
          type: type ?? this.type, value: value ?? this.value);

  Map<String, dynamic> toJson() => {'type': type, 'value': value};
}

class QuickSaleCustomer {
  const QuickSaleCustomer({
    required this.id,
    required this.name,
    this.phone = '',
    this.document = '',
    this.email = '',
  });

  factory QuickSaleCustomer.fromJson(Map<String, dynamic> json) =>
      QuickSaleCustomer(
        id: json['id'] as int,
        name: json['name'] as String? ?? '',
        phone: json['phone'] as String? ?? '',
        document: json['document'] as String? ?? '',
        email: json['email'] as String? ?? '',
      );

  final int id;
  final String name;
  final String phone;
  final String document;
  final String email;
}

class QuickSaleCustomerSearch {
  const QuickSaleCustomerSearch({
    required this.customers,
    this.inactiveIdentity,
    this.canReactivate = false,
  });

  factory QuickSaleCustomerSearch.fromJson(Map<String, dynamic> json) {
    final inactive = json['inactive_identity'] as Map<String, dynamic>?;
    return QuickSaleCustomerSearch(
      customers: (json['customers'] as List<dynamic>? ?? const [])
          .cast<Map<String, dynamic>>()
          .map(QuickSaleCustomer.fromJson)
          .toList(growable: false),
      inactiveIdentity: inactive?['customer'] is Map<String, dynamic>
          ? QuickSaleCustomer.fromJson(
              inactive!['customer'] as Map<String, dynamic>)
          : null,
      canReactivate: inactive?['can_reactivate'] == true,
    );
  }

  final List<QuickSaleCustomer> customers;
  final QuickSaleCustomer? inactiveIdentity;
  final bool canReactivate;
}

class QuickSaleDraft extends ChangeNotifier {
  final List<QuickSaleCartItem> cart = [];
  QuickSalePreview? preview;
  QuickSaleCustomer? customer;
  QuickSaleDiscountIntent discount = const QuickSaleDiscountIntent();
  QuickSaleAuthorization? discountAuthorization;
  QuickSaleAuthorization? itemDiscountAuthorization;
  QuickSaleAuthorization? serviceFeeAuthorization;
  bool serviceFeeWaived = false;
  bool loadingPreview = false;

  void changed() => notifyListeners();

  void clearAfterSale() {
    cart.clear();
    preview = null;
    customer = null;
    discount = const QuickSaleDiscountIntent();
    discountAuthorization = null;
    itemDiscountAuthorization = null;
    serviceFeeAuthorization = null;
    serviceFeeWaived = false;
    loadingPreview = false;
    notifyListeners();
  }
}

class QuickSaleModifierOption {
  const QuickSaleModifierOption({
    required this.id,
    required this.name,
    required this.additionalPrice,
  });

  factory QuickSaleModifierOption.fromJson(Map<String, dynamic> json) =>
      QuickSaleModifierOption(
        id: json['id'] as int,
        name: json['name'] as String? ?? '',
        additionalPrice: json['additional_price'] as String? ?? '0.00',
      );

  final int id;
  final String name;
  final String additionalPrice;
}

class QuickSaleModifierGroup {
  const QuickSaleModifierGroup({
    required this.id,
    required this.name,
    required this.required,
    required this.minSelections,
    this.maxSelections,
    required this.allowOptionQuantity,
    required this.minTotalQuantity,
    this.maxTotalQuantity,
    this.requiredQuantity,
    required this.options,
  });

  factory QuickSaleModifierGroup.fromJson(Map<String, dynamic> json) =>
      QuickSaleModifierGroup(
        id: json['id'] as int,
        name: json['name'] as String? ?? '',
        required: json['is_required'] as bool? ?? false,
        minSelections: json['min_selections'] as int? ?? 0,
        maxSelections: json['max_selections'] as int?,
        allowOptionQuantity: json['allow_option_quantity'] as bool? ?? false,
        minTotalQuantity: json['min_total_quantity'] as String? ?? '0',
        maxTotalQuantity: json['max_total_quantity'] as String?,
        requiredQuantity: json['required_quantity'] as String?,
        options: (json['options'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>()
            .map(QuickSaleModifierOption.fromJson)
            .toList(growable: false),
      );

  final int id;
  final String name;
  final bool required;
  final int minSelections;
  final int? maxSelections;
  final bool allowOptionQuantity;
  final String minTotalQuantity;
  final String? maxTotalQuantity;
  final String? requiredQuantity;
  final List<QuickSaleModifierOption> options;
}

class QuickSaleProduct {
  const QuickSaleProduct({
    required this.id,
    required this.name,
    required this.internalCode,
    required this.price,
    required this.favorite,
    required this.emitsTicket,
    required this.modifierGroups,
    this.barcode,
    this.categoryId,
    this.categoryName,
    this.imageUrl,
    this.unit = 'un',
    this.inventoryBehavior = 'direct',
    this.stockApplicable = true,
    this.stockAvailable = true,
    this.canSell = true,
    this.availabilityReason,
    this.recoveryOnly = false,
  });

  factory QuickSaleProduct.fromJson(Map<String, dynamic> json) =>
      QuickSaleProduct(
        id: json['id'] as int,
        name: json['name'] as String? ?? '',
        internalCode: json['internal_code'] as String? ?? '',
        barcode: json['barcode'] as String?,
        categoryId: (json['category'] as Map<String, dynamic>?)?['id'] as int?,
        categoryName:
            (json['category'] as Map<String, dynamic>?)?['name'] as String?,
        imageUrl: json['image'] as String?,
        price: json['price'] as String? ?? '0.00',
        unit: json['unit'] as String? ?? 'un',
        favorite: json['favorite'] as bool? ?? false,
        emitsTicket: json['emits_ticket'] as bool? ?? false,
        inventoryBehavior: json['inventory_behavior'] as String? ?? 'direct',
        stockApplicable: json['stock_applicable'] as bool? ?? true,
        stockAvailable: json['stock_available'] as bool? ?? true,
        canSell: json['can_sell'] as bool? ?? true,
        availabilityReason: json['availability_reason'] as String?,
        recoveryOnly: json['recovery_only'] as bool? ?? false,
        modifierGroups: (json['modifier_groups'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>()
            .map(QuickSaleModifierGroup.fromJson)
            .toList(growable: false),
      );

  final int id;
  final String name;
  final String internalCode;
  final String? barcode;
  final int? categoryId;
  final String? categoryName;
  final String? imageUrl;
  final String price;
  final String unit;
  final bool favorite;
  final bool emitsTicket;
  final List<QuickSaleModifierGroup> modifierGroups;
  final String inventoryBehavior;
  final bool stockApplicable;
  final bool stockAvailable;
  final bool canSell;
  final String? availabilityReason;
  final bool recoveryOnly;
}

class QuickSaleAuthorizer {
  const QuickSaleAuthorizer({required this.id, required this.displayName});

  factory QuickSaleAuthorizer.fromJson(Map<String, dynamic> json) =>
      QuickSaleAuthorizer(
        id: json['id'] as int,
        displayName: json['display_name'] as String? ?? '',
      );

  final int id;
  final String displayName;
}

class QuickSaleAuthorization {
  const QuickSaleAuthorization(
      {required this.userId, required this.credential});

  final int userId;
  final String credential;

  Map<String, dynamic> toJson() => {
        'user': userId,
        'method': 'pin',
        'credential': credential,
      };

  // The PIN must never become part of a persisted idempotency intent.
  Map<String, dynamic> get idempotencyIdentity => {
        'user': userId,
        'method': 'pin',
      };
}

class QuickSaleStockAvailability {
  const QuickSaleStockAvailability({
    required this.available,
    required this.enforced,
    required this.shortages,
  });

  factory QuickSaleStockAvailability.fromJson(Map<String, dynamic> json) =>
      QuickSaleStockAvailability(
        available: json['available'] as bool? ?? false,
        enforced: json['enforced'] as bool? ?? true,
        shortages: (json['shortages'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>(),
      );

  final bool available;
  final bool enforced;
  final List<Map<String, dynamic>> shortages;

  String? get availableQuantity {
    for (final shortage in shortages) {
      final value = shortage['available_quantity'];
      if (value != null) return '$value';
    }
    return null;
  }
}

class QuickSaleCartItem {
  const QuickSaleCartItem({
    required this.clientItemId,
    required this.product,
    required this.quantity,
    this.modifiers = const [],
    this.notes = '',
    this.discount = const QuickSaleDiscountIntent(),
  });

  final String clientItemId;
  final QuickSaleProduct product;
  final String quantity;
  final List<Map<String, dynamic>> modifiers;
  final String notes;
  final QuickSaleDiscountIntent discount;

  QuickSaleCartItem copyWith({
    String? quantity,
    List<Map<String, dynamic>>? modifiers,
    String? notes,
    QuickSaleDiscountIntent? discount,
  }) =>
      QuickSaleCartItem(
        clientItemId: clientItemId,
        product: product,
        quantity: quantity ?? this.quantity,
        modifiers: modifiers ?? this.modifiers,
        notes: notes ?? this.notes,
        discount: discount ?? this.discount,
      );

  Map<String, dynamic> toJson() => {
        'client_item_id': clientItemId,
        'product': product.id,
        'quantity': quantity,
        'modifiers': modifiers,
        'notes': notes,
        'discount': discount.toJson(),
      };
}

class QuickSaleCategory {
  const QuickSaleCategory({required this.id, required this.name});

  factory QuickSaleCategory.fromJson(Map<String, dynamic> json) =>
      QuickSaleCategory(
          id: json['id'] as int, name: json['name'] as String? ?? '');

  final int id;
  final String name;
}

class QuickSalePreview {
  const QuickSalePreview({
    required this.items,
    required this.subtotal,
    required this.promotionDiscountTotal,
    required this.itemDiscountTotal,
    required this.discount,
    required this.serviceFeeRate,
    required this.serviceFeeAmount,
    required this.total,
  });

  factory QuickSalePreview.fromJson(Map<String, dynamic> json) {
    final financials =
        Map<String, dynamic>.from(json['financials'] as Map? ?? const {});
    final values = {...json, ...financials};
    return QuickSalePreview(
      items: (json['items'] as List<dynamic>? ?? const [])
          .cast<Map<String, dynamic>>()
          .map(QuickSalePreviewItem.fromJson)
          .toList(growable: false),
      subtotal: values['subtotal'] as String? ?? '0.00',
      promotionDiscountTotal:
          values['promotion_discount_total'] as String? ?? '0.00',
      itemDiscountTotal: values['item_discount_total'] as String? ?? '0.00',
      discount: values['discount'] as String? ?? '0.00',
      serviceFeeRate: values['service_fee_rate'] as String? ?? '0.00',
      serviceFeeAmount: values['service_fee_amount'] as String? ?? '0.00',
      total: values['total'] as String? ?? '0.00',
    );
  }

  final List<QuickSalePreviewItem> items;
  final String subtotal;
  final String promotionDiscountTotal;
  final String itemDiscountTotal;
  final String discount;
  final String serviceFeeRate;
  final String serviceFeeAmount;
  final String total;

  QuickSalePreviewItem? itemFor(String clientItemId) {
    for (final item in items) {
      if (item.clientItemId == clientItemId) return item;
    }
    return null;
  }
}

class QuickSalePreviewItem {
  const QuickSalePreviewItem({
    required this.clientItemId,
    required this.unitPrice,
    required this.modifiersTotal,
    required this.grossTotal,
    required this.itemDiscount,
    required this.lineTotal,
  });

  factory QuickSalePreviewItem.fromJson(Map<String, dynamic> json) =>
      QuickSalePreviewItem(
        clientItemId: json['client_item_id'] as String? ?? '',
        unitPrice: json['unit_price'] as String? ?? '0.00',
        modifiersTotal: json['modifiers_total'] as String? ?? '0.00',
        grossTotal: json['gross_total'] as String? ?? '0.00',
        itemDiscount: json['item_discount'] as String? ?? '0.00',
        lineTotal: json['line_total'] as String? ?? '0.00',
      );

  final String clientItemId;
  final String unitPrice;
  final String modifiersTotal;
  final String grossTotal;
  final String itemDiscount;
  final String lineTotal;
}

class QuickSalePaymentMethod {
  const QuickSalePaymentMethod({
    required this.id,
    required this.code,
    required this.name,
    this.visualGroup = 'other',
    this.kind = 'other',
    this.source = 'manual',
  });

  factory QuickSalePaymentMethod.fromJson(Map<String, dynamic> json) =>
      QuickSalePaymentMethod(
        id: json['id'] as int,
        code: json['code'] as String? ?? '',
        name: json['name'] as String? ?? '',
        visualGroup: json['visual_group'] as String? ?? 'other',
        kind: json['kind'] as String? ?? 'other',
        source: json['source'] as String? ?? 'manual',
      );

  final int id;
  final String code;
  final String name;
  final String visualGroup;
  final String kind;
  final String source;

  bool get isCash => kind == 'cash';
}

class QuickSaleCheckout {
  const QuickSaleCheckout({
    required this.id,
    required this.status,
    required this.preview,
    required this.paidAmount,
    required this.remainingAmount,
    required this.hasPaymentHistory,
    required this.discountIntent,
    required this.serviceFeeWaived,
    required this.items,
    required this.payments,
    required this.canEditFinancials,
    required this.canRecordPayment,
    required this.canPayByItems,
    required this.canFinalize,
    required this.canReversePayment,
    this.customer,
  });

  factory QuickSaleCheckout.fromJson(Map<String, dynamic> json) =>
      QuickSaleCheckout(
        id: json['id'] as String,
        status: json['operational_status'] as String? ??
            json['status'] as String? ??
            'editing',
        preview: QuickSalePreview.fromJson(
            json['preview'] as Map<String, dynamic>? ?? const {}),
        paidAmount: json['paid_amount'] as String? ?? '0.00',
        remainingAmount: json['remaining_amount'] as String? ?? '0.00',
        hasPaymentHistory: json['has_payment_history'] as bool? ?? false,
        discountIntent: QuickSaleDiscountIntent.fromJson(
            json['discount_intent'] as Map<String, dynamic>? ?? const {}),
        serviceFeeWaived: json['service_fee_waived'] as bool? ?? false,
        items: (json['items'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>()
            .map(QuickSaleCheckoutItem.fromJson)
            .toList(growable: false),
        payments: (json['payments'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>()
            .map(QuickSaleCheckoutPayment.fromJson)
            .toList(growable: false),
        canEditFinancials: json['capabilities']?['can_edit_financials'] == true,
        canRecordPayment: json['capabilities']?['can_record_payment'] == true,
        canPayByItems: json['capabilities']?['can_pay_by_items'] == true,
        canFinalize: json['capabilities']?['can_finalize'] == true,
        canReversePayment: json['capabilities']?['can_reverse_payment'] == true,
        customer: json['customer'] is Map<String, dynamic>
            ? QuickSaleCustomer.fromJson(
                json['customer'] as Map<String, dynamic>)
            : null,
      );

  final String id;
  final String status;
  final QuickSalePreview preview;
  final String paidAmount;
  final String remainingAmount;
  final bool hasPaymentHistory;
  final QuickSaleDiscountIntent discountIntent;
  final bool serviceFeeWaived;
  final List<QuickSaleCheckoutItem> items;
  final List<QuickSaleCheckoutPayment> payments;
  final bool canEditFinancials;
  final bool canRecordPayment;
  final bool canPayByItems;
  final bool canFinalize;
  final bool canReversePayment;
  final QuickSaleCustomer? customer;

  bool hasReversalFor(String paymentId) =>
      payments.any((payment) => payment.reversalOf == paymentId);

  QuickSaleCheckoutPayment? reversalFor(String paymentId) {
    for (final payment in payments) {
      if (payment.reversalOf == paymentId) return payment;
    }
    return null;
  }
}

class QuickSaleCheckoutItem {
  const QuickSaleCheckoutItem({
    required this.id,
    required this.name,
    required this.quantity,
    required this.availableQuantity,
    required this.unit,
    required this.input,
    this.recoveryProduct,
  });
  factory QuickSaleCheckoutItem.fromJson(Map<String, dynamic> json) =>
      QuickSaleCheckoutItem(
          id: json['id'] as int,
          name: json['product_name'] as String? ?? 'Item',
          quantity: json['quantity'] as String? ?? '0',
          availableQuantity: json['available_quantity'] as String? ??
              json['quantity'] as String? ??
              '0',
          unit: json['unit'] as String? ?? 'un',
          input: Map<String, dynamic>.from(json['input'] as Map? ?? const {}),
          recoveryProduct: json['recovery_product'] is Map
              ? QuickSaleProduct.fromJson(
                  Map<String, dynamic>.from(json['recovery_product'] as Map))
              : null);
  final int id;
  final String name;
  final String quantity;
  final String availableQuantity;
  final String unit;
  final Map<String, dynamic> input;
  final QuickSaleProduct? recoveryProduct;
}

/// A persisted operator payment attempt. Its UUID is also the API idempotency key.
class QuickSalePaymentAttempt {
  const QuickSalePaymentAttempt({
    required this.intentId,
    required this.paymentMethodId,
    required this.mode,
    required this.amount,
    required this.receivedAmount,
    required this.allocations,
  });

  factory QuickSalePaymentAttempt.fromJson(Map<String, dynamic> json) =>
      QuickSalePaymentAttempt(
        intentId: json['intent_id'] as String,
        paymentMethodId: json['payment_method_id'] as int,
        mode: json['mode'] as String,
        amount: json['amount'] as String?,
        receivedAmount: json['received_amount'] as String?,
        allocations: (json['allocations'] as List<dynamic>? ?? const [])
            .map((row) => Map<String, dynamic>.from(row as Map))
            .toList(growable: false),
      );

  final String intentId;
  final int paymentMethodId;
  final String mode;
  final String? amount;
  final String? receivedAmount;
  final List<Map<String, dynamic>> allocations;

  Map<String, dynamic> toJson() => {
        'intent_id': intentId,
        'payment_method_id': paymentMethodId,
        'mode': mode,
        'amount': amount,
        'received_amount': receivedAmount,
        'allocations': allocations,
      };
}

class QuickSaleCheckoutPayment {
  const QuickSaleCheckoutPayment(
      {required this.id,
      required this.methodName,
      required this.amount,
      required this.status,
      this.receivedAmount,
      this.changeAmount,
      this.idempotencyKey,
      this.reversalOf,
      this.reversalReason});
  factory QuickSaleCheckoutPayment.fromJson(Map<String, dynamic> json) =>
      QuickSaleCheckoutPayment(
          id: json['id'] as String,
          methodName: json['payment_method_name'] as String? ?? 'Pagamento',
          amount: json['amount'] as String? ?? '0.00',
          status: json['status'] as String? ?? '',
          receivedAmount: json['received_amount'] as String?,
          changeAmount: json['change_amount'] as String?,
          idempotencyKey: json['idempotency_key'] as String?,
          reversalOf: json['reversal_of'] as String?,
          reversalReason: json['reversal_reason'] as String?);
  final String id;
  final String methodName;
  final String amount;
  final String status;
  final String? receivedAmount;
  final String? changeAmount;
  final String? idempotencyKey;
  final String? reversalOf;
  final String? reversalReason;
  bool get isReversal => reversalOf != null || status == 'reversed';
}

class QuickSalePaymentPreview {
  const QuickSalePaymentPreview(
      {required this.total, required this.availableQuantities});
  factory QuickSalePaymentPreview.fromJson(Map<String, dynamic> json) =>
      QuickSalePaymentPreview(
          total: json['total'] as String? ?? '0.00',
          availableQuantities:
              (json['available_quantities'] as Map<String, dynamic>? ??
                      const {})
                  .map((key, value) => MapEntry(int.parse(key), '$value')));
  final String total;
  final Map<int, String> availableQuantities;
}

class QuickSaleCashSession {
  const QuickSaleCashSession({required this.id, required this.registerName});

  factory QuickSaleCashSession.fromJson(Map<String, dynamic> json) =>
      QuickSaleCashSession(
        id: json['id'] as int,
        registerName: json['register_name'] as String? ?? '',
      );

  final int id;
  final String registerName;
}

class QuickSaleCheckoutOptions {
  const QuickSaleCheckoutOptions({
    required this.paymentMethods,
    required this.cashBindingMode,
    required this.cashRequired,
    required this.cashReady,
    required this.fixedCashAvailable,
    this.fixedRegisterName,
  });

  factory QuickSaleCheckoutOptions.fromJson(Map<String, dynamic> json) =>
      QuickSaleCheckoutOptions(
        paymentMethods: (json['payment_methods'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>()
            .map(QuickSalePaymentMethod.fromJson)
            .toList(growable: false),
        cashBindingMode: json['cash_binding_mode'] as String? ?? 'FLEXIBLE',
        cashRequired: json['cash_required'] as bool? ?? true,
        cashReady: json['cash_ready'] as bool? ?? false,
        fixedCashAvailable: json['fixed_cash_available'] as bool? ?? true,
        fixedRegisterName: (json['fixed_register']
            as Map<String, dynamic>?)?['name'] as String?,
      );

  final List<QuickSalePaymentMethod> paymentMethods;
  final String cashBindingMode;
  final bool cashRequired;
  final bool cashReady;
  final bool fixedCashAvailable;
  final String? fixedRegisterName;
}

/// Legacy command checkout still selects a cash session explicitly.
class LegacyCheckoutOptions {
  const LegacyCheckoutOptions({
    required this.paymentMethods,
    this.cashSessions = const [],
  });

  factory LegacyCheckoutOptions.fromJson(Map<String, dynamic> json) =>
      LegacyCheckoutOptions(
        paymentMethods: (json['payment_methods'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>()
            .map(QuickSalePaymentMethod.fromJson)
            .toList(growable: false),
        cashSessions: (json['cash_sessions'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>()
            .map(QuickSaleCashSession.fromJson)
            .toList(growable: false),
      );

  final List<QuickSalePaymentMethod> paymentMethods;
  final List<QuickSaleCashSession> cashSessions;
}

class QuickSaleResult {
  const QuickSaleResult({
    required this.saleNumber,
    required this.total,
    required this.cash,
    this.saleId,
    this.receiptDocument,
    this.ticketNumbers = const [],
    this.ticketIds = const [],
    this.productionJobCount = 0,
  });

  factory QuickSaleResult.fromJson(Map<String, dynamic> json) {
    final sale = json['sale'] as Map<String, dynamic>? ?? const {};
    final effects = json['effects'] as Map<String, dynamic>? ?? const {};
    final tickets = effects['tickets'] as List<dynamic>? ?? const [];
    final receiptDocument = PrintDocumentResult.maybeFromJson(
          effects['print_document'] ??
              effects['quick_sale_receipt_document'] ??
              effects['print_document_id'],
        ) ??
        _documentFromList(effects['print_documents']);
    return QuickSaleResult(
      saleNumber: sale['sale_number'] as String? ?? '',
      saleId: sale['id']?.toString(),
      receiptDocument: receiptDocument,
      total: sale['total'] as String? ?? '0.00',
      cash: CashOverview.fromJson(
          json['cash_state'] as Map<String, dynamic>? ?? const {}),
      ticketNumbers: tickets
          .map((ticket) => ticket is Map ? ticket['number'] : ticket)
          .whereType<num>()
          .map((number) => number.toInt())
          .toList(growable: false),
      ticketIds: tickets
          .whereType<Map>()
          .map((ticket) => ticket['id']?.toString())
          .whereType<String>()
          .toList(growable: false),
      productionJobCount: effects['production_job_count'] as int? ?? 0,
    );
  }

  final String saleNumber;
  final String? saleId;
  final PrintDocumentResult? receiptDocument;
  final String total;
  final CashOverview cash;
  final List<int> ticketNumbers;
  final List<String> ticketIds;
  final int productionJobCount;

  String? get receiptDocumentId => receiptDocument?.id;

  static PrintDocumentResult? _documentFromList(Object? value) {
    if (value is! List) return null;
    for (final document in value) {
      final result = PrintDocumentResult.maybeFromJson(document);
      if (result?.documentType == PrintDocumentType.quickSaleReceipt) {
        return result;
      }
    }
    return null;
  }
}
