import 'package:flutter/material.dart';

import '../attendance/attendance_models.dart';
import '../attendance/table_order_item_grouping.dart';
import '../cash/cash_models.dart' show createIdempotencyKey;
import '../core/app_controller.dart';
import '../sales/sale_models.dart';
import '../sales/shared_authorization_dialog.dart';
import '../sales/shared_customer_dialog.dart';
import '../sales/shared_discount_dialog.dart';
import '../printing/models.dart';
import 'payment_contract.dart';
import 'payment_flow_components.dart';
import 'shared_payment_widgets.dart';
import 'table_payment_adapter.dart';

class TablePaymentPage extends StatefulWidget {
  const TablePaymentPage({
    required this.controller,
    required this.attendance,
    required this.onClosed,
    super.key,
  });

  final AppController controller;
  final TableAttendance attendance;
  final Future<void> Function(TableAttendance attendance) onClosed;

  @override
  State<TablePaymentPage> createState() => _TablePaymentPageState();
}

class _TablePaymentPageState extends State<TablePaymentPage> {
  late TableAttendance _attendance = widget.attendance;
  TablePaymentLedger? _ledger;
  QuickSaleCheckoutOptions? _options;
  _TablePaymentRequest? _pending;
  Map<String, dynamic> _pendingRaw = const {};
  final Map<int, String> _reverseKeys = {};
  String? _closeKey;
  bool _loading = true;
  bool _working = false;
  bool _details = false;
  final Set<int> _printedReceipts = {};
  final Map<int, String> _paymentDocumentIds = {};

  bool _can(String permission) =>
      widget.controller.bootstrapSnapshot?.permissions.contains(permission) ==
      true;
  Map<String, dynamic> get _summary => _ledger?.summary ?? _attendance.summary;
  String _money(String key) => '${_summary[key] ?? '0.00'}';
  bool get _isOpen => _attendance.status == 'open';
  bool get _canRecord =>
      _isOpen &&
      _can('tables.payments.record') &&
      _cents(_money('remaining_balance')) > 0;
  bool get _canClose =>
      _isOpen &&
      _can('tables.close') &&
      _cents(_money('remaining_balance')) == 0;
  bool get _financialEditable =>
      _isOpen && _activePayments.isEmpty && _can('tables.add_items');
  bool get _hasPending => _pendingRaw.isNotEmpty;

