"""
MailAllegati per Windows - interfaccia grafica.
Avvio:  python mail_allegati.py         (finestra)
        python mail_allegati.py --auto  (avvio ridotto a icona con monitoraggio attivo)
"""
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import mail_core as core

PAD = {"padx": 6, "pady": 3}


def show_disclaimer(parent=None, require_accept=True):
    """Mostra le avvertenze. Con require_accept=True restituisce True solo se l'utente accetta."""
    text = core.disclaimer_text()
    if text is None:
        messagebox.showerror("MailAllegati",
                             f"File {core.DISCLAIMER_FILE_NAME} non trovato.\n"
                             "Reinstalla il programma: senza le avvertenze non può essere avviato.")
        return False

    own_root = parent is None
    win = tk.Tk() if own_root else tk.Toplevel(parent)
    win.title("MailAllegati - Avvertenze e condizioni d'uso")
    win.geometry("760x620")
    win.minsize(560, 420)
    result = {"ok": False}

    head = ttk.Label(win, wraplength=720, justify="left",
                     text=("Leggi fino in fondo le avvertenze. Per usare il programma devi accettarle."
                           if require_accept else "Avvertenze e condizioni d'uso"))
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
        ttk.Button(bottom, text="Chiudi", command=win.destroy).pack(side="right")
        if not own_root:
            win.transient(parent)
            win.grab_set()
        return True

    v_ok = tk.BooleanVar(value=False)
    chk = ttk.Checkbutton(bottom, variable=v_ok, state="disabled",
                          text="Ho letto e accetto integralmente avvertenze, condizioni d'uso e limitazioni di responsabilità")
    chk.pack(anchor="w")
    hint = ttk.Label(bottom, foreground="gray", text="Scorri il testo fino in fondo per poter accettare.")
    hint.pack(anchor="w", pady=(2, 6))
    btns = ttk.Frame(bottom)
    btns.pack(fill="x")

    def accept():
        result["ok"] = True
        win.destroy()

    def refuse():
        result["ok"] = False
        win.destroy()

    b_ok = ttk.Button(btns, text="Accetto e proseguo", command=accept, state="disabled")
    b_ok.pack(side="right")
    ttk.Button(btns, text="Non accetto (esci)", command=refuse).pack(side="right", padx=6)

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


