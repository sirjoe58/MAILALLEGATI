package it.mailallegati

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings as AndroidSettings
import android.view.Gravity
import android.widget.CheckBox
import android.widget.EditText
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.documentfile.provider.DocumentFile
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.google.android.material.button.MaterialButton
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.materialswitch.MaterialSwitch
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : AppCompatActivity() {

    private lateinit var s: Settings
    private lateinit var appLog: AppLog
    private val folders = mutableListOf<String>()

    private fun et(id: Int) = findViewById<EditText>(id)
    private fun cb(id: Int) = findViewById<CheckBox>(id)
    private fun btn(id: Int) = findViewById<MaterialButton>(id)

    private val pickFolder = registerForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri ->
        if (uri != null) {
            contentResolver.takePersistableUriPermission(
                uri,
                Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION
            )
            val u = uri.toString()
            if (u !in folders) folders += u
            renderFolders()
            saveSettings(quiet = true)
        }
    }

    private val askNotify = registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        val root = findViewById<android.view.View>(R.id.root)
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val b = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.ime())
            v.setPadding(b.left, b.top, b.right, b.bottom)
            insets
        }

        s = Settings(this)
        appLog = AppLog(this)
        loadIntoUi()

        cb(R.id.imapSsl).setOnCheckedChangeListener { _, ssl ->
            val p = et(R.id.imapPort)
            if (p.text.toString() in listOf("", "993", "143")) p.setText(if (ssl) "993" else "143")
        }
        btn(R.id.btnAddFolder).setOnClickListener { pickFolder.launch(null) }
        btn(R.id.btnSave).setOnClickListener { saveSettings() }
        btn(R.id.btnTestImap).setOnClickListener { testImap() }
        btn(R.id.btnTestNas).setOnClickListener { testNas() }
        btn(R.id.btnCheckNow).setOnClickListener {
            saveSettings(quiet = true)
            CheckWorker.runNow(this)
            toast("Controllo avviato, guarda il registro")
        }
        btn(R.id.btnReset).setOnClickListener {
            MaterialAlertDialogBuilder(this)
                .setTitle("Ricomincia da capo")
                .setMessage("L'app dimenticherà quali email ha già visto. Al prossimo controllo si comporterà come al primo avvio.")
                .setPositiveButton("Sì") { _, _ -> s.resetState(); appLog.add("Stato azzerato"); refreshLog() }
                .setNegativeButton("Annulla", null)
                .show()
        }
        btn(R.id.btnBattery).setOnClickListener {
            try {
                startActivity(Intent(AndroidSettings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
            } catch (_: Exception) {
                toast("Apri Impostazioni › App › MailAllegati › Batteria › Senza restrizioni")
            }
        }
        btn(R.id.btnClearLog).setOnClickListener { appLog.clear(); refreshLog() }
        findViewById<MaterialSwitch>(R.id.monitor).setOnCheckedChangeListener { _, on ->
            if (on == s.monitorOn) return@setOnCheckedChangeListener
            saveSettings(quiet = true)
            s.monitorOn = on
            if (on) {
                CheckWorker.schedule(this, s.intervalMinutes)
                CheckWorker.runNow(this)
                appLog.add("Monitoraggio attivato (ogni ${s.intervalMinutes} minuti)")
            } else {
                CheckWorker.cancel(this)
                appLog.add("Monitoraggio disattivato")
            }
            refreshLog()
        }

        btn(R.id.btnDisclaimer).setOnClickListener { showDisclaimer(required = false) }
        btn(R.id.btnQueueSend).setOnClickListener {
            saveSettings(quiet = true)
            when {
                !s.nasEnabled -> toast("Attiva prima il caricamento sul NAS")
                NasQueue.count(this) == 0 -> toast("Nessun file in attesa")
                else -> {
                    NasQueue.retryNow(this)
                    toast("Invio avviato, guarda il registro")
                }
            }
        }
        btn(R.id.btnQueueClear).setOnClickListener {
            val n = NasQueue.count(this)
            if (n == 0) {
                toast("La coda è già vuota")
            } else {
                MaterialAlertDialogBuilder(this)
                    .setTitle("Svuota coda")
                    .setMessage("Eliminare $n file in attesa di invio al NAS?\nLe copie nelle cartelle del telefono NON vengono toccate.")
                    .setPositiveButton("Elimina") { _, _ ->
                        NasQueue.clear(this)
                        appLog.add("Coda NAS svuotata ($n file eliminati)")
                        refreshLog()
                    }
                    .setNegativeButton("Annulla", null)
                    .show()
            }
        }

        if (s.disclaimerAccepted < Settings.DISCLAIMER_VERSION) {
            showDisclaimer(required = true)
        } else if (Build.VERSION.SDK_INT >= 33) {
            askNotify.launch(Manifest.permission.POST_NOTIFICATIONS)
        }

        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                while (true) {
                    refreshLog()
                    delay(3000)
                }
            }
        }
    }

    override fun onPause() {
        super.onPause()
        saveSettings(quiet = true)
    }

    private fun loadIntoUi() {
        et(R.id.imapServer).setText(s.imapServer)
        et(R.id.imapPort).setText(s.imapPort.toString())
        cb(R.id.imapSsl).isChecked = s.imapSsl
        et(R.id.imapUser).setText(s.imapUser)
        et(R.id.imapPassword).setText(s.imapPassword)
        et(R.id.imapFolder).setText(s.imapFolder)
        et(R.id.senders).setText(s.senders)
        folders.clear(); folders += s.folders
        renderFolders()
        et(R.id.extensions).setText(s.extensions)
        cb(R.id.ignoreInline).isChecked = s.ignoreInline
        cb(R.id.subSender).isChecked = s.subPerSender
        cb(R.id.subMonth).isChecked = s.subPerMonth
        cb(R.id.markRead).isChecked = s.markRead
        cb(R.id.processExisting).isChecked = s.processExisting
        cb(R.id.nasEnabled).isChecked = s.nasEnabled
        et(R.id.nasPath).setText(s.nasPath)
        et(R.id.nasUser).setText(s.nasUser)
        et(R.id.nasPassword).setText(s.nasPassword)
        et(R.id.nasDomain).setText(s.nasDomain)
        et(R.id.interval).setText(s.intervalMinutes.toString())
        cb(R.id.notify).isChecked = s.notify
        findViewById<MaterialSwitch>(R.id.monitor).isChecked = s.monitorOn
    }

    private fun saveSettings(quiet: Boolean = false) {
        val oldInterval = s.intervalMinutes
        s.imapServer = et(R.id.imapServer).text.toString()
        s.imapPort = et(R.id.imapPort).text.toString().toIntOrNull()
            ?: if (cb(R.id.imapSsl).isChecked) 993 else 143
        s.imapSsl = cb(R.id.imapSsl).isChecked
        s.imapUser = et(R.id.imapUser).text.toString()
        s.imapPassword = et(R.id.imapPassword).text.toString()
        s.imapFolder = et(R.id.imapFolder).text.toString()
        s.senders = et(R.id.senders).text.toString()
        s.folders = folders.toList()
        s.extensions = et(R.id.extensions).text.toString()
        s.ignoreInline = cb(R.id.ignoreInline).isChecked
        s.subPerSender = cb(R.id.subSender).isChecked
        s.subPerMonth = cb(R.id.subMonth).isChecked
        s.markRead = cb(R.id.markRead).isChecked
        s.processExisting = cb(R.id.processExisting).isChecked
        s.nasEnabled = cb(R.id.nasEnabled).isChecked
        s.nasPath = et(R.id.nasPath).text.toString()
        s.nasUser = et(R.id.nasUser).text.toString()
        s.nasPassword = et(R.id.nasPassword).text.toString()
        s.nasDomain = et(R.id.nasDomain).text.toString()
        val iv = maxOf(15, et(R.id.interval).text.toString().toIntOrNull() ?: 15)
        s.intervalMinutes = iv
        s.notify = cb(R.id.notify).isChecked
        if (s.monitorOn && iv != oldInterval) CheckWorker.schedule(this, iv)
        if (!quiet) {
            et(R.id.interval).setText(iv.toString())
            toast("Impostazioni salvate")
        }
    }

    private fun renderFolders() {
        val list = findViewById<LinearLayout>(R.id.folderList)
        list.removeAllViews()
        if (folders.isEmpty()) {
            list.addView(TextView(this).apply {
                text = "Nessuna cartella scelta"
                setPadding(0, 12, 0, 12)
            })
        }
        for (u in folders.toList()) {
            val name = try {
                DocumentFile.fromTreeUri(this, Uri.parse(u))?.name
            } catch (_: Exception) { null } ?: Uri.decode(u.substringAfterLast("/"))
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
            }
            row.addView(TextView(this).apply {
                text = "📁  " + Uri.decode(Uri.parse(u).lastPathSegment ?: name).ifBlank { name }
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                setPadding(0, 12, 0, 12)
            })
            row.addView(ImageButton(this).apply {
                setImageResource(android.R.drawable.ic_menu_delete)
                background = null
                contentDescription = "Rimuovi"
                setOnClickListener {
                    folders.remove(u)
                    try {
                        contentResolver.releasePersistableUriPermission(
                            Uri.parse(u),
                            Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                        )
                    } catch (_: Exception) {}
                    renderFolders()
                    saveSettings(quiet = true)
                }
            })
            list.addView(row)
        }
    }

    private fun testImap() {
        saveSettings(quiet = true)
        lifecycleScope.launch {
            val msg = withContext(Dispatchers.IO) {
                try {
                    val n = MailChecker(this@MainActivity, s) {}.testImap()
                    "Connessione riuscita: $n messaggi in '${s.imapFolder}'"
                } catch (e: Exception) {
                    "Connessione fallita: ${e.message ?: e.javaClass.simpleName}"
                }
            }
            appLog.add(msg); refreshLog()
            dialog("Email", msg)
        }
    }

    private fun testNas() {
        saveSettings(quiet = true)
        lifecycleScope.launch {
            val msg = withContext(Dispatchers.IO) {
                try {
                    NasUploader(s).use { n ->
                        val c = n.test()
                        "NAS raggiungibile: ${n.display} ($c elementi)"
                    }
                } catch (e: Exception) {
                    "NAS non raggiungibile: ${e.message ?: e.javaClass.simpleName}"
                }
            }
            appLog.add(msg); refreshLog()
            dialog("NAS", msg)
        }
    }

    private fun disclaimerText(): String = try {
        resources.openRawResource(R.raw.avvertenze).bufferedReader(Charsets.UTF_8)
            .use { it.readText() }.removePrefix("\uFEFF")
    } catch (e: Exception) {
        "Testo delle avvertenze non disponibile."
    }

    /**
     * Mostra le avvertenze. Con required=true l'app non prosegue finché
     * l'utente non scorre fino in fondo, spunta la casella e accetta.
     */
    private fun showDisclaimer(required: Boolean) {
        val dp = resources.displayMetrics.density
        val pad = (20 * dp).toInt()
        val textView = TextView(this).apply {
            text = disclaimerText()
            textSize = 13f
            setTextIsSelectable(true)
            setPadding(pad, pad / 2, pad, pad / 2)
        }
        val scroll = ScrollView(this).apply {
            addView(textView)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                (resources.displayMetrics.heightPixels * 0.55).toInt()
            )
        }
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(scroll)
        }
        val builder = MaterialAlertDialogBuilder(this)
            .setTitle("Avvertenze e condizioni d'uso")
            .setView(box)

        if (!required) {
            builder.setPositiveButton("Chiudi", null).show()
            return
        }

        val check = CheckBox(this).apply {
            text = "Ho letto e accetto integralmente avvertenze, condizioni d'uso e limitazioni di responsabilità"
            isEnabled = false
            setPadding(0, (8 * dp).toInt(), 0, 0)
        }
        val hint = TextView(this).apply {
            text = "Scorri il testo fino in fondo per poter accettare."
            textSize = 12f
            setPadding(pad, 0, pad, 0)
        }
        box.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad / 2, 0, pad, 0)
            addView(check)
        })
        box.addView(hint)

        val dialog = builder
            .setCancelable(false)
            .setPositiveButton("Accetto e proseguo") { _, _ ->
                s.disclaimerAccepted = Settings.DISCLAIMER_VERSION
                appLog.add("Avvertenze accettate")
                refreshLog()
                if (Build.VERSION.SDK_INT >= 33) askNotify.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
            .setNegativeButton("Non accetto (esci)") { _, _ ->
                CheckWorker.cancel(this)
                s.monitorOn = false
                finishAffinity()
            }
            .create()
        dialog.setCanceledOnTouchOutside(false)
        dialog.show()
        val ok = dialog.getButton(android.content.DialogInterface.BUTTON_POSITIVE)
        ok.isEnabled = false
        check.setOnCheckedChangeListener { _, c -> ok.isEnabled = c }

        fun unlockIfAtEnd() {
            if (!check.isEnabled && !scroll.canScrollVertically(1)) {
                check.isEnabled = true
                hint.visibility = android.view.View.GONE
            }
        }
        scroll.setOnScrollChangeListener { _, _, _, _, _ -> unlockIfAtEnd() }
        scroll.post { unlockIfAtEnd() }
    }

    private fun refreshLog() {
        findViewById<TextView>(R.id.log).text = appLog.tail(150).ifBlank { "(vuoto)" }
        val q = try { NasQueue.count(this) } catch (_: Exception) { 0 }
        findViewById<TextView>(R.id.queueInfo).text =
            if (q > 0) "File in attesa di invio al NAS: $q" else "Nessun file in attesa per il NAS"
    }

    private fun dialog(title: String, msg: String) {
        MaterialAlertDialogBuilder(this).setTitle(title).setMessage(msg)
            .setPositiveButton("OK", null).show()
    }

    private fun toast(t: String) = Toast.makeText(this, t, Toast.LENGTH_LONG).show()
}
