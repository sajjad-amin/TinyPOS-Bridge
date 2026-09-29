package com.sajjadamin.tinypos

import android.content.Intent
import android.os.Build
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private val channelName = "com.sajjadamin.tinypos/background_relay"

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channelName).setMethodCallHandler { call, result ->
            when (call.method) {
                "startKeepAlive" -> {
                    val title = call.argument<String>("title") ?: "TinyPOS Cloud Relay Active"
                    val message = call.argument<String>("message") ?: "Terminal online • Ready for thermal print jobs"
                    startForegroundService(title, message)
                    result.success(true)
                }
                "stopKeepAlive" -> {
                    stopForegroundService()
                    result.success(true)
                }
                "isKeepAliveActive" -> {
                    result.success(RelayForegroundService.isRunning)
                }
                else -> result.notImplemented()
            }
        }
    }

    private fun startForegroundService(title: String, message: String) {
        val intent = Intent(this, RelayForegroundService::class.java).apply {
            putExtra("title", title)
            putExtra("message", message)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
    }

    private fun stopForegroundService() {
        val intent = Intent(this, RelayForegroundService::class.java)
        stopService(intent)
    }
}
