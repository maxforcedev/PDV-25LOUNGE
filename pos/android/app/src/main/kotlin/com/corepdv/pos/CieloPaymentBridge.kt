package com.corepdv.pos

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.util.Log
import io.flutter.plugin.common.MethodChannel

object CieloPaymentBridge {
    private const val cieloPackage = "br.com.cielosmart.orderservice"
    private const val logTag = "CieloPaymentBridge"
    private const val preferencesName = "cielo_payment_bridge"
    private const val activeAttemptPreference = "active_attempt_id"
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
                "getPendingCallback" -> {
                    Log.i(logTag, "CIELO_CALLBACK_PENDING present=${pendingCallback != null}")
                    result.success(pendingCallback)
                }
                "acknowledgeCallback" -> {
                    val attemptId = (call.arguments as? Map<*, *>)?.get("attempt_id") as? String
                    var cleared = false
                    if (attemptId != null && pendingCallback?.get("attempt_id") == attemptId) {
                        pendingCallback = null
                        clearActiveAttempt(appContext)
                        appContext?.let { context ->
                            CieloPaymentForegroundService.stop(context)
                        }
                        cleared = true
                        Log.i(logTag, "CIELO_CALLBACK_ACK attempt_id=$attemptId cleared=true")
                    } else {
                        Log.w(logTag, "CIELO_CALLBACK_ACK attempt_id=${attemptId ?: "missing"} cleared=false")
                    }
                    result.success(cleared)
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
            setActiveAttempt(context, attemptId)
            CieloPaymentForegroundService.start(context)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
            result.success(null)
        } catch (error: Exception) {
            clearActiveAttempt(context)
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
        val attemptId = activeAttempt(context)
        val response = callbackParameter(uri, "response").orEmpty()
        val responseCode = callbackParameter(uri, "responsecode")
        Log.i(
            logTag,
            "CIELO_CALLBACK_RECEIVED attempt_present=${attemptId != null} response_present=${response.isNotEmpty()} response_length=${response.length} responsecode_present=${!responseCode.isNullOrEmpty()}",
        )
        if (attemptId == null) {
            Log.w(logTag, "CIELO_CALLBACK_UNASSOCIATED")
            return
        }
        if (pendingCallback != null) {
            Log.w(logTag, "CIELO_CALLBACK_DUPLICATE attempt_id=$attemptId")
            return
        }
        pendingCallback = mapOf(
            "attempt_id" to attemptId,
            "response" to response,
            "responsecode" to responseCode,
        )
        Log.i(logTag, "CIELO_CALLBACK_PENDING_CREATED attempt_id=$attemptId")
        val callbackChannel = channel
        if (callbackChannel == null) {
            Log.w(logTag, "CIELO_CALLBACK_CHANNEL unavailable=true")
            return
        }
        runCatching {
            callbackChannel.invokeMethod("paymentCallback", pendingCallback)
        }.onSuccess {
            Log.i(logTag, "CIELO_CALLBACK_CHANNEL dispatched=true attempt_id=$attemptId")
        }.onFailure { error ->
            Log.w(logTag, "CIELO_CALLBACK_CHANNEL dispatched=false exception=${error.javaClass.simpleName}")
        }
    }

    fun hasActiveAttempt(context: Context): Boolean = activeAttempt(context) != null

    fun callbackParameter(uri: Uri, name: String): String? {
        val query = uri.encodedQuery ?: return null
        for (entry in query.split("&")) {
            val separator = entry.indexOf('=')
            val encodedName = if (separator < 0) entry else entry.substring(0, separator)
            if (Uri.decode(encodedName) != name) continue
            val encodedValue = if (separator < 0) "" else entry.substring(separator + 1)
            // Uri.decode preserves literal '+', unlike form-style query decoding.
            return Uri.decode(encodedValue)
        }
        return null
    }

    private fun activeAttempt(context: Context?): String? {
        val inMemory = activeAttemptId
        if (inMemory != null) return inMemory
        val persisted = context?.applicationContext
            ?.getSharedPreferences(preferencesName, Context.MODE_PRIVATE)
            ?.getString(activeAttemptPreference, null)
        activeAttemptId = persisted
        return persisted
    }

    private fun setActiveAttempt(context: Context, attemptId: String) {
        activeAttemptId = attemptId
        context.getSharedPreferences(preferencesName, Context.MODE_PRIVATE)
            .edit()
            .putString(activeAttemptPreference, attemptId)
            .apply()
    }

    private fun clearActiveAttempt(context: Context?) {
        activeAttemptId = null
        context?.applicationContext
            ?.getSharedPreferences(preferencesName, Context.MODE_PRIVATE)
            ?.edit()
            ?.remove(activeAttemptPreference)
            ?.apply()
    }
}
