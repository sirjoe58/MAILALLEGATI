# MailAllegati

**Salva automaticamente gli allegati delle email** dei mittenti che scegli in una o più cartelle e, se vuoi, anche sul **NAS** di casa (FRITZ!Box, Synology, QNAP… qualsiasi cartella di rete Windows/SMB).
Gratuito e open source, per **Windows** e **Android**. Interfaccia in italiano.

## Funzioni principali
- Controlla la casella email (IMAP) a intervalli regolari, anche in background.
- Filtra per **mittente** (indirizzo o dominio) e per **parole nell'oggetto** (es. `fattura, bolletta`).
- Salva gli allegati in **più cartelle** e li **rinomina** con data e mittente: `2026-10-12_Enel_FT_000123.pdf`.
- Copia sul **NAS**; se il NAS è spento li mette in **coda** e li invia appena torna raggiungibile.
- **Niente doppioni**, **notifiche**, icona accanto all'orologio di Windows, avvio con Windows.
- Password custodite nella Gestione credenziali di Windows / cifrate su Android.

## Download
Vai su **[Releases](../../releases/latest)** e scarica:
- **Windows:** `MailAllegati-Setup.exe` (installazione) oppure `MailAllegati-portatile.exe` (senza installazione).
  Windows potrebbe mostrare «PC protetto da Windows» perché il programma non è firmato: *Ulteriori informazioni › Esegui comunque*.
- **Android:** `MailAllegati-Android.apk` (consenti l'installazione da origini sconosciute quando richiesto).

> **Avvertenze** – Prima del primo utilizzo il programma mostra `LEGGIMI_AVVERTENZE.txt` (modalità d'uso, divieto di uso illecito, esclusione di garanzia e limitazione di responsabilità) e non prosegue senza accettazione. Usalo solo su caselle e dispositivi tuoi o per cui sei autorizzato.

## Configurazione (uguale su Windows e Android)

### Casella email (IMAP)
| Provider | Server | Porta |
|---|---|---|
| Aruba | imaps.aruba.it | 993 |
| Libero | imapmail.libero.it | 993 |
| Tiscali | imap.tiscali.it | 993 |
| Altri | vedi le impostazioni IMAP del tuo provider | 993 |

Utente = indirizzo email completo, password = quella dell'email.

### Mittenti
Uno per riga:
- `fatture@ditta.it` → solo quell'indirizzo
- `@ditta.it` → tutti gli indirizzi di quel dominio

### Cartelle di destinazione
Aggiungi una o più cartelle: ogni allegato viene salvato in **tutte**.
Opzioni: solo certi tipi di file (es. `pdf, xml`), sottocartella per mittente, sottocartella per mese, segna come lette.
Se un file con lo stesso nome esiste già, viene salvato come `nome (1).pdf`.

### Altre opzioni
- **Nomi chiari:** i file vengono rinominati con data e mittente, es. `FT_000123.pdf` → `2026-10-12_Enel_FT_000123.pdf`. Il modello si cambia in *Cartelle di destinazione* (`{data}`, `{mittente}`, `{nome}`, `{oggetto}`).
- **Filtro sull'oggetto:** in *Email e mittenti* puoi indicare parole come `fattura, bolletta`: vengono salvati solo gli allegati delle email il cui oggetto ne contiene almeno una.
- **Niente doppioni:** un file identico a uno già salvato non viene salvato di nuovo.
- **Windows – icona accanto all'orologio:** chiudendo la finestra il programma continua a lavorare; doppio clic sull'icona per riaprirlo, tasto destro per *Controlla ora* o *Esci*.
- **Notifiche:** quando vengono salvati allegati compare una notifica con i nomi dei file (Windows e Android).

### NAS
- Indirizzo: `\\192.168.1.10\condivisa\allegati` (si accetta anche `smb://192.168.1.10/condivisa/allegati`)
- Utente e password dell'utente NAS (vuoto = accesso ospite)
- Premi **Prova connessione NAS**: se la sottocartella non esiste viene creata.
- Su Android il telefono deve essere sulla stessa rete Wi-Fi del NAS (o in VPN).
- **NAS spento o irraggiungibile:** gli allegati vengono messi in **coda** e inviati da soli appena il NAS torna raggiungibile, nello stesso ordine in cui sono arrivati. La coda sopravvive anche al riavvio del PC o del telefono.
  - **Windows:** riprova ogni N minuti (impostabile, predefinito 2) finché il programma è aperto, e comunque a ogni controllo della posta.
  - **Android:** riprova appena c'è una rete, poi a intervalli crescenti (1, 2, 3… minuti), e comunque a ogni controllo periodico della posta.
  - Il numero di file in attesa è visibile nella sezione NAS, con i pulsanti **Invia ora al NAS** e **Svuota coda**.
  - I file vengono caricati prima con un nome temporaneo (`.parziale`) e poi rinominati: se il NAS si spegne durante l'invio non restano file incompleti con il nome definitivo.

### Primo avvio
Di default l'app parte "da adesso": elabora solo le email che arrivano dopo l'attivazione.
Se vuoi recuperare anche gli allegati delle email già presenti, spunta **"Al primo avvio elabora anche le email già presenti"** prima di avviare.
**"Ricomincia da capo"** fa dimenticare le email già viste.

---

## Windows
- **Avvia monitoraggio**: controlla ogni N minuti finché il programma è aperto.
- **Avvia automaticamente con Windows**: parte ridotto a icona all'accensione del PC, con il monitoraggio attivo.
- Le password sono custodite nella *Gestione credenziali* di Windows.
- Impostazioni e registro: `%APPDATA%\MailAllegati`.
- Al primo avvio dell'exe Windows potrebbe mostrare "PC protetto da Windows": clicca *Ulteriori informazioni › Esegui comunque* (succede con i programmi non firmati).

## Android
- Installa l'apk (consenti "installa app sconosciute" quando richiesto).
- Le cartelle si scelgono con il selettore di Android (memoria interna, SD, ecc.).
- Attiva **Monitoraggio automatico**: funziona anche ad app chiusa e dopo il riavvio.
  Android consente al massimo un controllo ogni **15 minuti**.
- Premi **Escludi dal risparmio batteria**, altrimenti alcuni telefoni (Xiaomi, Huawei, Samsung…) ritardano i controlli.
- Le password sono salvate cifrate nel telefono.

---

## Compilare da soli
Il progetto si compila automaticamente con GitHub Actions (`.github/workflows/build.yml`): fai un fork, apri la scheda **Actions** e scarica i file da **Artifacts**.
- `windows/` – Python + Tkinter, impacchettato con PyInstaller e Inno Setup (`build_exe.bat` per compilare in locale).
- `android/` – Kotlin, apribile con Android Studio.
- Firma Android: impostare i Secrets `ANDROID_KEYSTORE_B64` e `ANDROID_KEYSTORE_PASSWORD` (alias `mailallegati`); senza, l'apk viene firmato con una chiave di prova.
- Nuova release: aumenta `APP_VERSION` in `windows/mail_core.py`, poi in **Actions › Compila MailAllegati › Run workflow** spunta *Pubblica una nuova release* (oppure scrivi `[release]` nel messaggio del commit).

## Licenza
[MIT](LICENSE) – libero uso, modifica e ridistribuzione, mantenendo l'avviso di copyright. Il software è fornito «così com'è», senza garanzie (vedi anche `LEGGIMI_AVVERTENZE.txt`).
