import 'package:flutter/material.dart';

import '../attendance/attendance_models.dart';
import '../cash/cash_models.dart';
import '../core/app_controller.dart';
import '../sales/sale_models.dart';
import '../sales/shared_authorization_dialog.dart';
import '../sales/shared_customer_dialog.dart';
import '../sales/shared_discount_dialog.dart';
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
  final Map<int, String> _reverseKeys = {};
  String? _closeKey;
  bool _loading = true;
  bool _working = false;
  bool _details = false;

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
    setState(() {
      _attendance = results[0] as TableAttendance? ?? _attendance;
      _ledger = results[1] as TablePaymentLedger? ?? _ledger;
      _options = results[2] as QuickSaleCheckoutOptions? ?? _options;
      _pending ??= _TablePaymentRequest.fromJson(
          Map<String, dynamic>.from(results[3] as Map), _methods);
      if (_pending != null &&
          (_ledger?.payments ?? const []).any((payment) =>
              payment.idempotencyKey == _pending!.idempotencyKey)) {
        _pending = null;
      }
      _loading = false;
    });
    if (_pending == null)
      await widget.controller
          .writeTablePaymentPending(_attendance.id, const {});
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
    if (!_canRecord || _working || _pending != null) return;
    await _requestPayment(method, mode: 'value');
  }

  Future<void> _requestPayment(
    QuickSalePaymentMethod method, {
    required String mode,
    List<Map<String, dynamic>> allocations = const [],
    String? officialAmount,
  }) async {
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
                        : PaymentAmountContext.value,
                cashSessions: _options?.cashSessions ?? const [],
              )),
    );
    if (entry == null || !mounted) return;
    final request = _TablePaymentRequest(
      method: method,
      mode: mode,
      idempotencyKey: entry.intentId,
      amount: entry.amount,
      receivedAmount: entry.receivedAmount,
      cashSessionId: entry.cashSessionId,
      allocations: allocations,
    );
    await _record(request);
  }

  Future<void> _record(_TablePaymentRequest request) async {
    setState(() {
      _working = true;
      _pending = request;
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
      cashSessionId: request.cashSessionId,
      allocations: request.allocations,
    );
    if (!mounted) return;
    setState(() => _working = false);
    if (payment != null) {
      setState(() => _pending = null);
      await widget.controller
          .writeTablePaymentPending(_attendance.id, const {});
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

  Future<void> _close() async {
    int? sessionId;
    final sessions = _options?.cashSessions ?? const [];
    if (sessions.isNotEmpty) {
      sessionId = sessions.length == 1
          ? sessions.single.id
          : await showDialog<int>(
              context: context,
              builder: (_) => _CashSessionDialog(sessions: sessions),
            );
      if (sessionId == null || !mounted) return;
    }
    setState(() => _working = true);
    final closed = await widget.controller.closeTableAttendance(
      attendanceId: _attendance.id,
      idempotencyKey: _closeKey ??= createIdempotencyKey(),
      cashSessionId: sessionId,
    );
    if (!mounted) return;
    setState(() => _working = false);
    if (closed != null) {
      _closeKey = null;
      await widget.onClosed(closed);
      if (mounted) Navigator.of(context).pop(closed);
    }
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
          enabled: _canRecord && !_working && _pending == null,
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
    final method =
        await _pickMethod(_methods, title: 'Forma para pessoa $person');
    if (method != null && mounted)
      await _requestPayment(method, mode: 'equal_people');
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
    final items = _attendance.orders
        .expand((order) => order.items)
        .where((item) => item.status == 'confirmed')
        .map((item) => PaymentAllocationItem(
              id: item.id,
              name: item.productName,
              quantity: item.quantity,
              availableQuantity: _quantityValue(
                  _quantityUnits(item.quantity) - allocated(item)),
              unit: item.unit,
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
    final method = await _pickMethod(_methods, title: 'Forma para os itens');
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
              canSplit: _canRecord && !_working && _pending == null,
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
                pendingAction: _pending == null
                    ? null
                    : OutlinedButton.icon(
                        onPressed: _working ? null : () => _record(_pending!),
                        icon: const Icon(Icons.refresh),
                        label: const Text('TENTAR NOVAMENTE'),
                      ),
                history: _history(),
                summaryPanel: _summaryPanel(),
              ),
      );

  Widget _methodGrid() {
    return PaymentMethodGrid(
      methods: _methods,
      enabled: _canRecord && !_working && _pending == null,
      onSelect: (methods) async {
        final method = methods.length == 1
            ? methods.single
            : await _pickMethod(methods, title: 'Formas de pagamento');
        if (method != null && mounted) await _selectMethod(method);
      },
    );
  }

  Future<QuickSalePaymentMethod?> _pickMethod(
          List<QuickSalePaymentMethod> methods,
          {String title = 'FORMAS DE PAGAMENTO'}) =>
      showModalBottomSheet<QuickSalePaymentMethod>(
        context: context,
        isScrollControlled: true,
        builder: (context) => SafeArea(
          child: ConstrainedBox(
            constraints: BoxConstraints(
                maxHeight: MediaQuery.sizeOf(context).height * .7),
            child: ListView(children: [
              Padding(
                padding: const EdgeInsets.all(16),
                child: Text(title,
                    style: const TextStyle(
                        fontSize: 20, fontWeight: FontWeight.w900)),
              ),
              for (final method in methods)
                ListTile(
                  leading: Icon(_methodIcon(method)),
                  title: Text(method.name),
                  onTap: () => Navigator.pop(context, method),
                ),
            ]),
          ),
        ),
      );

  Widget _history() {
    final payments = (_ledger?.payments ?? const [])
        .where((payment) => !payment.isReversal)
        .toList(growable: false);
    if (payments.isEmpty) {
      return const Center(child: Text('Nenhum pagamento registrado.'));
    }
    return ListView.separated(
      itemCount: payments.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (_, index) {
        final payment = payments[index];
        final reversal = _reversalFor(payment.id);
        return PaymentHistoryItem(
          payment: _display(payment),
          reversed: reversal != null,
          reversalReason: reversal?.reversalReason,
          working: _working,
          onReverse: () => _reverse(payment),
        );
      },
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

IconData _methodIcon(QuickSalePaymentMethod method) => switch (method.kind) {
      'cash' => Icons.payments_outlined,
      'pix' => Icons.qr_code_2,
      'card' || 'credit' || 'debit' || 'benefit' => Icons.credit_card,
      _ => Icons.account_balance_wallet_outlined,
    };

class _TablePaymentRequest {
  const _TablePaymentRequest({
    required this.method,
    required this.mode,
    required this.idempotencyKey,
    required this.allocations,
    this.amount,
    this.receivedAmount,
    this.cashSessionId,
  });

  final QuickSalePaymentMethod method;
  final String mode;
  final String idempotencyKey;
  final String? amount;
  final String? receivedAmount;
  final int? cashSessionId;
  final List<Map<String, dynamic>> allocations;

  Map<String, dynamic> toJson() => {
        'payment_method_id': method.id,
        'mode': mode,
        'idempotency_key': idempotencyKey,
        'amount': amount,
        'received_amount': receivedAmount,
        'cash_session_id': cashSessionId,
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
      cashSessionId: json['cash_session_id'] as int?,
      allocations: (json['allocations'] as List? ?? const [])
          .map((value) => Map<String, dynamic>.from(value as Map))
          .toList(growable: false),
    );
  }
}

class _TablePaymentDialog extends StatefulWidget {
  const _TablePaymentDialog({
    required this.method,
    required this.mode,
    required this.remaining,
    required this.sessions,
    required this.allocations,
  });

  final QuickSalePaymentMethod method;
  final String mode;
  final String remaining;
  final List<QuickSaleCashSession> sessions;
  final List<Map<String, dynamic>> allocations;

  @override
  State<_TablePaymentDialog> createState() => _TablePaymentDialogState();
}

class _TablePaymentDialogState extends State<_TablePaymentDialog> {
  late final _amount = TextEditingController(
      text: widget.mode == 'remaining' ? widget.remaining : '');
  final _received = TextEditingController();
  int? _sessionId;

  @override
  void initState() {
    super.initState();
    _sessionId = widget.sessions.length == 1 ? widget.sessions.single.id : null;
    if (widget.method.isCash && widget.mode == 'remaining') {
      _received.text = widget.remaining;
    }
  }

  @override
  void dispose() {
    _amount.dispose();
    _received.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(
            widget.mode == 'items' ? 'PAGAR POR ITENS' : widget.method.name),
        content: SizedBox(
          width: 360,
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            if (widget.mode == 'equal_people')
              const Align(
                alignment: Alignment.centerLeft,
                child: Text(
                    'O valor da próxima pessoa será calculado oficialmente pela Mesa.'),
              )
            else if (widget.mode == 'items')
              const Align(
                alignment: Alignment.centerLeft,
                child: Text(
                    'O valor dos itens será calculado oficialmente pela Mesa.'),
              )
            else
              TextField(
                controller: _amount,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Valor aplicado'),
              ),
            if (widget.method.isCash) ...[
              const SizedBox(height: 10),
              DropdownButtonFormField<int>(
                initialValue: _sessionId,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Caixa'),
                items: widget.sessions
                    .map((session) => DropdownMenuItem(
                          value: session.id,
                          child: Text(session.registerName),
                        ))
                    .toList(growable: false),
                onChanged: (value) => setState(() => _sessionId = value),
              ),
              TextField(
                controller: _received,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Valor recebido'),
              ),
            ],
          ]),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('VOLTAR')),
          FilledButton(
            onPressed: _valid
                ? () => Navigator.pop(
                      context,
                      _TablePaymentRequest(
                        method: widget.method,
                        mode: widget.mode,
                        idempotencyKey: createIdempotencyKey(),
                        amount:
                            widget.mode == 'value' || widget.mode == 'remaining'
                                ? _normalizedMoney(_amount.text)
                                : null,
                        receivedAmount: widget.method.isCash
                            ? _normalizedMoney(_received.text)
                            : null,
                        cashSessionId: widget.method.isCash ? _sessionId : null,
                        allocations: widget.allocations,
                      ),
                    )
                : null,
            child: const Text('CONFIRMAR PAGAMENTO'),
          ),
        ],
      );

  bool get _valid {
    final cashValid = !widget.method.isCash ||
        (_sessionId != null && _cents(_received.text) > 0);
    if (!cashValid) return false;
    if (widget.mode == 'equal_people' || widget.mode == 'items') return true;
    return _cents(_amount.text) > 0;
  }
}

class _CashSessionDialog extends StatefulWidget {
  const _CashSessionDialog({required this.sessions});
  final List<QuickSaleCashSession> sessions;

  @override
  State<_CashSessionDialog> createState() => _CashSessionDialogState();
}

class _CashSessionDialogState extends State<_CashSessionDialog> {
  int? _selected;

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('CAIXA PARA FECHAMENTO'),
        content: DropdownButtonFormField<int>(
          initialValue: _selected,
          isExpanded: true,
          items: widget.sessions
              .map((session) => DropdownMenuItem(
                    value: session.id,
                    child: Text(session.registerName),
                  ))
              .toList(growable: false),
          onChanged: (value) => setState(() => _selected = value),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('VOLTAR')),
          FilledButton(
            onPressed: _selected == null
                ? null
                : () => Navigator.pop(context, _selected),
            child: const Text('FECHAR MESA'),
          ),
        ],
      );
}

