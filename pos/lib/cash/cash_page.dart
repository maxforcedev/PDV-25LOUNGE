import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../core/app_controller.dart';
import '../sync/sync_status_button.dart';
import '../sync/sync_center_page.dart';
import 'cash_models.dart';

class CashPage extends StatefulWidget {
  const CashPage({required this.controller, super.key});

  final AppController controller;

  @override
  State<CashPage> createState() => _CashPageState();
}

class _CashPageState extends State<CashPage> {
  int? _selectedRegisterId;
  CashSessionSummary? _summary;
  int? _summarySessionId;
  int? _observedSessionId;
  int _summaryRequest = 0;
  bool _loadingSummary = false;

  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_synchronizeSummary);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _synchronizeSummary();
    });
  }

  @override
  void dispose() {
    widget.controller.removeListener(_synchronizeSummary);
    _summaryRequest++;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: widget.controller,
        builder: (context, _) {
          final snapshot = widget.controller.bootstrapSnapshot!;
          final cash = snapshot.cash;
          final session = _currentSession(cash);
          return Scaffold(
            appBar: AppBar(
              title: const Text('Caixa'),
              actions: [
                SyncStatusButton(
                  status: widget.controller.syncStatus,
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute(
                        builder: (_) =>
                            SyncCenterPage(controller: widget.controller)),
                  ),
                ),
                IconButton(
                  onPressed:
                      widget.controller.busy ? null : _refreshCashOverview,
                  icon: const Icon(Icons.refresh_rounded),
                  tooltip: 'Atualizar caixa',
                ),
              ],
            ),
            body: SafeArea(
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 520),
                  child: ListView(
                    padding: const EdgeInsets.all(20),
                    children: [
                      Text('Operação de caixa',
                          style: Theme.of(context)
                              .textTheme
                              .headlineSmall
                              ?.copyWith(fontWeight: FontWeight.w800)),
                      const SizedBox(height: 20),
                      if (!cash.enabled)
                        const _Notice(
                            message:
                                'O caixa não está habilitado para esta filial.')
                      else ...[
                        if (!cash.isFixed)
                          _FlexibleRegisterPicker(
                              cash: cash,
                              selectedRegisterId: _selectedRegisterId,
                              onSelected: _selectRegister),
                        if (!cash.isFixed) const SizedBox(height: 16),
                        _CashStateCard(cash: cash, session: session),
                        const SizedBox(height: 16),
                        if (session == null)
                          _ClosedCashActions(
                            canOpen: snapshot.permissions
                                .contains('cash_registers.open'),
                            canOpenHere: cash.isFixed
                                ? cash.register != null
                                : _selectedRegisterId != null,
                            onOpen: _openSession,
                          )
                        else ...[
                          if (snapshot.permissions
                              .contains('cash_registers.view')) ...[
                            _SummaryCard(
                                summary: _summarySessionId == session.id
                                    ? _summary
                                    : null,
                                loading: _summarySessionId == session.id &&
                                    _loadingSummary),
                            const SizedBox(height: 16),
                          ],
                          _OpenCashActions(
                            canEntry: snapshot.permissions
                                .contains('cash_registers.manual_entry'),
                            canWithdraw: snapshot.permissions
                                .contains('cash_registers.withdraw'),
                            canClose: snapshot.permissions
                                .contains('cash_registers.close'),
                            onEntry: () =>
                                _movement(session, withdrawal: false),
                            onWithdraw: () =>
                                _movement(session, withdrawal: true),
                            onClose: () => _closeSession(session),
                          ),
                        ],
                      ],
                    ],
                  ),
                ),
              ),
            ),
          );
        },
      );

  CashSessionInfo? _currentSession(CashOverview cash) {
    if (cash.isFixed) return cash.session;
    return cash.registers
        .where((item) => item.id == _selectedRegisterId)
        .firstOrNull
        ?.session;
  }

  void _selectRegister(int? id) {
    setState(() {
      _selectedRegisterId = id;
    });
    _synchronizeSummary();
  }

  void _synchronizeSummary() {
    final snapshot = widget.controller.bootstrapSnapshot;
    final sessionId =
        snapshot == null ? null : _currentSession(snapshot.cash)?.id;
    if (_observedSessionId == sessionId) return;
    _observedSessionId = sessionId;
    _summaryRequest++;
    if (!mounted) return;
    setState(() {
      _summarySessionId = sessionId;
      _summary = null;
      _loadingSummary = false;
    });
    if (sessionId != null &&
        snapshot!.permissions.contains('cash_registers.view')) {
      unawaited(_loadSummary(sessionId));
    }
  }

  Future<void> _loadSummary(int sessionId) async {
    final snapshot = widget.controller.bootstrapSnapshot;
    if (snapshot == null ||
        !snapshot.permissions.contains('cash_registers.view') ||
        _currentSession(snapshot.cash)?.id != sessionId) {
      return;
    }
    final request = ++_summaryRequest;
    if (!mounted) return;
    setState(() {
      _summarySessionId = sessionId;
      _loadingSummary = true;
    });
    final summary = await widget.controller.cashSessionSummary(sessionId);
    final currentSessionId = _currentSession(
            widget.controller.bootstrapSnapshot?.cash ??
                const CashOverview(mode: 'FLEXIBLE', enabled: false))
        ?.id;
    if (!mounted ||
        request != _summaryRequest ||
        currentSessionId != sessionId) {
      return;
    }
    setState(() {
      _summary = summary;
      _loadingSummary = false;
    });
  }

  Future<void> _refreshCashOverview() async {
    final refreshed = await widget.controller.refreshCashOverview();
    if (!mounted || !refreshed) return;
    _synchronizeSummary();
  }

  Future<void> _openSession() async {
    final snapshot = widget.controller.bootstrapSnapshot;
    if (snapshot == null) return;
    final request = await showDialog<_OpenCashRequest>(
      context: context,
      builder: (_) => _OpenCashDialog(
          cash: snapshot.cash, selectedRegisterId: _selectedRegisterId),
    );
    if (!mounted || request == null) return;
    final opened = await widget.controller.openCashSession(
        openingAmount: request.openingAmount, registerId: request.registerId);
    if (!mounted || !opened) return;
    if (!snapshot.cash.isFixed) {
      setState(() {
        _selectedRegisterId = request.registerId;
      });
    }
    _synchronizeSummary();
  }

  Future<void> _movement(CashSessionInfo session,
      {required bool withdrawal}) async {
    final request = await showDialog<_CashMovementRequest>(
      context: context,
      builder: (_) => _CashMovementDialog(
          withdrawal: withdrawal,
          loadBeneficiaries: widget.controller.cashWithdrawalBeneficiaries),
    );
    if (!mounted || request == null) return;
    final completed = withdrawal
        ? await widget.controller.recordCashWithdrawal(
            sessionId: session.id,
            amount: request.amount,
            reason: request.reason,
            category: request.category!,
            beneficiaryType: request.beneficiaryType,
            beneficiaryId: request.beneficiaryId,
          )
        : await widget.controller.recordCashEntry(
            sessionId: session.id,
            amount: request.amount,
            reason: request.reason);
    if (!mounted || !completed) return;
    unawaited(_loadSummary(session.id));
  }

  Future<void> _closeSession(CashSessionInfo session) async {
    final request = await showDialog<_CloseCashRequest>(
      context: context,
      builder: (_) => const _CloseCashDialog(),
    );
    if (!mounted || request == null) return;
    final closed = await widget.controller.closeCashSession(
        sessionId: session.id, closingAmount: request.closingAmount);
    if (!mounted || !closed) return;
    _synchronizeSummary();
  }
}

