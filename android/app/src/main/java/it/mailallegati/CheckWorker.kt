package it.mailallegati

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.withContext
import java.util.concurrent.TimeUnit

/** Lavoro in background che controlla la posta (anche ad app chiusa). */
class CheckWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        if (!lock.tryLock()) return@withContext Result.success()
        val log = AppLog(applicationContext)
        try {
            val s = Settings(applicationContext)
            if (s.disclaimerAccepted < Settings.DISCLAIMER_VERSION) {
                log.add("Avvertenze non accettate: controllo non eseguito")
                return@withContext Result.success()
            }
            val checker = MailChecker(applicationContext, s, log::add)
            val n = checker.check()
            log.add(if (n > 0) "Controllo completato: $n allegati salvati" else "Controllo completato: nessun nuovo allegato")
            if (n > 0 && s.notify) {
                val names = checker.savedNames
                val title = if (names.size == 1) "Salvato 1 allegato" else "Salvati ${names.size} allegati"
                val text = names.take(4).joinToString("\n") + if (names.size > 4) "\n… e altri ${names.size - 4}" else ""
                notify(applicationContext, title, text)
            }
        } catch (e: Exception) {
            log.add("ERRORE: ${e.message ?: e.javaClass.simpleName}")
        } finally {
            lock.unlock()
        }
        Result.success()
    }

    companion object {
        private const val PERIODIC = "controllo_periodico"
        private const val ONCE = "controllo_singolo"
        private const val CHANNEL = "allegati"
        private val lock = Mutex()

        private val net = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()

        fun schedule(context: Context, minutes: Int) {
            val req = PeriodicWorkRequestBuilder<CheckWorker>(maxOf(15, minutes).toLong(), TimeUnit.MINUTES)
                .setConstraints(net)
                .build()
            WorkManager.getInstance(context)
                .enqueueUniquePeriodicWork(PERIODIC, ExistingPeriodicWorkPolicy.UPDATE, req)
        }

        fun cancel(context: Context) {
            WorkManager.getInstance(context).cancelUniqueWork(PERIODIC)
        }

        fun runNow(context: Context) {
            val req = OneTimeWorkRequestBuilder<CheckWorker>().setConstraints(net).build()
            WorkManager.getInstance(context).enqueueUniqueWork(ONCE, ExistingWorkPolicy.KEEP, req)
        }

        fun notify(context: Context, title: String, text: String) {
            if (Build.VERSION.SDK_INT >= 33 &&
                ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
            ) return
            val nm = context.getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL, "Allegati salvati", NotificationManager.IMPORTANCE_DEFAULT)
            )
            val pi = PendingIntent.getActivity(
                context, 0, Intent(context, MainActivity::class.java),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )
            val n = NotificationCompat.Builder(context, CHANNEL)
                .setSmallIcon(R.drawable.ic_notify)
                .setContentTitle(title)
                .setContentText(text.lineSequence().firstOrNull() ?: text)
                .setStyle(NotificationCompat.BigTextStyle().bigText(text))
                .setContentIntent(pi)
                .setAutoCancel(true)
                .build()
            NotificationManagerCompat.from(context).notify(1, n)
        }
    }
}
