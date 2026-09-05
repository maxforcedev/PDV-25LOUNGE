import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../core/app_controller.dart';
import '../core/core_branding.dart';
import 'pairing_models.dart';

const _primary = Color(0xff3454d1);
const _primaryDark = Color(0xff2945b6);
const _ink = Color(0xff283c50);
const _muted = Color(0xff64748b);
const _border = Color(0xffe2e8f0);

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
  Widget build(BuildContext context) => _PairingFrame(
        title: 'Parear este dispositivo',
        subtitle: 'Informe os dados da filial para começar a configurar este terminal.',
        errorMessage: widget.controller.errorMessage,
        isInitialPage: true,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: _identifier,
              enabled: !widget.controller.busy,
              autocorrect: false,
              textCapitalization: TextCapitalization.characters,
              textInputAction: TextInputAction.done,
              decoration: const InputDecoration(
                labelText: 'CNPJ ou código de licenciamento',
                hintText: 'Ex.: 12.345.678/0001-90 ou CORE-7K9P2M',
              ),
              onSubmitted: (_) => _identify(),
            ),
            const SizedBox(height: 16),
            _PrimaryAction(
              label: 'Continuar',
              loading: widget.controller.busy,
              onPressed: _identify,
            ),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: _openCoreSite,
              icon: const Icon(Icons.open_in_new_rounded, size: 18),
              label: const Text('Seja cliente'),
              style: OutlinedButton.styleFrom(
                foregroundColor: _primary,
                minimumSize: const Size.fromHeight(50),
                side: const BorderSide(color: _border),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
              ),
            ),
            const SizedBox(height: 20),
            const Text(
              'O código identifica a filial e não substitui a confirmação de segurança.',
              textAlign: TextAlign.center,
              style: TextStyle(color: _muted, fontSize: 12, height: 1.45),
            ),
          ],
        ),
      );

  Future<void> _identify() => widget.controller.identify(_identifier.text);

  Future<void> _openCoreSite() async {
    final opened = await launchUrl(
      Uri.parse('https://corepdv.com'),
      mode: LaunchMode.externalApplication,
    );
    if (!opened && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Não foi possível abrir o site do CORE PDV.')),
      );
    }
  }
}

class PairingChannelPage extends StatelessWidget {
  const PairingChannelPage({required this.controller, super.key});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    final discovery = controller.discovery!;
    return _PairingFrame(
      title: discovery.branchName,
      subtitle: 'Escolha onde deseja receber o código de verificação.',
      errorMessage: controller.errorMessage,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: discovery.channels
            .map(
              (channel) => Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: OutlinedButton.icon(
                  onPressed: controller.busy ? null : () => controller.requestOtp(channel),
                  icon: const Icon(Icons.mark_email_read_outlined),
                  label: Text('${_channelLabel(channel)}: ${channel.masked}'),
                  style: OutlinedButton.styleFrom(
                    alignment: Alignment.centerLeft,
                    foregroundColor: _ink,
                    minimumSize: const Size.fromHeight(58),
                    side: const BorderSide(color: _border),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                  ),
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
  Widget build(BuildContext context) => _PairingFrame(
        title: 'Confirme o código',
        subtitle: 'Enviamos um código para ${widget.controller.challenge!.destination}.',
        errorMessage: widget.controller.errorMessage,
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
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700, letterSpacing: 8),
              decoration: const InputDecoration(
                counterText: '',
                labelText: 'Código de seis dígitos',
              ),
              onSubmitted: (_) => _confirm(),
            ),
            const SizedBox(height: 16),
            _PrimaryAction(
              label: 'Parear dispositivo',
              loading: widget.controller.busy,
              onPressed: _confirm,
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

class _PairingFrame extends StatelessWidget {
  const _PairingFrame({
    required this.title,
    required this.subtitle,
    required this.child,
    this.errorMessage,
    this.isInitialPage = false,
  });

  final String title;
  final String subtitle;
  final String? errorMessage;
  final bool isInitialPage;
  final Widget child;

  @override
  Widget build(BuildContext context) => Scaffold(
        body: DecoratedBox(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [Color(0xffe8edff), Color(0xfff0f2f8)],
            ),
          ),
          child: SafeArea(
            child: LayoutBuilder(
              builder: (context, constraints) {
                final isTablet = constraints.maxWidth >= 600;
                final padding = isTablet ? 32.0 : 20.0;
                return Center(
                  child: SingleChildScrollView(
                    padding: EdgeInsets.all(padding),
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 440),
                      child: TweenAnimationBuilder<double>(
                        duration: const Duration(milliseconds: 650),
                        curve: Curves.easeOutCubic,
                        tween: Tween(begin: 0, end: 1),
                        builder: (context, value, content) => Opacity(
                          opacity: value,
                          child: Transform.translate(
                            offset: Offset(0, 22 * (1 - value)),
                            child: content,
                          ),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Center(
                              child: Container(
                                width: isInitialPage ? 220 : 184,
                                height: isInitialPage ? 82 : 68,
                                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                decoration: BoxDecoration(
                                  color: Colors.white,
                                  borderRadius: BorderRadius.circular(22),
                                  boxShadow: const [
                                    BoxShadow(color: Color(0x143454d1), blurRadius: 28, offset: Offset(0, 12)),
                                  ],
                                ),
                                child: CoreWordmark(width: isInitialPage ? 196 : 160),
                              ),
                            ),
                            const SizedBox(height: 28),
                            Container(
                              padding: EdgeInsets.all(isTablet ? 36 : 24),
                              decoration: BoxDecoration(
                                color: Colors.white,
                                borderRadius: BorderRadius.circular(24),
                                border: Border.all(color: _border),
                                boxShadow: const [
                                  BoxShadow(color: Color(0x0f283c50), blurRadius: 24, offset: Offset(0, 10)),
                                ],
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  Text(title, style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800, color: _ink)),
                                  const SizedBox(height: 8),
                                  Text(subtitle, style: const TextStyle(color: _muted, fontSize: 15, height: 1.45)),
                                  if (errorMessage != null) ...[
                                    const SizedBox(height: 20),
                                    _ErrorNotice(message: errorMessage!),
                                  ],
                                  const SizedBox(height: 28),
                                  child,
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
        ),
      );
}

class _PrimaryAction extends StatelessWidget {
  const _PrimaryAction({required this.label, required this.loading, required this.onPressed});

  final String label;
  final bool loading;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) => FilledButton(
        onPressed: loading ? null : onPressed,
        style: FilledButton.styleFrom(backgroundColor: _primary, disabledBackgroundColor: _primaryDark),
        child: loading
            ? const SizedBox(height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2.4, color: Colors.white))
            : Text(label),
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
