import 'package:flutter/material.dart';

import '../core/app_controller.dart';
import '../core/transient_feedback.dart';
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
  bool _loadingSummary = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadSummary());
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: widget.controller,
        builder: (context, _) {
          final snapshot = widget.controller.bootstrapSnapshot!;
          final cash = snapshot.cash;
          final session = _currentSession(cash);
          return Stack(
            fit: StackFit.expand,
            children: [
              Scaffold(
                appBar: AppBar(
              title: const Text('Caixa'),
              actions: [
                IconButton(
                  onPressed: widget.controller.busy ? null : () => widget.controller.refreshCashOverview(),
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
                      Text('${snapshot.companyName} - ${snapshot.branchName}', style: const TextStyle(color: Color(0xff64748b))),
                      const SizedBox(height: 8),
                      Text('Operação de caixa', style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800)),
                      const SizedBox(height: 20),
                      if (!cash.enabled)
                        const _Notice(message: 'O caixa não está habilitado para esta filial.')
                      else ...[
                        if (!cash.isFixed) _FlexibleRegisterPicker(cash: cash, selectedRegisterId: _selectedRegisterId, onSelected: _selectRegister),
                        if (!cash.isFixed) const SizedBox(height: 16),
                        _CashStateCard(cash: cash, session: session),
                        const SizedBox(height: 16),
                        if (session == null)
                          _ClosedCashActions(
                            canOpen: snapshot.permissions.contains('cash_registers.open'),
                            canOpenHere: cash.isFixed ? cash.register != null : _selectedRegisterId != null,
                            onOpen: _openSession,
                          )
                        else ...[
                          if (snapshot.permissions.contains('cash_registers.view')) ...[
                            _SummaryCard(summary: _summary, loading: _loadingSummary),
                            const SizedBox(height: 16),
                          ],
                          _OpenCashActions(
                            canEntry: snapshot.permissions.contains('cash_registers.manual_entry'),
                            canWithdraw: snapshot.permissions.contains('cash_registers.withdraw'),
                            canClose: snapshot.permissions.contains('cash_registers.close'),
                            onEntry: () => _movement(session, withdrawal: false),
                            onWithdraw: () => _movement(session, withdrawal: true),
                            onClose: () => _closeSession(session),
                          ),
                        ],
                      ],
                    ],
                  ),
                ),
              ),
                ),
              ),
              TransientAlertOverlay(alert: widget.controller.transientAlert),
            ],
          );
        },
      );

  CashSessionInfo? _currentSession(CashOverview cash) {
    if (cash.isFixed) return cash.session;
    return cash.registers.where((item) => item.id == _selectedRegisterId).firstOrNull?.session;
  }

  void _selectRegister(int? id) {
    setState(() {
      _selectedRegisterId = id;
      _summary = null;
    });
    _loadSummary();
  }

  Future<void> _loadSummary() async {
    final snapshot = widget.controller.bootstrapSnapshot;
    if (snapshot == null || !snapshot.permissions.contains('cash_registers.view')) return;
    final session = _currentSession(snapshot.cash);
    if (session == null) return;
    setState(() => _loadingSummary = true);
    final summary = await widget.controller.cashSessionSummary(session.id);
    if (mounted) {
      setState(() {
        _summary = summary;
        _loadingSummary = false;
      });
    }
  }

  Future<void> _openSession() async {
    final opening = TextEditingController();
    final cash = widget.controller.bootstrapSnapshot!.cash;
    final selected = await showDialog<int>(
      context: context,
      builder: (context) {
        var registerId = _selectedRegisterId ?? (cash.registers.isNotEmpty ? cash.registers.first.id : null);
        return StatefulBuilder(
          builder: (context, setDialogState) => AlertDialog(
            title: const Text('Abrir caixa'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (!cash.isFixed) ...[
                  DropdownButtonFormField<int>(
                    initialValue: registerId,
                    decoration: const InputDecoration(labelText: 'Caixa'),
                    items: cash.registers.map((item) => DropdownMenuItem(value: item.id, child: Text(item.name))).toList(growable: false),
                    onChanged: (value) => setDialogState(() => registerId = value),
                  ),
                  const SizedBox(height: 16),
                ],
                TextField(
                  controller: opening,
                  autofocus: true,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(labelText: 'Fundo inicial', prefixText: 'R\$ '),
                ),
              ],
            ),
            actions: [
              TextButton(onPressed: () => Navigator.pop(context), child: const Text('CANCELAR')),
              FilledButton(
                onPressed: () async {
                  final value = _moneyInput(opening.text);
                  if (value == null || (!cash.isFixed && registerId == null)) return;
                  await widget.controller.openCashSession(openingAmount: value, registerId: cash.isFixed ? null : registerId);
                  if (context.mounted) Navigator.pop(context, registerId);
                },
                child: const Text('ABRIR'),
              ),
            ],
          ),
        );
      },
    );
    opening.dispose();
    if (selected != null) {
      setState(() => _selectedRegisterId = selected);
    }
    await _loadSummary();
  }

  Future<void> _movement(CashSessionInfo session, {required bool withdrawal}) async {
    final amount = TextEditingController();
    final reason = TextEditingController();
    var category = 'other';
    String? resultEffect;
    int? beneficiaryId;
    var beneficiaries = const <CashBeneficiary>[];
    var loadingBeneficiaries = false;
    await showDialog<void>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) {
          Future<void> loadBeneficiaries(String nextCategory) async {
            if (!withdrawalRequiresBeneficiary(nextCategory)) return;
            setDialogState(() => loadingBeneficiaries = true);
            final result = await widget.controller.cashWithdrawalBeneficiaries(nextCategory);
            if (context.mounted) {
              setDialogState(() {
                beneficiaries = result ?? const [];
                loadingBeneficiaries = false;
              });
            }
          }

          return AlertDialog(
            title: Text(withdrawal ? 'Registrar sangria' : 'Registrar suprimento'),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextField(
                    controller: amount,
                    autofocus: true,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(labelText: 'Valor', prefixText: 'R\$ '),
                  ),
                  const SizedBox(height: 12),
                  TextField(controller: reason, maxLines: 2, decoration: const InputDecoration(labelText: 'Motivo')),
                  if (withdrawal) ...[
                    const SizedBox(height: 12),
                    DropdownButtonFormField<String>(
                      initialValue: category,
                      decoration: const InputDecoration(labelText: 'Categoria'),
                      items: withdrawalCategories.entries
                          .map((item) => DropdownMenuItem(value: item.key, child: Text(item.value)))
                          .toList(growable: false),
                      onChanged: (value) {
                        if (value == null) return;
                        setDialogState(() {
                          category = value;
                          beneficiaryId = null;
                          beneficiaries = const [];
                        });
                        loadBeneficiaries(value);
                      },
                    ),
                    const SizedBox(height: 12),
                    DropdownButtonFormField<String>(
                      initialValue: resultEffect,
                      decoration: const InputDecoration(labelText: 'Efeito financeiro'),
                      hint: const Text('Selecione o efeito'),
                      items: withdrawalResultEffects.entries
                          .map((item) => DropdownMenuItem(value: item.key, child: Text(item.value)))
                          .toList(growable: false),
                      onChanged: (value) => setDialogState(() => resultEffect = value),
                    ),
                    if (withdrawalRequiresBeneficiary(category)) ...[
                      const SizedBox(height: 12),
                      if (loadingBeneficiaries)
                        const Padding(padding: EdgeInsets.all(12), child: CircularProgressIndicator())
                      else
                        DropdownButtonFormField<int>(
                          initialValue: beneficiaryId,
                          decoration: const InputDecoration(labelText: 'Beneficiário'),
                          hint: const Text('Selecione o beneficiário'),
                          items: beneficiaries
                              .map((item) => DropdownMenuItem(value: item.id, child: Text(item.name)))
                              .toList(growable: false),
                          onChanged: (value) => setDialogState(() => beneficiaryId = value),
                        ),
                    ],
                  ],
                ],
              ),
            ),
            actions: [
              TextButton(onPressed: () => Navigator.pop(context), child: const Text('CANCELAR')),
              FilledButton(
                onPressed: () async {
                  final value = _moneyInput(amount.text);
                  if (value == null || reason.text.trim().isEmpty) return;
                  if (withdrawal && (resultEffect == null || (withdrawalRequiresBeneficiary(category) && beneficiaryId == null))) {
                    widget.controller.showTransientMessage('Preencha os campos obrigatórios da sangria.');
                    return;
                  }
                  if (withdrawal) {
                    await widget.controller.recordCashWithdrawal(
                      sessionId: session.id,
                      amount: value,
                      reason: reason.text.trim(),
                      category: category,
                      resultEffect: resultEffect!,
                      beneficiaryId: beneficiaryId,
                    );
                  } else {
                    await widget.controller.recordCashEntry(sessionId: session.id, amount: value, reason: reason.text.trim());
                  }
                  if (context.mounted) Navigator.pop(context);
                },
                child: const Text('CONFIRMAR'),
              ),
            ],
          );
        },
      ),
    );
    amount.dispose();
    reason.dispose();
    await _loadSummary();
  }

  Future<void> _closeSession(CashSessionInfo session) async {
    final closing = TextEditingController();
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Fechar caixa'),
        content: TextField(
          controller: closing,
          autofocus: true,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(labelText: 'Valor contado', prefixText: 'R\$ '),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('CANCELAR')),
          FilledButton(
            onPressed: () async {
              final value = _moneyInput(closing.text);
              if (value == null) return;
              await widget.controller.closeCashSession(sessionId: session.id, closingAmount: value);
              if (context.mounted) Navigator.pop(context);
            },
            child: const Text('FECHAR CAIXA'),
          ),
        ],
      ),
    );
    closing.dispose();
  }

  String? _moneyInput(String input) {
    final raw = input.trim();
    final value = raw.contains(',') ? raw.replaceAll('.', '').replaceAll(',', '.') : raw;
    if (double.tryParse(value) == null) {
      widget.controller.showTransientMessage('Informe um valor válido.');
      return null;
    }
    return value;
  }
}

