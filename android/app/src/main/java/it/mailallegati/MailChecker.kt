package it.mailallegati

import android.content.Context
import android.net.Uri
import androidx.documentfile.provider.DocumentFile
import com.sun.mail.imap.IMAPFolder
import java.util.Properties
import javax.mail.FetchProfile
import javax.mail.Flags
import javax.mail.Folder
import javax.mail.Multipart
import javax.mail.Part
import javax.mail.Session
import javax.mail.Store
import javax.mail.UIDFolder
import javax.mail.internet.InternetAddress
import javax.mail.internet.MimePart
import javax.mail.internet.MimeUtility

/**
 * Controlla la casella IMAP, filtra i mittenti scelti e salva gli allegati
 * nelle cartelle selezionate e (opzionale) sul NAS.
 */
class MailChecker(
    private val context: Context,
    private val s: Settings,
    private val log: (String) -> Unit
) {
    private fun connect(): Store {
        val proto = if (s.imapSsl) "imaps" else "imap"
        val props = Properties().apply {
            put("mail.store.protocol", proto)
            put("mail.$proto.host", s.imapServer)
            put("mail.$proto.port", s.imapPort.toString())
            put("mail.$proto.connectiontimeout", "20000")
            put("mail.$proto.timeout", "60000")
            put("mail.$proto.peek", (!s.markRead).toString())
            put("mail.$proto.partialfetch", "false")
            if (!s.imapSsl) put("mail.imap.starttls.enable", "true")
            put("mail.$proto.ssl.checkserveridentity", "true")
        }
        val session = Session.getInstance(props)
        val store = session.getStore(proto)
        store.connect(s.imapServer, s.imapPort, s.imapUser, s.imapPassword)
        return store
    }

    /** Prova la connessione: restituisce il numero di messaggi nella cartella. */
    fun testImap(): Int {
        val store = connect()
        try {
            val f = store.getFolder(s.imapFolder)
            if (!f.exists()) throw IllegalStateException("Cartella '${s.imapFolder}' non trovata")
            f.open(Folder.READ_ONLY)
            val n = f.messageCount
            f.close(false)
            return n
        } finally {
            store.close()
        }
    }

    /** Esegue un controllo. Restituisce il numero di allegati salvati. */
    fun check(): Int {
        val senders = Util.parseList(s.senders)
        if (s.imapServer.isBlank() || s.imapUser.isBlank())
            throw IllegalStateException("Configura server e utente email")
        if (senders.isEmpty()) throw IllegalStateException("Inserisci almeno un mittente")
        val folders = s.folders
        if (folders.isEmpty() && !s.nasEnabled)
            throw IllegalStateException("Scegli almeno una cartella o attiva il NAS")

        val exts = Util.parseExtensions(s.extensions)

        // prima di tutto prova a inviare al NAS i file rimasti in coda
        var nasDown = false
        if (s.nasEnabled && NasQueue.count(context) > 0) {
            nasDown = NasQueue.flush(context, s, log) > 0
        }

        val store = try {
            connect()
        } catch (e: Exception) {
            if (s.nasEnabled && NasQueue.count(context) > 0) NasQueue.scheduleRetry(context)
            throw e
        }
        var saved = 0
        var nas: NasUploader? = null
        try {
            val folder = store.getFolder(s.imapFolder) as IMAPFolder
            if (!folder.exists()) throw IllegalStateException("Cartella '${s.imapFolder}' non trovata")
            folder.open(if (s.markRead) Folder.READ_WRITE else Folder.READ_ONLY)
            try {
                val key = "${s.imapUser.lowercase()}@${s.imapServer.lowercase()}/${s.imapFolder}"
                val uv = folder.uidValidity
                if (s.stateKey != key || s.uidValidity != uv) {
                    s.stateKey = key; s.uidValidity = uv; s.lastUid = -1
                }
                if (s.lastUid < 0) {
                    if (s.processExisting) {
                        s.lastUid = 0
                        log("Primo avvio: elaboro anche le email già presenti")
                    } else {
                        var last = 0L
                        if (folder.messageCount > 0) last = folder.getUID(folder.getMessage(folder.messageCount))
                        s.lastUid = maxOf(last, folder.uidNext - 1)
                        log("Primo avvio: da ora in poi verranno elaborate solo le nuove email")
                        return 0
                    }
                }

                val start = s.lastUid + 1
                val msgs = folder.getMessagesByUID(start, UIDFolder.LASTUID)
                    .filterNotNull()
                if (msgs.isEmpty()) return 0
                val fp = FetchProfile().apply {
                    add(FetchProfile.Item.ENVELOPE)
                    add(UIDFolder.FetchProfileItem.UID)
                }
                folder.fetch(msgs.toTypedArray(), fp)
                val todo = msgs.map { folder.getUID(it) to it }
                    .filter { it.first >= start }
                    .sortedBy { it.first }

                for ((uid, m) in todo) {
                    val addrs = (m.from ?: emptyArray())
                        .mapNotNull { (it as? InternetAddress)?.address?.lowercase() }
                    val match = addrs.firstOrNull { Util.senderMatches(it, senders) }
                    if (match != null) {
                        val subject = m.subject ?: ""
                        val atts = mutableListOf<Pair<String, ByteArray>>()
                        collect(m, atts, exts)
                        if (atts.isEmpty()) {
                            log("Email da $match \"$subject\": nessun allegato")
                        } else {
                            val sub = mutableListOf<String>()
                            if (s.subPerSender) sub += Util.safeName(match)
                            if (s.subPerMonth) sub += Util.monthFolder()
                            for ((name, data) in atts) {
                                for (f in folders) {
                                    try {
                                        val where = saveToFolder(Uri.parse(f), sub, name, data)
                                        log("Salvato: $where")
                                    } catch (e: Exception) {
                                        log("ERRORE salvataggio $name: ${e.message}")
                                    }
                                }
                                if (s.nasEnabled) {
                                    var uploaded = false
                                    if (!nasDown) {
                                        try {
                                            if (nas == null) nas = NasUploader(s)
                                            log("Caricato su NAS: ${nas!!.upload(sub, name, data)}")
                                            uploaded = true
                                        } catch (e: Exception) {
                                            nasDown = true
                                            log("NAS non raggiungibile (${NasQueue.shortError(e)}): i file verranno inviati appena torna disponibile")
                                        }
                                    }
                                    if (!uploaded) {
                                        NasQueue.add(context, sub, name, data)
                                        log("In coda per il NAS: $name")
                                    }
                                }
                                saved++
                            }
                        }
                        if (s.markRead) m.setFlag(Flags.Flag.SEEN, true)
                    }
                    s.lastUid = uid
                }
            } finally {
                try { folder.close(false) } catch (_: Exception) {}
            }
        } finally {
            try { store.close() } catch (_: Exception) {}
            nas?.close()
            if (s.nasEnabled && NasQueue.count(context) > 0) NasQueue.scheduleRetry(context)
        }
        return saved
    }

    private fun collect(p: Part, out: MutableList<Pair<String, ByteArray>>, exts: List<String>) {
        if (p.isMimeType("multipart/*")) {
            val mp = p.content as Multipart
            for (i in 0 until mp.count) collect(mp.getBodyPart(i), out, exts)
            return
        }
        val isAttachment = Part.ATTACHMENT.equals(p.disposition, ignoreCase = true)
        var name = p.fileName?.let { try { MimeUtility.decodeText(it) } catch (_: Exception) { it } }
        if (name.isNullOrBlank()) {
            if (!isAttachment) return
            name = "allegato"
        }
        if (s.ignoreInline && !isAttachment && p is MimePart && p.contentID != null && p.isMimeType("image/*")) return
        val clean = Util.safeName(name ?: "allegato")
        if (exts.isNotEmpty() && Util.extOf(clean) !in exts) return
        val data = p.inputStream.use { it.readBytes() }
        out += clean to data
    }

    private fun saveToFolder(tree: Uri, sub: List<String>, name: String, data: ByteArray): String {
        var dir = DocumentFile.fromTreeUri(context, tree)
            ?: throw IllegalStateException("Cartella non accessibile, sceglila di nuovo")
        if (!dir.canWrite()) throw IllegalStateException("Permesso mancante sulla cartella, sceglila di nuovo")
        for (part in sub) {
            dir = dir.findFile(part)?.takeIf { it.isDirectory }
                ?: dir.createDirectory(part)
                ?: throw IllegalStateException("Impossibile creare la sottocartella $part")
        }
        val existing = dir.listFiles().mapNotNull { it.name }.toSet()
        val finalName = Util.uniqueName(name) { it in existing }
        val file = dir.createFile("application/octet-stream", finalName)
            ?: throw IllegalStateException("Impossibile creare il file")
        context.contentResolver.openOutputStream(file.uri)?.use { it.write(data) }
            ?: throw IllegalStateException("Impossibile scrivere il file")
        return (listOf(dir.name ?: "") + (file.name ?: finalName)).joinToString("/")
    }
}
