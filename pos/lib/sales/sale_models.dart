import '../cash/cash_models.dart';

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
        favorite: json['favorite'] as bool? ?? false,
        emitsTicket: json['emits_ticket'] as bool? ?? false,
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
  final bool favorite;
  final bool emitsTicket;
  final List<QuickSaleModifierGroup> modifierGroups;
}

class QuickSaleCartItem {
  const QuickSaleCartItem({
    required this.clientItemId,
    required this.product,
    required this.quantity,
    this.modifiers = const [],
    this.notes = '',
    this.discount = '0.00',
  });

  final String clientItemId;
  final QuickSaleProduct product;
  final String quantity;
  final List<Map<String, dynamic>> modifiers;
  final String notes;
  final String discount;

  QuickSaleCartItem copyWith({
    String? quantity,
    List<Map<String, dynamic>>? modifiers,
    String? notes,
    String? discount,
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
        'discount': discount,
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
    required this.subtotal,
    required this.promotionDiscountTotal,
    required this.itemDiscountTotal,
    required this.discount,
    required this.serviceFeeRate,
    required this.serviceFeeAmount,
    required this.total,
  });

  factory QuickSalePreview.fromJson(Map<String, dynamic> json) =>
      QuickSalePreview(
        subtotal: json['subtotal'] as String? ?? '0.00',
        promotionDiscountTotal:
            json['promotion_discount_total'] as String? ?? '0.00',
        itemDiscountTotal: json['item_discount_total'] as String? ?? '0.00',
        discount: json['discount'] as String? ?? '0.00',
        serviceFeeRate: json['service_fee_rate'] as String? ?? '0.00',
        serviceFeeAmount: json['service_fee_amount'] as String? ?? '0.00',
        total: json['total'] as String? ?? '0.00',
      );

  final String subtotal;
  final String promotionDiscountTotal;
  final String itemDiscountTotal;
  final String discount;
  final String serviceFeeRate;
  final String serviceFeeAmount;
  final String total;
}

class QuickSalePaymentMethod {
  const QuickSalePaymentMethod({
    required this.id,
    required this.code,
    required this.name,
  });

  factory QuickSalePaymentMethod.fromJson(Map<String, dynamic> json) =>
      QuickSalePaymentMethod(
        id: json['id'] as int,
        code: json['code'] as String? ?? '',
        name: json['name'] as String? ?? '',
      );

  final int id;
  final String code;
  final String name;
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
    required this.cashSessions,
    required this.cashBindingMode,
    required this.cashRequired,
    required this.fixedCashAvailable,
    this.fixedRegisterName,
  });

  factory QuickSaleCheckoutOptions.fromJson(Map<String, dynamic> json) =>
      QuickSaleCheckoutOptions(
        paymentMethods: (json['payment_methods'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>()
            .map(QuickSalePaymentMethod.fromJson)
            .toList(growable: false),
        cashSessions: (json['cash_sessions'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>()
            .map(QuickSaleCashSession.fromJson)
            .toList(growable: false),
        cashBindingMode: json['cash_binding_mode'] as String? ?? 'FLEXIBLE',
        cashRequired: json['cash_required'] as bool? ?? true,
        fixedCashAvailable: json['fixed_cash_available'] as bool? ?? true,
        fixedRegisterName: (json['fixed_register']
            as Map<String, dynamic>?)?['name'] as String?,
      );

  final List<QuickSalePaymentMethod> paymentMethods;
  final List<QuickSaleCashSession> cashSessions;
  final String cashBindingMode;
  final bool cashRequired;
  final bool fixedCashAvailable;
  final String? fixedRegisterName;
}

class QuickSaleResult {
  const QuickSaleResult({
    required this.saleNumber,
    required this.total,
    required this.cash,
    this.ticketNumbers = const [],
    this.productionJobCount = 0,
  });

  factory QuickSaleResult.fromJson(Map<String, dynamic> json) {
    final sale = json['sale'] as Map<String, dynamic>? ?? const {};
    final effects = json['effects'] as Map<String, dynamic>? ?? const {};
    return QuickSaleResult(
      saleNumber: sale['sale_number'] as String? ?? '',
      total: sale['total'] as String? ?? '0.00',
      cash: CashOverview.fromJson(
          json['cash_state'] as Map<String, dynamic>? ?? const {}),
      ticketNumbers:
          (effects['tickets'] as List<dynamic>? ?? const []).cast<int>(),
      productionJobCount: effects['production_job_count'] as int? ?? 0,
    );
  }

  final String saleNumber;
  final String total;
  final CashOverview cash;
  final List<int> ticketNumbers;
  final int productionJobCount;
}