class _OpenCashRequest {
  const _OpenCashRequest({required this.openingAmount, this.registerId});

  final String openingAmount;
  final int? registerId;
}

class _CashMovementRequest {
  const _CashMovementRequest({
    required this.amount,
    required this.reason,
    this.category,
    this.beneficiaryType,
    this.beneficiaryId,
  });

  final String amount;
  final String reason;
  final String? category;
  final String? beneficiaryType;
  final int? beneficiaryId;
}

class _CloseCashRequest {
  const _CloseCashRequest({required this.closingAmount});

  final String closingAmount;
}

class _OperationalDialog extends StatelessWidget {
  const _OperationalDialog({
    required this.title,
    required this.content,
    required this.actions,
  });

  final String title;
  final Widget content;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    final width = math.min(MediaQuery.sizeOf(context).width - 32, 520.0);
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(
            16, 16, 16, MediaQuery.viewInsetsOf(context).bottom + 16),
        child: Center(
          child: SizedBox(
            width: math.max(0, width),
            child: Material(
              color: Theme.of(context).colorScheme.surface,
              borderRadius: BorderRadius.circular(28),
              clipBehavior: Clip.antiAlias,
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(title,
                        style: Theme.of(context)
                            .textTheme
                            .headlineSmall
                            ?.copyWith(fontWeight: FontWeight.w800)),
                    const SizedBox(height: 20),
                    content,
                    const SizedBox(height: 24),
                    Wrap(
                      alignment: WrapAlignment.end,
                      spacing: 12,
                      runSpacing: 8,
                      children: actions,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _OpenCashDialog extends StatefulWidget {
  const _OpenCashDialog({required this.cash, required this.selectedRegisterId});

  final CashOverview cash;
  final int? selectedRegisterId;

  @override
  State<_OpenCashDialog> createState() => _OpenCashDialogState();
}

class _OpenCashDialogState extends State<_OpenCashDialog> {
  final _opening = TextEditingController();
  late int? _registerId = widget.selectedRegisterId ??
      (widget.cash.registers.isNotEmpty
          ? widget.cash.registers.first.id
          : null);
  String? _error;
  bool _submitting = false;

  @override
  void dispose() {
    _opening.dispose();
    super.dispose();
  }

  void _submit() {
    if (_submitting) return;
    final openingAmount = _moneyInput(_opening.text);
    if (openingAmount == null ||
        (!widget.cash.isFixed && _registerId == null)) {
      setState(() => _error = 'Informe os campos obrigatórios.');
      return;
    }
    setState(() => _submitting = true);
    Navigator.of(context).pop(_OpenCashRequest(
        openingAmount: openingAmount,
        registerId: widget.cash.isFixed ? null : _registerId));
  }

  @override
  Widget build(BuildContext context) => _OperationalDialog(
        title: 'Abrir caixa',
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (!widget.cash.isFixed) ...[
              DropdownButtonFormField<int>(
                initialValue: _registerId,
                decoration: const InputDecoration(labelText: 'Caixa'),
                items: widget.cash.registers
                    .map((item) => DropdownMenuItem(
                        value: item.id, child: Text(item.name)))
                    .toList(growable: false),
                onChanged: _submitting
                    ? null
                    : (value) => setState(() => _registerId = value),
              ),
              const SizedBox(height: 16),
            ],
            TextField(
              controller: _opening,
              autofocus: true,
              enabled: !_submitting,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(
                  labelText: 'Fundo inicial', prefixText: 'R\$ '),
            ),
            if (_error != null) _DialogError(message: _error!),
          ],
        ),
        actions: [
          TextButton(
              onPressed: _submitting ? null : () => Navigator.of(context).pop(),
              child: const Text('CANCELAR')),
          FilledButton(
              onPressed: _submitting ? null : _submit,
              child: const Text('ABRIR')),
        ],
      );
}

class _CashMovementDialog extends StatefulWidget {
  const _CashMovementDialog(
      {required this.withdrawal, required this.loadBeneficiaries});

  final bool withdrawal;
  final Future<List<CashBeneficiary>?> Function(String category)
      loadBeneficiaries;

  @override
  State<_CashMovementDialog> createState() => _CashMovementDialogState();
}

class _CashMovementDialogState extends State<_CashMovementDialog> {
  final _amount = TextEditingController();
  final _reason = TextEditingController();
  String _category = 'other';
  String? _beneficiaryType;
  int? _beneficiaryId;
  List<CashBeneficiary> _beneficiaries = const [];
  int _beneficiaryRequest = 0;
  bool _loadingBeneficiaries = false;
  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    _beneficiaryRequest++;
    _amount.dispose();
    _reason.dispose();
    super.dispose();
  }

  Future<void> _loadBeneficiaries(String category) async {
    if (!withdrawalRequiresBeneficiary(category)) return;
    final request = ++_beneficiaryRequest;
    setState(() => _loadingBeneficiaries = true);
    final beneficiaries = await widget.loadBeneficiaries(category);
    if (!mounted || request != _beneficiaryRequest || _category != category) {
      return;
    }
    setState(() {
      _beneficiaries = beneficiaries ?? const [];
      _loadingBeneficiaries = false;
    });
  }

  void _changeCategory(String? value) {
    if (value == null || _submitting) return;
    _beneficiaryRequest++;
    setState(() {
      _category = value;
      _beneficiaryType = null;
      _beneficiaryId = null;
      _beneficiaries = const [];
      _loadingBeneficiaries = false;
    });
    if (withdrawalRequiresBeneficiary(value)) {
      unawaited(_loadBeneficiaries(value));
    }
  }

  void _submit() {
    if (_submitting) return;
    final amount = _moneyInput(_amount.text);
    if (amount == null) {
      setState(() => _error = 'Informe um valor válido.');
      return;
    }
    if (widget.withdrawal &&
        withdrawalRequiresBeneficiary(_category) &&
        (_beneficiaryId == null || _beneficiaryType == null)) {
      setState(() => _error = 'Preencha os campos obrigatórios da sangria.');
      return;
    }
    setState(() => _submitting = true);
    Navigator.of(context).pop(_CashMovementRequest(
      amount: amount,
      reason: _reason.text.trim(),
      category: widget.withdrawal ? _category : null,
      beneficiaryType: _beneficiaryType,
      beneficiaryId: _beneficiaryId,
    ));
  }

  @override
  Widget build(BuildContext context) => _OperationalDialog(
        title: widget.withdrawal ? 'Registrar sangria' : 'Registrar suprimento',
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: _amount,
              autofocus: true,
              enabled: !_submitting,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration:
                  const InputDecoration(labelText: 'Valor', prefixText: 'R\$ '),
            ),
            const SizedBox(height: 12),
            TextField(
                controller: _reason,
                enabled: !_submitting,
                maxLines: 2,
                decoration:
                    const InputDecoration(labelText: 'Motivo (opcional)')),
            if (widget.withdrawal) ...[
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _category,
                decoration: const InputDecoration(labelText: 'Categoria'),
                items: withdrawalCategories.entries
                    .map((item) => DropdownMenuItem(
                        value: item.key, child: Text(item.value)))
                    .toList(growable: false),
                onChanged: _submitting ? null : _changeCategory,
              ),
              if (withdrawalRequiresBeneficiary(_category)) ...[
                const SizedBox(height: 12),
                if (_loadingBeneficiaries)
                  const Padding(
                      padding: EdgeInsets.all(12),
                      child: CircularProgressIndicator())
                else
                  DropdownButtonFormField<int>(
                    initialValue: _beneficiaryId,
                    decoration:
                        const InputDecoration(labelText: 'Beneficiário'),
                    hint: const Text('Selecione o beneficiário'),
                    items: _beneficiaries
                        .map((item) => DropdownMenuItem(
                            value: item.id, child: Text(item.name)))
                        .toList(growable: false),
                    onChanged: _submitting
                        ? null
                        : (value) => setState(() {
                              _beneficiaryId = value;
                              _beneficiaryType = _beneficiaries
                                  .where((item) => item.id == value)
                                  .firstOrNull
                                  ?.type;
                            }),
                  ),
              ],
            ],
            if (_error != null) _DialogError(message: _error!),
          ],
        ),
        actions: [
          TextButton(
              onPressed: _submitting ? null : () => Navigator.of(context).pop(),
              child: const Text('CANCELAR')),
          FilledButton(
              onPressed: _submitting ? null : _submit,
              child: const Text('CONFIRMAR')),
        ],
      );
}

