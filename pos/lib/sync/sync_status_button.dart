import 'package:flutter/material.dart';

import 'sync_status.dart';

class SyncStatusButton extends StatelessWidget {
  const SyncStatusButton({
    required this.status,
    required this.onPressed,
    super.key,
  });

  final SyncStatus status;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final color = switch (status.phase) {
      SyncPhase.synced => const Color(0xff4ade80),
      SyncPhase.syncing => const Color(0xff7dd3fc),
      SyncPhase.pending => const Color(0xfff59e0b),
      SyncPhase.error => const Color(0xfff87171),
      SyncPhase.idle => Colors.white,
    };
    return IconButton(
      onPressed: onPressed,
      tooltip: status.label,
      icon: Icon(Icons.sync_rounded, color: color),
    );
  }
}
