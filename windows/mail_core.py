"""
Motore di MailAllegati: controlla una casella IMAP, filtra i mittenti scelti,
salva gli allegati in una o piu' cartelle locali e (opzionale) li carica su un NAS (SMB).
Nessuna dipendenza dall'interfaccia grafica: si puo' usare anche da riga di comando.
"""
import email
import email.policy
import imaplib
import json
import os
import re
import socket
import ssl
import time
from email.header import decode_header, make_header
from email.utils import getaddresses

from i18n import T

APP_NAME = "MailAllegati"
APP_VERSION = "1.4.1"
BLOCK_PAUSE_MINUTES = 30
GITHUB_REPO = "sirjoe58/MAILALLEGATI"
APP_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
STATE_FILE = os.path.join(APP_DIR, "stato.json")
LOG_FILE = os.path.join(APP_DIR, "registro.txt")
RECENT_FILE = os.path.join(APP_DIR, "ultimi_file.json")
BILLS_FILE = os.path.join(APP_DIR, "bollette.json")

DEFAULT_CONFIG = {
    "imap_server": "",
    "imap_port": 993,
    "imap_ssl": True,
    "imap_user": "",
    "imap_folder": "INBOX",
    "senders": [],              # indirizzi o domini (es. "fatture@ditta.it", "@ditta.it")
    "local_folders": [],        # una o piu' cartelle di destinazione
    "extensions": "",           # es. "pdf, xml, jpg" (vuoto = tutti)
    "ignore_inline": True,      # ignora immagini incorporate (loghi delle firme)
    "subfolder_per_sender": False,
    "subfolder_per_date": False,
    "mark_as_read": False,
    "process_existing": False,  # al primo avvio elabora anche le email gia' presenti
    "nas_enabled": False,
    "nas_path": "",             # es. \\192.168.1.10\condivisa\allegati
    "nas_user": "",
    "nas_domain": "",
    "nas_retry_minutes": 2,     # ogni quanto riprovare l'invio dei file in coda
    "interval_minutes": 5,
    "auto_start_monitor": False,
    # novita' 1.3
    "subject_keywords": "",     # salva solo se l'oggetto contiene una di queste parole (vuoto = tutte)
    "rename_enabled": True,     # rinomina i file con data e mittente
    "rename_template": "{data}_{mittente}_{nome}",
    "skip_duplicates": True,    # non salvare di nuovo un file identico gia' salvato
    "tray_icon": True,          # icona accanto all'orologio di Windows
    "notify_saved": True,       # notifica di Windows quando salva un allegato
    # novita' 1.4
    "accounts": [],             # piu' caselle email: [{name, server, port, ssl, user, folder}]
    "language": "it",           # "it" oppure "en"
    "check_updates": True,      # avvisa se su GitHub c'e' una versione nuova
    "bills_enabled": False,     # legge importo e scadenza dalle bollette PDF
    "bills_excel": "",          # foglio Excel riepilogativo (vuoto = cartella predefinita)
    "bills_remind_days": 3,     # avviso N giorni prima della scadenza
}

# ---------------------------------------------------------------- password

KEYRING_SERVICE = APP_NAME
try:
    import keyring  # Gestione credenziali di Windows
    _HAS_KEYRING = True
except Exception:  # pragma: no cover
    _HAS_KEYRING = False


def set_secret(name, value):
    if _HAS_KEYRING:
        try:
            if value:
                keyring.set_password(KEYRING_SERVICE, name, value)
            else:
                try:
                    keyring.delete_password(KEYRING_SERVICE, name)
                except Exception:
                    pass
            return
        except Exception:
            pass
    # ripiego: file locale (meno sicuro)
    data = _load_json(os.path.join(APP_DIR, "segreti.json"), {})
    data[name] = value
    _save_json(os.path.join(APP_DIR, "segreti.json"), data)


def get_secret(name):
    if _HAS_KEYRING:
        try:
            v = keyring.get_password(KEYRING_SERVICE, name)
            if v is not None:
                return v
        except Exception:
            pass
    return _load_json(os.path.join(APP_DIR, "segreti.json"), {}).get(name, "")


# ---------------------------------------------------------------- file json

def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    saved = _load_json(CONFIG_FILE, {})
    cfg.update(saved)
    if "language" not in saved:          # primo avvio: lingua del sistema
        cfg["language"] = system_language()
    return cfg


