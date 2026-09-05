import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'auth_models.dart';
import '../core/app_controller.dart';
import '../core/core_branding.dart';

class OperatorAccessPage extends StatefulWidget {
  const OperatorAccessPage({required this.controller, super.key});

  final AppController controller;

  @override
  State<OperatorAccessPage> createState() => _OperatorAccessPageState();
}

class _OperatorAccessPageState extends State<OperatorAccessPage> {
  final _pin = TextEditingController();
  final _pinFocus = FocusNode();

  @override
  void dispose() {
    _pin.dispose();
    _pinFocus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    final operator = controller.selectedOperator;
    final canEnter = operator != null && _pin.text.length == 6 && !controller.busy;

    return Scaffold(
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) => Center(
            child: SingleChildScrollView(
              padding: EdgeInsets.symmetric(
                horizontal: constraints.maxWidth >= 600 ? 32 : 20,
                vertical: 24,
              ),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 420),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Center(child: CoreWordmark(width: 196)),
                    const SizedBox(height: 32),
                    Container(
                      padding: const EdgeInsets.all(24),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(24),
                        border: Border.all(color: const Color(0xffe2e8f0)),
                        boxShadow: const [
                          BoxShadow(color: Color(0x0f283c50), blurRadius: 24, offset: Offset(0, 10)),
                        ],
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Text(
                            'Acesse o caixa',
                            style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
                          ),
                          const SizedBox(height: 8),
                          const Text(
                            'Selecione o operador e informe seu PIN de acesso.',
                            style: TextStyle(color: Color(0xff64748b), height: 1.45),
                          ),
                          const SizedBox(height: 24),
                          DropdownButtonFormField<PosOperator>(
                            key: ValueKey(operator?.id ?? 'no-operator'),
                            initialValue: operator,
                            isExpanded: true,
                            decoration: const InputDecoration(labelText: 'Operador'),
                            hint: const Text('Selecione seu perfil'),
                            items: controller.operators
                                .map(
                                  (item) => DropdownMenuItem(
                                    value: item,
                                    child: Row(
                                      children: [
                                        CircleAvatar(radius: 16, child: Text(item.initials)),
                                        const SizedBox(width: 12),
                                        Expanded(child: Text(item.displayName, overflow: TextOverflow.ellipsis)),
                                      ],
                                    ),
                                  ),
                                )
                                .toList(growable: false),
                            onChanged: controller.busy ? null : _selectOperator,
                          ),
                          if (controller.operators.isEmpty) ...[
                            const SizedBox(height: 12),
                            const Text(
                              'Nenhum operador elegível está disponível nesta filial.',
                              style: TextStyle(color: Color(0xff64748b)),
                            ),
                          ],
                          const SizedBox(height: 20),
                          _OperatorIdentity(operator: operator),
                          const SizedBox(height: 20),
                          TextField(
                            controller: _pin,
                            focusNode: _pinFocus,
                            enabled: operator != null && !controller.busy,
                            autofocus: operator != null,
                            keyboardType: TextInputType.number,
                            textInputAction: TextInputAction.done,
                            obscureText: true,
                            maxLength: 6,
                            inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                            decoration: const InputDecoration(
                              labelText: 'PIN de 6 dígitos',
                              counterText: '',
                            ),
                            onChanged: (_) => setState(() {}),
                            onSubmitted: (_) => _login(),
                          ),
                          if (controller.errorMessage != null) ...[
                            const SizedBox(height: 16),
                            _ErrorNotice(message: controller.errorMessage!),
                          ],
                          const SizedBox(height: 20),
                          FilledButton(
                            onPressed: canEnter ? _login : null,
                            child: controller.busy
                                ? const SizedBox(
                                    height: 22,
                                    width: 22,
                                    child: CircularProgressIndicator(strokeWidth: 2.4, color: Colors.white),
                                  )
                                : const Text('ENTRAR'),
                          ),
                          const SizedBox(height: 10),
                          TextButton.icon(
                            onPressed: controller.busy ? null : controller.recoverPairedDevice,
                            icon: const Icon(Icons.sync_rounded, size: 18),
                            label: const Text('Atualizar operadores'),
                          ),
                        ],
                      ),
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

  void _selectOperator(PosOperator? operator) {
    if (operator == null) return;
    setState(_pin.clear);
    widget.controller.selectOperator(operator);
    WidgetsBinding.instance.addPostFrameCallback((_) => _pinFocus.requestFocus());
  }

  Future<void> _login() async {
    if (widget.controller.selectedOperator == null || _pin.text.length != 6) return;
    try {
      await widget.controller.login(_pin.text);
    } finally {
      if (mounted) setState(_pin.clear);
    }
  }
}

class _OperatorIdentity extends StatelessWidget {
  const _OperatorIdentity({required this.operator});

  final PosOperator? operator;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: const Color(0xfff0f2f8),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          children: [
            CircleAvatar(
              radius: 24,
              backgroundColor: const Color(0xffdce4ff),
              foregroundColor: const Color(0xff2945b6),
              child: Text(operator?.initials ?? '?'),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Text(
                operator?.displayName ?? 'Selecione um operador',
                style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
              ),
            ),
          ],
        ),
      );
}

class _ErrorNotice extends StatelessWidget {
  const _ErrorNotice({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: const Color(0xfffff4f2),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: const Color(0xfffecaca)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.info_outline_rounded, color: Color(0xffb42318), size: 20),
            const SizedBox(width: 10),
            Expanded(child: Text(message, style: const TextStyle(color: Color(0xff8f1d14), height: 1.35))),
          ],
        ),
      );
}