class _FlexibleRegisterPicker extends StatelessWidget {
  const _FlexibleRegisterPicker({required this.cash, required this.selectedRegisterId, required this.onSelected});

  final CashOverview cash;
  final int? selectedRegisterId;
  final ValueChanged<int?> onSelected;

  @override
  Widget build(BuildContext context) => DropdownButtonFormField<int>(
        key: ValueKey(selectedRegisterId),
        initialValue: selectedRegisterId,
        decoration: const InputDecoration(labelText: 'Caixa'),
        hint: const Text('Selecione um caixa'),
        items: cash.registers.map((item) => DropdownMenuItem(value: item.id, child: Text(item.name))).toList(growable: false),
        onChanged: onSelected,
      );
}

class _CashStateCard extends StatelessWidget {
  const _CashStateCard({required this.cash, required this.session});

  final CashOverview cash;
  final CashSessionInfo? session;

  @override
  Widget build(BuildContext context) {
    final registerName = cash.isFixed ? cash.register?.name : session?.registerName;
    final needsSelection = !cash.isFixed && registerName == null;
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(20), border: Border.all(color: const Color(0xffe2e8f0))),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(session == null ? Icons.lock_outline_rounded : Icons.lock_open_rounded, color: session == null ? const Color(0xff64748b) : const Color(0xff087443)),
          const SizedBox(width: 10),
          Text(needsSelection ? 'Selecione um caixa' : session == null ? 'Caixa fechado' : 'Caixa aberto', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
        ]),
        const SizedBox(height: 12),
        Text(registerName ?? (cash.isFixed ? 'Caixa não configurado' : 'Selecione um caixa'), style: const TextStyle(color: Color(0xff64748b))),
        if (session != null) ...[
          const SizedBox(height: 4),
          Text('Aberto por ${session!.openedByName} ${_dateLabel(session!.openedAt)}', style: const TextStyle(color: Color(0xff64748b))),
        ],
      ]),
    );
  }
}

