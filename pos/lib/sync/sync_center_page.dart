import 'package:flutter/material.dart';

import '../core/app_controller.dart';
import '../core/transient_feedback.dart';
import 'sync_status.dart';

class SyncCenterPage extends StatelessWidget {
  const SyncCenterPage({required this.controller, super.key});

  final AppController controller;

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: controller,
        builder: (context, _) {
          final status = controller.syncStatus;
          final snapshot = controller.bootstrapSnapshot!;
          return Stack(
            fit: StackFit.expand,
            children: [
              Scaffold(
                appBar: AppBar(title: const Text('Central de sincronização')),
                body: SafeArea(
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 520),
                  child: ListView(
                    padding: const EdgeInsets.all(20),
                    children: [
                      _StatusCard(status: status),
                      const SizedBox(height: 16),
                      _DetailsCard(status: status, deviceName: snapshot.deviceName, deviceStatus: snapshot.deviceStatus),
                      const SizedBox(height: 20),
                      FilledButton.icon(
                        onPressed: controller.busy ? null : controller.synchronize,
                        icon: const Icon(Icons.sync_rounded),
                        label: const Text('SINCRONIZAR AGORA'),
                      ),
                      const SizedBox(height: 28),
                      Text('Histórico', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
                      const SizedBox(height: 12),
                      if (status.history.isEmpty)
                        const _EmptyHistory()
                      else
                        ...status.history.map((item) => _HistoryItem(item: item)),
                    ],
                  ),
                ),
              ),
                ),
              ),
              TransientAlertOverlay(alert: controller.transientAlert),
            ],
          );
        },
      );
}

class _StatusCard extends StatelessWidget {
  const _StatusCard({required this.status});

  final SyncStatus status;

  @override
  Widget build(BuildContext context) {
    final color = switch (status.phase) {
      SyncPhase.synced => const Color(0xff087443),
      SyncPhase.syncing => const Color(0xff2945b6),
      SyncPhase.pending => const Color(0xffa15c00),
      SyncPhase.error => const Color(0xffb42318),
      SyncPhase.idle => const Color(0xff64748b),
    };
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(20), border: Border.all(color: const Color(0xffe2e8f0))),
      child: Row(children: [
        Icon(status.phase == SyncPhase.syncing ? Icons.sync_rounded : Icons.cloud_done_outlined, color: color, size: 30),
        const SizedBox(width: 14),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(status.label, style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800, color: color)),
          if (status.error != null) ...[const SizedBox(height: 4), Text(status.error!, style: const TextStyle(color: Color(0xff64748b)))],
        ])),
      ]),
    );
  }
}

class _DetailsCard extends StatelessWidget {
  const _DetailsCard({required this.status, required this.deviceName, required this.deviceStatus});

  final SyncStatus status;
  final String deviceName;
  final String deviceStatus;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(color: const Color(0xfff0f2f8), borderRadius: BorderRadius.circular(20)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          _DetailLine(label: 'Última sincronização', value: _time(status.lastSyncedAt)),
          _DetailLine(label: 'Heartbeat', value: status.lastHeartbeatAt == null ? 'Sem confirmação' : 'Online ${_time(status.lastHeartbeatAt)}'),
          _DetailLine(label: 'Dispositivo', value: '$deviceName ${deviceStatus.isEmpty ? '' : '($deviceStatus)'}'),
          _DetailLine(label: 'Pendências locais', value: '${status.pendingCount}'),
          _DetailLine(label: 'Erros', value: '${status.errorCount}'),
        ]),
      );
}

class _DetailLine extends StatelessWidget {
  const _DetailLine({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          Text(label, style: const TextStyle(color: Color(0xff64748b))),
          Flexible(child: Text(value, textAlign: TextAlign.end, style: const TextStyle(fontWeight: FontWeight.w700))),
        ]),
      );
}

class _HistoryItem extends StatelessWidget {
  const _HistoryItem({required this.item});

  final SyncHistoryItem item;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: ListTile(
          tileColor: Colors.white,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
          leading: Icon(item.succeeded ? Icons.check_circle_outline_rounded : Icons.error_outline_rounded, color: item.succeeded ? const Color(0xff087443) : const Color(0xffb42318)),
          title: Text(item.message),
          subtitle: Text(_time(item.occurredAt)),
        ),
      );
}

class _EmptyHistory extends StatelessWidget {
  const _EmptyHistory();

  @override
  Widget build(BuildContext context) => const Padding(
        padding: EdgeInsets.all(16),
        child: Text('As próximas sincronizações aparecerão aqui.', style: TextStyle(color: Color(0xff64748b))),
      );
}

String _time(DateTime? value) {
  if (value == null) return 'Ainda não sincronizado';
  final day = value.day.toString().padLeft(2, '0');
  final month = value.month.toString().padLeft(2, '0');
  final hour = value.hour.toString().padLeft(2, '0');
  final minute = value.minute.toString().padLeft(2, '0');
  return '$day/$month $hour:$minute';
}
