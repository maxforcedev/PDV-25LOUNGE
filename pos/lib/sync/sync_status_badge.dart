import 'package:flutter/material.dart';

import 'sync_status.dart';

class SyncStatusBadge extends StatelessWidget {
  const SyncStatusBadge({
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
      SyncPhase.syncing || SyncPhase.idle => const Color(0xff60a5fa),
      SyncPhase.pending => const Color(0xfffacc15),
      SyncPhase.error => const Color(0xfff87171),
    };
    return IconButton(
      onPressed: onPressed,
      tooltip: status.label,
      icon: Stack(
        clipBehavior: Clip.none,
        children: [
          const Icon(Icons.sync_rounded),
          Positioned(
            top: -1,
            right: -2,
            child: Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                color: color,
                shape: BoxShape.circle,
                border: Border.all(color: Colors.white, width: 1.5),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