def system_language():
    try:
        import locale
        lang = (locale.getlocale()[0] or "") or (os.environ.get("LANG") or "")
        if os.name == "nt":
            import ctypes
            lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return "it" if (lid & 0x3FF) == 0x10 else "en"
        return "it" if lang.lower().startswith(("it", "italian")) else "en"
    except Exception:
        return "it"


def save_config(cfg):
    _save_json(CONFIG_FILE, cfg)


# ---------------------------------------------------------------- utilita'

def decode_str(value):
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def safe_filename(name):
    name = decode_str(name).replace("\r", "").replace("\n", "")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    if not name:
        name = "allegato"
    if len(name) > 180:
        base, ext = os.path.splitext(name)
        name = base[: 180 - len(ext)] + ext
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
    if os.path.splitext(name)[0].upper() in reserved:
        name = "_" + name
    return name


def parse_list(text):
    """Accetta lista o testo con un elemento per riga / separati da virgola o ;"""
    if isinstance(text, list):
        items = text
    else:
        items = re.split(r"[\n,;]+", text or "")
    return [i.strip() for i in items if i.strip()]


def split_rule(line):
    """'@enel.it = BOLLETTE\\Luce' -> ('@enel.it', 'BOLLETTE\\Luce'). Senza '=' la cartella e' ''."""
    if "=" in line:
        pat, folder = line.split("=", 1)
        return pat.strip(), folder.strip()
    return line.strip(), ""


def rule_parts(folder):
    """Cartella della regola -> elenco di sottocartelle sicure (niente '..', niente lettere di unita')."""
    parts = []
    for p in re.split(r"[\\/]+", folder or ""):
        p = p.strip()
        if not p or p in (".", "..") or p.endswith(":"):
            continue
        parts.append(safe_filename(p))
    return parts


def _pattern_matches(addr, s):
    s = s.lower().strip()
    if not s:
        return False
    if s.startswith("@"):
        return addr.endswith(s)
    if "@" in s:
        return addr == s
    return s in addr  # parte di indirizzo o dominio senza @


def sender_rule(from_header, senders):
    """Restituisce (trovato, indirizzo, cartella_regola)."""
    addrs = [a.lower() for _, a in getaddresses([decode_str(from_header)]) if a]
    for addr in addrs:
        for line in senders or []:
            pat, folder = split_rule(line)
            if _pattern_matches(addr, pat):
                return True, addr, folder
    return False, (addrs[0] if addrs else ""), ""


def sender_matches(from_header, senders):
    ok, addr, _ = sender_rule(from_header, senders)
    return ok, addr


def unique_path(folder, filename):
    base, ext = os.path.splitext(filename)
    path = os.path.join(folder, filename)
    n = 1
    while os.path.exists(path):
        path = os.path.join(folder, f"{base} ({n}){ext}")
        n += 1
    return path


def extract_attachments(msg, cfg):
    """Restituisce lista di (nome_file, bytes)."""
    exts = [e.lower().lstrip(".") for e in parse_list(cfg.get("extensions", "").replace(" ", ","))]
    result = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        disp = (part.get("Content-Disposition") or "").lower()
        is_attachment = disp.startswith("attachment")
        if not filename:
            if not is_attachment:
                continue
            ext = (part.get_content_subtype() or "bin")
            filename = f"allegato.{ext}"
        if cfg.get("ignore_inline", True) and not is_attachment and part.get("Content-ID") \
                and part.get_content_maintype() == "image":
            continue
        filename = safe_filename(filename)
        if exts:
            ext = os.path.splitext(filename)[1].lower().lstrip(".")
            if ext not in exts:
                continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        result.append((filename, payload))
    return result


# ---------------------------------------------------------------- nomi file, filtri, doppioni

def sender_label(from_header, addr):
    """Nome breve del mittente: il nome visualizzato (es. 'Enel Energia') oppure il dominio (es. 'Enel')."""
    from email.utils import parseaddr
    name, _ = parseaddr(decode_str(from_header))
    name = (name or "").strip().strip('"').strip("'").strip()
    if not name or "@" in name:
        domain = (addr or "").split("@")[-1].lower()
        parts = [x for x in domain.split(".") if x]
        if len(parts) >= 3 and parts[-2] in ("co", "com", "gov", "ac"):
            name = parts[-3]
        elif len(parts) >= 2:
            name = parts[-2]
        else:
            name = parts[0] if parts else "mittente"
        name = name.capitalize()
    name = re.sub(r"\s+", "_", name)
    return safe_filename(name)[:30].strip("_") or "mittente"


