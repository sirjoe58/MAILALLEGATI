package it.mailallegati

import android.content.Context
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object Util {
    fun parseList(text: String): List<String> =
        text.split('\n', ',', ';').map { it.trim() }.filter { it.isNotEmpty() }

    fun parseExtensions(text: String): List<String> =
        text.split('\n', ',', ';', ' ').map { it.trim().trimStart('.').lowercase() }.filter { it.isNotEmpty() }

    /** Restituisce true se l'indirizzo corrisponde a uno dei mittenti scelti. */
    fun senderMatches(address: String, senders: List<String>): Boolean {
        val a = address.lowercase().trim()
        for (raw in senders) {
            val s = raw.lowercase().trim()
            if (s.isEmpty()) continue
            when {
                s.startsWith("@") -> if (a.endsWith(s)) return true
                s.contains("@") -> if (a == s) return true
                else -> if (a.contains(s)) return true
            }
        }
        return false
    }

    fun safeName(name: String): String {
        var n = name.replace(Regex("[\\r\\n]"), "")
            .replace(Regex("[<>:\"/\\\\|?*#%\\x00-\\x1f]"), "_")
            .trim(' ', '.')
        if (n.isEmpty()) n = "allegato"
        if (n.length > 150) {
            val ext = extOf(n)
            n = n.take(150 - ext.length - 1) + if (ext.isNotEmpty()) ".$ext" else ""
        }
        return n
    }

    fun extOf(name: String): String =
        name.substringAfterLast('.', "").lowercase().takeIf { it.length in 1..8 } ?: ""

    /** "nome (1).pdf", "nome (2).pdf"... finche' il nome non e' libero */
    fun uniqueName(name: String, exists: (String) -> Boolean): String {
        if (!exists(name)) return name
        val ext = extOf(name)
        val base = if (ext.isNotEmpty()) name.dropLast(ext.length + 1) else name
        var i = 1
        while (true) {
            val c = if (ext.isNotEmpty()) "$base ($i).$ext" else "$base ($i)"
            if (!exists(c)) return c
            i++
        }
    }

    data class NasPath(val server: String, val port: Int, val segments: List<String>) {
        val display get() = "\\\\" + server + (if (port != 445) ":$port" else "") + "\\" + segments.joinToString("\\")
    }

    /** Accetta \\server\condivisa\sotto, //server/condivisa o smb://server/condivisa */
    fun parseNas(path: String): NasPath {
        var p = path.trim()
        if (p.lowercase().startsWith("smb://")) p = p.substring(6)
        p = p.replace('\\', '/').trim('/')
        val parts = p.split('/').filter { it.isNotEmpty() }
        if (parts.size < 2) throw IllegalArgumentException(
            "Percorso NAS non valido. Esempio: \\\\192.168.1.10\\condivisa\\allegati")
        var server = parts[0]
        var port = 445
        if (server.contains(':')) {
            port = server.substringAfterLast(':').toIntOrNull() ?: 445
            server = server.substringBeforeLast(':')
        }
        return NasPath(server, port, parts.drop(1))
    }

    fun monthFolder(): String = SimpleDateFormat("yyyy-MM", Locale.ITALY).format(Date())
}

/** Registro attivita' salvato su file, mostrato nell'app. */
class AppLog(context: Context) {
    private val file = File(context.filesDir, "registro.txt")
    private val fmt = SimpleDateFormat("dd/MM HH:mm:ss", Locale.ITALY)

    @Synchronized
    fun add(text: String) {
        try {
            if (file.exists() && file.length() > 300_000) {
                val keep = file.readLines().takeLast(500)
                file.writeText(keep.joinToString("\n") + "\n")
            }
            file.appendText("${fmt.format(Date())}  $text\n")
        } catch (_: Exception) {
        }
    }

    fun tail(lines: Int = 200): String = try {
        if (file.exists()) file.readLines().takeLast(lines).joinToString("\n") else ""
    } catch (_: Exception) {
        ""
    }

    fun clear() {
        file.delete()
    }
}