class _CloseCashDialog extends StatefulWidget {
  const _CloseCashDialog();

  @override
  State<_CloseCashDialog> createState() => _CloseCashDialogState();
}

class _CloseCashDialogState extends State<_CloseCashDialog> {
  final _closing = TextEditingController();
  String? _error;
  bool _submitting = false;

  @override
  void dispose() {
    _closing.dispose();
    super.dispose();
  }

  void _submit() {
    if (_submitting) return;
    final closingAmount = _moneyInput(_closing.text);
    if (closingAmount == null) {
      setState(() => _error = 'Informe um valor válido.');
      return;
    }
    setState(() => _submitting = true);
    Navigator.of(context).pop(_CloseCashRequest(closingAmount: closingAmount));
  }

  @override
  Widget build(BuildContext context) => _OperationalDialog(
        title: 'Fechar caixa',
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: _closing,
              autofocus: true,
              enabled: !_submitting,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(
                  labelText: 'Valor contado', prefixText: 'R\$ '),
            ),
            if (_error != null) _DialogError(message: _error!),
          ],
        ),
        actions: [
          TextButton(
              onPressed: _submitting ? null : () => Navigator.of(context).pop(),
              child: const Text('CANCELAR')),
          FilledButton(
              onPressed: _submitting ? null : _submit,
              child: const Text('FECHAR CAIXA')),
        ],
      );
}