def email_date(date_header):
    from email.utils import parsedate_to_datetime
    try:
        d = parsedate_to_datetime(decode_str(date_header))
        if d is not None:
            return d.strftime("%Y-%m-%d")
    except Exception:
        pass
    return time.strftime("%Y-%m-%d")


def build_filename(template, original, data, mittente, oggetto=""):
    """Applica il modello: {data} {mittente} {nome} {oggetto}. L'estensione originale resta."""
    base, ext = os.path.splitext(original)
    template = (template or "").strip() or "{data}_{mittente}_{nome}"
    out = (template.replace("{data}", data).replace("{mittente}", mittente)
           .replace("{nome}", base).replace("{oggetto}", re.sub(r"\s+", "_", oggetto.strip())[:40]))
    out = safe_filename(out)
    out = re.sub(r"_{2,}", "_", out).strip("_ .")
    if not out:
        out = base or "allegato"
    if ext and out.lower().endswith(ext.lower()):
        return out
    return out + ext


def subject_matches(subject, keywords):
    kws = [k.lower() for k in parse_list(keywords)]
    if not kws:
        return True
    s = (subject or "").lower()
    return any(k in s for k in kws)


HASH_LIMIT = 5000


def file_hash(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- NAS (SMB)

def parse_nas_path(path):
    """Converte \\\\server\\share\\sub, //server/share/sub o smb://server/share/sub in (server, unc)."""
    p = (path or "").strip()
    p = re.sub(r"^smb://", "", p, flags=re.I)
    p = p.replace("/", "\\").strip("\\")
    parts = [x for x in p.split("\\") if x]
    if len(parts) < 2:
        raise ValueError(T("Percorso NAS non valido. Esempio: \\\\192.168.1.10\\cartella_condivisa\\allegati"))
    server = parts[0]
    port = 445
    if ":" in server:
        server, port_s = server.rsplit(":", 1)
        port_s = port_s.strip()
        if port_s:
            if not port_s.isdigit():
                raise ValueError(T("Porta NAS non valida: '{}'").format(port_s))
            port = int(port_s)
    if not server:
        raise ValueError(T("Percorso NAS non valido: manca l'indirizzo del NAS"))
    unc = "\\\\" + server + "\\" + "\\".join(parts[1:])
    return server, port, unc


def friendly_nas_error(server, port, err):
    """Traduce gli errori di rete/SMB in un messaggio comprensibile."""
    t = str(err)
    low = t.lower()
    if any(k in low for k in ("timed out", "10060", "winerror 53", "winerror 64",
                              "no route", "unreachable", "10065", "10061", "connection refused")):
        return T("Il NAS {} non risponde come cartella condivisa (porta {}). Controlla che il NAS sia acceso, "
                 "che l'indirizzo sia giusto e che sul NAS sia attiva la condivisione file Windows/SMB.").format(server, port) \
            + " [{}]".format(t[:150])
    if any(k in low for k in ("logon_failure", "access_denied", "access is denied", "accesso negato",
                              "winerror 5]", "winerror 1326", "winerror 86", "password", "1326")):
        return T("Utente o password del NAS non accettati, oppure l'utente non ha i permessi sulla cartella.") + f" [{t[:150]}]"
    if any(k in low for k in ("bad_network_name", "winerror 67", "network name")):
        return T("La cartella condivisa indicata non esiste sul NAS: controlla il nome dopo l'indirizzo.") + f" [{t[:150]}]"
    return t


class NasClient:
    """Scrive sul NAS. Su Windows usa prima la condivisione di rete del sistema
    (funziona con qualsiasi NAS che si apre da Esplora file), altrimenti il client SMB integrato."""

    def __init__(self, cfg, password):
        self.cfg = cfg
        self.password = password
        self.server, self.port, self.base = parse_nas_path(cfg["nas_path"])
        self.mode = None   # "windows" oppure "smb"

    # --- modalita' Windows (come Esplora file)
    def _share_root(self):
        parts = [x for x in self.base.split("\\") if x]
        return "\\\\" + parts[0] + "\\" + parts[1]

    def _native_connect(self):
        user = (self.cfg.get("nas_user") or "").strip()
        if user:
            if self.cfg.get("nas_domain"):
                user = self.cfg["nas_domain"].strip() + "\\" + user
            import subprocess
            subprocess.run(["net", "use", self._share_root(), self.password or "", "/user:" + user,
                            "/persistent:no"], capture_output=True, timeout=40,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        os.makedirs(self.base, exist_ok=True)
        os.listdir(self.base)

    # --- modalita' SMB integrata
    def _smb_connect(self):
        import smbclient
        user = self.cfg.get("nas_user") or None
        if user and self.cfg.get("nas_domain"):
            user = self.cfg["nas_domain"] + "\\" + user
        smbclient.register_session(self.server, username=user, password=self.password or None,
                                   port=self.port, connection_timeout=15,
                                   auth_protocol="ntlm" if user else "negotiate",
                                   require_signing=False)
        smbclient.makedirs(self.base, exist_ok=True, port=self.port)

    def _connect(self):
        if self.mode:
            return
        errors = []
        if os.name == "nt" and self.port == 445:
            try:
                self._native_connect()
                self.mode = "windows"
                return
            except Exception as e:
                errors.append(e)
        try:
            self._smb_connect()
            self.mode = "smb"
            return
        except Exception as e:
            errors.append(e)
        # l'errore piu' significativo e' di solito il primo (quello di Windows)
        raise ConnectionError(friendly_nas_error(self.server, self.port, errors[0]))

    def test(self):
        self._connect()
        if self.mode == "windows":
            return os.listdir(self.base)
        import smbclient
        return smbclient.listdir(self.base, port=self.port)

    def upload(self, rel_dir, filename, data):
        """Carica prima con nome temporaneo e poi rinomina: niente file a meta' se il NAS cade."""
        self._connect()
        target_dir = self.base
        if rel_dir:
            target_dir = target_dir + "\\" + rel_dir.replace("/", "\\")
        base, ext = os.path.splitext(filename)
        tmp = target_dir + "\\" + filename + ".parziale"
        target = target_dir + "\\" + filename
        if self.mode == "windows":
            os.makedirs(target_dir, exist_ok=True)
            with open(tmp, "wb") as f:
                f.write(data)
            n = 1
            while os.path.exists(target):
                target = f"{target_dir}\\{base} ({n}){ext}"
                n += 1
            os.rename(tmp, target)
            return target
        import smbclient
        smbclient.makedirs(target_dir, exist_ok=True, port=self.port)
        with smbclient.open_file(tmp, mode="wb", port=self.port) as f:
            f.write(data)
        n = 1
        while smbclient.path.exists(target, port=self.port):
            target = f"{target_dir}\\{base} ({n}){ext}"
            n += 1
        smbclient.rename(tmp, target, port=self.port)
        return target

    def close(self):
        if self.mode == "smb":
            try:
                import smbclient
                smbclient.reset_connection_cache()
            except Exception:
                pass
        self.mode = None


# ---------------------------------------------------------------- coda NAS
# Se il NAS e' spento o irraggiungibile, gli allegati vengono messi in coda qui
# e inviati automaticamente appena il NAS torna raggiungibile.

import threading
import uuid

QUEUE_DIR = os.path.join(APP_DIR, "coda_nas")
_queue_lock = threading.Lock()


def queue_add(rel_dir, filename, data):
    item = os.path.join(QUEUE_DIR, f"{time.time_ns():020d}_{uuid.uuid4().hex[:6]}")
    os.makedirs(item, exist_ok=True)
    with open(os.path.join(item, "dati.bin"), "wb") as f:
        f.write(data)
    _save_json(os.path.join(item, "info.json"),
               {"rel_dir": rel_dir, "name": filename, "added": time.strftime("%Y-%m-%d %H:%M:%S")})


def _queue_items():
    if not os.path.isdir(QUEUE_DIR):
        return []
    items = []
    for d in sorted(os.listdir(QUEUE_DIR)):
        full = os.path.join(QUEUE_DIR, d)
        if os.path.exists(os.path.join(full, "info.json")) and os.path.exists(os.path.join(full, "dati.bin")):
            items.append(full)
    return items


def queue_count():
    return len(_queue_items())


def queue_clear():
    import shutil
    with _queue_lock:
        shutil.rmtree(QUEUE_DIR, ignore_errors=True)


def flush_queue(cfg, nas_password, log=print, nas_factory=None):
    """Prova a inviare al NAS i file in coda. Restituisce (inviati, rimasti)."""
    import shutil
    if not cfg.get("nas_enabled") or not cfg.get("nas_path"):
        return 0, queue_count()
    if not _queue_lock.acquire(blocking=False):
        return 0, queue_count()
    sent = 0
    nas = None
    try:
        items = _queue_items()
        if not items:
            return 0, 0
        try:
            nas = (nas_factory or NasClient)(cfg, nas_password)
        except Exception as e:
            log(T("Percorso NAS non valido: {}").format(e))
            return 0, len(items)
        for item in items:
            info = _load_json(os.path.join(item, "info.json"), {})
            try:
                with open(os.path.join(item, "dati.bin"), "rb") as f:
                    data = f.read()
                target = nas.upload(info.get("rel_dir", ""), info.get("name", "allegato"), data)
            except Exception as e:
                log(T("NAS ancora non raggiungibile ({}): {} file in attesa").format(short_error(e), len(items) - sent))
                break
            shutil.rmtree(item, ignore_errors=True)
            sent += 1
            log(T("Inviato al NAS dalla coda: {}").format(target))
        if sent:
            rest = queue_count()
            log(T("Coda NAS: {} file inviati").format(sent)
                + (T(", {} ancora in attesa").format(rest) if rest else T(", coda vuota")))
    finally:
        if nas:
            nas.close()
        _queue_lock.release()
    return sent, queue_count()


class BlockedError(Exception):
    """Il server di posta ha bloccato la connessione (blacklist, IP sospetto, VPN)."""


_BLOCK_WORDS = ("[alert]", "rbl", "blacklist", "blocklist", "blocked", "banned")


def is_block_error(e):
    t = str(e).lower()
    return any(w in t for w in _BLOCK_WORDS)


def block_message(acc_name=""):
    base = T("Il server di posta ha bloccato la connessione (blacklist). Spegni la VPN se e' attiva: "
             "i controlli sono sospesi per {} minuti. Con 'Controlla ora' puoi riprovare subito dopo aver spento la VPN.")
    base = base.format(BLOCK_PAUSE_MINUTES)
    return (acc_name + ": " if acc_name else "") + base


def short_error(e):
    t = str(e) or e.__class__.__name__
    return t if len(t) < 120 else t[:117] + "..."


# ---------------------------------------------------------------- IMAP

def imap_connect(cfg, password):
    server = cfg["imap_server"].strip()
    port = int(cfg.get("imap_port") or (993 if cfg.get("imap_ssl", True) else 143))
    socket.setdefaulttimeout(30)
    if cfg.get("imap_ssl", True):
        conn = imaplib.IMAP4_SSL(server, port, ssl_context=ssl.create_default_context())
    else:
        conn = imaplib.IMAP4(server, port)
        try:
            conn.starttls(ssl_context=ssl.create_default_context())
        except Exception:
            pass
    conn.login(cfg["imap_user"].strip(), password)
    return conn


def _quote_folder(name):
    name = name or "INBOX"
    if re.search(r'[\s"()]', name):
        return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return name


def test_imap(cfg, password):
    conn = imap_connect(cfg, password)
    try:
        typ, data = conn.select(_quote_folder(cfg.get("imap_folder")), readonly=True)
        if typ != "OK":
            raise RuntimeError(T("Cartella '{}' non trovata").format(cfg.get('imap_folder')))
        return int(data[0])
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def check_mail(cfg, imap_password, nas_password="", log=print, nas_factory=None, on_saved=None):
    """Esegue un controllo. Restituisce il numero di allegati salvati."""
    if not disclaimer_accepted():
        raise RuntimeError(T("Le avvertenze d'uso non sono state accettate"))
    senders = parse_list(cfg.get("senders", []))
    folders = [f for f in parse_list(cfg.get("local_folders", []))]
    if not cfg.get("imap_server") or not cfg.get("imap_user"):
        raise RuntimeError(T("Configura server e utente email"))
    if not senders:
        raise RuntimeError(T("Inserisci almeno un mittente da controllare"))
    if not folders and not cfg.get("nas_enabled"):
        raise RuntimeError(T("Scegli almeno una cartella di destinazione o attiva il NAS"))

    prefix = f"[{cfg.get('imap_user', '')}] " if cfg.get("_multi") else ""
    state = _load_json(STATE_FILE, {})
    hashes = state.get("_hashes", [])
    hash_set = set(hashes)
    key = f"{cfg['imap_user'].lower()}@{cfg['imap_server'].lower()}/{cfg.get('imap_folder') or 'INBOX'}"
    st = state.get(key, {})

    # prima di tutto prova a svuotare la coda del NAS
    if cfg.get("nas_enabled") and queue_count():
        flush_queue(cfg, nas_password, log, nas_factory)
    nas_down = bool(cfg.get("nas_enabled") and queue_count())  # se c'e' ancora coda, il NAS e' giu'

    conn = imap_connect(cfg, imap_password)
    nas = None
    saved = 0
    try:
        typ, _ = conn.select(_quote_folder(cfg.get("imap_folder")), readonly=not cfg.get("mark_as_read"))
        if typ != "OK":
            raise RuntimeError(T("Cartella '{}' non trovata").format(cfg.get('imap_folder')))
        uidvalidity = None
        try:
            r = conn.response("UIDVALIDITY")[1]
            uidvalidity = r[0].decode() if r and r[0] else None
        except Exception:
            pass

        if st.get("uidvalidity") != uidvalidity:
            st = {"uidvalidity": uidvalidity, "last_uid": None}

        typ, data = conn.uid("SEARCH", None, "ALL")
        all_uids = [int(x) for x in (data[0] or b"").split()] if typ == "OK" else []

        if st.get("last_uid") is None:
            if cfg.get("process_existing"):
                st["last_uid"] = 0
                log(prefix + T("Primo avvio: elaboro anche le email già presenti"))
            else:
                st["last_uid"] = max(all_uids) if all_uids else 0
                state[key] = st
                _save_json(STATE_FILE, state)
                log(prefix + T("Primo avvio: da ora in poi verranno elaborate solo le nuove email"))
                return 0

        new_uids = [u for u in all_uids if u > st["last_uid"]]
        if not new_uids:
            return 0

        for uid in new_uids:
            typ, hdr = conn.uid("FETCH", str(uid), "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if typ != "OK" or not hdr or not isinstance(hdr[0], tuple):
                st["last_uid"] = uid
                continue
            h = email.message_from_bytes(hdr[0][1], policy=email.policy.compat32)
            ok, addr, rule_folder = sender_rule(h.get("From", ""), senders)
            subject = decode_str(h.get("Subject", ""))
            if ok and not subject_matches(subject, cfg.get("subject_keywords", "")):
                log(T("Email da {} \"{}\": l'oggetto non contiene le parole scelte, ignorata").format(addr, subject))
                ok = False
            if ok:
                fetch_cmd = "(RFC822)" if cfg.get("mark_as_read") else "(BODY.PEEK[])"
                typ, full = conn.uid("FETCH", str(uid), fetch_cmd)
                raw = None
                for item in full or []:
                    if isinstance(item, tuple):
                        raw = item[1]
                        break
                if raw:
                    msg = email.message_from_bytes(raw, policy=email.policy.compat32)
                    atts = extract_attachments(msg, cfg)
                    if not atts:
                        log(T("Email da {} \"{}\": nessun allegato").format(addr, subject))
                    else:
                        rel = rule_parts(rule_folder)
                        if cfg.get("subfolder_per_sender"):
                            rel.append(safe_filename(addr))
                        if cfg.get("subfolder_per_date"):
                            rel.append(time.strftime("%Y-%m"))
                        rel_dir = os.path.join(*rel) if rel else ""
                        mittente = sender_label(h.get("From", ""), addr)
                        data_mail = email_date(h.get("Date", ""))
                        for name, payload in atts:
                            hsh = file_hash(payload)
                            if cfg.get("skip_duplicates", True) and hsh in hash_set:
                                log(T("Doppione già salvato in precedenza, saltato: {}").format(name))
                                continue
                            if cfg.get("rename_enabled", True):
                                name = build_filename(cfg.get("rename_template"), name, data_mail, mittente, subject)
                            first_path = ""
                            for folder in folders:
                                dest = os.path.join(folder, rel_dir) if rel_dir else folder
                                os.makedirs(dest, exist_ok=True)
                                path = unique_path(dest, name)
                                with open(path, "wb") as f:
                                    f.write(payload)
                                first_path = first_path or path
                                log(T("Salvato: {}").format(path))
                            if cfg.get("nas_enabled"):
                                nas_rel = rel_dir.replace(os.sep, "\\")
                                uploaded = False
                                if not nas_down:
                                    try:
                                        if nas is None:
                                            nas = (nas_factory or NasClient)(cfg, nas_password)
                                        t = nas.upload(nas_rel, name, payload)
                                        first_path = first_path or t
                                        log(T("Caricato su NAS: {}").format(t))
                                        uploaded = True
                                    except Exception as e:
                                        nas_down = True
                                        log(T("NAS non raggiungibile ({}): i file verranno inviati appena torna disponibile").format(short_error(e)))
                                if not uploaded:
                                    queue_add(nas_rel, name, payload)
                                    log(T("In coda per il NAS: {}").format(name))
                                    if not first_path:
                                        first_path = cfg.get("nas_path", "").rstrip("\\/") + "\\" + \
                                            (nas_rel + "\\" if nas_rel else "") + name
                            saved += 1
                            add_recent(name, first_path, mittente, subject)
                            if cfg.get("bills_enabled") and name.lower().endswith(".pdf"):
                                process_bill(cfg, payload, hsh, name, first_path, mittente.replace("_", " "), data_mail, log)
                            if hsh not in hash_set:
                                hash_set.add(hsh)
                                hashes.append(hsh)
                                if len(hashes) > HASH_LIMIT:
                                    hash_set.discard(hashes.pop(0))
                                state["_hashes"] = hashes
                            if on_saved:
                                try:
                                    on_saved(name)
                                except Exception:
                                    pass
            st["last_uid"] = uid
            state[key] = st
            _save_json(STATE_FILE, state)
    finally:
        state[key] = st
        _save_json(STATE_FILE, state)
        try:
            conn.logout()
        except Exception:
            pass
        if nas:
            nas.close()
    return saved


# ---------------------------------------------------------------- piu' caselle email

def account_key(acc):
    return f"{(acc.get('user') or '').strip().lower()}@{(acc.get('server') or '').strip().lower()}"


def get_accounts(cfg):
    """Elenco delle caselle. Le configurazioni precedenti (una sola casella) vengono convertite."""
    accs = [a for a in (cfg.get("accounts") or []) if isinstance(a, dict)]
    if not accs and cfg.get("imap_server"):
        accs = [{"name": cfg.get("imap_user") or cfg.get("imap_server"), "server": cfg.get("imap_server", ""),
                 "port": cfg.get("imap_port", 993), "ssl": cfg.get("imap_ssl", True),
                 "user": cfg.get("imap_user", ""), "folder": cfg.get("imap_folder", "INBOX"), "enabled": True}]
    return accs


def account_password(acc):
    pw = get_secret("imap_password:" + account_key(acc))
    return pw if pw else get_secret("imap_password")  # versioni precedenti: una sola password


def set_account_password(acc, value):
    set_secret("imap_password:" + account_key(acc), value)


def account_cfg(cfg, acc, multi=False):
    c = dict(cfg)
    c.update({"imap_server": acc.get("server", ""), "imap_port": int(acc.get("port") or 993),
              "imap_ssl": bool(acc.get("ssl", True)), "imap_user": acc.get("user", ""),
              "imap_folder": acc.get("folder") or "INBOX", "_multi": multi})
    return c


def check_all(cfg, nas_password="", log=print, on_saved=None, nas_factory=None):
    """Controlla tutte le caselle attive. Un errore su una casella non ferma le altre."""
    accs = [a for a in get_accounts(cfg) if a.get("enabled", True)]
    if not accs:
        raise RuntimeError(T("Configura server e utente email"))
    total = 0
    multi = len(accs) > 1
    blocked = []
    for acc in accs:
        try:
            total += check_mail(account_cfg(cfg, acc, multi), account_password(acc), nas_password,
                                log=log, nas_factory=nas_factory, on_saved=on_saved)
        except Exception as e:
            name = acc.get("name") or acc.get("user")
            if is_block_error(e):
                blocked.append(block_message(name if multi else ""))
                continue
            if not multi:
                raise
            log(T("ERRORE casella {}: {}").format(name, e))
    if blocked:
        raise BlockedError("\n".join(blocked))
    return total


# ---------------------------------------------------------------- ultimi file salvati

RECENT_LIMIT = 200
_recent_lock = threading.Lock()


def add_recent(name, path, sender="", subject=""):
    with _recent_lock:
        items = _load_json(RECENT_FILE, [])
        items.insert(0, {"time": time.strftime("%Y-%m-%d %H:%M"), "name": name, "path": path,
                         "sender": sender, "subject": subject})
        _save_json(RECENT_FILE, items[:RECENT_LIMIT])


def recent_files():
    return _load_json(RECENT_FILE, [])


def clear_recent():
    with _recent_lock:
        _save_json(RECENT_FILE, [])


# ---------------------------------------------------------------- bollette

def bills_store():
    import bills
    return bills.BillStore(BILLS_FILE)


def bills_excel_path(cfg):
    p = (cfg.get("bills_excel") or "").strip()
    if p:
        return p
    folders = parse_list(cfg.get("local_folders", []))
    base = folders[0] if folders else APP_DIR
    return os.path.join(base, T("Bollette") + ".xlsx")


def bill_labels():
    return {"sheet": T("Bollette"), "email_date": T("Data email"), "sender": T("Mittente"), "amount": T("Importo"),
            "due": T("Scadenza"), "status": T("Stato"), "file": T("File"), "path": T("Percorso"),
            "paid": T("Pagata"), "overdue": T("Scaduta"), "to_pay": T("Da pagare"), "unknown": T("Da verificare"),
            "total_to_pay": T("Totale da pagare")}


def update_bills_excel(cfg, log=print):
    import bills
    path = bills_excel_path(cfg)
    try:
        bills.write_excel(bills_store().load(), path, bill_labels())
        return path
    except PermissionError:
        log(T("Il foglio Excel delle bollette è aperto: lo aggiorno al prossimo controllo ({})").format(path))
    except Exception as e:
        log(T("Impossibile aggiornare il foglio Excel delle bollette: {}").format(e))
    return None


def process_bill(cfg, payload, hsh, name, path, sender, email_day, log=print):
    import bills
    try:
        amount, due = bills.analyze_pdf(payload)
    except Exception:
        amount, due = None, None
    if amount is None and due is None:
        return
    rec = {"hash": hsh, "sender": sender, "amount": amount, "due": due.isoformat() if due else None,
           "email_date": email_day, "file": name, "path": path, "paid": False}
    if bills_store().add(rec):
        euro = (f"{amount:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")) if amount is not None else "?"
        log(T("Bolletta registrata: {} – importo {} – scadenza {}").format(
            name, euro, due.strftime("%d/%m/%Y") if due else "?"))
        update_bills_excel(cfg, log)


# ---------------------------------------------------------------- aggiornamenti

def _ver_tuple(v):
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:3]) + (0,) * (3 - len(nums[:3]))


