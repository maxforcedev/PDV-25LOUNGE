package com.corepdv.pos

import android.content.Context
import android.content.Intent
import android.net.Uri
import io.flutter.plugin.common.MethodChannel

object CieloPaymentBridge {
    private const val cieloPackage = "com.ads.lio.uriappclient"
    private var channel: MethodChannel? = null
    private var appContext: Context? = null
    private var activeAttemptId: String? = null
    private var pendingCallback: Map<String, String?>? = null

    fun attach(context: Context, channel: MethodChannel) {
        appContext = context.applicationContext
        this.channel = channel
        channel.setMethodCallHandler { call, result ->
            when (call.method) {
                "launchPayment" -> launch(call.arguments as? Map<*, *>, result)
                "getPendingCallback" -> result.success(pendingCallback)
                "acknowledgeCallback" -> {
                    val attemptId = (call.arguments as? Map<*, *>)?.get("attempt_id") as? String
                    if (attemptId != null && pendingCallback?.get("attempt_id") == attemptId) {
                        pendingCallback = null
                        activeAttemptId = null
                        CieloPaymentForegroundService.stop(channel.context)
                    }
                    result.success(null)
                }
                else -> result.notImplemented()
            }
        }
    }

    private fun launch(arguments: Map<*, *>?, result: MethodChannel.Result) {
        val attemptId = arguments?.get("attempt_id") as? String
        val launchUri = arguments?.get("launch_uri") as? String
        if (attemptId.isNullOrBlank() || launchUri.isNullOrBlank()) {
            result.error("cielo_launch_invalid", "Dados de lançamento inválidos.", null)
            return
        }
        val context = appContext
        if (context == null) {
            result.error("cielo_launch_unavailable", "A ponte Cielo não está disponível.", null)
            return
        }
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(launchUri))
            .setPackage(cieloPackage)
            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
        if (intent.resolveActivity(context.packageManager) == null) {
            result.error("cielo_app_unavailable", "O aplicativo Cielo não está disponível.", null)
            return
        }
        activeAttemptId = attemptId
        CieloPaymentForegroundService.start(context)
        try {
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
            result.success(null)
        } catch (_: Exception) {
            activeAttemptId = null
            CieloPaymentForegroundService.stop(context)
            result.error("cielo_launch_failed", "Não foi possível abrir o aplicativo Cielo.", null)
        }
    }

    fun deliverCallback(context: Context, uri: Uri) {
        val attemptId = activeAttemptId ?: return
        pendingCallback = mapOf(
            "attempt_id" to attemptId,
            "response" to uri.getQueryParameter("response").orEmpty(),
            "responsecode" to uri.getQueryParameter("responsecode"),
        )
        channel?.invokeMethod("paymentCallback", pendingCallback)
    }
}
