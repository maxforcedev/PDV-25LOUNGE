import 'dart:async';

import 'package:flutter/services.dart';

class CieloPaymentCallback {
  const CieloPaymentCallback({
    required this.operation,
    required this.operationId,
    required this.response,
    this.responseCode,
  });

  factory CieloPaymentCallback.fromMap(Map<Object?, Object?> value) =>
      CieloPaymentCallback(
        // Native clients before reversal support only sent attempt_id.
        operation: value['operation'] as String? ?? 'payment',
        operationId:
            value['operation_id'] as String? ?? value['attempt_id'] as String,
        response: value['response'] as String? ?? '',
        responseCode: value['responsecode'] as String?,
      );

  final String operation;
  final String operationId;
  final String response;
  final String? responseCode;

  bool get isPayment => operation == 'payment';
  bool get isReversal => operation == 'reversal';

  // Retains the established payment-only bridge API for existing callers.
  String get attemptId => operationId;
}

/// Native Cielo transport only. Financial status remains exclusively in CORE.
class CieloPaymentBridge {
  CieloPaymentBridge() {
    _channel.setMethodCallHandler(_onMethodCall);
  }

  static const _channel = MethodChannel('core_pos/cielo_payment');
  final _callbacks = StreamController<CieloPaymentCallback>.broadcast();

  Stream<CieloPaymentCallback> get callbacks => _callbacks.stream;

  Future<void> launch({
    required String operation,
    required String operationId,
    required String launchUri,
  }) =>
      _channel.invokeMethod<void>('launchPayment', {
        'operation': operation,
        'operation_id': operationId,
        'launch_uri': launchUri,
      });

  Future<CieloPaymentCallback?> getPendingCallback() async {
    final value =
        await _channel.invokeMapMethod<Object?, Object?>('getPendingCallback');
    return value == null ? null : CieloPaymentCallback.fromMap(value);
  }

  Future<bool> acknowledgeCallback(CieloPaymentCallback callback) async =>
      await _channel.invokeMethod<bool>(
        'acknowledgeCallback',
        {
          'operation': callback.operation,
          'operation_id': callback.operationId,
        },
      ) ??
      false;

  Future<void> _onMethodCall(MethodCall call) async {
    if (call.method != 'paymentCallback' || call.arguments is! Map) return;
    _callbacks.add(CieloPaymentCallback.fromMap(
      Map<Object?, Object?>.from(call.arguments as Map),
    ));
  }

  void dispose() {
    _callbacks.close();
  }
}
