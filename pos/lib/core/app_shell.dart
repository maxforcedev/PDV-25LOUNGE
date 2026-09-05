import 'package:flutter/material.dart';

import '../auth/operator_pages.dart';
import '../home/home_page.dart';
import '../pairing/pairing_pages.dart';
import 'app_controller.dart';
import 'core_branding.dart';

class AppShell extends StatelessWidget {
  const AppShell({required this.controller, super.key});

  final AppController controller;

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: controller,
        builder: (context, _) {
          final page = switch (controller.phase) {
            AppPhase.loading => const _LoadingPage(),
            AppPhase.pairingIdentifier => PairingIdentifierPage(controller: controller),
            AppPhase.pairingChannel => PairingChannelPage(controller: controller),
            AppPhase.pairingOtp => PairingOtpPage(controller: controller),
            AppPhase.operatorSelection || AppPhase.operatorPin => OperatorAccessPage(controller: controller),
            AppPhase.home => HomePage(controller: controller),
            AppPhase.deviceUnavailable => _DeviceUnavailablePage(controller: controller),
            AppPhase.updateRequired => const _UpdateRequiredPage(),
            AppPhase.error => _ErrorPage(controller: controller),
          };
          return AnimatedSwitcher(
            duration: const Duration(milliseconds: 260),
            reverseDuration: const Duration(milliseconds: 180),
            switchInCurve: Curves.easeOutCubic,
            switchOutCurve: Curves.easeInCubic,
            transitionBuilder: (child, animation) => FadeTransition(
              opacity: animation,
              child: SlideTransition(
                position: Tween<Offset>(begin: const Offset(0, 0.025), end: Offset.zero).animate(animation),
                child: ScaleTransition(scale: Tween<double>(begin: 0.985, end: 1).animate(animation), child: child),
              ),
            ),
            child: KeyedSubtree(key: ValueKey(controller.phase), child: page),
          );
        },
      );
}

class _LoadingPage extends StatefulWidget {
  const _LoadingPage();

  @override
  State<_LoadingPage> createState() => _LoadingPageState();
}

class _LoadingPageState extends State<_LoadingPage> with SingleTickerProviderStateMixin {
  late final AnimationController _animation = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _animation.dispose();
    super.dispose();
  }

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
          child: Center(
            child: AnimatedBuilder(
              animation: _animation,
              builder: (context, child) => Opacity(
                opacity: 0.72 + (_animation.value * 0.28),
                child: Transform.scale(scale: 0.94 + (_animation.value * 0.06), child: child),
              ),
              child: const CoreSymbol(size: 112),
            ),
          ),
        ),
      );
}

class _ErrorPage extends StatelessWidget {
  const _ErrorPage({required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) => _StatusPage(
        title: 'Nao foi possivel sincronizar',
        message: controller.errorMessage ?? 'Verifique sua conexao e tente novamente.',
        actionLabel: 'TENTAR NOVAMENTE',
        onPressed: controller.busy ? null : controller.recoverPairedDevice,
      );
}

class _DeviceUnavailablePage extends StatelessWidget {
  const _DeviceUnavailablePage({required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    final code = controller.deviceError?.code;
    final title = switch (code) {
      'device_blocked' => 'Dispositivo bloqueado',
      'device_revoked' => 'Dispositivo revogado',
      'device_replaced' => 'Dispositivo substituido',
      _ => 'Dispositivo indisponivel',
    };
    final canPairAgain = code == 'device_revoked' || code == 'device_replaced';
    return _StatusPage(
      title: title,
      message: controller.errorMessage ?? 'Este dispositivo nao esta autorizado a operar.',
      actionLabel: canPairAgain ? 'PAREAR NOVAMENTE' : 'TENTAR NOVAMENTE',
      onPressed: controller.busy
          ? null
          : canPairAgain
              ? controller.forgetDevice
              : controller.recoverPairedDevice,
    );
  }
}

class _UpdateRequiredPage extends StatelessWidget {
  const _UpdateRequiredPage();

  @override
  Widget build(BuildContext context) => const _StatusPage(
        title: 'Atualizacao obrigatoria',
        message: 'Esta versão do CORE PDV não é mais suportada. Atualize o aplicativo para continuar.',
      );
}

class _StatusPage extends StatelessWidget {
  const _StatusPage({
    required this.title,
    required this.message,
    this.actionLabel,
    this.onPressed,
  });

  final String title;
  final String message;
  final String? actionLabel;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) => Scaffold(
        body: SafeArea(
          child: Center(
            child: Padding(
              padding: const EdgeInsets.all(28),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.info_outline, size: 48),
                  const SizedBox(height: 16),
                  Text(title, style: Theme.of(context).textTheme.headlineSmall),
                  const SizedBox(height: 8),
                  Text(message, textAlign: TextAlign.center),
                  if (actionLabel != null) ...[
                    const SizedBox(height: 20),
                    FilledButton(onPressed: onPressed, child: Text(actionLabel!)),
                  ],
                ],
              ),
            ),
          ),
        ),
      );
}
