class BarcodeCooldown {
  BarcodeCooldown({
    this.cooldown = const Duration(seconds: 2),
    this.absenceWindow = const Duration(milliseconds: 500),
    Duration Function()? now,
  }) : _now = now ?? _monotonicNow;

  final Duration cooldown;
  final Duration absenceWindow;
  final Duration Function() _now;
  final Map<String, Duration> _lastAcceptedAt = {};
  final Map<String, Duration> _lastSeenAt = {};

  static final Stopwatch _clock = Stopwatch()..start();

  static Duration _monotonicNow() => _clock.elapsed;

  void keepBlocked(String value) {
    final barcode = value.trim();
    if (barcode.isNotEmpty) _lastSeenAt[barcode] = _now();
  }

  bool accept(String value) {
    final barcode = value.trim();
    if (barcode.isEmpty) return false;
    final now = _now();
    final lastSeen = _lastSeenAt[barcode];
    _lastSeenAt[barcode] = now;
    if (lastSeen != null && now - lastSeen < absenceWindow) return false;
    final previous = _lastAcceptedAt[barcode];
    if (previous != null && now - previous < cooldown) return false;
    _lastAcceptedAt[barcode] = now;
    _lastAcceptedAt.removeWhere(
        (_, acceptedAt) => now - acceptedAt >= const Duration(minutes: 5));
    _lastSeenAt
        .removeWhere((_, seenAt) => now - seenAt >= const Duration(minutes: 5));
    return true;
  }
}
