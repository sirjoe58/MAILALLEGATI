package it.mailallegati

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * Coda dei file da inviare al NAS.
 * Se il NAS e' spento o irraggiungibile gli allegati restano qui (nella memoria dell'app)
 * e vengono inviati automaticamente appena il NAS torna raggiungibile.
 */
object NasQueue {
    private val seq = java.util.concurrent.atomic.AtomicInteger(0)
    private fun dir(ctx: Context) = File(ctx.filesDir, "coda_nas").apply { mkdirs() }

    @Synchronized
    fun add(ctx: Context, sub: List<String>, name: String, data: ByteArray) {
        val item = File(dir(ctx), "%013d_%06d_%s".format(
            System.currentTimeMillis(), seq.incrementAndGet() % 1_000_000, UUID.randomUUID().toString().take(4)))
        item.mkdirs()
        File(item, "dati.bin").writeBytes(data)
        File(item, "info.json").writeText(
            JSONObject().put("sub", JSONArray(sub)).put("name", name)
                .put("added", System.currentTimeMillis()).toString()
        )
    }

    private fun items(ctx: Context): List<File> =
        (dir(ctx).listFiles() ?: emptyArray())
            .filter { File(it, "info.json").exists() && File(it, "dati.bin").exists() }
            .sortedBy { it.name }

    fun count(ctx: Context): Int = items(ctx).size

    @Synchronized
    fun clear(ctx: Context) {
        dir(ctx).deleteRecursively()
    }

    /** Prova a inviare i file in coda. Restituisce quanti ne restano. */
    @Synchronized
    fun flush(ctx: Context, s: Settings, log: (String) -> Unit): Int {
        val list = items(ctx)
        if (list.isEmpty() || !s.nasEnabled || s.nasPath.isBlank()) return list.size
        var sent = 0
        val nas = try {
            NasUploader(s)
        } catch (e: Exception) {
            log("Percorso NAS non valido: ${e.message}")
            return list.size
        }
        nas.use { n ->
            for (item in list) {
                try {
                    val info = JSONObject(File(item, "info.json").readText())
                    val arr = info.optJSONArray("sub") ?: JSONArray()
                    val sub = (0 until arr.length()).map { arr.getString(it) }
                    val target = n.upload(sub, info.optString("name", "allegato"), File(item, "dati.bin").readBytes())
                    item.deleteRecursively()
                    sent++
                    log("Inviato al NAS dalla coda: $target")
                } catch (e: Exception) {
                    log("NAS ancora non raggiungibile (${shortError(e)}): ${list.size - sent} file in attesa")
                    break
                }
            }
        }
        val rest = count(ctx)
        if (sent > 0) log("Coda NAS: $sent file inviati" + if (rest > 0) ", $rest ancora in attesa" else ", coda vuota")
        return rest
    }

    fun shortError(e: Exception): String {
        val t = e.message ?: e.javaClass.simpleName
        return if (t.length < 120) t else t.take(117) + "..."
    }

    // ------------------------------------------------ nuovi tentativi automatici

    private const val RETRY = "invio_coda_nas"

    /**
     * Pianifica un nuovo tentativo: parte appena c'e' una rete e poi si ripete
     * a intervalli crescenti (1, 2, 3... minuti) finche' la coda non e' vuota.
     * In ogni caso anche il controllo periodico della posta riprova l'invio.
     */
    fun scheduleRetry(ctx: Context, delayMinutes: Long = 1) {
        val req = OneTimeWorkRequestBuilder<NasRetryWorker>()
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .setInitialDelay(delayMinutes, TimeUnit.MINUTES)
            .setBackoffCriteria(BackoffPolicy.LINEAR, 1, TimeUnit.MINUTES)
            .build()
        WorkManager.getInstance(ctx).enqueueUniqueWork(RETRY, ExistingWorkPolicy.KEEP, req)
    }

    fun retryNow(ctx: Context) {
        WorkManager.getInstance(ctx).cancelUniqueWork(RETRY)
        scheduleRetry(ctx, 0)
    }
}

class NasRetryWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val s = Settings(applicationContext)
        if (s.disclaimerAccepted < Settings.DISCLAIMER_VERSION || !s.nasEnabled) return@withContext Result.success()
        val log = AppLog(applicationContext)
        val rest = try {
            NasQueue.flush(applicationContext, s, log::add)
        } catch (e: Exception) {
            log.add("ERRORE coda NAS: ${NasQueue.shortError(e)}")
            NasQueue.count(applicationContext)
        }
        if (rest > 0) {
            // limite di sicurezza: dopo molti tentativi ci pensa il controllo periodico
            if (runAttemptCount >= 60) Result.success() else Result.retry()
        } else {
            Result.success()
        }
    }
}
