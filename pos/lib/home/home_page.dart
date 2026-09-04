import 'package:flutter/material.dart';

import '../bootstrap/bootstrap_models.dart';
import '../core/app_controller.dart';
import '../sync/sync_status.dart';

class HomePage extends StatelessWidget {
  const HomePage({required this.controller, super.key});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    final snapshot = controller.bootstrapSnapshot!;
    return Scaffold(
      appBar: AppBar(
        title: Text('${snapshot.companyName} - ${snapshot.branchName}'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: Center(child: _SyncIndicator(controller: controller)),
          ),
          IconButton(
            onPressed: controller.busy ? null : controller.logout,
            icon: const Icon(Icons.logout),
            tooltip: 'Sair do operador',
          ),
        ],
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Ola, ${snapshot.operatorName}', style: Theme.of(context).textTheme.headlineSmall),
              if (snapshot.release.updateAvailable) ...[
                const SizedBox(height: 8),
                const Text('Uma atualizacao do CORE POS esta disponivel.'),
              ],
              const SizedBox(height: 24),
              Expanded(
                child: snapshot.enabledModules.isEmpty
                    ? const Center(child: Text('Nenhum modulo esta habilitado para este operador.'))
                    : GridView.count(
                        crossAxisCount: MediaQuery.sizeOf(context).width > 700 ? 3 : 2,
                        crossAxisSpacing: 12,
                        mainAxisSpacing: 12,
                        children: snapshot.enabledModules
                            .map((module) => _ModuleCard(module: module))
                            .toList(growable: false),
                      ),
              ),
              Text('Dispositivo: ${snapshot.deviceName}'),
            ],
          ),
        ),
      ),
    );
  }
}

class _SyncIndicator extends StatelessWidget {
  const _SyncIndicator({required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    final status = controller.syncStatus;
    final color = switch (status.phase) {
      SyncPhase.synced => Colors.green,
      SyncPhase.syncing => Colors.orange,
      SyncPhase.error => Colors.red,
      SyncPhase.idle => Colors.grey,
    };
    return Chip(
      avatar: Icon(Icons.sync, size: 16, color: color),
      label: Text(status.label),
    );
  }
}

class _ModuleCard extends StatelessWidget {
  const _ModuleCard({required this.module});

  final HomeModule module;

  static const _labels = {
    'quick_sale': 'Venda Rapida',
    'commands': 'Mesas e Comandas',
    'ticket_validator': 'Validador de Ticket',
    'inventory': 'Estoque',
    'reports': 'Relatorios',
  };

  @override
  Widget build(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.dashboard_outlined),
              const Spacer(),
              Text(_labels[module.key] ?? module.key, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 4),
              const Text('Disponivel em uma proxima etapa.'),
            ],
          ),
        ),
      );
}
