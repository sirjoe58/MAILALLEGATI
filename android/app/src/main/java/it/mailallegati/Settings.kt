package it.mailallegati

import android.content.Context
import android.content.SharedPreferences
import androidx.core.content.edit
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKeys
import org.json.JSONArray

/** Impostazioni dell'app. Le password sono salvate cifrate. */
class Settings(context: Context) {
    companion object {
        const val DISCLAIMER_VERSION = 1
    }

    private val p: SharedPreferences =
        context.getSharedPreferences("config", Context.MODE_PRIVATE)

    private val secret: SharedPreferences = try {
        EncryptedSharedPreferences.create(
            "segreti",
            MasterKeys.getOrCreate(MasterKeys.AES256_GCM_SPEC),
            context,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    } catch (e: Exception) {
        context.getSharedPreferences("segreti_semplici", Context.MODE_PRIVATE)
    }

    private fun str(k: String, d: String = "") = p.getString(k, d) ?: d
    private fun setStr(k: String, v: String) = p.edit { putString(k, v) }
    private fun bool(k: String, d: Boolean) = p.getBoolean(k, d)
    private fun setBool(k: String, v: Boolean) = p.edit { putBoolean(k, v) }

    var imapServer: String get() = str("imap_server"); set(v) = setStr("imap_server", v.trim())
    var imapPort: Int get() = p.getInt("imap_port", 993); set(v) = p.edit { putInt("imap_port", v) }
    var imapSsl: Boolean get() = bool("imap_ssl", true); set(v) = setBool("imap_ssl", v)
    var imapUser: String get() = str("imap_user"); set(v) = setStr("imap_user", v.trim())
    var imapFolder: String get() = str("imap_folder", "INBOX").ifBlank { "INBOX" }; set(v) = setStr("imap_folder", v.trim())
    var imapPassword: String
        get() = secret.getString("imap_password", "") ?: ""
        set(v) = secret.edit { putString("imap_password", v) }

    /** Un mittente per riga: indirizzo completo oppure @dominio.it */
    var senders: String get() = str("senders"); set(v) = setStr("senders", v)

    /** Cartelle di destinazione (URI di cartelle scelte dall'utente) */
    var folders: List<String>
        get() {
            val arr = JSONArray(str("folders", "[]"))
            return (0 until arr.length()).map { arr.getString(it) }
        }
        set(v) = setStr("folders", JSONArray(v).toString())

    var extensions: String get() = str("extensions"); set(v) = setStr("extensions", v.trim())
    var ignoreInline: Boolean get() = bool("ignore_inline", true); set(v) = setBool("ignore_inline", v)
    var subPerSender: Boolean get() = bool("sub_sender", false); set(v) = setBool("sub_sender", v)
    var subPerMonth: Boolean get() = bool("sub_month", false); set(v) = setBool("sub_month", v)
    var markRead: Boolean get() = bool("mark_read", false); set(v) = setBool("mark_read", v)
    var processExisting: Boolean get() = bool("process_existing", false); set(v) = setBool("process_existing", v)
    var notify: Boolean get() = bool("notify", true); set(v) = setBool("notify", v)

    var nasEnabled: Boolean get() = bool("nas_enabled", false); set(v) = setBool("nas_enabled", v)
    var nasPath: String get() = str("nas_path"); set(v) = setStr("nas_path", v.trim())
    var nasUser: String get() = str("nas_user"); set(v) = setStr("nas_user", v.trim())
    var nasDomain: String get() = str("nas_domain"); set(v) = setStr("nas_domain", v.trim())
    var nasPassword: String
        get() = secret.getString("nas_password", "") ?: ""
        set(v) = secret.edit { putString("nas_password", v) }

    var intervalMinutes: Int get() = p.getInt("interval", 15); set(v) = p.edit { putInt("interval", v) }
    var monitorOn: Boolean get() = bool("monitor_on", false); set(v) = setBool("monitor_on", v)

    /** Versione delle avvertenze accettate (0 = mai accettate) */
    var disclaimerAccepted: Int get() = p.getInt("disclaimer_accepted", 0); set(v) = p.edit { putInt("disclaimer_accepted", v) }

    // ---- stato: quali email sono gia' state viste
    var stateKey: String get() = str("state_key"); set(v) = setStr("state_key", v)
    var uidValidity: Long get() = p.getLong("uid_validity", -1); set(v) = p.edit { putLong("uid_validity", v) }
    var lastUid: Long get() = p.getLong("last_uid", -1); set(v) = p.edit { putLong("last_uid", v) }

    fun resetState() = p.edit { remove("state_key"); remove("uid_validity"); remove("last_uid") }
}