  List<TablePayment> get _activePayments => (_ledger?.payments ?? const [])
      .where((payment) => !payment.isReversal && !_hasReversal(payment.id))
      .toList(growable: false);

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() => _loading = true);
    final results = await Future.wait<Object?>([
      widget.controller.tableAttendanceDetail(_attendance.id),
      widget.controller.tablePaymentLedger(_attendance.id),
      widget.controller.tableCheckoutOptions(),
      widget.controller.tablePaymentPending(_attendance.id),
    ]);
    if (!mounted) return;
    final pending = Map<String, dynamic>.from(results[3] as Map);
    final pendingKey = pending['idempotency_key'] as String?;
    final confirmed = pendingKey != null &&
        (results[1] as TablePaymentLedger? ?? _ledger)
                ?.payments
                .any((payment) => payment.idempotencyKey == pendingKey) ==
            true;
    setState(() {
      _attendance = results[0] as TableAttendance? ?? _attendance;
      _ledger = results[1] as TablePaymentLedger? ?? _ledger;
      _options = results[2] as QuickSaleCheckoutOptions? ?? _options;
      _pendingRaw = confirmed ? const {} : pending;
      _pending = _TablePaymentRequest.fromJson(_pendingRaw, _methods);
      if (confirmed) {
        _pending = null;
      }
      _loading = false;
    });
    if (confirmed) {
      await widget.controller
          .writeTablePaymentPending(_attendance.id, const {});
    }
  }

  PaymentSummaryData get _summaryData => _adapter.summary;

  List<QuickSalePaymentMethod> get _methods =>
      _options?.paymentMethods ?? const [];

  bool _hasReversal(int paymentId) => (_ledger?.payments ?? const [])
      .any((payment) => payment.reversalOf == paymentId);

  TablePayment? _reversalFor(int paymentId) {
    for (final payment in _ledger?.payments ?? const <TablePayment>[]) {
      if (payment.reversalOf == paymentId) return payment;
    }
    return null;
  }

  Future<void> _selectMethod(QuickSalePaymentMethod method) async {
    if (!_canRecord || _working || _hasPending) return;
    await _requestPayment(method, mode: 'value');
  }

  Future<void> _requestPayment(
    QuickSalePaymentMethod method, {
    required String mode,
    List<Map<String, dynamic>> allocations = const [],
    String? officialAmount,
  }) async {
    if (!mounted) return;
    final entry = await Navigator.of(context).push<PaymentEntryResult>(
      MaterialPageRoute(
          builder: (_) => PaymentEntryPage(
                method: method,
                remaining: _money('remaining_balance'),
                initialAmount: mode == 'equal_people'
                    ? '${(_summary['equal_split'] as Map? ?? const {})['next_amount'] ?? '0.00'}'
                    : officialAmount,
                amountLocked: mode == 'equal_people' || mode == 'items',
                amountContext: mode == 'equal_people'
                    ? PaymentAmountContext.equalSplit
                    : mode == 'items'
                        ? PaymentAmountContext.items
                        : mode == 'remaining'
                            ? PaymentAmountContext.remaining
                            : PaymentAmountContext.value,
              )),
    );
    if (entry == null || !mounted) return;
    final request = _TablePaymentRequest(
      method: method,
      mode: mode == 'value' && entry.payingRemaining ? 'remaining' : mode,
      idempotencyKey: entry.intentId,
      amount: entry.amount,
      receivedAmount: entry.receivedAmount,
      allocations: allocations,
    );
    await _record(request);
  }

  Future<void> _record(_TablePaymentRequest request) async {
    setState(() {
      _working = true;
      _pending = request;
      _pendingRaw = request.toJson();
    });
    await widget.controller
        .writeTablePaymentPending(_attendance.id, request.toJson());
    final payment = await widget.controller.recordTablePayment(
      attendanceId: _attendance.id,
      paymentMethodId: request.method.id,
      mode: request.mode,
      idempotencyKey: request.idempotencyKey,
      amount: request.amount,
      receivedAmount: request.receivedAmount,
      allocations: request.allocations,
    );
    if (!mounted) return;
    setState(() => _working = false);
    if (payment != null) {
      await _refresh();
    }
  }

  Future<void> _reverse(TablePayment payment) async {
    final reason = await showDialog<String>(
      context: context,
      builder: (_) => PaymentReversalDialog(payment: _display(payment)),
    );
    if (reason == null || !mounted) return;
    QuickSaleAuthorization? authorization;
    if (!_can('tables.payments.reverse')) {
      final authorizers =
          await widget.controller.tablePaymentReverseAuthorizers();
      if (!mounted || authorizers == null) return;
      if (authorizers.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content:
              Text('Nenhum autorizador elegível está disponível nesta filial.'),
        ));
        return;
      }
      authorization = await showDialog<QuickSaleAuthorization>(
        context: context,
        builder: (_) => SharedAuthorizationDialog(
          authorizers: authorizers,
          onAuthorize: widget.controller.validateTablePaymentAuthorization,
        ),
      );
      if (authorization == null || !mounted) return;
    }
    setState(() => _working = true);
    final reversed = await widget.controller.reverseTablePayment(
      paymentId: payment.id,
      idempotencyKey:
          _reverseKeys.putIfAbsent(payment.id, createIdempotencyKey),
      reason: reason,
      authorization: authorization,
    );
    if (!mounted) return;
    setState(() => _working = false);
    if (reversed != null) {
      _reverseKeys.remove(payment.id);
      await _refresh();
    }
  }

  Future<void> _printPaymentReceipt(TablePayment payment) async {
    if (_working || payment.isReversal) return;
    setState(() => _working = true);
    final documentId = _paymentDocumentIds[payment.id];
    final result = documentId == null
        ? await widget.controller.requestPrintDocument(
            PrintDocumentRequest(
              type: PrintDocumentType.paymentReceipt,
              sourceType: 'table_payment',
              sourceId: '${payment.id}',
              idempotencyKey: createIdempotencyKey(),
            ),
          )
        : await widget.controller.reprintPrintDocument(
            PrintDocumentReprintRequest(
              documentId: documentId,
              idempotencyKey: createIdempotencyKey(),
              reason: 'Reimpressão de comprovante de pagamento',
            ),
          );
    if (!mounted) return;
    setState(() {
      _working = false;
      if (result != null) {
        _printedReceipts.add(payment.id);
        if (result.id != null) _paymentDocumentIds[payment.id] = result.id!;
      }
    });
  }

  Future<void> _close() async {
    setState(() => _working = true);
    final closed = await widget.controller.closeTableAttendance(
      attendanceId: _attendance.id,
      idempotencyKey: _closeKey ??= createIdempotencyKey(),
    );
    if (!mounted) return;
    setState(() => _working = false);
    if (closed != null) {
      _closeKey = null;
      await widget.onClosed(closed);
      if (mounted && closed.finalSaleId != null) {
        await _showFinalReceiptAction(
          closed.id,
          documentId:
              closed.printDocumentFor(PrintDocumentType.tableFinalReceipt)?.id,
        );
      }
      if (mounted) Navigator.of(context).pop(closed);
    }
  }

  Future<void> _showFinalReceiptAction(int attendanceId,
      {String? documentId}) async {
    var printed = documentId != null;
    await showDialog<void>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('Mesa fechada'),
          content: const Text('A mesa foi fechada com sucesso.'),
          actions: [
            TextButton(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('FECHAR')),
            FilledButton.icon(
              onPressed: () async {
                final result = documentId == null
                    ? await widget.controller.requestPrintDocument(
                        PrintDocumentRequest(
                          type: PrintDocumentType.tableFinalReceipt,
                          sourceType: 'table_attendance',
                          sourceId: '$attendanceId',
                          idempotencyKey: createIdempotencyKey(),
                        ),
                      )
                    : await widget.controller.reprintPrintDocument(
                        PrintDocumentReprintRequest(
                          documentId: documentId!,
                          idempotencyKey: createIdempotencyKey(),
                          reason: 'Reimpressão de recibo final de mesa',
                        ),
                      );
                if (result != null && context.mounted) {
                  setDialogState(() {
                    printed = true;
                    documentId ??= result.id;
                  });
                }
              },
              icon: const Icon(Icons.print_outlined),
              label: Text(printed ? 'REIMPRIMIR RECIBO' : 'IMPRIMIR RECIBO'),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _setCustomer() async {
    final customer = await showDialog<QuickSaleCustomer>(
      context: context,
      builder: (_) => SharedCustomerPickerDialog(
        controller: widget.controller,
        canCreate: _can('customers.add'),
        canReactivate: _can('customers.change'),
      ),
    );
    if (customer == null || !mounted) return;
    final updated = await widget.controller.setTableAttendanceCustomer(
      attendanceId: _attendance.id,
      customerId: customer.id,
      idempotencyKey: createIdempotencyKey(),
    );
    if (updated != null && mounted) await _refresh();
  }

  Future<void> _showSplitSelector() => showModalBottomSheet<void>(
        context: context,
        builder: (_) => PaymentSplitSelector(
          canPayByItems: true,
          enabled: _canRecord && !_working && !_hasPending,
          onEqualSplit: () {
            Navigator.pop(context);
            _selectEqualSplit();
          },
          onItems: () {
            Navigator.pop(context);
            _selectItems();
          },
        ),
      );

  Future<void> _selectEqualSplit() async {
    final split =
        Map<String, dynamic>.from(_summary['equal_split'] as Map? ?? const {});
    final person = split['next_person'];
    final amount = '${split['next_amount'] ?? '0.00'}';
    if (person == null || _cents(amount) == 0) return;
    final personNumber = person as int;
    final people = split['people_count'] as int? ?? personNumber;
    final selection =
        await Navigator.of(context).push<PaymentEqualSplitSelection>(
      MaterialPageRoute(
        builder: (_) => PaymentEqualSplitPage(
          remaining: _money('remaining_balance'),
          officialPerson: personNumber,
          officialPeopleCount: people,
          officialAmount: amount,
        ),
      ),
    );
    if (selection == null || !mounted) return;
    final method = await PaymentMethodPicker.show(
      context,
      title: 'Forma para pessoa $person',
      methods: _methods,
    );
    if (method != null && mounted)
      await _requestPayment(
        method,
        mode: 'equal_people',
        officialAmount: selection.amount,
      );
  }

  Future<void> _selectItems() async {
    final payments = _ledger?.payments ?? const <TablePayment>[];
    int allocated(TableOrderItem item) => payments
        .where((payment) => !payment.isReversal && !_hasReversal(payment.id))
        .expand((payment) => payment.allocations)
        .where((allocation) => allocation['item'] == item.id)
        .fold(
            0,
            (total, allocation) =>
                total +
                _quantityUnits('${allocation['allocated_quantity'] ?? '0'}'));
    String availableQuantity(TableOrderItem item) {
      final available = _quantityUnits(item.quantity) - allocated(item);
      return _quantityValue(available < 0 ? 0 : available);
    }

    final items = tableOrderItemGroups(_attendance, confirmedOnly: true)
        .map((group) => PaymentAllocationItem(
              name: group.item.productName,
              quantity: _quantityValue(group.entries.fold<int>(
                  0,
                  (total, entry) =>
                      total + _quantityUnits(entry.item.quantity))),
              unit: group.item.unit,
              sources: group.entriesByOperationalAge
                  .map((entry) => PaymentAllocationSource(
                        itemId: entry.item.id,
                        quantity: entry.item.quantity,
                        availableQuantity: availableQuantity(entry.item),
                      ))
                  .toList(growable: false),
            ))
        .toList(growable: false);
    final selection =
        await Navigator.of(context).push<PaymentAllocationSelection>(
      MaterialPageRoute(
          builder: (_) => PaymentItemAllocationPage(
                items: items,
                remaining: _money('remaining_balance'),
                preview: (allocations) async {
                  final preview = await widget.controller.previewTablePayment(
                      attendanceId: _attendance.id, allocations: allocations);
                  return preview == null
                      ? null
                      : PaymentAllocationPreview(
                          total: preview.total,
                          availableQuantities: preview.availableQuantities);
                },
              )),
    );
    if (selection == null || !mounted) return;
    final method = await PaymentMethodPicker.show(
      context,
      title: 'Forma para os itens',
      methods: _methods,
    );
    if (method != null && mounted) {
      await _requestPayment(method,
          mode: 'items',
          allocations: selection.allocations,
          officialAmount: selection.total);
    }
  }

  Future<QuickSaleAuthorization?> _financialAuthorization(
      String type, String permission) async {
    if (_can(permission)) return null;
    final authorizers = await widget.controller.tableFinancialAuthorizers(type);
    if (!mounted || authorizers == null) return null;
    if (authorizers.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content:
            Text('Nenhum autorizador elegível está disponível nesta filial.'),
      ));
      return null;
    }
    return showDialog<QuickSaleAuthorization>(
      context: context,
      builder: (_) => SharedAuthorizationDialog(
        authorizers: authorizers,
        onAuthorize: (authorization) =>
            widget.controller.validateTableFinancialAuthorization(
          type: type,
          authorization: authorization,
        ),
      ),
    );
  }

  Future<void> _editDiscount() async {
    final discount = await showDialog<QuickSaleDiscountIntent>(
      context: context,
      builder: (_) => SharedDiscountDialog(
        initial: QuickSaleDiscountIntent(
          type: _attendance.checkoutDiscountType,
          value: _attendance.checkoutDiscount,
        ),
        maximumAmount: _cents(_summaryData.total) / 100,
        prefillInitialValue: true,
      ),
    );
    if (discount == null || !mounted) return;
    final authorization = _cents(discount.value) > 0
        ? await _financialAuthorization('sale', 'sales.apply_discount')
        : null;
    if (!mounted ||
        (_cents(discount.value) > 0 &&
            authorization == null &&
            !_can('sales.apply_discount'))) {
      return;
    }
    await _updateFinancialContext(
        discount.toJson(), _attendance.checkoutServiceFeeWaived,
        discountAuthorization: authorization);
  }

  Future<void> _toggleServiceFee() async {
    final waive = !_attendance.checkoutServiceFeeWaived;
    final authorization = waive
        ? await _financialAuthorization(
            'service_fee', 'sales.waive_service_fee')
        : null;
    if (!mounted ||
        (waive && authorization == null && !_can('sales.waive_service_fee'))) {
      return;
    }
    await _updateFinancialContext({
      'type': _attendance.checkoutDiscountType,
      'value': _attendance.checkoutDiscount,
    }, waive, serviceFeeAuthorization: authorization);
  }

  Future<void> _updateFinancialContext(Object discount, bool serviceFeeWaived,
      {QuickSaleAuthorization? discountAuthorization,
      QuickSaleAuthorization? serviceFeeAuthorization}) async {
    setState(() => _working = true);
    final updated = await widget.controller.setTableCheckoutContext(
      attendanceId: _attendance.id,
      discount: discount,
      serviceFeeWaived: serviceFeeWaived,
      idempotencyKey: createIdempotencyKey(),
      discountAuthorization: discountAuthorization?.toJson(),
      serviceFeeAuthorization: serviceFeeAuthorization?.toJson(),
    );
    if (!mounted) return;
    setState(() => _working = false);
    if (updated != null) await _refresh();
  }

  PaymentDisplayEntry _display(TablePayment payment) =>
      _adapter.payment(payment);

  TablePaymentAdapter get _adapter => TablePaymentAdapter(_attendance, _ledger);

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: const Text('PAGAMENTO'),
          actions: [
            PaymentHeaderActions(
              customerLabel: _attendance.customerName.isEmpty
                  ? 'CLIENTE'
                  : _attendance.customerName,
              canEditCustomer: _financialEditable &&
                  _can('tables.set_customer') &&
                  !_working,
              canSplit: _canRecord && !_working && !_hasPending,
              onCustomer: _setCustomer,
              onSplit: _showSplitSelector,
              menu: PopupMenuButton<String>(
                enabled: !_working,
                onSelected: (action) {
                  if (action == 'refresh') _refresh();
                  if (action == 'discount') _editDiscount();
                  if (action == 'fee') _toggleServiceFee();
                },
                itemBuilder: (_) => [
                  const PopupMenuItem(
                      value: 'refresh', child: Text('ATUALIZAR')),
                  if (_financialEditable) ...[
                    const PopupMenuItem(
                        value: 'discount', child: Text('ALTERAR DESCONTO')),
                    PopupMenuItem(
                      value: 'fee',
                      child: Text(_attendance.checkoutServiceFeeWaived
                          ? 'RESTAURAR TAXA DE SERVIÇO'
                          : 'RETIRAR TAXA DE SERVIÇO'),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
        body: _loading
            ? const Center(child: CircularProgressIndicator())
            : PaymentPageLayout(
                summary: _summaryData,
                methodGrid: _methodGrid(),
                pendingAction: !_hasPending
                    ? null
                    : OutlinedButton.icon(
                        onPressed: _working
                            ? null
                            : _pending == null
                                ? _refresh
                                : () => _record(_pending!),
                        icon: const Icon(Icons.refresh),
                        label: Text(_pending == null
                            ? 'RECONCILIAR PENDÊNCIA'
                            : 'TENTAR NOVAMENTE'),
                      ),
                history: _history(),
                summaryPanel: _summaryPanel(),
              ),
      );

  Widget _methodGrid() {
    return PaymentMethodGrid(
      methods: _methods,
      enabled: _canRecord && !_working && !_hasPending,
      onSelect: (methods) async {
        final method = methods.length == 1
            ? methods.single
            : await PaymentMethodPicker.show(
                context,
                title: 'Formas de pagamento',
                methods: methods,
              );
        if (method != null && mounted) await _selectMethod(method);
      },
    );
  }

  Widget _history() {
    final payments = (_ledger?.payments ?? const [])
        .where((payment) => !payment.isReversal)
        .toList(growable: false);
    return PaymentHistoryList(
      entries: payments.map((payment) {
        final reversal = _reversalFor(payment.id);
        return PaymentHistoryEntry(
          payment: _display(payment),
          reversed: reversal != null,
          reversalReason: reversal?.reversalReason,
          working: _working,
          onReverse: () => _reverse(payment),
          onPrint: reversal == null
              ? () {
                  _printPaymentReceipt(payment);
                }
              : null,
          printTooltip: _printedReceipts.contains(payment.id)
              ? 'Reimprimir comprovante'
              : 'Imprimir comprovante',
        );
      }).toList(growable: false),
    );
  }

  Widget _summaryPanel() => PaymentFinancialSummary(
        summary: _summaryData,
        showDetails: _details,
        onToggleDetails: () => setState(() => _details = !_details),
        primaryAction: _canClose
            ? FilledButton(
                onPressed: _working ? null : _close,
                child: const Text('FECHAR MESA'),
              )
            : null,
      );
}

class _TablePaymentRequest {
  const _TablePaymentRequest({
    required this.method,
    required this.mode,
    required this.idempotencyKey,
    required this.allocations,
    this.amount,
    this.receivedAmount,
  });

  final QuickSalePaymentMethod method;
  final String mode;
  final String idempotencyKey;
  final String? amount;
  final String? receivedAmount;
  final List<Map<String, dynamic>> allocations;

  Map<String, dynamic> toJson() => {
        'payment_method_id': method.id,
        'mode': mode,
        'idempotency_key': idempotencyKey,
        'amount': amount,
        'received_amount': receivedAmount,
        'allocations': allocations,
      };

  static _TablePaymentRequest? fromJson(
      Map<String, dynamic> json, List<QuickSalePaymentMethod> methods) {
    if (json.isEmpty) return null;
    final methodId = json['payment_method_id'] as int?;
    final method = methods.where((value) => value.id == methodId).firstOrNull;
    final key = json['idempotency_key'] as String?;
    if (method == null || key == null) return null;
    return _TablePaymentRequest(
      method: method,
      mode: json['mode'] as String? ?? 'value',
      idempotencyKey: key,
      amount: json['amount'] as String?,
      receivedAmount: json['received_amount'] as String?,
      allocations: (json['allocations'] as List? ?? const [])
          .map((value) => Map<String, dynamic>.from(value as Map))
          .toList(growable: false),
    );
  }
}

int _cents(String value) {
  final bits = value.replaceAll(',', '.').split('.');
  return (int.tryParse(bits.first) ?? 0) * 100 +
      (int.tryParse('${bits.length > 1 ? bits[1] : ''}00'.substring(0, 2)) ??
          0);
}

int _quantityUnits(String value) {
  final bits = value.replaceAll(',', '.').split('.');
  return (int.tryParse(bits.first) ?? 0) * 1000 +
      (int.tryParse('${bits.length > 1 ? bits[1] : ''}000'.substring(0, 3)) ??
          0);
}

String _quantityValue(int thousandths) {
  final whole = thousandths ~/ 1000;
  final fraction = (thousandths % 1000)
      .toString()
      .padLeft(3, '0')
      .replaceFirst(RegExp(r'0+$'), '');
  return fraction.isEmpty ? '$whole' : '$whole.$fraction';
}