class _ClosedCashActions extends StatelessWidget {
  const _ClosedCashActions({required this.canOpen, required this.canOpenHere, required this.onOpen});

  final bool canOpen;
  final bool canOpenHere;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) => canOpen
      ? FilledButton.icon(onPressed: canOpenHere ? onOpen : null, icon: const Icon(Icons.lock_open_rounded), label: const Text('ABRIR CAIXA'))
      : const _Notice(message: 'Não há caixa aberto para esta operação.');
}

class _OpenCashActions extends StatelessWidget {
  const _OpenCashActions({required this.canEntry, required this.canWithdraw, required this.canClose, required this.onEntry, required this.onWithdraw, required this.onClose});

  final bool canEntry;
  final bool canWithdraw;
  final bool canClose;
  final VoidCallback onEntry;
  final VoidCallback onWithdraw;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        if (canEntry) FilledButton.icon(onPressed: onEntry, icon: const Icon(Icons.add_circle_outline_rounded), label: const Text('SUPRIMENTO / ENTRADA')),
        if (canEntry && (canWithdraw || canClose)) const SizedBox(height: 10),
        if (canWithdraw) OutlinedButton.icon(onPressed: onWithdraw, icon: const Icon(Icons.remove_circle_outline_rounded), label: const Text('SANGRIA')),
        if (canWithdraw && canClose) const SizedBox(height: 10),
        if (canClose) TextButton.icon(onPressed: onClose, icon: const Icon(Icons.lock_outline_rounded), label: const Text('FECHAR CAIXA')),
      ]);
}

