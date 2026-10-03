package com.corepdv.pos

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.util.Log

class CieloResponseActivity : Activity() {
    private companion object {
        const val logTag = "CieloResponseActivity"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (intent?.action == Intent.ACTION_VIEW && intent.data != null) {
            val uri: Uri = intent.data!!
            val queryNames = uri.queryParameterNames.sorted().joinToString(",")
            val response = CieloPaymentBridge.callbackParameter(uri, "response")
            val responseCode = CieloPaymentBridge.callbackParameter(uri, "responsecode")
            Log.i(
                logTag,
                "CIELO_CALLBACK_ACTIVITY action=${intent.action} scheme=${uri.scheme} host=${uri.host} query_names=$queryNames response_present=${!response.isNullOrEmpty()} response_length=${response?.length ?: 0} responsecode_present=${!responseCode.isNullOrEmpty()} active_operation_present=${CieloPaymentBridge.hasActiveAttempt(this)}",
            )
            CieloPaymentBridge.deliverCallback(this, uri)
        }
        startActivity(Intent(this, MainActivity::class.java).addFlags(
            Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP,
        ))
        finish()
    }
}
