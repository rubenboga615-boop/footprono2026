package com.footprono.footprono

import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity

class MainActivity : FlutterActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Canal des notifications push (paris réglés, montantes) : son et bannière.
        // Même identifiant que le serveur (notifications/push.py, ANDROID_CHANNEL).
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                "footprono",
                "Paris et montantes",
                NotificationManager.IMPORTANCE_HIGH,
            )
            channel.description = "Pari réglé, palier de montante, score corrigé"
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }
}
