package com.corepdv.pos

import android.app.Activity
import android.content.Intent
import android.os.Bundle

class CieloResponseActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (intent?.action == Intent.ACTION_VIEW && intent.data != null) {
            CieloPaymentBridge.deliverCallback(this, intent.data!!)
        }
        startActivity(Intent(this, MainActivity::class.java).addFlags(
            Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP,
        ))
        finish()
    }
}