class _DialogError extends StatelessWidget {
  const _DialogError({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 12),
        child: Text(message, style: const TextStyle(color: Color(0xffb42318))),
      );
}

String? _moneyInput(String input) {
  final raw = input.trim();
  final value =
      raw.contains(',') ? raw.replaceAll('.', '').replaceAll(',', '.') : raw;
  return double.tryParse(value) == null ? null : value;
}

class _FlexibleRegisterPicker extends StatelessWidget {
  const _FlexibleRegisterPicker(
      {required this.cash,
      required this.selectedRegisterId,
      required this.onSelected});

  final CashOverview cash;
  final int? selectedRegisterId;
  final ValueChanged<int?> onSelected;

  @override
  Widget build(BuildContext context) => DropdownButtonFormField<int>(
        key: ValueKey(selectedRegisterId),
        initialValue: selectedRegisterId,
        decoration: const InputDecoration(labelText: 'Caixa'),
        hint: const Text('Selecione um caixa'),
        items: cash.registers
            .map((item) =>
                DropdownMenuItem(value: item.id, child: Text(item.name)))
            .toList(growable: false),
        onChanged: onSelected,
      );
}

class _CashStateCard extends StatelessWidget {
  const _CashStateCard({required this.cash, required this.session});

  final CashOverview cash;
  final CashSessionInfo? session;