def check_update(timeout=10):
    """Restituisce (versione, pagina) se su GitHub c'e' una versione piu' recente, altrimenti None."""
    import urllib.request
    req = urllib.request.Request(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                                 headers={"Accept": "application/vnd.github+json",
                                          "User-Agent": f"{APP_NAME}/{APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    tag = data.get("tag_name") or ""
    if _ver_tuple(tag) > _ver_tuple(APP_VERSION):
        return tag.lstrip("v"), data.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases/latest"
    return None


# ---------------------------------------------------------------- backup impostazioni

def export_settings(cfg, path):
    """Salva le impostazioni in un file. Le password NON sono incluse."""
    data = {"app": APP_NAME, "version": APP_VERSION, "exported": time.strftime("%Y-%m-%d %H:%M"),
            "settings": {k: v for k, v in cfg.items() if not k.startswith("_")}}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def import_settings(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or data.get("app") != APP_NAME or not isinstance(data.get("settings"), dict):
        raise ValueError(T("Il file scelto non è un backup di MailAllegati"))
    cfg = dict(DEFAULT_CONFIG)
    cfg.update({k: v for k, v in data["settings"].items() if k in DEFAULT_CONFIG})
    save_config(cfg)
    return cfg


# ---------------------------------------------------------------- avvertenze

DISCLAIMER_VERSION = 2
DISCLAIMER_FILE_NAME = "LEGGIMI_AVVERTENZE.txt"
DISCLAIMER_FILE_NAME_EN = "WARNINGS_EN.txt"
ACCEPT_FILE = os.path.join(APP_DIR, "accettazione.json")


def disclaimer_path(name=None):
    """Cerca il file avvertenze accanto al programma (o dentro l'exe)."""
    import sys
    import i18n
    if name is None:
        if i18n.LANG == "en":
            p = disclaimer_path(DISCLAIMER_FILE_NAME_EN)
            if p:
                return p
        name = DISCLAIMER_FILE_NAME
    dirs = []
    if getattr(sys, "frozen", False):
        dirs.append(os.path.dirname(sys.executable))
        dirs.append(getattr(sys, "_MEIPASS", ""))
    dirs.append(os.path.dirname(os.path.abspath(__file__)))
    for d in dirs:
        p = os.path.join(d, name)
        if d and os.path.exists(p):
            return p
    return None


def disclaimer_text():
    p = disclaimer_path()
    if not p:
        return None
    with open(p, "r", encoding="utf-8-sig") as f:
        return f.read().replace("\r\n", "\n")


def disclaimer_accepted():
    return _load_json(ACCEPT_FILE, {}).get("version", 0) >= DISCLAIMER_VERSION


def accept_disclaimer():
    _save_json(ACCEPT_FILE, {"version": DISCLAIMER_VERSION,
                             "accepted_at": time.strftime("%Y-%m-%d %H:%M:%S")})


def reset_state():
    try:
        os.remove(STATE_FILE)
    except FileNotFoundError:
        pass