class _SummaryCard extends StatelessWidget {
  const _SummaryCard({required this.summary, required this.loading});

  final CashSessionSummary? summary;
  final bool loading;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(color: const Color(0xfff0f2f8), borderRadius: BorderRadius.circular(20)),
        child: loading
            ? const Center(child: Padding(padding: EdgeInsets.all(12), child: CircularProgressIndicator()))
            : summary == null
                ? const Text('Não foi possível carregar o resumo do caixa.')
                : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('Resumo operacional', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
                    const SizedBox(height: 14),
                    _SummaryLine(label: 'Fundo inicial', value: formatMoney(summary!.openingAmount)),
                    _SummaryLine(label: 'Suprimentos', value: formatMoney(summary!.manualEntries)),
                    _SummaryLine(label: 'Sangrias', value: formatMoney(summary!.withdrawals)),
                    _SummaryLine(label: 'Recebimentos em dinheiro', value: formatMoney(summary!.cashPayments)),
                    const Divider(height: 24),
                    _SummaryLine(label: 'Valor esperado', value: formatMoney(summary!.expectedAmount), emphasized: true),
                  ]),
      );
}

class _SummaryLine extends StatelessWidget {
  const _SummaryLine({required this.label, required this.value, this.emphasized = false});

  final String label;
  final String value;
  final bool emphasized;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          Text(label, style: TextStyle(fontWeight: emphasized ? FontWeight.w700 : FontWeight.w400)),
          Text(value, style: TextStyle(fontWeight: emphasized ? FontWeight.w800 : FontWeight.w600)),
        ]),
      );
}

class _Notice extends StatelessWidget {
  const _Notice({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(color: const Color(0xfff0f2f8), borderRadius: BorderRadius.circular(16)),
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