  @override
  Widget build(BuildContext context) {
    final registerName =
        cash.isFixed ? cash.register?.name : session?.registerName;
    final needsSelection = !cash.isFixed && registerName == null;
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: const Color(0xffe2e8f0))),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(
              session == null
                  ? Icons.lock_outline_rounded
                  : Icons.lock_open_rounded,
              color: session == null
                  ? const Color(0xff64748b)
                  : const Color(0xff087443)),
          const SizedBox(width: 10),
          Text(
              needsSelection
                  ? 'Selecione um caixa'
                  : session == null
                      ? 'Caixa fechado'
                      : 'Caixa aberto',
              style: Theme.of(context)
                  .textTheme
                  .titleLarge
                  ?.copyWith(fontWeight: FontWeight.w800)),
        ]),
        const SizedBox(height: 12),
        Text(
            registerName ??
                (cash.isFixed ? 'Caixa não configurado' : 'Selecione um caixa'),
            style: const TextStyle(color: Color(0xff64748b))),
        if (session != null) ...[
          const SizedBox(height: 4),
          Text(
              'Aberto por ${session!.openedByName} ${_dateLabel(session!.openedAt)}',
              style: const TextStyle(color: Color(0xff64748b))),
        ],
      ]),
    );
  }
}

class _ClosedCashActions extends StatelessWidget {
  const _ClosedCashActions(
      {required this.canOpen, required this.canOpenHere, required this.onOpen});

