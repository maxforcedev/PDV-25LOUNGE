enum SyncPhase { idle, syncing, synced, pending, error }

class SyncHistoryItem {
  const SyncHistoryItem({
    required this.occurredAt,
    required this.message,
    required this.succeeded,
  });

  final DateTime occurredAt;
  final String message;
  final bool succeeded;
}

class SyncStatus {
  const SyncStatus({
    this.phase = SyncPhase.idle,
    this.lastSyncedAt,
    this.lastHeartbeatAt,
    this.lastAttemptAt,
    this.pendingCount = 0,
    this.errorCount = 0,
    this.error,
    this.history = const [],
  });

  final SyncPhase phase;
  final DateTime? lastSyncedAt;
  final DateTime? lastHeartbeatAt;
  final DateTime? lastAttemptAt;
  final int pendingCount;
  final int errorCount;
  final String? error;
  final List<SyncHistoryItem> history;

  SyncStatus begin() => _copyWith(phase: SyncPhase.syncing, lastAttemptAt: DateTime.now(), error: null, errorCount: 0);

  SyncStatus heartbeat(DateTime when) => _copyWith(lastHeartbeatAt: when);

  SyncStatus succeeded(String message) {
    final now = DateTime.now();
    return _copyWith(
      phase: pendingCount > 0 ? SyncPhase.pending : SyncPhase.synced,
      lastSyncedAt: now,
      error: null,
      errorCount: 0,
      history: _withHistory(SyncHistoryItem(occurredAt: now, message: message, succeeded: true)),
    );
  }

  SyncStatus failed(String message) {
    final now = DateTime.now();
    return _copyWith(
      phase: SyncPhase.error,
      error: message,
      errorCount: 1,
      history: _withHistory(SyncHistoryItem(occurredAt: now, message: message, succeeded: false)),
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
    List<SyncHistoryItem>? history,
  }) => SyncStatus(
        phase: phase ?? this.phase,
        lastSyncedAt: lastSyncedAt ?? this.lastSyncedAt,
        lastHeartbeatAt: lastHeartbeatAt ?? this.lastHeartbeatAt,
        lastAttemptAt: lastAttemptAt ?? this.lastAttemptAt,
        pendingCount: pendingCount ?? this.pendingCount,
        errorCount: errorCount ?? this.errorCount,
        error: error,
        history: history ?? this.history,
      );

  List<SyncHistoryItem> _withHistory(SyncHistoryItem item) => [item, ...history].take(12).toList(growable: false);

  String get label => switch (phase) {
        SyncPhase.idle => 'Aguardando sincronizacao',
        SyncPhase.syncing => 'Sincronizando',
        SyncPhase.synced => 'Sincronizado',
        SyncPhase.pending => 'Pendencias',
        SyncPhase.error => 'Erro de sincronizacao',
      };
}
