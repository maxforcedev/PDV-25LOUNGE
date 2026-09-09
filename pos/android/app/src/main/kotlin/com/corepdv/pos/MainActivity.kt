package com.corepdv.pos

import android.media.AudioManager
import android.media.ToneGenerator
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private var scannerTone: ToneGenerator? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "core_pos/scanner_beep")
            .setMethodCallHandler { call, result ->
                if (call.method == "play") {
                    val tone = scannerTone ?: ToneGenerator(AudioManager.STREAM_MUSIC, 100)
                        .also { scannerTone = it }
                    tone.startTone(ToneGenerator.TONE_PROP_BEEP, 90)
                    result.success(null)
                } else {
                    result.notImplemented()
                }
            }
    }

    override fun onDestroy() {
        scannerTone?.release()
        scannerTone = null
        super.onDestroy()
    }
}
