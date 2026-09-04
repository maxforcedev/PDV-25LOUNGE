import 'package:flutter/material.dart';

import '../core/app_controller.dart';
import 'pairing_models.dart';

class PairingIdentifierPage extends StatefulWidget {
  const PairingIdentifierPage({required this.controller, super.key});

  final AppController controller;

  @override
  State<PairingIdentifierPage> createState() => _PairingIdentifierPageState();
}

class _PairingIdentifierPageState extends State<PairingIdentifierPage> {
  final _identifier = TextEditingController();

  @override
  void dispose() {
    _identifier.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => _PosPage(
        title: 'Parear este dispositivo',
        subtitle: 'Digite o CNPJ da filial ou o codigo de licenciamento CORE.',
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: _identifier,
              enabled: !widget.controller.busy,
              autocorrect: false,
              textCapitalization: TextCapitalization.characters,
              decoration: const InputDecoration(labelText: 'CNPJ ou codigo'),
              onSubmitted: (_) => _identify(),
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: widget.controller.busy ? null : _identify,
              child: const Text('CONTINUAR'),
            ),
          ],
        ),
      );

  Future<void> _identify() => widget.controller.identify(_identifier.text);
}

class PairingChannelPage extends StatelessWidget {
  const PairingChannelPage({required this.controller, super.key});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    final discovery = controller.discovery!;
    return _PosPage(
      title: discovery.branchName,
      subtitle: 'Escolha onde receber o codigo de verificacao.',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: discovery.channels
            .map(
              (channel) => Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: OutlinedButton(
                  onPressed: controller.busy ? null : () => controller.requestOtp(channel),
                  child: Text('${_channelLabel(channel)}: ${channel.masked}'),
                ),
              ),
            )
            .toList(growable: false),
      ),
    );
  }

  String _channelLabel(PairingChannel channel) =>
      channel.type == 'email' ? 'E-mail' : channel.type;
}

class PairingOtpPage extends StatefulWidget {
  const PairingOtpPage({required this.controller, super.key});

  final AppController controller;

  @override
  State<PairingOtpPage> createState() => _PairingOtpPageState();
}

class _PairingOtpPageState extends State<PairingOtpPage> {
  final _code = TextEditingController();

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => _PosPage(
        title: 'Confirme o codigo',
        subtitle: 'Enviamos um codigo para ${widget.controller.challenge!.destination}.',
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: _code,
              enabled: !widget.controller.busy,
              autofocus: true,
              keyboardType: TextInputType.number,
              maxLength: 6,
              obscureText: true,
              decoration: const InputDecoration(labelText: 'Codigo de seis digitos'),
              onSubmitted: (_) => _confirm(),
            ),
            FilledButton(
              onPressed: widget.controller.busy ? null : _confirm,
              child: const Text('PAREAR DISPOSITIVO'),
            ),
          ],
        ),
      );

  Future<void> _confirm() async {
    final code = _code.text;
    try {
      await widget.controller.confirmOtp(code);
    } finally {
      _code.clear();
    }
  }
}

class _PosPage extends StatelessWidget {
  const _PosPage({
    required this.title,
    required this.subtitle,
    required this.child,
  });

  final String title;
  final String subtitle;
  final Widget child;

  @override
  Widget build(BuildContext context) => Scaffold(
        body: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: Padding(
                padding: const EdgeInsets.all(28),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('CORE PDV', style: Theme.of(context).textTheme.labelLarge),
                    const SizedBox(height: 14),
                    Text(title, style: Theme.of(context).textTheme.headlineMedium),
                    const SizedBox(height: 8),
                    Text(subtitle, style: Theme.of(context).textTheme.bodyLarge),
                    const SizedBox(height: 28),
                    child,
                  ],
                ),
              ),
            ),
          ),
        ),
      );
}
