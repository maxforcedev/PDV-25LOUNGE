package com.corepdv.pos

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.util.Log
import io.flutter.plugin.common.MethodChannel

object CieloPaymentBridge {
    private const val cieloPackage = "br.com.cielosmart.orderservice"
    private const val logTag = "CieloPaymentBridge"
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
                        appContext?.let { context ->
                            CieloPaymentForegroundService.stop(context)
                        }
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
        val uri = try {
            Uri.parse(launchUri)
        } catch (_: Exception) {
            result.error("cielo_launch_invalid", "O pedido de pagamento Cielo é inválido.", null)
            return
        }
        if (uri.scheme != "lio" || uri.host != "payment") {
            Log.w(logTag, "CIELO_LAUNCH_FAILED attempt_id=$attemptId code=cielo_launch_invalid")
            result.error("cielo_launch_invalid", "O pedido de pagamento Cielo é inválido.", null)
            return
        }
        val packageInstalled = try {
            context.packageManager.getApplicationInfo(cieloPackage, 0)
            true
        } catch (_: Exception) {
            false
        }
        if (!packageInstalled) {
            Log.i(logTag, "CIELO_LAUNCH attempt_id=$attemptId package=$cieloPackage scheme=${uri.scheme} host=${uri.host} activity_resolvable=false")
            Log.w(logTag, "CIELO_LAUNCH_FAILED attempt_id=$attemptId code=cielo_app_unavailable")
            result.error("cielo_app_unavailable", "O aplicativo Cielo não está instalado neste dispositivo.", null)
            return
        }
        val intent = Intent(Intent.ACTION_VIEW, uri)
            .setPackage(cieloPackage)
            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
        val resolvable = intent.resolveActivity(context.packageManager) != null
        Log.i(logTag, "CIELO_LAUNCH attempt_id=$attemptId package=$cieloPackage scheme=${uri.scheme} host=${uri.host} activity_resolvable=$resolvable")
        if (!resolvable) {
            Log.w(logTag, "CIELO_LAUNCH_FAILED attempt_id=$attemptId code=cielo_launch_unresolved")
            result.error("cielo_launch_unresolved", "O aplicativo Cielo instalado não aceita este pagamento.", null)
            return
        }
        try {
            activeAttemptId = attemptId
            CieloPaymentForegroundService.start(context)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
            result.success(null)
        } catch (error: Exception) {
            activeAttemptId = null
            runCatching { CieloPaymentForegroundService.stop(context) }
            Log.w(logTag, "CIELO_LAUNCH_FAILED attempt_id=$attemptId code=cielo_launch_failed exception=${error.javaClass.simpleName}")
            result.error(
                "cielo_launch_failed",
                "O Android não conseguiu iniciar o aplicativo Cielo.",
                mapOf(
                    "package" to cieloPackage,
                    "scheme" to uri.scheme,
                    "host" to uri.host,
                    "exception" to error.javaClass.simpleName,
                ),
            )
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
