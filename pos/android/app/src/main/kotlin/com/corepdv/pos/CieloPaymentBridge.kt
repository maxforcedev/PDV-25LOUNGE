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
    private const val activeOperationTypePreference = "active_operation_type"
    private const val activeOperationIdPreference = "active_operation_id"
    private var channel: MethodChannel? = null
    private var appContext: Context? = null
    private var activeOperation: ActiveOperation? = null
    private var pendingCallback: Map<String, String?>? = null

    private data class ActiveOperation(val type: String, val id: String)

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
                    val arguments = call.arguments as? Map<*, *>
                    val operationType = arguments?.get("operation") as? String ?: "payment"
                    val operationId = arguments?.get("operation_id") as? String
                        ?: arguments?.get("attempt_id") as? String
                    var cleared = false
                    if (operationId != null &&
                        pendingCallback?.get("operation") == operationType &&
                        pendingCallback?.get("operation_id") == operationId
                    ) {
                        pendingCallback = null
                        clearActiveOperation(appContext)
                        appContext?.let { context ->
                            CieloPaymentForegroundService.stop(context)
                        }
                        cleared = true
                        Log.i(logTag, "CIELO_CALLBACK_ACK operation=$operationType operation_id=$operationId cleared=true")
                    } else {
                        Log.w(logTag, "CIELO_CALLBACK_ACK operation=$operationType operation_id=${operationId ?: "missing"} cleared=false")
                    }
                    result.success(cleared)
                }
                else -> result.notImplemented()
            }
        }
    }

    private fun launch(arguments: Map<*, *>?, result: MethodChannel.Result) {
        val operationType = arguments?.get("operation") as? String ?: "payment"
        val operationId = arguments?.get("operation_id") as? String
            ?: arguments?.get("attempt_id") as? String
        val launchUri = arguments?.get("launch_uri") as? String
        if (operationId.isNullOrBlank() || launchUri.isNullOrBlank()) {
            result.error("cielo_launch_invalid", "Dados de lançamento inválidos.", null)
            return
        }
        val expectedHost = when (operationType) {
            "payment" -> "payment"
            "reversal" -> "payment-reversal"
            else -> null
        }
        if (expectedHost == null) {
            result.error("cielo_launch_invalid", "A operação Cielo é inválida.", null)
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
        if (uri.scheme != "lio" || uri.host != expectedHost) {
            Log.w(logTag, "CIELO_LAUNCH_FAILED operation=$operationType operation_id=$operationId code=cielo_launch_invalid")
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
            Log.i(logTag, "CIELO_LAUNCH operation=$operationType operation_id=$operationId package=$cieloPackage scheme=${uri.scheme} host=${uri.host} activity_resolvable=false")
            Log.w(logTag, "CIELO_LAUNCH_FAILED operation=$operationType operation_id=$operationId code=cielo_app_unavailable")
            result.error("cielo_app_unavailable", "O aplicativo Cielo não está instalado neste dispositivo.", null)
            return
        }
        val intent = Intent(Intent.ACTION_VIEW, uri)
            .setPackage(cieloPackage)
            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
        val resolvable = intent.resolveActivity(context.packageManager) != null
        Log.i(logTag, "CIELO_LAUNCH operation=$operationType operation_id=$operationId package=$cieloPackage scheme=${uri.scheme} host=${uri.host} activity_resolvable=$resolvable")
        if (!resolvable) {
            Log.w(logTag, "CIELO_LAUNCH_FAILED operation=$operationType operation_id=$operationId code=cielo_launch_unresolved")
            result.error("cielo_launch_unresolved", "O aplicativo Cielo instalado não aceita este pagamento.", null)
            return
        }
        try {
            setActiveOperation(context, ActiveOperation(operationType, operationId))
            CieloPaymentForegroundService.start(context)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
            result.success(null)
        } catch (error: Exception) {
            clearActiveOperation(context)
            runCatching { CieloPaymentForegroundService.stop(context) }
            Log.w(logTag, "CIELO_LAUNCH_FAILED operation=$operationType operation_id=$operationId code=cielo_launch_failed exception=${error.javaClass.simpleName}")
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
        val operation = activeOperation(context)
        val response = callbackParameter(uri, "response").orEmpty()
        val responseCode = callbackParameter(uri, "responsecode")
        Log.i(
            logTag,
            "CIELO_CALLBACK_RECEIVED operation=${operation?.type ?: "missing"} operation_present=${operation != null} response_present=${response.isNotEmpty()} response_length=${response.length} responsecode_present=${!responseCode.isNullOrEmpty()}",
        )
        if (operation == null) {
            Log.w(logTag, "CIELO_CALLBACK_UNASSOCIATED")
            return
        }
        val expectedCallbackHost = if (operation.type == "reversal") {
            "cielo-payment-reversal-response"
        } else {
            "cielo-payment-response"
        }
        if (uri.host != expectedCallbackHost) {
            Log.w(logTag, "CIELO_CALLBACK_HOST_MISMATCH operation=${operation.type} operation_id=${operation.id}")
            return
        }
        if (pendingCallback != null) {
            if (pendingCallback?.get("operation") == operation.type &&
                pendingCallback?.get("operation_id") == operation.id
            ) {
                Log.w(logTag, "CIELO_CALLBACK_DUPLICATE operation=${operation.type} operation_id=${operation.id}")
                return
            }
            Log.w(logTag, "CIELO_CALLBACK_STALE_REPLACED operation=${operation.type} operation_id=${operation.id}")
            pendingCallback = null
        }
        pendingCallback = mapOf(
            "operation" to operation.type,
            "operation_id" to operation.id,
            // Kept for payment-only Flutter clients during the bridge rollout.
            "attempt_id" to if (operation.type == "payment") operation.id else null,
            "response" to response,
            "responsecode" to responseCode,
        )
        Log.i(logTag, "CIELO_CALLBACK_PENDING_CREATED operation=${operation.type} operation_id=${operation.id}")
        val callbackChannel = channel
        if (callbackChannel == null) {
            Log.w(logTag, "CIELO_CALLBACK_CHANNEL unavailable=true")
            return
        }
        runCatching {
            callbackChannel.invokeMethod("paymentCallback", pendingCallback)
        }.onSuccess {
            Log.i(logTag, "CIELO_CALLBACK_CHANNEL dispatched=true operation=${operation.type} operation_id=${operation.id}")
        }.onFailure { error ->
            Log.w(logTag, "CIELO_CALLBACK_CHANNEL dispatched=false exception=${error.javaClass.simpleName}")
        }
    }

    fun hasActiveAttempt(context: Context): Boolean = activeOperation(context) != null

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

    private fun activeOperation(context: Context?): ActiveOperation? {
        activeOperation?.let { return it }
        val preferences = context?.applicationContext
            ?.getSharedPreferences(preferencesName, Context.MODE_PRIVATE)
            ?: return null
        val type = preferences.getString(activeOperationTypePreference, null)
        val id = preferences.getString(activeOperationIdPreference, null)
        if (!type.isNullOrBlank() && !id.isNullOrBlank()) {
            return ActiveOperation(type, id).also { activeOperation = it }
        }
        // Migrate a payment launch started by an older POS build in place.
        val legacyAttemptId = preferences.getString(activeAttemptPreference, null)
        return legacyAttemptId?.takeIf { it.isNotBlank() }
            ?.let { ActiveOperation("payment", it) }
            ?.also { activeOperation = it }
    }

    private fun setActiveOperation(context: Context, operation: ActiveOperation) {
        activeOperation = operation
        context.getSharedPreferences(preferencesName, Context.MODE_PRIVATE)
            .edit()
            .putString(activeOperationTypePreference, operation.type)
            .putString(activeOperationIdPreference, operation.id)
            .remove(activeAttemptPreference)
            .apply()
    }

    private fun clearActiveOperation(context: Context?) {
        activeOperation = null
        context?.applicationContext
            ?.getSharedPreferences(preferencesName, Context.MODE_PRIVATE)
            ?.edit()
            ?.remove(activeAttemptPreference)
            ?.remove(activeOperationTypePreference)
            ?.remove(activeOperationIdPreference)
            ?.apply()
    }
}
