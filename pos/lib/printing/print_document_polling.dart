import 'dart:async';

import 'models.dart';

Future<void> pollPrintDocument({
  required Future<PrintDocumentResult?> Function() reload,
  required bool Function() isMounted,
  required void Function(PrintDocumentResult document) onUpdate,
  int attempts = 5,
  Duration interval = const Duration(seconds: 2),
}) async {
  for (var attempt = 0; attempt < attempts; attempt++) {
    await Future<void>.delayed(interval);
    if (!isMounted()) return;
    final document = await reload();
    if (!isMounted() || document == null) return;
    onUpdate(document);
    if (!document.queued) return;
  }
}
