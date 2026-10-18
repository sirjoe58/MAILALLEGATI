"""
MailAllegati per Windows - interfaccia grafica.
Avvio:  python mail_allegati.py         (finestra)
        python mail_allegati.py --auto  (avvio ridotto a icona con monitoraggio attivo)
"""
import datetime as dt
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

import i18n
import mail_core as core
from i18n import T

PAD = {"padx": 6, "pady": 3}
DEFAULT_TEMPLATE = "{data}_{mittente}_{nome}"


def open_path(path):
    """Apre un file o una cartella con il programma predefinito."""
    if not path:
        return
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        messagebox.showerror(T("Errore"), T("Impossibile aprire:\n{}\n\n{}").format(path, e))


def show_folder(path):
    """Apre la cartella che contiene il file, selezionandolo quando possibile."""
    if not path:
        return
    if os.name == "nt" and os.path.exists(path):
        try:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            return
        except Exception:
            pass
    open_path(os.path.dirname(path) or path)


def euro(v):
    if v is None:
        return "?"
    s = f"{v:,.2f}"
    if i18n.LANG == "it":
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return s + " €"


def show_disclaimer(parent=None, require_accept=True):
    """Mostra le avvertenze. Con require_accept=True restituisce True solo se l'utente accetta."""
    text = core.disclaimer_text()
    if text is None:
        messagebox.showerror("MailAllegati",
                             T("File {} non trovato.\nReinstalla il programma: senza le avvertenze non può essere avviato.")
                             .format(core.DISCLAIMER_FILE_NAME))
        return False

    own_root = parent is None
    win = tk.Tk() if own_root else tk.Toplevel(parent)
    win.title("MailAllegati - " + T("Avvertenze e condizioni d'uso"))
    win.geometry("760x620")
    win.minsize(560, 420)
    result = {"ok": False}

    head = ttk.Label(win, wraplength=720, justify="left",
                     text=(T("Leggi fino in fondo le avvertenze. Per usare il programma devi accettarle.")
                           if require_accept else T("Avvertenze e condizioni d'uso")))
    head.pack(fill="x", padx=10, pady=(10, 4))

    frame = ttk.Frame(win)
    frame.pack(fill="both", expand=True, padx=10)
    txt = tk.Text(frame, wrap="word", padx=8, pady=8)
    sb = ttk.Scrollbar(frame, command=txt.yview)
    txt.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    txt.insert("1.0", text)
    txt.configure(state="disabled")

    bottom = ttk.Frame(win)
    bottom.pack(fill="x", padx=10, pady=10)

    if not require_accept:
        txt.configure(yscrollcommand=sb.set)
        ttk.Button(bottom, text=T("Chiudi"), command=win.destroy).pack(side="right")
        if not own_root:
            win.transient(parent)
            win.grab_set()
        return True

    v_ok = tk.BooleanVar(value=False)
    chk = ttk.Checkbutton(bottom, variable=v_ok, state="disabled",
                          text=T("Ho letto e accetto integralmente avvertenze, condizioni d'uso e limitazioni di responsabilità"))
    chk.pack(anchor="w")
    hint = ttk.Label(bottom, foreground="gray", text=T("Scorri il testo fino in fondo per poter accettare."))
    hint.pack(anchor="w", pady=(2, 6))
    btns = ttk.Frame(bottom)
    btns.pack(fill="x")

    def accept():
        result["ok"] = True
        win.destroy()

    def refuse():
        result["ok"] = False
        win.destroy()

    b_ok = ttk.Button(btns, text=T("Accetto e proseguo"), command=accept, state="disabled")
    b_ok.pack(side="right")
    ttk.Button(btns, text=T("Non accetto (esci)"), command=refuse).pack(side="right", padx=6)

    def on_scroll(first, last):
        sb.set(first, last)
        if float(last) >= 0.999 and str(chk.cget("state")) == "disabled":
            chk.configure(state="normal")
            hint.configure(text="")
    txt.configure(yscrollcommand=on_scroll)
    v_ok.trace_add("write", lambda *a: b_ok.configure(state="normal" if v_ok.get() else "disabled"))
    win.protocol("WM_DELETE_WINDOW", refuse)

    if own_root:
        win.mainloop()
    else:
        win.transient(parent)
        win.grab_set()
        parent.wait_window(win)
    return result["ok"]


