import 'dart:async';

import 'package:flutter/material.dart';

import '../core/app_controller.dart';
import '../network/pos_api_error.dart';
import 'sale_models.dart';

class SharedCustomerPickerDialog extends StatefulWidget {
  const SharedCustomerPickerDialog({
    required this.controller,
    required this.canCreate,
    this.canReactivate = true,
    super.key,
  });

  final AppController controller;
  final bool canCreate;
  final bool canReactivate;

  @override
  State<SharedCustomerPickerDialog> createState() =>
      _SharedCustomerPickerDialogState();
}

class _SharedCustomerPickerDialogState
    extends State<SharedCustomerPickerDialog> {
  final _search = TextEditingController();
  List<QuickSaleCustomer> _customers = const [];
  QuickSaleCustomer? _inactiveIdentity;
  bool _canReactivate = false;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final result = await widget.controller.quickSaleCustomers(_search.text);
    if (!mounted) return;
    setState(() {
      _customers = result?.customers ?? const [];
      _inactiveIdentity = result?.inactiveIdentity;
      _canReactivate = widget.canReactivate && (result?.canReactivate ?? false);
      _loading = false;
    });
  }

  Future<void> _reactivate() async {
    final customer = _inactiveIdentity;
    if (customer == null || !_canReactivate) return;
    final active =
        await widget.controller.activateQuickSaleCustomer(customer.id);
    if (active != null && mounted) Navigator.of(context).pop(active);
  }

  Future<void> _create() async {
    final customer = await showDialog<QuickSaleCustomer>(
      context: context,
      builder: (_) => SharedCustomerCreateDialog(controller: widget.controller),
    );
    if (customer != null && mounted) Navigator.of(context).pop(customer);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Cliente'),
        content: SizedBox(
          width: 460,
          height: 420,
          child: Column(children: [
            TextField(
              controller: _search,
              onChanged: (_) => unawaited(_load()),
              decoration: const InputDecoration(
                labelText: 'Nome, telefone, documento ou e-mail',
                prefixIcon: Icon(Icons.search),
              ),
            ),
            const SizedBox(height: 8),
            if (_inactiveIdentity case final customer?)
              Card(
                child: ListTile(
                  leading: const Icon(Icons.person_off_outlined),
                  title: Text(customer.name),
                  subtitle: Text([
                    'Cliente inativo',
                    if (customer.phone.isNotEmpty) customer.phone,
                    if (customer.document.isNotEmpty) customer.document,
                  ].join(' | ')),
                  trailing: _canReactivate
                      ? TextButton(
                          onPressed: _reactivate,
                          child: const Text('REATIVAR'),
                        )
                      : null,
                ),
              ),
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator())
                  : ListView.builder(
                      itemCount: _customers.length,
                      itemBuilder: (_, index) {
                        final customer = _customers[index];
                        return ListTile(
                          title: Text(customer.name),
                          subtitle: Text([
                            if (customer.phone.isNotEmpty) customer.phone,
                            if (customer.document.isNotEmpty) customer.document,
                          ].join(' | ')),
                          onTap: () => Navigator.of(context).pop(customer),
                        );
                      },
                    ),
            ),
          ]),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('CANCELAR'),
          ),
          if (widget.canCreate)
            FilledButton.icon(
              onPressed: _create,
              icon: const Icon(Icons.person_add_alt_1),
              label: const Text('CADASTRAR'),
            ),
        ],
      );
}

class SharedCustomerCreateDialog extends StatefulWidget {
  const SharedCustomerCreateDialog({required this.controller, super.key});

  final AppController controller;

  @override
  State<SharedCustomerCreateDialog> createState() =>
      _SharedCustomerCreateDialogState();
}

class _SharedCustomerCreateDialogState
    extends State<SharedCustomerCreateDialog> {
  final _name = TextEditingController();
  final _phone = TextEditingController();
  final _document = TextEditingController();
  bool _saving = false;

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    _document.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_name.text.trim().isEmpty || _phone.text.trim().isEmpty || _saving) {
      return;
    }
    setState(() => _saving = true);
    QuickSaleCustomer? customer;
    try {
      customer = await widget.controller.createQuickSaleCustomer(
        name: _name.text.trim(),
        phone: _phone.text.trim(),
        document: _document.text.trim(),
      );
    } on PosApiException catch (error) {
      if (!mounted) return;
      final payload = error.details['customer'];
      if (payload is Map<String, dynamic>) {
        customer = await showDialog<QuickSaleCustomer>(
          context: context,
          builder: (_) => _SharedCustomerConflictDialog(
            controller: widget.controller,
            customer: QuickSaleCustomer.fromJson(payload),
            inactive: error.code == 'customer_inactive_identity_conflict',
            canReactivate: error.details['can_reactivate'] == true,
          ),
        );
      }
    }
    if (!mounted) return;
    setState(() => _saving = false);
    if (customer != null) Navigator.of(context).pop(customer);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Cadastrar cliente'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(
            controller: _name,
            autofocus: true,
            textCapitalization: TextCapitalization.words,
            decoration: const InputDecoration(labelText: 'Nome *'),
          ),
          TextField(
            controller: _phone,
            keyboardType: TextInputType.phone,
            decoration: const InputDecoration(labelText: 'Telefone *'),
          ),
          TextField(
            controller: _document,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(labelText: 'CPF'),
          ),
        ]),
        actions: [
          TextButton(
            onPressed: _saving ? null : () => Navigator.of(context).pop(),
            child: const Text('CANCELAR'),
          ),
          FilledButton(
            onPressed: _saving ? null : _save,
            child: Text(_saving ? 'SALVANDO...' : 'SALVAR'),
          ),
        ],
      );
}

class _SharedCustomerConflictDialog extends StatelessWidget {
  const _SharedCustomerConflictDialog({
    required this.controller,
    required this.customer,
    required this.inactive,
    required this.canReactivate,
  });

  final AppController controller;
  final QuickSaleCustomer customer;
  final bool inactive;
  final bool canReactivate;

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('CLIENTE JÁ CADASTRADO'),
        content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(customer.name,
                  style: const TextStyle(fontWeight: FontWeight.w700)),
              if (customer.phone.isNotEmpty)
                Text('Telefone: ${customer.phone}'),
              if (customer.document.isNotEmpty)
                Text('CPF: ${customer.document}'),
              const SizedBox(height: 12),
              Text(inactive
                  ? canReactivate
                      ? 'Este cliente está inativo.'
                      : 'Cliente cadastrado, porém inativo. Você não possui permissão para reativá-lo.'
                  : 'Este cliente já está ativo.'),
            ]),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('CANCELAR'),
          ),
          if (inactive && canReactivate)
            FilledButton(
              onPressed: () async {
                final active =
                    await controller.activateQuickSaleCustomer(customer.id);
                if (active != null && context.mounted) {
                  Navigator.of(context).pop(active);
                }
              },
              child: const Text('REATIVAR CLIENTE'),
            )
          else if (!inactive)
            FilledButton(
              onPressed: () => Navigator.of(context).pop(customer),
              child: const Text('USAR CLIENTE'),
            ),
        ],
      );
}