class App(tk.Tk):
    def __init__(self, auto=False):
        super().__init__()
        self.title(f"MailAllegati {core.APP_VERSION} - salva allegati email")
        self.geometry("820x760")
        self.minsize(720, 600)
        self.cfg = core.load_config()
        self.logq = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.check_lock = threading.Lock()

        self._build()
        self._load_into_ui()
        self.after(200, self._drain_log)
        self.retry_wake = threading.Event()
        threading.Thread(target=self._nas_retry_loop, daemon=True).start()
        self.after(500, self._update_queue_label)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        if auto or self.cfg.get("auto_start_monitor"):
            self.after(800, self.start_monitor)
        if auto:
            self.after(1200, self.iconify)

    # ------------------------------------------------------------ UI
    def _build(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        # --- Email
        f1 = ttk.Frame(nb)
        nb.add(f1, text="Email e mittenti")
        self.v_server = tk.StringVar()
        self.v_port = tk.StringVar()
        self.v_ssl = tk.BooleanVar()
        self.v_user = tk.StringVar()
        self.v_pass = tk.StringVar()
        self.v_imapfolder = tk.StringVar()
        rows = [("Server IMAP (es. imaps.aruba.it)", self.v_server),
                ("Porta", self.v_port),
                ("Utente / indirizzo email", self.v_user),
                ("Password", self.v_pass),
                ("Cartella da controllare", self.v_imapfolder)]
        for i, (lbl, var) in enumerate(rows):
            ttk.Label(f1, text=lbl).grid(row=i, column=0, sticky="w", **PAD)
            e = ttk.Entry(f1, textvariable=var, width=45, show="•" if var is self.v_pass else "")
            e.grid(row=i, column=1, sticky="we", **PAD)
        ttk.Checkbutton(f1, text="Connessione SSL (consigliato, porta 993)", variable=self.v_ssl,
                        command=self._ssl_changed).grid(row=len(rows), column=1, sticky="w", **PAD)
        ttk.Button(f1, text="Prova connessione email", command=self.test_email).grid(
            row=len(rows) + 1, column=1, sticky="w", **PAD)

        ttk.Label(f1, text="Mittenti da controllare\n(uno per riga: indirizzo completo\noppure @dominio.it per tutto il dominio)").grid(
            row=len(rows) + 2, column=0, sticky="nw", **PAD)
        self.t_senders = tk.Text(f1, height=8, width=45)
        self.t_senders.grid(row=len(rows) + 2, column=1, sticky="nsew", **PAD)
        f1.columnconfigure(1, weight=1)
        f1.rowconfigure(len(rows) + 2, weight=1)

        # --- Cartelle
        f2 = ttk.Frame(nb)
        nb.add(f2, text="Cartelle di destinazione")
        ttk.Label(f2, text="Gli allegati vengono salvati in TUTTE le cartelle dell'elenco:").pack(anchor="w", **PAD)
        lf = ttk.Frame(f2)
        lf.pack(fill="both", expand=True, **PAD)
        self.lb_folders = tk.Listbox(lf, height=8)
        self.lb_folders.pack(side="left", fill="both", expand=True)
        bf = ttk.Frame(lf)
        bf.pack(side="left", fill="y", padx=6)
        ttk.Button(bf, text="Aggiungi…", command=self.add_folder).pack(fill="x", pady=2)
        ttk.Button(bf, text="Rimuovi", command=self.remove_folder).pack(fill="x", pady=2)
        ttk.Button(bf, text="Apri", command=self.open_folder).pack(fill="x", pady=2)

        opt = ttk.LabelFrame(f2, text="Opzioni")
        opt.pack(fill="x", **PAD)
        self.v_ext = tk.StringVar()
        self.v_inline = tk.BooleanVar()
        self.v_subsender = tk.BooleanVar()
        self.v_subdate = tk.BooleanVar()
        self.v_markread = tk.BooleanVar()
        self.v_existing = tk.BooleanVar()
        r = ttk.Frame(opt)
        r.pack(fill="x", **PAD)
        ttk.Label(r, text="Solo questi tipi di file (vuoto = tutti), es: pdf, xml, jpg").pack(side="left")
        ttk.Entry(r, textvariable=self.v_ext, width=25).pack(side="left", padx=6)
        for text, var in [("Ignora immagini incorporate (loghi nelle firme)", self.v_inline),
                          ("Crea una sottocartella per ogni mittente", self.v_subsender),
                          ("Crea una sottocartella per mese (es. 2026-10)", self.v_subdate),
                          ("Segna come lette le email elaborate", self.v_markread),
                          ("Al primo avvio elabora anche le email già presenti", self.v_existing)]:
            ttk.Checkbutton(opt, text=text, variable=var).pack(anchor="w", **PAD)

        # --- NAS
        f3 = ttk.Frame(nb)
        nb.add(f3, text="NAS")
        self.v_nas = tk.BooleanVar()
        self.v_naspath = tk.StringVar()
        self.v_nasuser = tk.StringVar()
        self.v_naspass = tk.StringVar()
        self.v_nasdomain = tk.StringVar()
        ttk.Checkbutton(f3, text="Carica gli allegati anche sul NAS", variable=self.v_nas).grid(
            row=0, column=0, columnspan=2, sticky="w", **PAD)
        nrows = [("Indirizzo cartella NAS\n(es. \\\\192.168.1.10\\condivisa\\allegati)", self.v_naspath),
                 ("Utente NAS (vuoto = ospite)", self.v_nasuser),
                 ("Password NAS", self.v_naspass),
                 ("Dominio / gruppo (di solito vuoto)", self.v_nasdomain)]
        for i, (lbl, var) in enumerate(nrows, start=1):
            ttk.Label(f3, text=lbl).grid(row=i, column=0, sticky="w", **PAD)
            ttk.Entry(f3, textvariable=var, width=45, show="•" if var is self.v_naspass else "").grid(
                row=i, column=1, sticky="we", **PAD)
        ttk.Button(f3, text="Prova connessione NAS", command=self.test_nas).grid(
            row=len(nrows) + 1, column=1, sticky="w", **PAD)
        f3.columnconfigure(1, weight=1)

        qf = ttk.LabelFrame(f3, text="Se il NAS è spento o irraggiungibile")
        qf.grid(row=len(nrows) + 2, column=0, columnspan=2, sticky="we", padx=6, pady=(12, 3))
        ttk.Label(qf, wraplength=640, justify="left",
                  text="Gli allegati vengono messi in coda sul PC e inviati automaticamente al NAS "
                       "appena torna raggiungibile (anche dopo un riavvio del programma).").pack(anchor="w", **PAD)
        self.v_nasretry = tk.StringVar()
        rr = ttk.Frame(qf)
        rr.pack(anchor="w", **PAD)
        ttk.Label(rr, text="Riprova l'invio ogni").pack(side="left")
        ttk.Spinbox(rr, from_=1, to=120, textvariable=self.v_nasretry, width=5).pack(side="left", padx=6)
        ttk.Label(rr, text="minuti").pack(side="left")
        self.v_queue = tk.StringVar(value="")
        ttk.Label(qf, textvariable=self.v_queue, font=("Segoe UI", 10, "bold")).pack(anchor="w", **PAD)
        qb = ttk.Frame(qf)
        qb.pack(anchor="w", **PAD)
        ttk.Button(qb, text="Invia ora al NAS", command=self.flush_now).pack(side="left")
        ttk.Button(qb, text="Svuota coda", command=self.clear_queue).pack(side="left", padx=6)

        # --- Automazione
        f4 = ttk.Frame(nb)
        nb.add(f4, text="Automazione")
        self.v_interval = tk.StringVar()
        self.v_autostartmon = tk.BooleanVar()
        self.v_winstart = tk.BooleanVar(value=self._is_in_startup())
        r = ttk.Frame(f4)
        r.pack(anchor="w", **PAD)
        ttk.Label(r, text="Controlla la posta ogni").pack(side="left")
        ttk.Spinbox(r, from_=1, to=1440, textvariable=self.v_interval, width=6).pack(side="left", padx=6)
        ttk.Label(r, text="minuti").pack(side="left")
        ttk.Checkbutton(f4, text="Avvia il monitoraggio appena si apre il programma",
                        variable=self.v_autostartmon).pack(anchor="w", **PAD)
        ttk.Checkbutton(f4, text="Avvia automaticamente con Windows (ridotto a icona)",
                        variable=self.v_winstart, command=self._toggle_startup).pack(anchor="w", **PAD)
        ttk.Button(f4, text="Ricomincia da capo (dimentica le email già viste)",
                   command=self.reset_state).pack(anchor="w", **PAD)
        ttk.Label(f4, foreground="gray",
                  text=f"Impostazioni e registro in: {core.APP_DIR}").pack(anchor="w", **PAD)

        # --- barra comandi + registro
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=6)
        ttk.Button(bar, text="Salva impostazioni", command=self.save).pack(side="left")
        ttk.Button(bar, text="Avvertenze", command=lambda: show_disclaimer(self, require_accept=False)).pack(side="right", padx=(6, 0))
        ttk.Button(bar, text="Controlla ora", command=self.check_now).pack(side="left", padx=6)
        self.btn_mon = ttk.Button(bar, text="▶ Avvia monitoraggio", command=self.toggle_monitor)
        self.btn_mon.pack(side="left")
        self.v_status = tk.StringVar(value="Monitoraggio fermo")
        ttk.Label(bar, textvariable=self.v_status).pack(side="right")

        lg = ttk.LabelFrame(self, text="Registro attività")
        lg.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.t_log = tk.Text(lg, height=10, state="disabled", wrap="word")
        sb = ttk.Scrollbar(lg, command=self.t_log.yview)
        self.t_log.configure(yscrollcommand=sb.set)
        self.t_log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _ssl_changed(self):
        if self.v_port.get() in ("993", "143", ""):
            self.v_port.set("993" if self.v_ssl.get() else "143")

    # ------------------------------------------------------------ config
    def _load_into_ui(self):
        c = self.cfg
        self.v_server.set(c["imap_server"])
        self.v_port.set(str(c["imap_port"]))
        self.v_ssl.set(c["imap_ssl"])
        self.v_user.set(c["imap_user"])
        self.v_pass.set(core.get_secret("imap_password"))
        self.v_imapfolder.set(c["imap_folder"])
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
        self.v_nas.set(c["nas_enabled"])
        self.v_naspath.set(c["nas_path"])
        self.v_nasuser.set(c["nas_user"])
        self.v_naspass.set(core.get_secret("nas_password"))
        self.v_nasdomain.set(c["nas_domain"])
        self.v_nasretry.set(str(c.get("nas_retry_minutes", 2)))
        self.v_interval.set(str(c["interval_minutes"]))
        self.v_autostartmon.set(c["auto_start_monitor"])

    def _collect(self):
        c = dict(self.cfg)
        c["imap_server"] = self.v_server.get().strip()
        try:
            c["imap_port"] = int(self.v_port.get())
        except ValueError:
            c["imap_port"] = 993 if self.v_ssl.get() else 143
        c["imap_ssl"] = self.v_ssl.get()
        c["imap_user"] = self.v_user.get().strip()
        c["imap_folder"] = self.v_imapfolder.get().strip() or "INBOX"
        c["senders"] = core.parse_list(self.t_senders.get("1.0", "end"))
        c["local_folders"] = list(self.lb_folders.get(0, "end"))
        c["extensions"] = self.v_ext.get().strip()
        c["ignore_inline"] = self.v_inline.get()
        c["subfolder_per_sender"] = self.v_subsender.get()
        c["subfolder_per_date"] = self.v_subdate.get()
        c["mark_as_read"] = self.v_markread.get()
        c["process_existing"] = self.v_existing.get()
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
        return c

    def save(self, quiet=False):
        self.cfg = self._collect()
        core.save_config(self.cfg)
        core.set_secret("imap_password", self.v_pass.get())
        core.set_secret("nas_password", self.v_naspass.get())
        if not quiet:
            self.log("Impostazioni salvate")

    # ------------------------------------------------------------ cartelle
    def add_folder(self):
        d = filedialog.askdirectory(title="Scegli la cartella dove salvare gli allegati")
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
            try:
                os.startfile(self.lb_folders.get(sel[0]))  # type: ignore[attr-defined]
            except Exception as e:
                messagebox.showerror("Errore", str(e))

    # ------------------------------------------------------------ test
    def _run_bg(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def test_email(self):
        self.save(quiet=True)
        cfg, pw = self.cfg, self.v_pass.get()

        def job():
            try:
                n = core.test_imap(cfg, pw)
                self.log(f"✔ Connessione email riuscita: {n} messaggi in '{cfg['imap_folder']}'")
                self.after(0, lambda: messagebox.showinfo("Email", f"Connessione riuscita.\n{n} messaggi nella cartella."))
            except Exception as e:
                msg = str(e)
                self.log(f"✖ Connessione email fallita: {msg}")
                self.after(0, lambda: messagebox.showerror("Email", f"Connessione fallita:\n{msg}"))
        self._run_bg(job)

    def test_nas(self):
        self.save(quiet=True)
        cfg, pw = self.cfg, self.v_naspass.get()

        def job():
            nas = None
            try:
                nas = core.NasClient(cfg, pw)
                files = nas.test()
                self.log(f"✔ NAS raggiungibile: {nas.base} ({len(files)} elementi)")
                self.after(0, lambda: messagebox.showinfo("NAS", f"Connessione riuscita a\n{nas.base}"))
            except Exception as e:
                msg = str(e)
                self.log(f"✖ NAS non raggiungibile: {msg}")
                self.after(0, lambda: messagebox.showerror("NAS", f"Connessione fallita:\n{msg}"))
            finally:
                if nas:
                    nas.close()
        self._run_bg(job)

    # ------------------------------------------------------------ controllo
    def _do_check(self):
        if not self.check_lock.acquire(blocking=False):
            return
        try:
            n = core.check_mail(self.cfg, core.get_secret("imap_password"),
                                core.get_secret("nas_password"), log=self.log)
            self.log(f"Controllo completato: {n} allegati salvati" if n else "Controllo completato: nessun nuovo allegato")
        except Exception as e:
            self.log(f"ERRORE: {e}")
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
                self.log(f"ERRORE coda NAS: {e}")
            mins = max(1, int(self.cfg.get("nas_retry_minutes", 2) or 2))
            self.retry_wake.wait(mins * 60)
            self.retry_wake.clear()

    def flush_now(self):
        self.save(quiet=True)
        if not self.cfg.get("nas_enabled"):
            messagebox.showinfo("NAS", "Attiva prima il caricamento sul NAS.")
            return
        if not core.queue_count():
            self.log("Coda NAS vuota: niente da inviare")
            return
        self.retry_wake.set()

    def clear_queue(self):
        n = core.queue_count()
        if not n:
            messagebox.showinfo("Coda NAS", "La coda è già vuota.")
            return
        if messagebox.askyesno("Svuota coda",
                               f"Eliminare {n} file in attesa di invio al NAS?\n"
                               "Le copie nelle cartelle locali NON vengono toccate."):
            core.queue_clear()
            self.log(f"Coda NAS svuotata ({n} file eliminati)")

    def _update_queue_label(self):
        try:
            n = core.queue_count()
            self.v_queue.set(f"File in attesa di invio al NAS: {n}" if n else "Nessun file in attesa")
        except Exception:
            pass
        self.after(5000, self._update_queue_label)

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
                self.after(0, lambda: self.v_status.set(f"Monitoraggio attivo · prossimo controllo {nxt}"))
                self.stop_event.wait(mins * 60)

        self.worker = threading.Thread(target=loop, daemon=True)
        self.worker.start()
        self.btn_mon.configure(text="■ Ferma monitoraggio")
        self.v_status.set("Monitoraggio attivo")
        self.log(f"Monitoraggio avviato (ogni {self.cfg['interval_minutes']} minuti)")

    def stop_monitor(self):
        self.stop_event.set()
        self.btn_mon.configure(text="▶ Avvia monitoraggio")
        self.v_status.set("Monitoraggio fermo")
        self.log("Monitoraggio fermato")

    def reset_state(self):
        if messagebox.askyesno("Ricomincia",
                               "Il programma dimenticherà quali email ha già visto.\n"
                               "Al prossimo controllo si comporterà come al primo avvio. Continuare?"):
            core.reset_state()
            self.log("Stato azzerato")

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
                    self.log("Avvio automatico con Windows attivato")
                else:
                    try:
                        winreg.DeleteValue(k, core.APP_NAME)
                    except FileNotFoundError:
                        pass
                    self.log("Avvio automatico con Windows disattivato")
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile modificare l'avvio automatico:\n{e}")

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

    def _on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Esci", "Il monitoraggio è attivo: chiudendo si ferma.\n"
                                               "Vuoi davvero uscire? (Puoi anche ridurre a icona)"):
                return
        self.save(quiet=True)
        self.stop_event.set()
        self.destroy()


if __name__ == "__main__":
    if not core.disclaimer_accepted():
        if not show_disclaimer():
            sys.exit(0)
        core.accept_disclaimer()
    App(auto="--auto" in sys.argv).mainloop()