class TrayIcon:
    """Icona accanto all'orologio di Windows (area di notifica), con menu e notifiche."""

    def __init__(self, app):
        self.app = app
        self.icon = None
        self.ok = False
        try:
            import pystray
            from PIL import Image, ImageDraw
        except Exception:
            return
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((2, 2, 62, 62), radius=12, fill=(31, 111, 139, 255))
        d.rectangle((12, 20, 52, 46), outline=(255, 255, 255, 255), width=4)
        d.line((12, 20, 32, 36, 52, 20), fill=(255, 255, 255, 255), width=4)
        menu = pystray.Menu(
            pystray.MenuItem(T("Apri MailAllegati"), lambda *a: app.after(0, app.show_window), default=True),
            pystray.MenuItem(T("Controlla ora"), lambda *a: app.after(0, app.check_now)),
            pystray.MenuItem(T("Apri l'ultima cartella"), lambda *a: app.after(0, app.open_last_folder)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(T("Esci"), lambda *a: app.after(0, app.quit_app)),
        )
        try:
            self.icon = pystray.Icon("MailAllegati", img, "MailAllegati", menu)
            threading.Thread(target=self.icon.run, daemon=True).start()
            self.ok = True
        except Exception:
            self.icon = None

    def notify(self, title, message):
        if self.ok and self.icon:
            try:
                self.icon.notify(message, title)
            except Exception:
                pass

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass


class App(tk.Tk):
    def __init__(self, auto=False):
        super().__init__()
        self.cfg = core.load_config()
        i18n.set_language(self.cfg.get("language", "it"))
        self.title(f"MailAllegati {core.APP_VERSION} - " + T("salva allegati email"))
        self.geometry("900x840")
        self.minsize(760, 620)
        self.logq = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.check_lock = threading.Lock()
        self.accounts = [dict(a) for a in core.get_accounts(self.cfg)] or [self._blank_account()]
        self.acc_pw = [core.account_password(a) for a in self.accounts]
        self.acc_idx = 0
        self.update_info = None

        self._build()
        self._load_into_ui()
        self.after(200, self._drain_log)
        self.retry_wake = threading.Event()
        threading.Thread(target=self._nas_retry_loop, daemon=True).start()
        threading.Thread(target=self._daily_loop, daemon=True).start()
        self.after(500, self._update_queue_label)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.tray = TrayIcon(self) if self.cfg.get("tray_icon", True) else None
        self._hint_shown = False
        self.bind("<Unmap>", self._on_unmap)

        if auto or self.cfg.get("auto_start_monitor"):
            self.after(800, self.start_monitor)
        if auto:
            self.after(1200, self.hide_window if self._tray_ok() else self.iconify)

    @staticmethod
    def _blank_account():
        return {"name": "", "server": "", "port": 993, "ssl": True, "user": "", "folder": "INBOX", "enabled": True}

    # ------------------------------------------------------------ UI
    def _build(self):
        # banner aggiornamento (nascosto finche' non serve)
        self.banner = tk.Frame(self, bg="#FFF4E0", highlightbackground="#E0A030", highlightthickness=1)
        self.v_banner = tk.StringVar()
        tk.Label(self.banner, textvariable=self.v_banner, bg="#FFF4E0", anchor="w").pack(side="left", padx=8, pady=4)
        ttk.Button(self.banner, text=T("Più tardi"), command=lambda: self.banner.pack_forget()).pack(side="right", padx=4, pady=3)
        ttk.Button(self.banner, text=T("Scarica"), command=self._open_update).pack(side="right", padx=4, pady=3)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self._build_email_tab()
        self._build_folders_tab()
        self._build_nas_tab()
        self._build_bills_tab()
        self._build_recent_tab()
        self._build_auto_tab()

        # --- barra comandi + registro
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=6)
        ttk.Button(bar, text=T("Salva impostazioni"), command=self.save).pack(side="left")
        ttk.Button(bar, text=T("Avvertenze"), command=lambda: show_disclaimer(self, require_accept=False)).pack(side="right", padx=(6, 0))
        ttk.Button(bar, text=T("Controlla ora"), command=self.check_now).pack(side="left", padx=6)
        self.btn_mon = ttk.Button(bar, text=T("▶ Avvia monitoraggio"), command=self.toggle_monitor)
        self.btn_mon.pack(side="left")
        self.v_status = tk.StringVar(value=T("Monitoraggio fermo"))
        ttk.Label(bar, textvariable=self.v_status).pack(side="right")

        lg = ttk.LabelFrame(self, text=T("Registro attività"))
        lg.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.t_log = tk.Text(lg, height=7, state="disabled", wrap="word")
        sb = ttk.Scrollbar(lg, command=self.t_log.yview)
        self.t_log.configure(yscrollcommand=sb.set)
        self.t_log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _build_email_tab(self):
        f1 = ttk.Frame(self.nb)
        self.nb.add(f1, text=T("Email e mittenti"))
        top = ttk.Frame(f1)
        top.grid(row=0, column=0, columnspan=2, sticky="we", **PAD)
        ttk.Label(top, text=T("Casella:")).pack(side="left")
        self.cb_acc = ttk.Combobox(top, state="readonly", width=34)
        self.cb_acc.pack(side="left", padx=6)
        self.cb_acc.bind("<<ComboboxSelected>>", lambda e: self._select_account(self.cb_acc.current()))
        ttk.Button(top, text=T("+ Aggiungi casella"), command=self._add_account).pack(side="left", padx=2)
        ttk.Button(top, text=T("Rimuovi"), command=self._remove_account).pack(side="left", padx=2)
        self.v_acc_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text=T("Attiva"), variable=self.v_acc_enabled).pack(side="left", padx=8)

        self.v_accname = tk.StringVar()
        self.v_server = tk.StringVar()
        self.v_port = tk.StringVar()
        self.v_ssl = tk.BooleanVar()
        self.v_user = tk.StringVar()
        self.v_pass = tk.StringVar()
        self.v_imapfolder = tk.StringVar()
        rows = [(T("Nome della casella (a piacere)"), self.v_accname),
                (T("Server IMAP (es. imapmail.libero.it)"), self.v_server),
                (T("Porta"), self.v_port),
                (T("Utente / indirizzo email"), self.v_user),
                (T("Password"), self.v_pass),
                (T("Cartella da controllare"), self.v_imapfolder)]
        for i, (lbl, var) in enumerate(rows, start=1):
            ttk.Label(f1, text=lbl).grid(row=i, column=0, sticky="w", **PAD)
            ttk.Entry(f1, textvariable=var, width=45, show="•" if var is self.v_pass else "").grid(
                row=i, column=1, sticky="we", **PAD)
        r = len(rows) + 1
        ttk.Checkbutton(f1, text=T("Connessione SSL (consigliato, porta 993)"), variable=self.v_ssl,
                        command=self._ssl_changed).grid(row=r, column=1, sticky="w", **PAD)
        ttk.Button(f1, text=T("Prova connessione email"), command=self.test_email).grid(
            row=r + 1, column=1, sticky="w", **PAD)

        self.v_keywords = tk.StringVar()
        ttk.Label(f1, text=T("Solo se l'oggetto contiene\n(vuoto = tutte le email)")).grid(
            row=r + 2, column=0, sticky="nw", **PAD)
        kf = ttk.Frame(f1)
        kf.grid(row=r + 2, column=1, sticky="we", **PAD)
        ttk.Entry(kf, textvariable=self.v_keywords).pack(fill="x")
        ttk.Label(kf, foreground="gray",
                  text=T("Parole separate da virgola, es: fattura, bolletta (maiuscole/minuscole non contano)")).pack(anchor="w")

        ttk.Label(f1, text=T("Mittenti da controllare\n(validi per tutte le caselle)")).grid(
            row=r + 3, column=0, sticky="nw", **PAD)
        sf = ttk.Frame(f1)
        sf.grid(row=r + 3, column=1, sticky="nsew", **PAD)
        self.t_senders = tk.Text(sf, height=6, width=45)
        self.t_senders.pack(fill="both", expand=True)
        ttk.Label(sf, foreground="gray", justify="left",
                  text=T("Uno per riga: indirizzo completo oppure @dominio.it per tutto il dominio.\n"
                         "Per una cartella dedicata aggiungi = cartella, es:  @enel.it = Bollette\\Luce")).pack(anchor="w")
        f1.columnconfigure(1, weight=1)
        f1.rowconfigure(r + 3, weight=1)

    def _build_folders_tab(self):
        f2 = ttk.Frame(self.nb)
        self.nb.add(f2, text=T("Cartelle di destinazione"))
        ttk.Label(f2, text=T("Gli allegati vengono salvati in TUTTE le cartelle dell'elenco:")).pack(anchor="w", **PAD)
        lf = ttk.Frame(f2)
        lf.pack(fill="both", expand=True, **PAD)
        self.lb_folders = tk.Listbox(lf, height=6)
        self.lb_folders.pack(side="left", fill="both", expand=True)
        bf = ttk.Frame(lf)
        bf.pack(side="left", fill="y", padx=6)
        ttk.Button(bf, text=T("Aggiungi…"), command=self.add_folder).pack(fill="x", pady=2)
        ttk.Button(bf, text=T("Rimuovi"), command=self.remove_folder).pack(fill="x", pady=2)
        ttk.Button(bf, text=T("Apri"), command=self.open_folder).pack(fill="x", pady=2)

        opt = ttk.LabelFrame(f2, text=T("Opzioni"))
        opt.pack(fill="x", **PAD)
        self.v_ext = tk.StringVar()
        self.v_inline = tk.BooleanVar()
        self.v_subsender = tk.BooleanVar()
        self.v_subdate = tk.BooleanVar()
        self.v_markread = tk.BooleanVar()
        self.v_existing = tk.BooleanVar()
        self.v_dupes = tk.BooleanVar()
        r = ttk.Frame(opt)
        r.pack(fill="x", **PAD)
        ttk.Label(r, text=T("Solo questi tipi di file (vuoto = tutti), es: pdf, xml, jpg")).pack(side="left")
        ttk.Entry(r, textvariable=self.v_ext, width=25).pack(side="left", padx=6)
        for text, var in [(T("Ignora immagini incorporate (loghi nelle firme)"), self.v_inline),
                          (T("Crea una sottocartella per ogni mittente"), self.v_subsender),
                          (T("Crea una sottocartella per mese (es. 2026-10)"), self.v_subdate),
                          (T("Segna come lette le email elaborate"), self.v_markread),
                          (T("Al primo avvio elabora anche le email già presenti"), self.v_existing),
                          (T("Non salvare i doppioni (file identici già salvati in precedenza)"), self.v_dupes)]:
            ttk.Checkbutton(opt, text=text, variable=var).pack(anchor="w", **PAD)

        rn = ttk.LabelFrame(f2, text=T("Nome dei file salvati"))
        rn.pack(fill="x", **PAD)
        self.v_rename = tk.BooleanVar()
        self.v_template = tk.StringVar()
        ttk.Checkbutton(rn, text=T("Rinomina i file con data e mittente"), variable=self.v_rename,
                        command=self._update_preview).pack(anchor="w", **PAD)
        rr = ttk.Frame(rn)
        rr.pack(fill="x", **PAD)
        ttk.Label(rr, text=T("Modello:")).pack(side="left")
        ttk.Entry(rr, textvariable=self.v_template, width=40).pack(side="left", padx=6)
        ttk.Button(rr, text=T("Predefinito"), command=lambda: (self.v_template.set(DEFAULT_TEMPLATE),
                                                               self._update_preview())).pack(side="left")
        self.v_template.trace_add("write", lambda *a: self._update_preview())
        ttk.Label(rn, foreground="gray",
                  text=T("{data} = data dell'email   {mittente} = nome del mittente   "
                         "{nome} = nome originale   {oggetto} = oggetto dell'email")).pack(anchor="w", **PAD)
        self.v_preview = tk.StringVar()
        ttk.Label(rn, textvariable=self.v_preview).pack(anchor="w", **PAD)

    def _build_nas_tab(self):
        f3 = ttk.Frame(self.nb)
        self.nb.add(f3, text="NAS")
        self.v_nas = tk.BooleanVar()
        self.v_naspath = tk.StringVar()
        self.v_nasuser = tk.StringVar()
        self.v_naspass = tk.StringVar()
        self.v_nasdomain = tk.StringVar()
        ttk.Checkbutton(f3, text=T("Carica gli allegati anche sul NAS"), variable=self.v_nas).grid(
            row=0, column=0, columnspan=2, sticky="w", **PAD)
        nrows = [(T("Indirizzo cartella NAS\n(es. \\\\192.168.1.10\\condivisa\\allegati)"), self.v_naspath),
                 (T("Utente NAS (vuoto = ospite)"), self.v_nasuser),
                 (T("Password NAS"), self.v_naspass),
                 (T("Dominio / gruppo (di solito vuoto)"), self.v_nasdomain)]
        for i, (lbl, var) in enumerate(nrows, start=1):
            ttk.Label(f3, text=lbl).grid(row=i, column=0, sticky="w", **PAD)
            ttk.Entry(f3, textvariable=var, width=45, show="•" if var is self.v_naspass else "").grid(
                row=i, column=1, sticky="we", **PAD)
        ttk.Button(f3, text=T("Prova connessione NAS"), command=self.test_nas).grid(
            row=len(nrows) + 1, column=1, sticky="w", **PAD)
        f3.columnconfigure(1, weight=1)

        qf = ttk.LabelFrame(f3, text=T("Se il NAS è spento o irraggiungibile"))
        qf.grid(row=len(nrows) + 2, column=0, columnspan=2, sticky="we", padx=6, pady=(12, 3))
        ttk.Label(qf, wraplength=640, justify="left",
                  text=T("Gli allegati vengono messi in coda sul PC e inviati automaticamente al NAS "
                         "appena torna raggiungibile (anche dopo un riavvio del programma).")).pack(anchor="w", **PAD)
        self.v_nasretry = tk.StringVar()
        rr = ttk.Frame(qf)
        rr.pack(anchor="w", **PAD)
        ttk.Label(rr, text=T("Riprova l'invio ogni")).pack(side="left")
        ttk.Spinbox(rr, from_=1, to=120, textvariable=self.v_nasretry, width=5).pack(side="left", padx=6)
        ttk.Label(rr, text=T("minuti")).pack(side="left")
        self.v_queue = tk.StringVar(value="")
        ttk.Label(qf, textvariable=self.v_queue, font=("Segoe UI", 10, "bold")).pack(anchor="w", **PAD)
        qb = ttk.Frame(qf)
        qb.pack(anchor="w", **PAD)
        ttk.Button(qb, text=T("Invia ora al NAS"), command=self.flush_now).pack(side="left")
        ttk.Button(qb, text=T("Svuota coda"), command=self.clear_queue).pack(side="left", padx=6)

    def _build_bills_tab(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text=T("Bollette"))
        self.v_bills = tk.BooleanVar()
        self.v_billsxl = tk.StringVar()
        self.v_billsdays = tk.StringVar()
        ttk.Checkbutton(f, text=T("Leggi importo e scadenza dalle bollette PDF salvate"),
                        variable=self.v_bills).pack(anchor="w", **PAD)
        ttk.Label(f, foreground="gray", wraplength=780, justify="left",
                  text=T("Funziona con i PDF che contengono testo (quasi tutte le bollette inviate per email); "
                         "con i documenti scansionati non trova i dati. Controlla sempre importi e scadenze sul documento originale.")
                  ).pack(anchor="w", **PAD)
        r1 = ttk.Frame(f)
        r1.pack(fill="x", **PAD)
        ttk.Label(r1, text=T("Foglio Excel riepilogativo:")).pack(side="left")
        ttk.Entry(r1, textvariable=self.v_billsxl).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(r1, text=T("Scegli…"), command=self._choose_excel).pack(side="left")
        ttk.Button(r1, text=T("Apri Excel"), command=self._open_excel).pack(side="left", padx=4)
        r2 = ttk.Frame(f)
        r2.pack(anchor="w", **PAD)
        ttk.Label(r2, text=T("Avvisami")).pack(side="left")
        ttk.Spinbox(r2, from_=0, to=30, textvariable=self.v_billsdays, width=4).pack(side="left", padx=6)
        ttk.Label(r2, text=T("giorni prima della scadenza")).pack(side="left")

        tf = ttk.Frame(f)
        tf.pack(fill="both", expand=True, **PAD)
        cols = ("due", "amount", "sender", "status", "file")
        self.tv_bills = ttk.Treeview(tf, columns=cols, show="headings", height=8)
        for c, txt, w in [("due", T("Scadenza"), 90), ("amount", T("Importo"), 90), ("sender", T("Mittente"), 140),
                          ("status", T("Stato"), 100), ("file", T("File"), 320)]:
            self.tv_bills.heading(c, text=txt)
            self.tv_bills.column(c, width=w, anchor="w")
        sb = ttk.Scrollbar(tf, command=self.tv_bills.yview)
        self.tv_bills.configure(yscrollcommand=sb.set)
        self.tv_bills.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tv_bills.tag_configure("overdue", foreground="#C0392B")
        self.tv_bills.tag_configure("paid", foreground="#2E8B57")
        self.tv_bills.bind("<Double-1>", lambda e: self._bill_open())
        bb = ttk.Frame(f)
        bb.pack(fill="x", **PAD)
        ttk.Button(bb, text=T("✔ Segna come pagata"), command=lambda: self._bill_paid(True)).pack(side="left")
        ttk.Button(bb, text=T("Segna come da pagare"), command=lambda: self._bill_paid(False)).pack(side="left", padx=4)
        ttk.Button(bb, text=T("Apri documento"), command=self._bill_open).pack(side="left", padx=4)
        ttk.Button(bb, text=T("Togli dall'elenco"), command=self._bill_remove).pack(side="left", padx=4)
        ttk.Button(bb, text=T("Aggiorna"), command=self.refresh_bills).pack(side="right")
        self.v_billsum = tk.StringVar()
        ttk.Label(f, textvariable=self.v_billsum, font=("Segoe UI", 10, "bold")).pack(anchor="w", **PAD)

    def _build_recent_tab(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text=T("Ultimi file"))
        tf = ttk.Frame(f)
        tf.pack(fill="both", expand=True, **PAD)
        cols = ("time", "name", "sender", "path")
        self.tv_recent = ttk.Treeview(tf, columns=cols, show="headings", height=12)
        for c, txt, w in [("time", T("Quando"), 120), ("name", T("File"), 280), ("sender", T("Mittente"), 120),
                          ("path", T("Percorso"), 300)]:
            self.tv_recent.heading(c, text=txt)
            self.tv_recent.column(c, width=w, anchor="w")
        sb = ttk.Scrollbar(tf, command=self.tv_recent.yview)
        self.tv_recent.configure(yscrollcommand=sb.set)
        self.tv_recent.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tv_recent.bind("<Double-1>", lambda e: self._recent_open(False))
        bb = ttk.Frame(f)
        bb.pack(fill="x", **PAD)
        ttk.Button(bb, text=T("Apri file"), command=lambda: self._recent_open(False)).pack(side="left")
        ttk.Button(bb, text=T("Apri cartella"), command=lambda: self._recent_open(True)).pack(side="left", padx=4)
        ttk.Button(bb, text=T("Svuota elenco"), command=self._recent_clear).pack(side="left", padx=4)
        ttk.Button(bb, text=T("Aggiorna"), command=self.refresh_recent).pack(side="right")
        ttk.Label(f, foreground="gray", text=T("Doppio clic su una riga per aprire il file.")).pack(anchor="w", **PAD)

    def _build_auto_tab(self):
        f4 = ttk.Frame(self.nb)
        self.nb.add(f4, text=T("Automazione"))
        self.v_interval = tk.StringVar()
        self.v_autostartmon = tk.BooleanVar()
        self.v_winstart = tk.BooleanVar(value=self._is_in_startup())
        self.v_tray = tk.BooleanVar()
        self.v_notify = tk.BooleanVar()
        self.v_updates = tk.BooleanVar()
        self.v_lang = tk.StringVar()
        r = ttk.Frame(f4)
        r.pack(anchor="w", **PAD)
        ttk.Label(r, text=T("Controlla la posta ogni")).pack(side="left")
        ttk.Spinbox(r, from_=1, to=1440, textvariable=self.v_interval, width=6).pack(side="left", padx=6)
        ttk.Label(r, text=T("minuti")).pack(side="left")
        ttk.Checkbutton(f4, text=T("Avvia il monitoraggio appena si apre il programma"),
                        variable=self.v_autostartmon).pack(anchor="w", **PAD)
        ttk.Checkbutton(f4, text=T("Avvia automaticamente con Windows (ridotto a icona)"),
                        variable=self.v_winstart, command=self._toggle_startup).pack(anchor="w", **PAD)
        ttk.Checkbutton(f4, text=T("Icona accanto all'orologio: chiudendo la finestra il programma continua a lavorare lì"),
                        variable=self.v_tray).pack(anchor="w", **PAD)
        ttk.Checkbutton(f4, text=T("Mostra una notifica di Windows quando salvo degli allegati"),
                        variable=self.v_notify).pack(anchor="w", **PAD)

        up = ttk.LabelFrame(f4, text=T("Aggiornamenti"))
        up.pack(fill="x", **PAD)
        ttk.Checkbutton(up, text=T("Avvisami quando è disponibile una nuova versione"),
                        variable=self.v_updates).pack(side="left", **PAD)
        ttk.Button(up, text=T("Controlla ora"), command=lambda: self._check_update(manual=True)).pack(side="left", **PAD)

        lf = ttk.LabelFrame(f4, text=T("Lingua / Language"))
        lf.pack(fill="x", **PAD)
        cb = ttk.Combobox(lf, textvariable=self.v_lang, state="readonly", values=["Italiano", "English"], width=12)
        cb.pack(side="left", **PAD)
        cb.bind("<<ComboboxSelected>>", lambda e: messagebox.showinfo(
            "MailAllegati", T("La nuova lingua sarà usata al prossimo avvio del programma.")))

        bk = ttk.LabelFrame(f4, text=T("Backup delle impostazioni"))
        bk.pack(fill="x", **PAD)
        ttk.Button(bk, text=T("Esporta impostazioni…"), command=self._export_settings).pack(side="left", **PAD)
        ttk.Button(bk, text=T("Importa impostazioni…"), command=self._import_settings).pack(side="left", **PAD)
        ttk.Label(bk, foreground="gray", text=T("Le password non vengono salvate nel file.")).pack(side="left", **PAD)

        ttk.Button(f4, text=T("Ricomincia da capo (dimentica le email già viste)"),
                   command=self.reset_state).pack(anchor="w", **PAD)
        ttk.Label(f4, foreground="gray",
                  text=T("Impostazioni e registro in: {}").format(core.APP_DIR)).pack(anchor="w", **PAD)

    def _ssl_changed(self):
        if self.v_port.get() in ("993", "143", ""):
            self.v_port.set("993" if self.v_ssl.get() else "143")

    # ------------------------------------------------------------ caselle
    def _acc_label(self, i, a):
        name = a.get("name") or a.get("user") or T("(nuova casella)")
        off = "" if a.get("enabled", True) else "  " + T("(disattivata)")
        return f"{i + 1}. {name}{off}"

    def _refresh_acc_combo(self):
        self.cb_acc["values"] = [self._acc_label(i, a) for i, a in enumerate(self.accounts)]
        self.cb_acc.current(self.acc_idx)

    def _store_account_fields(self):
        if not (0 <= self.acc_idx < len(self.accounts)):
            return
        a = self.accounts[self.acc_idx]
        try:
            port = int(self.v_port.get())
        except ValueError:
            port = 993 if self.v_ssl.get() else 143
        a.update({"name": self.v_accname.get().strip(), "server": self.v_server.get().strip(), "port": port,
                  "ssl": self.v_ssl.get(), "user": self.v_user.get().strip(),
                  "folder": self.v_imapfolder.get().strip() or "INBOX", "enabled": self.v_acc_enabled.get()})
        self.acc_pw[self.acc_idx] = self.v_pass.get()

    def _show_account(self, i):
        a = self.accounts[i]
        self.v_accname.set(a.get("name", ""))
        self.v_server.set(a.get("server", ""))
        self.v_port.set(str(a.get("port", 993)))
        self.v_ssl.set(bool(a.get("ssl", True)))
        self.v_user.set(a.get("user", ""))
        self.v_imapfolder.set(a.get("folder") or "INBOX")
        self.v_acc_enabled.set(bool(a.get("enabled", True)))
        self.v_pass.set(self.acc_pw[i] or "")

    def _select_account(self, i):
        if i < 0:
            return
        self._store_account_fields()
        self.acc_idx = i
        self._show_account(i)
        self._refresh_acc_combo()

    def _add_account(self):
        self._store_account_fields()
        self.accounts.append(self._blank_account())
        self.acc_pw.append("")
        self.acc_idx = len(self.accounts) - 1
        self._show_account(self.acc_idx)
        self._refresh_acc_combo()

    def _remove_account(self):
        if len(self.accounts) <= 1:
            messagebox.showinfo("MailAllegati", T("Serve almeno una casella."))
            return
        a = self.accounts[self.acc_idx]
        if not messagebox.askyesno(T("Rimuovi"), T("Rimuovere la casella «{}»?").format(a.get("name") or a.get("user"))):
            return
        core.set_account_password(a, "")
        del self.accounts[self.acc_idx]
        del self.acc_pw[self.acc_idx]
        self.acc_idx = max(0, self.acc_idx - 1)
        self._show_account(self.acc_idx)
        self._refresh_acc_combo()

    # ------------------------------------------------------------ config
    def _load_into_ui(self):
        c = self.cfg
        self._show_account(0)
        self._refresh_acc_combo()
        self.t_senders.delete("1.0", "end")
        self.t_senders.insert("1.0", "\n".join(c["senders"]))
        self.lb_folders.delete(0, "end")
        for f in c["local_folders"]:
            self.lb_folders.insert("end", f)
        self.v_ext.set(c["extensions"])
        self.v_inline.set(c["ignore_inline"])
        self.v_subsender.set(c["subfolder_per_sender"])
        self.v_subdate.set(c["subfolder_per_date"])
        self.v_markread.set(c["mark_as_read"])
        self.v_existing.set(c["process_existing"])
        self.v_keywords.set(c.get("subject_keywords", ""))
        self.v_rename.set(c.get("rename_enabled", True))
        self.v_template.set(c.get("rename_template", DEFAULT_TEMPLATE))
        self.v_dupes.set(c.get("skip_duplicates", True))
        self.v_tray.set(c.get("tray_icon", True))
        self.v_notify.set(c.get("notify_saved", True))
        self._update_preview()
        self.v_nas.set(c["nas_enabled"])
        self.v_naspath.set(c["nas_path"])
        self.v_nasuser.set(c["nas_user"])
        self.v_naspass.set(core.get_secret("nas_password"))
        self.v_nasdomain.set(c["nas_domain"])
        self.v_nasretry.set(str(c.get("nas_retry_minutes", 2)))
        self.v_interval.set(str(c["interval_minutes"]))
        self.v_autostartmon.set(c["auto_start_monitor"])
        self.v_updates.set(c.get("check_updates", True))
        self.v_lang.set("English" if c.get("language") == "en" else "Italiano")
        self.v_bills.set(c.get("bills_enabled", False))
        self.v_billsxl.set(c.get("bills_excel", "") or core.bills_excel_path(c))
        self.v_billsdays.set(str(c.get("bills_remind_days", 3)))
        self.refresh_recent()
        self.refresh_bills()

    def _collect(self):
        self._store_account_fields()
        c = dict(self.cfg)
        c["accounts"] = [dict(a) for a in self.accounts]
        first = self.accounts[0]
        # campi della prima casella tenuti anche nel formato precedente
        c.update({"imap_server": first.get("server", ""), "imap_port": first.get("port", 993),
                  "imap_ssl": first.get("ssl", True), "imap_user": first.get("user", ""),
                  "imap_folder": first.get("folder") or "INBOX"})
        c["senders"] = [line.strip() for line in self.t_senders.get("1.0", "end").splitlines() if line.strip()]
        c["local_folders"] = list(self.lb_folders.get(0, "end"))
        c["extensions"] = self.v_ext.get().strip()
        c["ignore_inline"] = self.v_inline.get()
        c["subfolder_per_sender"] = self.v_subsender.get()
        c["subfolder_per_date"] = self.v_subdate.get()
        c["mark_as_read"] = self.v_markread.get()
        c["process_existing"] = self.v_existing.get()
        c["subject_keywords"] = self.v_keywords.get().strip()
        c["rename_enabled"] = self.v_rename.get()
        c["rename_template"] = self.v_template.get().strip() or DEFAULT_TEMPLATE
        c["skip_duplicates"] = self.v_dupes.get()
        c["tray_icon"] = self.v_tray.get()
        c["notify_saved"] = self.v_notify.get()
        c["nas_enabled"] = self.v_nas.get()
        c["nas_path"] = self.v_naspath.get().strip()
        c["nas_user"] = self.v_nasuser.get().strip()
        c["nas_domain"] = self.v_nasdomain.get().strip()
        try:
            c["nas_retry_minutes"] = max(1, int(self.v_nasretry.get()))
        except ValueError:
            c["nas_retry_minutes"] = 2
        try:
            c["interval_minutes"] = max(1, int(self.v_interval.get()))
        except ValueError:
            c["interval_minutes"] = 5
        c["auto_start_monitor"] = self.v_autostartmon.get()
        c["check_updates"] = self.v_updates.get()
        c["language"] = "en" if self.v_lang.get() == "English" else "it"
        c["bills_enabled"] = self.v_bills.get()
        c["bills_excel"] = self.v_billsxl.get().strip()
        try:
            c["bills_remind_days"] = max(0, int(self.v_billsdays.get()))
        except ValueError:
            c["bills_remind_days"] = 3
        return c

    def save(self, quiet=False):
        self.cfg = self._collect()
        core.save_config(self.cfg)
        for a, pw in zip(self.accounts, self.acc_pw):
            if a.get("user") and a.get("server"):
                core.set_account_password(a, pw or "")
        core.set_secret("nas_password", self.v_naspass.get())
        self._refresh_acc_combo()
        if not quiet:
            self.log(T("Impostazioni salvate"))

    # ------------------------------------------------------------ cartelle
    def add_folder(self):
        d = filedialog.askdirectory(title=T("Scegli la cartella dove salvare gli allegati"))
        if d:
            d = os.path.normpath(d)
            if d not in self.lb_folders.get(0, "end"):
                self.lb_folders.insert("end", d)

    def remove_folder(self):
        for i in reversed(self.lb_folders.curselection()):
            self.lb_folders.delete(i)

    def open_folder(self):
        sel = self.lb_folders.curselection()
        if sel:
            open_path(self.lb_folders.get(sel[0]))

    # ------------------------------------------------------------ test
    def _run_bg(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def test_email(self):
        self.save(quiet=True)
        acc = dict(self.accounts[self.acc_idx])
        cfg, pw = core.account_cfg(self.cfg, acc), self.acc_pw[self.acc_idx]

        def job():
            try:
                n = core.test_imap(cfg, pw)
                self.log(T("✔ Connessione email riuscita: {} messaggi in '{}'").format(n, cfg["imap_folder"]))
                self.after(0, lambda: messagebox.showinfo("Email", T("Connessione riuscita.\n{} messaggi nella cartella.").format(n)))
            except Exception as e:
                msg = str(e)
                self.log(T("✖ Connessione email fallita: {}").format(msg))
                self.after(0, lambda: messagebox.showerror("Email", T("Connessione fallita:\n{}").format(msg)))
        self._run_bg(job)

    def test_nas(self):
        self.save(quiet=True)
        cfg, pw = self.cfg, self.v_naspass.get()

        def job():
            nas = None
            try:
                nas = core.NasClient(cfg, pw)
                files = nas.test()
                self.log(T("✔ NAS raggiungibile: {} ({} elementi)").format(nas.base, len(files)))
                self.after(0, lambda: messagebox.showinfo("NAS", T("Connessione riuscita a\n{}").format(nas.base)))
            except Exception as e:
                msg = str(e)
                self.log(T("✖ NAS non raggiungibile: {}").format(msg))
                self.after(0, lambda: messagebox.showerror("NAS", T("Connessione fallita:\n{}").format(msg)))
            finally:
                if nas:
                    nas.close()
        self._run_bg(job)

    # ------------------------------------------------------------ controllo
    def _do_check(self):
        if not self.check_lock.acquire(blocking=False):
            return
        try:
            names = []
            n = core.check_all(self.cfg, core.get_secret("nas_password"), log=self.log, on_saved=names.append)
            self.log(T("Controllo completato: {} allegati salvati").format(n) if n
                     else T("Controllo completato: nessun nuovo allegato"))
            if names and self.cfg.get("notify_saved", True) and self.tray:
                testo = "\n".join(names[:4]) + (T("\n… e altri {}").format(len(names) - 4) if len(names) > 4 else "")
                self.tray.notify(T("Salvati {} allegati").format(len(names)) if len(names) > 1 else T("Salvato 1 allegato"), testo)
            if names:
                self.after(0, self.refresh_recent)
                self.after(0, self.refresh_bills)
            self._bill_reminders()
        except Exception as e:
            self.log(T("ERRORE: {}").format(e))
        finally:
            self.check_lock.release()

    # ------------------------------------------------------------ coda NAS
    def _nas_retry_loop(self):
        """Riprova in continuazione l'invio dei file in coda, finché il programma è aperto."""
        time.sleep(5)
        while True:
            try:
                if core.disclaimer_accepted() and self.cfg.get("nas_enabled") and core.queue_count():
                    core.flush_queue(self.cfg, core.get_secret("nas_password"), log=self.log)
            except Exception as e:
                self.log(T("ERRORE coda NAS: {}").format(e))
            mins = max(1, int(self.cfg.get("nas_retry_minutes", 2) or 2))
            self.retry_wake.wait(mins * 60)
            self.retry_wake.clear()

    def flush_now(self):
        self.save(quiet=True)
        if not self.cfg.get("nas_enabled"):
            messagebox.showinfo("NAS", T("Attiva prima il caricamento sul NAS."))
            return
        if not core.queue_count():
            self.log(T("Coda NAS vuota: niente da inviare"))
            return
        self.retry_wake.set()

    def clear_queue(self):
        n = core.queue_count()
        if not n:
            messagebox.showinfo(T("Coda NAS"), T("La coda è già vuota."))
            return
        if messagebox.askyesno(T("Svuota coda"),
                               T("Eliminare {} file in attesa di invio al NAS?\n"
                                 "Le copie nelle cartelle locali NON vengono toccate.").format(n)):
            core.queue_clear()
            self.log(T("Coda NAS svuotata ({} file eliminati)").format(n))

    def _update_queue_label(self):
        try:
            n = core.queue_count()
            self.v_queue.set(T("File in attesa di invio al NAS: {}").format(n) if n else T("Nessun file in attesa"))
        except Exception:
            pass
        self.after(5000, self._update_queue_label)

    # ------------------------------------------------------------ attivita' giornaliere
    def _daily_loop(self):
        """Controllo aggiornamenti (all'avvio e ogni giorno) e promemoria bollette (ogni ora)."""
        time.sleep(8)
        last_update = 0
        while True:
            try:
                if self.cfg.get("check_updates", True) and time.time() - last_update > 86400:
                    last_update = time.time()
                    self._check_update(manual=False)
                self._bill_reminders()
            except Exception:
                pass
            time.sleep(3600)

    def _check_update(self, manual=False):
        def job():
            try:
                info = core.check_update()
            except Exception as e:
                if manual:
                    self.after(0, lambda: messagebox.showwarning(
                        T("Aggiornamenti"), T("Impossibile controllare gli aggiornamenti:\n{}").format(e)))
                return
            if info:
                ver, url = info
                self.update_info = info
                self.log(T("È disponibile la versione {} di MailAllegati").format(ver))
                self.after(0, lambda: self._show_banner(ver))
                if not manual and self.tray:
                    self.tray.notify(T("Nuova versione disponibile"),
                                     T("MailAllegati {} è pronto da scaricare.").format(ver))
            elif manual:
                self.after(0, lambda: messagebox.showinfo(
                    T("Aggiornamenti"), T("Hai già l'ultima versione ({}).").format(core.APP_VERSION)))
        if manual:
            self._run_bg(job)
        else:
            job()

    def _show_banner(self, ver):
        self.v_banner.set(T("È disponibile MailAllegati {} (tu hai la {}).").format(ver, core.APP_VERSION))
        self.banner.pack(fill="x", padx=8, pady=(8, 0), before=self.nb)

    def _open_update(self):
        url = (self.update_info or (None, f"https://github.com/{core.GITHUB_REPO}/releases/latest"))[1]
        webbrowser.open(url)

    # ------------------------------------------------------------ bollette
    def _choose_excel(self):
        p = filedialog.asksaveasfilename(title=T("Foglio Excel delle bollette"), defaultextension=".xlsx",
                                         filetypes=[("Excel", "*.xlsx")], initialfile=T("Bollette") + ".xlsx")
        if p:
            self.v_billsxl.set(os.path.normpath(p))

    def _open_excel(self):
        self.save(quiet=True)
        path = core.update_bills_excel(self.cfg, self.log)
        if path and os.path.exists(path):
            open_path(path)
        elif not core.bills_store().load():
            messagebox.showinfo(T("Bollette"), T("Non ci sono ancora bollette registrate."))

    def refresh_bills(self):
        try:
            items = core.bills_store().load()
        except Exception:
            items = []
        self.tv_bills.delete(*self.tv_bills.get_children())
        today = dt.date.today()
        total = 0.0
        n_open = 0

        def key(i):
            return (bool(i.get("paid")), i.get("due") or "9999")
        for i in sorted(items, key=key):
            due = None
            try:
                due = dt.date.fromisoformat(i["due"]) if i.get("due") else None
            except ValueError:
                pass
            if i.get("paid"):
                status, tag = T("Pagata"), "paid"
            elif due and due < today:
                status, tag = T("Scaduta"), "overdue"
            elif due:
                status, tag = T("Da pagare"), ""
            else:
                status, tag = T("Da verificare"), ""
            if not i.get("paid"):
                n_open += 1
                total += i.get("amount") or 0
            self.tv_bills.insert("", "end", iid=i.get("hash"), tags=(tag,),
                                 values=(due.strftime("%d/%m/%Y") if due else "?", euro(i.get("amount")),
                                         i.get("sender", ""), status, i.get("file", "")))
        self.v_billsum.set(T("Da pagare: {} bollette, totale {}").format(n_open, euro(total)) if n_open else "")

    def _sel_bill(self):
        sel = self.tv_bills.selection()
        if not sel:
            messagebox.showinfo(T("Bollette"), T("Seleziona prima una bolletta nell'elenco."))
            return None
        return sel[0]

    def _bill_paid(self, paid):
        h = self._sel_bill()
        if h:
            core.bills_store().update(h, paid=paid)
            self.refresh_bills()
            core.update_bills_excel(self.cfg, self.log)

    def _bill_open(self):
        h = self._sel_bill()
        if h:
            for i in core.bills_store().load():
                if i.get("hash") == h:
                    open_path(i.get("path"))

    def _bill_remove(self):
        h = self._sel_bill()
        if h and messagebox.askyesno(T("Bollette"), T("Togliere la bolletta dall'elenco? Il file non viene cancellato.")):
            core.bills_store().remove(h)
            self.refresh_bills()
            core.update_bills_excel(self.cfg, self.log)

    def _bill_reminders(self):
        if not self.cfg.get("bills_enabled"):
            return
        try:
            due = core.bills_store().due_soon(int(self.cfg.get("bills_remind_days", 3)))
        except Exception:
            return
        for i, left in due:
            if left < 0:
                when = T("scaduta da {} giorni").format(-left)
            elif left == 0:
                when = T("scade oggi")
            elif left == 1:
                when = T("scade domani")
            else:
                when = T("scade tra {} giorni").format(left)
            msg = T("Bolletta {} di {}: {}").format(i.get("sender", ""), euro(i.get("amount")), when)
            self.log("⏰ " + msg)
            if self.tray:
                self.tray.notify(T("Promemoria bolletta"), msg)
        if due:
            self.after(0, self.refresh_bills)

    # ------------------------------------------------------------ ultimi file
    def refresh_recent(self):
        self.tv_recent.delete(*self.tv_recent.get_children())
        for idx, r in enumerate(core.recent_files()):
            self.tv_recent.insert("", "end", iid=str(idx),
                                  values=(r.get("time", ""), r.get("name", ""), r.get("sender", "").replace("_", " "),
                                          r.get("path", "")))

    def _recent_open(self, folder):
        sel = self.tv_recent.selection()
        if not sel:
            messagebox.showinfo(T("Ultimi file"), T("Seleziona prima un file nell'elenco."))
            return
        path = self.tv_recent.item(sel[0], "values")[3]
        show_folder(path) if folder else open_path(path)

    def _recent_clear(self):
        if messagebox.askyesno(T("Ultimi file"), T("Svuotare l'elenco? I file non vengono cancellati.")):
            core.clear_recent()
            self.refresh_recent()

    def open_last_folder(self):
        items = core.recent_files()
        if items:
            show_folder(items[0].get("path"))
        elif self.cfg.get("local_folders"):
            open_path(self.cfg["local_folders"][0])

    # ------------------------------------------------------------ backup
    def _export_settings(self):
        self.save(quiet=True)
        p = filedialog.asksaveasfilename(title=T("Esporta impostazioni"), defaultextension=".json",
                                         filetypes=[(T("Impostazioni MailAllegati"), "*.json")],
                                         initialfile="MailAllegati-" + T("impostazioni") + ".json")
        if p:
            try:
                core.export_settings(self.cfg, p)
                messagebox.showinfo(T("Backup"), T("Impostazioni esportate in:\n{}\n\nLe password non sono incluse.").format(p))
            except Exception as e:
                messagebox.showerror(T("Errore"), str(e))

    def _import_settings(self):
        p = filedialog.askopenfilename(title=T("Importa impostazioni"),
                                       filetypes=[(T("Impostazioni MailAllegati"), "*.json")])
        if not p:
            return
        if not messagebox.askyesno(T("Backup"), T("Sostituire le impostazioni attuali con quelle del file?")):
            return
        try:
            self.cfg = core.import_settings(p)
        except Exception as e:
            messagebox.showerror(T("Errore"), str(e))
            return
        self.accounts = [dict(a) for a in core.get_accounts(self.cfg)] or [self._blank_account()]
        self.acc_pw = [core.account_password(a) for a in self.accounts]
        self.acc_idx = 0
        self._load_into_ui()
        self.log(T("Impostazioni importate da {}").format(p))
        messagebox.showinfo(T("Backup"), T("Impostazioni importate. Reinserisci le password delle caselle e del NAS, poi premi Salva impostazioni."))

    # ------------------------------------------------------------ monitoraggio
    def check_now(self):
        self.save(quiet=True)
        self._run_bg(self._do_check)

    def toggle_monitor(self):
        if self.worker and self.worker.is_alive():
            self.stop_monitor()
        else:
            self.start_monitor()

    def start_monitor(self):
        if self.worker and self.worker.is_alive():
            return
        self.save(quiet=True)
        self.stop_event.clear()

        def loop():
            while not self.stop_event.is_set():
                self._do_check()
                mins = self.cfg.get("interval_minutes", 5)
                nxt = time.strftime("%H:%M", time.localtime(time.time() + mins * 60))
                self.after(0, lambda: self.v_status.set(T("Monitoraggio attivo · prossimo controllo {}").format(nxt)))
                self.stop_event.wait(mins * 60)

        self.worker = threading.Thread(target=loop, daemon=True)
        self.worker.start()
        self.btn_mon.configure(text=T("■ Ferma monitoraggio"))
        self.v_status.set(T("Monitoraggio attivo"))
        self.log(T("Monitoraggio avviato (ogni {} minuti)").format(self.cfg["interval_minutes"]))

    def stop_monitor(self):
        self.stop_event.set()
        self.btn_mon.configure(text=T("▶ Avvia monitoraggio"))
        self.v_status.set(T("Monitoraggio fermo"))
        self.log(T("Monitoraggio fermato"))

    def reset_state(self):
        if messagebox.askyesno(T("Ricomincia"),
                               T("Il programma dimenticherà quali email ha già visto.\n"
                                 "Al prossimo controllo si comporterà come al primo avvio. Continuare?")):
            core.reset_state()
            self.log(T("Stato azzerato"))

    # ------------------------------------------------------------ avvio con Windows
    def _startup_cmd(self):
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}" --auto'
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        return f'"{pyw if os.path.exists(pyw) else sys.executable}" "{os.path.abspath(__file__)}" --auto'

    def _is_in_startup(self):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                winreg.QueryValueEx(k, core.APP_NAME)
                return True
        except Exception:
            return False

    def _toggle_startup(self):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                                0, winreg.KEY_SET_VALUE) as k:
                if self.v_winstart.get():
                    winreg.SetValueEx(k, core.APP_NAME, 0, winreg.REG_SZ, self._startup_cmd())
                    self.log(T("Avvio automatico con Windows attivato"))
                else:
                    try:
                        winreg.DeleteValue(k, core.APP_NAME)
                    except FileNotFoundError:
                        pass
                    self.log(T("Avvio automatico con Windows disattivato"))
        except Exception as e:
            messagebox.showerror(T("Errore"), T("Impossibile modificare l'avvio automatico:\n{}").format(e))

    # ------------------------------------------------------------ registro
    def log(self, text):
        line = f"{time.strftime('%d/%m %H:%M:%S')}  {text}"
        self.logq.put(line)
        try:
            os.makedirs(core.APP_DIR, exist_ok=True)
            if os.path.exists(core.LOG_FILE) and os.path.getsize(core.LOG_FILE) > 2_000_000:
                os.replace(core.LOG_FILE, core.LOG_FILE + ".old")
            with open(core.LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def _drain_log(self):
        try:
            while True:
                line = self.logq.get_nowait()
                self.t_log.configure(state="normal")
                self.t_log.insert("end", line + "\n")
                if int(self.t_log.index("end-1c").split(".")[0]) > 1000:
                    self.t_log.delete("1.0", "200.0")
                self.t_log.see("end")
                self.t_log.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(300, self._drain_log)

    def _tray_ok(self):
        return bool(self.tray and self.tray.ok)

    def _update_preview(self):
        try:
            if self.v_rename.get():
                ex = core.build_filename(self.v_template.get(), "FT_000123.pdf",
                                         time.strftime("%Y-%m-%d"), "Enel", T("Bolletta ottobre"))
                self.v_preview.set(T("Esempio: FT_000123.pdf  →  {}").format(ex))
            else:
                self.v_preview.set(T("I file mantengono il nome originale"))
        except Exception:
            pass

    def hide_window(self):
        self.withdraw()
        if self._tray_ok() and not self._hint_shown:
            self._hint_shown = True
            self.tray.notify(T("MailAllegati è attivo"),
                             T("Continua a lavorare qui, accanto all'orologio. Doppio clic sull'icona per aprirlo."))

    def show_window(self):
        self.deiconify()
        self.state("normal")
        self.lift()
        self.focus_force()

    def _on_unmap(self, event):
        # ridotto a icona: con l'icona attiva sparisce dalla barra e resta accanto all'orologio
        if event.widget is self and self._tray_ok() and self.state() == "iconic":
            self.after(10, self.hide_window)

    def quit_app(self):
        self.save(quiet=True)
        self.stop_event.set()
        if self.tray:
            self.tray.stop()
        self.destroy()

    def _on_close(self):
        if self._tray_ok():
            self.save(quiet=True)
            self.hide_window()
            return
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno(T("Esci"), T("Il monitoraggio è attivo: chiudendo si ferma.\n"
                                                    "Vuoi davvero uscire? (Puoi anche ridurre a icona)")):
                return
        self.quit_app()


if __name__ == "__main__":
    i18n.set_language(core.load_config().get("language", "it"))
    if not core.disclaimer_accepted():
        if not show_disclaimer():
            sys.exit(0)
        core.accept_disclaimer()
    App(auto="--auto" in sys.argv).mainloop()