  final bool canOpen;
  final bool canOpenHere;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) => canOpen
      ? FilledButton.icon(
          onPressed: canOpenHere ? onOpen : null,
          icon: const Icon(Icons.lock_open_rounded),
          label: const Text('ABRIR CAIXA'))
      : const _Notice(message: 'Não há caixa aberto para esta operação.');
}

class _OpenCashActions extends StatelessWidget {
  const _OpenCashActions(
      {required this.canEntry,
      required this.canWithdraw,
      required this.canClose,
      required this.onEntry,
      required this.onWithdraw,
      required this.onClose});

  final bool canEntry;
  final bool canWithdraw;
  final bool canClose;
  final VoidCallback onEntry;
  final VoidCallback onWithdraw;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) =>
      Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        if (canEntry)
          FilledButton.icon(
              onPressed: onEntry,
              icon: const Icon(Icons.add_circle_outline_rounded),
              label: const Text('SUPRIMENTO / ENTRADA')),
        if (canEntry && (canWithdraw || canClose)) const SizedBox(height: 10),
        if (canWithdraw)
          OutlinedButton.icon(
              onPressed: onWithdraw,
              icon: const Icon(Icons.remove_circle_outline_rounded),
              label: const Text('SANGRIA')),
        if (canWithdraw && canClose) const SizedBox(height: 10),
        if (canClose)
          TextButton.icon(
              onPressed: onClose,
              icon: const Icon(Icons.lock_outline_rounded),
              label: const Text('FECHAR CAIXA')),
      ]);
}

class _SummaryCard extends StatelessWidget {
  const _SummaryCard({required this.summary, required this.loading});

  final CashSessionSummary? summary;
  final bool loading;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
            color: const Color(0xfff0f2f8),
            borderRadius: BorderRadius.circular(20)),
        child: loading
            ? const Center(
                child: Padding(
                    padding: EdgeInsets.all(12),
                    child: CircularProgressIndicator()))
            : summary == null
                ? const Text('Não foi possível carregar o resumo do caixa.')
                : Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                        Text('Resumo operacional',
                            style: Theme.of(context)
                                .textTheme
                                .titleMedium
                                ?.copyWith(fontWeight: FontWeight.w800)),
                        const SizedBox(height: 14),
                        _SummaryLine(
                            label: 'Fundo inicial',
                            value: formatMoney(summary!.openingAmount)),
                        _SummaryLine(
                            label: 'Suprimentos',
                            value: formatMoney(summary!.manualEntries)),
                        _SummaryLine(
                            label: 'Sangrias',
                            value: formatMoney(summary!.withdrawals)),
                        _SummaryLine(
                            label: 'Recebimentos em dinheiro',
                            value: formatMoney(summary!.cashPayments)),
                        const Divider(height: 24),
                        _SummaryLine(
                            label: 'Valor esperado',
                            value: formatMoney(summary!.expectedAmount),
                            emphasized: true),
                      ]),
      );
}

class _SummaryLine extends StatelessWidget {
  const _SummaryLine(
      {required this.label, required this.value, this.emphasized = false});

  final String label;
  final String value;
  final bool emphasized;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child:
            Row(children: [
          Expanded(
            child: Text(label,
                style: TextStyle(
                    fontWeight:
                        emphasized ? FontWeight.w700 : FontWeight.w400)),
          ),
          const SizedBox(width: 12),
          Flexible(
            child: Text(value,
                textAlign: TextAlign.end,
                style: TextStyle(
                    fontWeight:
                        emphasized ? FontWeight.w800 : FontWeight.w600)),
          ),
        ]),
      );
}

class _Notice extends StatelessWidget {
  const _Notice({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
            color: const Color(0xfff0f2f8),
            borderRadius: BorderRadius.circular(16)),
        child: Text(message, style: const TextStyle(color: Color(0xff64748b))),
      );
}

String _dateLabel(DateTime? value) {
  if (value == null) return '';
  final hour = value.hour.toString().padLeft(2, '0');
  final minute = value.minute.toString().padLeft(2, '0');
  return 'às $hour:$minute';
}

extension _FirstOrNull<T> on Iterable<T> {
  T? get firstOrNull => isEmpty ? null : first;
}
