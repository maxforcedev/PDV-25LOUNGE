import 'package:flutter/material.dart';

import '../core/app_controller.dart';

class OperatorSelectionPage extends StatelessWidget {
  const OperatorSelectionPage({required this.controller, super.key});

  final AppController controller;

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('CORE PDV')),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Quem esta operando?', style: Theme.of(context).textTheme.headlineSmall),
                const SizedBox(height: 8),
                const Text('Selecione seu perfil e informe o PIN.'),
                const SizedBox(height: 16),
                Expanded(
                  child: controller.operators.isEmpty
                      ? const Center(child: Text('Nenhum operador elegivel nesta filial.'))
                      : ListView.separated(
                          itemCount: controller.operators.length,
                          separatorBuilder: (_, __) => const Divider(),
                          itemBuilder: (context, index) {
                            final operator = controller.operators[index];
                            return ListTile(
                              leading: CircleAvatar(child: Text(operator.initials)),
                              title: Text(operator.displayName),
                              trailing: const Icon(Icons.chevron_right),
                              onTap: controller.busy ? null : () => controller.selectOperator(operator),
                            );
                          },
                        ),
                ),
                TextButton.icon(
                  onPressed: controller.busy ? null : controller.recoverPairedDevice,
                  icon: const Icon(Icons.sync),
                  label: const Text('Atualizar operadores'),
                ),
              ],
            ),
          ),
        ),
      );
}

class OperatorPinPage extends StatefulWidget {
  const OperatorPinPage({required this.controller, super.key});

  final AppController controller;

  @override
  State<OperatorPinPage> createState() => _OperatorPinPageState();
}

class _OperatorPinPageState extends State<OperatorPinPage> {
  final _pin = TextEditingController();

  @override
  void dispose() {
    _pin.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final operator = widget.controller.selectedOperator!;
    return Scaffold(
      appBar: AppBar(title: const Text('CORE PDV')),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 400),
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  CircleAvatar(radius: 28, child: Text(operator.initials)),
                  const SizedBox(height: 16),
                  Text(operator.displayName, textAlign: TextAlign.center, style: Theme.of(context).textTheme.headlineSmall),
                  const SizedBox(height: 24),
                  TextField(
                    controller: _pin,
                    autofocus: true,
                    enabled: !widget.controller.busy,
                    obscureText: true,
                    keyboardType: TextInputType.number,
                    maxLength: 6,
                    decoration: const InputDecoration(labelText: 'PIN de seis digitos'),
                    onSubmitted: (_) => _login(),
                  ),
                  FilledButton(
                    onPressed: widget.controller.busy ? null : _login,
                    child: const Text('ENTRAR'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _login() async {
    final pin = _pin.text;
    try {
      await widget.controller.login(pin);
    } finally {
      _pin.clear();
    }
  }
}
