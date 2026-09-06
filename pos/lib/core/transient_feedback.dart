import 'dart:async';

import 'package:flutter/material.dart';

enum TransientAlertTone { success, info, warning, error }

class TransientAlert {
  const TransientAlert({
    required this.id,
    required this.message,
    required this.tone,
  });

  final int id;
  final String message;
  final TransientAlertTone tone;
}

class TransientFeedback {
  static const duration = Duration(seconds: 5);

  Timer? _dismissalTimer;
  int _nextAlertId = 0;
  TransientAlert? alert;

  void show(
    String message,
    VoidCallback onExpired, {
    TransientAlertTone tone = TransientAlertTone.error,
  }) {
    _dismissalTimer?.cancel();
    alert = TransientAlert(id: _nextAlertId++, message: message, tone: tone);
    _dismissalTimer = Timer(duration, () {
      _dismissalTimer = null;
      alert = null;
      onExpired();
    });
  }

  bool clear() {
    _dismissalTimer?.cancel();
    _dismissalTimer = null;
    if (alert == null) return false;
    alert = null;
    return true;
  }

  void dispose() => _dismissalTimer?.cancel();
}

class TransientAlertOverlay extends StatelessWidget {
  const TransientAlertOverlay({required this.alert, super.key});

  final TransientAlert? alert;

  @override
  Widget build(BuildContext context) => IgnorePointer(
        child: SafeArea(
          child: Align(
            alignment: Alignment.topCenter,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 420),
                child: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 220),
                  reverseDuration: const Duration(milliseconds: 160),
                  switchInCurve: Curves.easeOutCubic,
                  switchOutCurve: Curves.easeInCubic,
                  transitionBuilder: (child, animation) => FadeTransition(
                    opacity: animation,
                    child: SlideTransition(
                      position: Tween<Offset>(begin: const Offset(0, -0.12), end: Offset.zero).animate(animation),
                      child: child,
                    ),
                  ),
                  child: alert == null
                      ? const SizedBox.shrink(key: ValueKey('empty-alert'))
                      : _TransientAlertCard(key: ValueKey(alert!.id), alert: alert!),
                ),
              ),
            ),
          ),
        ),
      );
}

class _TransientAlertCard extends StatelessWidget {
  const _TransientAlertCard({required this.alert, super.key});

  final TransientAlert alert;

  @override
  Widget build(BuildContext context) {
    final style = switch (alert.tone) {
      TransientAlertTone.success => (icon: Icons.check_circle_outline_rounded, color: const Color(0xff087443), background: const Color(0xffecfdf3), border: const Color(0xffa6f4c5)),
      TransientAlertTone.info => (icon: Icons.info_outline_rounded, color: const Color(0xff2945b6), background: const Color(0xffeff4ff), border: const Color(0xffc7d7fe)),
      TransientAlertTone.warning => (icon: Icons.warning_amber_rounded, color: const Color(0xffa15c00), background: const Color(0xfffffaeb), border: const Color(0xfffedf89)),
      TransientAlertTone.error => (icon: Icons.info_outline_rounded, color: const Color(0xffb42318), background: const Color(0xfffff4f2), border: const Color(0xfffecaca)),
    };
    return Material(
      color: Colors.transparent,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: style.background,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: style.border),
          boxShadow: const [
            BoxShadow(color: Color(0x1a283c50), blurRadius: 20, offset: Offset(0, 8)),
          ],
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(style.icon, color: style.color, size: 20),
            const SizedBox(width: 10),
            Expanded(child: Text(alert.message, style: TextStyle(color: style.color, height: 1.35))),
          ],
        ),
      ),
    );
  }
}
