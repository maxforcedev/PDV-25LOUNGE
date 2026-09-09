class BarcodeCooldown {
  BarcodeCooldown({
    this.cooldown = const Duration(seconds: 2),
    Duration Function()? now,
  }) : _now = now ?? _monotonicNow;

  final Duration cooldown;
  final Duration Function() _now;
  final Map<String, Duration> _lastAcceptedAt = {};

  static final Stopwatch _clock = Stopwatch()..start();

  static Duration _monotonicNow() => _clock.elapsed;

  bool accept(String value) {
    final barcode = value.trim();
    if (barcode.isEmpty) return false;
    final now = _now();
    final previous = _lastAcceptedAt[barcode];
    if (previous != null && now - previous < cooldown) return false;
    _lastAcceptedAt[barcode] = now;
    _lastAcceptedAt.removeWhere(
        (_, acceptedAt) => now - acceptedAt >= const Duration(minutes: 5));
    return true;
  }
}
