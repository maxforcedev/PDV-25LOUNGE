import 'dart:async';

import 'package:flutter/services.dart';

class CieloPaymentCallback {
  const CieloPaymentCallback({
    required this.attemptId,
    required this.response,
    this.responseCode,
  });

  factory CieloPaymentCallback.fromMap(Map<Object?, Object?> value) =>
      CieloPaymentCallback(
        attemptId: value['attempt_id'] as String,
        response: value['response'] as String? ?? '',
        responseCode: value['responsecode'] as String?,
      );

  final String attemptId;
  final String response;
  final String? responseCode;
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
    required String attemptId,
    required String launchUri,
  }) =>
      _channel.invokeMethod<void>('launchPayment', {
        'attempt_id': attemptId,
        'launch_uri': launchUri,
      });

  Future<CieloPaymentCallback?> getPendingCallback() async {
    final value =
        await _channel.invokeMapMethod<Object?, Object?>('getPendingCallback');
    return value == null ? null : CieloPaymentCallback.fromMap(value);
  }

  Future<bool> acknowledgeCallback(String attemptId) async =>
      await _channel.invokeMethod<bool>(
        'acknowledgeCallback',
        {'attempt_id': attemptId},
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
