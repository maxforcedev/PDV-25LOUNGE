import 'package:flutter/material.dart';

import '../bootstrap/bootstrap_models.dart';
import '../cash/cash_page.dart';
import '../core/app_controller.dart';
import '../core/transient_feedback.dart';
import '../sync/sync_center_page.dart';
import '../sync/sync_status_button.dart';
import '../sales/quick_sale_page.dart';
import '../tickets/ticket_validator_page.dart';

class HomePage extends StatelessWidget {
  const HomePage({required this.controller, super.key});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    final snapshot = controller.bootstrapSnapshot!;
    return Scaffold(
      appBar: AppBar(
        title: const Text('CORE PDV'),
        actions: [
          _SyncButton(controller: controller),
          IconButton(
            onPressed: controller.busy ? null : controller.logout,
            icon: const Icon(Icons.logout_rounded),
            tooltip: 'Sair do operador',
          ),
        ],
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 760),
            child: LayoutBuilder(
              builder: (context, constraints) => ListView(
                padding: EdgeInsets.all(constraints.maxWidth >= 600 ? 28 : 20),
                children: [
                  if (snapshot.release.updateAvailable) ...[
                    const _UpdateNotice(),
                  ],
                  const SizedBox(height: 24),
                  if (snapshot.cash.enabled && snapshot.cash.canOperate) ...[
                    _CashHomeCard(snapshot: snapshot, controller: controller),
                    const SizedBox(height: 28),
                  ],
                  Text('Módulos disponíveis',
                      style: Theme.of(context)
                          .textTheme
                          .titleLarge
                          ?.copyWith(fontWeight: FontWeight.w800)),
                  const SizedBox(height: 12),
                  if (snapshot.enabledModules.isEmpty)
                    const _EmptyModules()
                  else
                    GridView.count(
                      crossAxisCount: constraints.maxWidth >= 620 ? 3 : 2,
                      crossAxisSpacing: 12,
                      mainAxisSpacing: 12,
                      childAspectRatio:
                          constraints.maxWidth >= 620 ? 1.35 : 1.12,
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      children: snapshot.enabledModules
                          .map((module) => _ModuleCard(
                              module: module, controller: controller))
                          .toList(growable: false),
                    ),
                  const SizedBox(height: 24),
                  Text('Dispositivo: ${snapshot.deviceName}',
                      style: const TextStyle(color: Color(0xff64748b))),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _SyncButton extends StatelessWidget {
  const _SyncButton({required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    final status = controller.syncStatus;
    return SyncStatusButton(
      status: status,
      onPressed: () => Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => SyncCenterPage(controller: controller))),
    );
  }
}

class _CashHomeCard extends StatelessWidget {
  const _CashHomeCard({required this.snapshot, required this.controller});

  final BootstrapSnapshot snapshot;
  final AppController controller;

  @override
  Widget build(BuildContext context) {
    final cash = snapshot.cash;
    final openCount = cash.isFixed
        ? (cash.session == null ? 0 : 1)
        : cash.openRegisters.length;
    final title = !cash.enabled
        ? 'Caixa indisponível'
        : openCount == 0
            ? 'Caixa fechado'
            : openCount == 1
                ? 'Caixa aberto'
                : '$openCount caixas abertos';
    final subtitle = cash.isFixed
        ? cash.register?.name ?? 'Caixa não configurado'
        : openCount == 0
            ? 'Nenhum caixa com sessão aberta'
            : 'Selecione o caixa para operar';
    return InkWell(
      borderRadius: BorderRadius.circular(20),
      onTap: cash.enabled && cash.canOperate
          ? () => Navigator.of(context).push(MaterialPageRoute(
              builder: (_) => CashPage(controller: controller)))
          : null,
      child: Ink(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: const Color(0xffe2e8f0))),
        child: Row(children: [
          Container(
            width: 46,
            height: 46,
            decoration: BoxDecoration(
                color: const Color(0xffe8edff),
                borderRadius: BorderRadius.circular(14)),
            child: const Icon(Icons.point_of_sale_outlined,
                color: Color(0xff2945b6)),
          ),
          const SizedBox(width: 14),
          Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                Text(title,
                    style: Theme.of(context)
                        .textTheme
                        .titleLarge
                        ?.copyWith(fontWeight: FontWeight.w800)),
                const SizedBox(height: 3),
                Text(subtitle,
                    style: const TextStyle(color: Color(0xff64748b))),
              ])),
          const Icon(Icons.chevron_right_rounded),
        ]),
      ),
    );
  }
}

class _ModuleCard extends StatelessWidget {
  const _ModuleCard({required this.module, required this.controller});

  final HomeModule module;
  final AppController controller;

  static const _labels = {
    'quick_sale': 'Venda Rápida',
    'commands': 'Mesas / Comandas',
    'ticket_validator': 'Validador de Ticket',
    'inventory': 'Estoque',
    'reports': 'Relatórios',
  };
  static const _icons = {
    'quick_sale': Icons.shopping_bag_outlined,
    'commands': Icons.table_restaurant_outlined,
    'ticket_validator': Icons.confirmation_number_outlined,
    'inventory': Icons.inventory_2_outlined,
    'reports': Icons.insights_outlined,
  };

  @override
  Widget build(BuildContext context) => InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: () {
          if (module.key == 'quick_sale') {
            Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => QuickSalePage(controller: controller)));
            return;
          }
          if (module.key == 'ticket_validator') {
            Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => TicketValidatorPage(controller: controller)));
            return;
          }
          controller.showTransientMessage(
              'Este módulo estará disponível em uma próxima etapa.',
              tone: TransientAlertTone.info);
        },
        child: Ink(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(18),
              border: Border.all(color: const Color(0xffe2e8f0))),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Icon(_icons[module.key] ?? Icons.dashboard_outlined,
                color: const Color(0xff2945b6)),
            const Spacer(),
            Text(_labels[module.key] ?? module.key,
                style: Theme.of(context)
                    .textTheme
                    .titleMedium
                    ?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 4),
            Text(
                module.key == 'quick_sale' ? 'Catálogo e checkout' : 'Em breve',
                style: const TextStyle(color: Color(0xff64748b), fontSize: 12)),
          ]),
        ),
      );
}

class _UpdateNotice extends StatelessWidget {
  const _UpdateNotice();

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
            color: const Color(0xfffffaeb),
            borderRadius: BorderRadius.circular(14)),
        child: const Text('Uma atualização do CORE PDV está disponível.',
            style: TextStyle(color: Color(0xffa15c00))),
      );
}

class _EmptyModules extends StatelessWidget {
  const _EmptyModules();

  @override
  Widget build(BuildContext context) => const Padding(
        padding: EdgeInsets.all(20),
        child: Text('Nenhum módulo está habilitado para este operador.',
            style: TextStyle(color: Color(0xff64748b))),
      );
}