class _TableItemAllocationPage extends StatefulWidget {
  const _TableItemAllocationPage(
      {required this.attendance, required this.payments});
  final TableAttendance attendance;
  final List<TablePayment> payments;

  @override
  State<_TableItemAllocationPage> createState() =>
      _TableItemAllocationPageState();
}

class _TableItemAllocationPageState extends State<_TableItemAllocationPage> {
  final Map<int, int> _quantities = {};

  int _allocated(TableOrderItem item) => widget.payments
      .where((payment) =>
          !payment.isReversal &&
          !widget.payments.any((row) => row.reversalOf == payment.id))
      .expand((payment) => payment.allocations)
      .where((allocation) => allocation['item'] == item.id)
      .fold(
          0,
          (total, allocation) =>
              total +
              _quantityUnits('${allocation['allocated_quantity'] ?? '0'}'));

  @override
  Widget build(BuildContext context) {
    final items = widget.attendance.orders
        .expand((order) => order.items)
        .where((item) => item.status == 'confirmed')
        .toList(growable: false);
    return Scaffold(
      appBar: AppBar(title: const Text('PAGAR POR ITENS')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        const Text(
            'A Mesa calculará oficialmente o valor dos itens selecionados.'),
        const SizedBox(height: 8),
        for (final item in items) _item(item),
        const SizedBox(height: 12),
        FilledButton(
          onPressed: _quantities.values.any((value) => value > 0)
              ? () => Navigator.pop(
                    context,
                    _quantities.entries
                        .where((entry) => entry.value > 0)
                        .map((entry) => {
                              'item': entry.key,
                              'allocated_quantity': _quantityValue(entry.value),
                            })
                        .toList(growable: false),
                  )
              : null,
          child: const Text('CONTINUAR'),
        ),
      ]),
    );
  }

  Widget _item(TableOrderItem item) {
    final max = _quantityUnits(item.quantity) - _allocated(item);
    final value = _quantities[item.id] ?? 0;
    final step = item.unit.toLowerCase() == 'un' ? 1000 : 1;
    return ListTile(
      title: Text(item.productName),
      subtitle: Text('Disponível: ${_quantityValue(max)} ${item.unit}'),
      trailing: Row(mainAxisSize: MainAxisSize.min, children: [
        IconButton(
          onPressed: value <= 0
              ? null
              : () => setState(() => _quantities[item.id] = value - step),
          icon: const Icon(Icons.remove),
        ),
        Text(_quantityValue(value)),
        IconButton(
          onPressed: value + step > max
              ? null
              : () => setState(() => _quantities[item.id] = value + step),
          icon: const Icon(Icons.add),
        ),
      ]),
    );
  }
}

int _cents(String value) {
  final bits = value.replaceAll(',', '.').split('.');
  return (int.tryParse(bits.first) ?? 0) * 100 +
      (int.tryParse('${bits.length > 1 ? bits[1] : ''}00'.substring(0, 2)) ??
          0);
}

String _normalizedMoney(String value) =>
    '${_cents(value) ~/ 100}.${(_cents(value) % 100).toString().padLeft(2, '0')}';

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
