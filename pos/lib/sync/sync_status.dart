enum SyncPhase { idle, syncing, synced, pending, error }

class SyncStatus {
  const SyncStatus({
    this.phase = SyncPhase.idle,
    this.lastSyncedAt,
    this.lastHeartbeatAt,
    this.lastAttemptAt,
    this.pendingCount = 0,
    this.errorCount = 0,
    this.error,
  });

  final SyncPhase phase;
  final DateTime? lastSyncedAt;
  final DateTime? lastHeartbeatAt;
  final DateTime? lastAttemptAt;
  final int pendingCount;
  final int errorCount;
  final String? error;

  SyncStatus begin() => _copyWith(
      phase: SyncPhase.syncing,
      lastAttemptAt: DateTime.now(),
      error: null,
      errorCount: 0);

  SyncStatus heartbeat(DateTime when) => _copyWith(lastHeartbeatAt: when);

  SyncStatus succeeded() {
    final now = DateTime.now();
    return _copyWith(
      phase: pendingCount > 0 ? SyncPhase.pending : SyncPhase.synced,
      lastSyncedAt: now,
      error: null,
      errorCount: 0,
    );
  }

  SyncStatus failed(String message) {
    return _copyWith(
      phase: SyncPhase.error,
      error: message,
      errorCount: 1,
    );
  }

  SyncStatus _copyWith({
    SyncPhase? phase,
    DateTime? lastSyncedAt,
    DateTime? lastHeartbeatAt,
    DateTime? lastAttemptAt,
    int? pendingCount,
    int? errorCount,
    String? error,
  }) =>
      SyncStatus(
        phase: phase ?? this.phase,
        lastSyncedAt: lastSyncedAt ?? this.lastSyncedAt,
        lastHeartbeatAt: lastHeartbeatAt ?? this.lastHeartbeatAt,
        lastAttemptAt: lastAttemptAt ?? this.lastAttemptAt,
        pendingCount: pendingCount ?? this.pendingCount,
        errorCount: errorCount ?? this.errorCount,
        error: error,
      );

  String get label => switch (phase) {
        SyncPhase.idle => 'Aguardando sincronizacao',
        SyncPhase.syncing => 'Sincronizando',
        SyncPhase.synced => 'Sincronizado',
        SyncPhase.pending => 'Pendencias',
        SyncPhase.error => 'Erro de sincronizacao',
      };
}
