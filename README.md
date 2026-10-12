# MailAllegati

Controlla automaticamente la tua casella email, prende le email dei **mittenti che scegli**, salva gli **allegati** in una o più cartelle e, se vuoi, li carica anche sul **NAS**.
Funziona su **Windows** e **Android**.

> **Avvertenze obbligatorie** – Ogni versione contiene il file `LEGGIMI_AVVERTENZE.txt` (modalità d'uso, avvertenze, divieto di uso illecito, esclusione di garanzia e limitazione di responsabilità).
> - **Windows (installazione):** la pagina "Contratto di licenza" mostra il testo e l'installazione non prosegue senza accettarlo.
> - **Windows e Android (primo avvio):** il programma mostra le avvertenze; si possono accettare solo dopo averle scorse fino in fondo e spuntato la casella. Rifiutando, il programma si chiude e i controlli automatici non vengono eseguiti.
> - Il testo resta consultabile dal pulsante **Avvertenze**. Se in futuro modifichi il testo, aumenta il numero di versione (`DISCLAIMER_VERSION` in `windows/mail_core.py` e `android/.../Settings.kt`) per richiedere una nuova accettazione.

---

## 1. Ottenere i programmi pronti (.exe e .apk) – consigliato

1. Crea un account gratuito su https://github.com (se non ce l'hai).
2. In alto a destra: **+ › New repository** → nome `MailAllegati` → **Private** → *Create repository*.
3. Nella pagina del nuovo repository clicca **uploading an existing file** e trascina **tutto il contenuto** di questa cartella (anche la cartella nascosta `.github`). Poi *Commit changes*.
   > Se Windows non mostra `.github`, in Esplora file attiva *Visualizza › Elementi nascosti*.
4. Apri la scheda **Actions**: parte da sola la compilazione (circa 5–10 minuti).
5. Quando c'è la spunta verde, apri l'esecuzione e in fondo, in **Artifacts**, scarica:
   - `MailAllegati-Windows` → **MailAllegati-Setup.exe** (installazione con accettazione delle avvertenze), **MailAllegati.exe** (versione portatile) e le avvertenze
   - `MailAllegati-Android` → **MailAllegati.apk** e le avvertenze

In alternativa:
- **Windows**: installa Python da python.org (e, per il programma di installazione, Inno Setup 6 da jrsoftware.org) e fai doppio clic su `windows\build_exe.bat`.
- **Android**: apri la cartella `android` con Android Studio e premi *Run*.

---

## 2. Configurazione (uguale su Windows e Android)

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

### Novità della versione 1.3
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

## 3. Windows
- **Avvia monitoraggio**: controlla ogni N minuti finché il programma è aperto.
- **Avvia automaticamente con Windows**: parte ridotto a icona all'accensione del PC, con il monitoraggio attivo.
- Le password sono custodite nella *Gestione credenziali* di Windows.
- Impostazioni e registro: `%APPDATA%\MailAllegati`.
- Al primo avvio dell'exe Windows potrebbe mostrare "PC protetto da Windows": clicca *Ulteriori informazioni › Esegui comunque* (succede con i programmi non firmati).

## 4. Android
- Installa l'apk (consenti "installa app sconosciute" quando richiesto).
- Le cartelle si scelgono con il selettore di Android (memoria interna, SD, ecc.).
- Attiva **Monitoraggio automatico**: funziona anche ad app chiusa e dopo il riavvio.
  Android consente al massimo un controllo ogni **15 minuti**.
- Premi **Escludi dal risparmio batteria**, altrimenti alcuni telefoni (Xiaomi, Huawei, Samsung…) ritardano i controlli.
- Le password sono salvate cifrate nel telefono.
