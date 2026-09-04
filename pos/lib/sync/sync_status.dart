enum SyncPhase { idle, syncing, synced, error }

class SyncStatus {
  const SyncStatus({this.phase = SyncPhase.idle, this.lastSyncedAt, this.error});

  final SyncPhase phase;
  final DateTime? lastSyncedAt;
  final String? error;

  String get label => switch (phase) {
        SyncPhase.idle => 'Aguardando sincronizacao',
        SyncPhase.syncing => 'Sincronizando',
        SyncPhase.synced => 'Sincronizado',
        SyncPhase.error => 'Erro de sincronizacao',
      };
}
