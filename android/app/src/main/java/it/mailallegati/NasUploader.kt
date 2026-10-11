package it.mailallegati

import jcifs.CIFSContext
import jcifs.config.PropertyConfiguration
import jcifs.context.BaseContext
import jcifs.smb.NtlmPasswordAuthenticator
import jcifs.smb.SmbFile
import java.util.Properties

/** Carica file su una cartella condivisa del NAS (SMB, come le cartelle di rete di Windows). */
class NasUploader(s: Settings) : AutoCloseable {
    private val nas = Util.parseNas(s.nasPath)
    private val ctx: CIFSContext

    val display: String get() = nas.display

    init {
        val props = Properties().apply {
            setProperty("jcifs.smb.client.responseTimeout", "30000")
            setProperty("jcifs.smb.client.soTimeout", "35000")
            setProperty("jcifs.smb.client.connTimeout", "15000")
            setProperty("jcifs.resolveOrder", "DNS,BCAST")
            // compatibile anche con NAS vecchi (SMB1) e recenti (SMB3)
            setProperty("jcifs.smb.client.minVersion", "SMB1")
            setProperty("jcifs.smb.client.maxVersion", "SMB311")
        }
        val base = BaseContext(PropertyConfiguration(props))
        ctx = if (s.nasUser.isBlank()) {
            base.withGuestCrendentials()
        } else {
            base.withCredentials(
                NtlmPasswordAuthenticator(s.nasDomain.ifBlank { null }, s.nasUser, s.nasPassword)
            )
        }
    }

    private fun dirUrl(extra: List<String>): String {
        val host = if (nas.port != 445) "${nas.server}:${nas.port}" else nas.server
        val segs = nas.segments + extra
        return "smb://$host/" + segs.joinToString("") { "$it/" }
    }

    /** Verifica la connessione (crea la cartella se manca). Restituisce il numero di elementi. */
    fun test(): Int {
        SmbFile(dirUrl(emptyList()), ctx).use { d ->
            if (!d.exists()) d.mkdirs()
            return d.list().size
        }
    }

    /**
     * Carica il file e restituisce il percorso finale sul NAS.
     * Scrive prima un file temporaneo e poi lo rinomina: se il NAS cade a meta'
     * non resta un file incompleto con il nome giusto.
     */
    fun upload(subfolders: List<String>, name: String, data: ByteArray): String {
        val url = dirUrl(subfolders)
        SmbFile(url, ctx).use { d -> if (!d.exists()) d.mkdirs() }
        SmbFile(url + name + ".parziale", ctx).use { tmp ->
            tmp.openOutputStream().use { it.write(data) }
            val finalName = Util.uniqueName(name) { candidate ->
                SmbFile(url + candidate, ctx).use { it.exists() }
            }
            SmbFile(url + finalName, ctx).use { dest -> tmp.renameTo(dest) }
            return (nas.segments + subfolders + finalName).joinToString("\\", prefix = "\\\\${nas.server}\\")
        }
    }

    override fun close() {
        try {
            ctx.close()
        } catch (_: Exception) {
        }
    }
}
