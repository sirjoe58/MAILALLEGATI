"""
Bollette: legge importo e scadenza dai PDF salvati, li conserva in un archivio,
crea un foglio Excel riepilogativo e segnala le scadenze in arrivo.
L'estrazione e' basata su regole (parole chiave): funziona con i PDF che contengono
testo leggibile; con i PDF scansionati (immagini) non trova nulla.
"""
import datetime as _dt
import io
import json
import os
import re
import threading

_lock = threading.Lock()

MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6, "luglio": 7,
    "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

_NUM = r"(\d{1,3}(?:[.\s']\d{3})*(?:,\d{2})|\d+,\d{2}|\d{1,3}(?:,\d{3})*\.\d{2}|\d+\.\d{2})"
_CUR = r"(?:€|eur(?:o|i)?\b)?"
# parole chiave dell'importo, in ordine di affidabilita'
_AMOUNT_KEYS = [
    r"totale\s+da\s+pagare", r"importo\s+da\s+pagare", r"totale\s+(?:bolletta|fattura|documento|dovuto|importo)",
    r"importo\s+totale", r"da\s+pagare", r"totale\s+a\s+pagare", r"importo\s+(?:dovuto|addebitato|bolletta|fattura)",
    r"amount\s+due", r"total\s+due", r"balance\s+due", r"total\s+amount", r"totale",
]
_DUE_KEYS = r"(?:data\s+(?:di\s+)?scadenza|scadenza(?:\s+pagamento)?|scade\s+il|da\s+pagare\s+entro(?:\s+il)?|" \
            r"pagare\s+entro(?:\s+il)?|pagamento\s+entro(?:\s+il)?|entro\s+il|due\s+date|payment\s+due|due\s+by|due\s+on)"


def pdf_text(data, max_pages=6):
    try:
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(data))
        parts = []
        for page in r.pages[:max_pages]:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                pass
        return "\n".join(parts)
    except Exception:
        return ""


def _to_float(s):
    s = s.replace(" ", "").replace("'", "")
    if "," in s and (s.rfind(",") > s.rfind(".")):
        s = s.replace(".", "").replace(",", ".")       # 1.234,56
    else:
        s = s.replace(",", "")                          # 1,234.56
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def find_amount(text):
    t = re.sub(r"[ \t ]+", " ", text)
    for key in _AMOUNT_KEYS:
        rx = re.compile(key + r"[^\d\n€]{0,40}(?:\n[^\d\n€]{0,40})?" + _CUR + r"\s*" + _NUM + r"\s*" + _CUR, re.I)
        for m in rx.finditer(t):
            v = _to_float(m.group(1))
            if v is not None and 0 < v < 100000:
                return v
    return None


def _mk_date(d, m, y):
    y = int(y)
    if y < 100:
        y += 2000
    try:
        return _dt.date(y, int(m), int(d))
    except ValueError:
        return None


def find_due_date(text):
    t = re.sub(r"[ \t ]+", " ", text)
    num = re.compile(_DUE_KEYS + r"[^\d\n]{0,30}(?:\n[^\d\n]{0,30})?(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})", re.I)
    words = re.compile(_DUE_KEYS + r"[^\d\n]{0,30}(\d{1,2})\s+(" + "|".join(MONTHS) + r")\s+(\d{4})", re.I)
    found = []
    for m in num.finditer(t):
        d = _mk_date(m.group(1), m.group(2), m.group(3))
        if d:
            found.append((m.start(), d))
    for m in words.finditer(t):
        d = _mk_date(m.group(1), MONTHS[m.group(2).lower()], m.group(3))
        if d:
            found.append((m.start(), d))
    if not found:
        return None
    found.sort()
    today = _dt.date.today()
    plausible = [d for _, d in found if today - _dt.timedelta(days=400) <= d <= today + _dt.timedelta(days=400)]
    return (plausible or [found[0][1]])[0]


def analyze_pdf(data):
    """Restituisce (importo, scadenza) oppure (None, None)."""
    text = pdf_text(data)
    if not text.strip():
        return None, None
    return find_amount(text), find_due_date(text)


# ---------------------------------------------------------------- archivio

class BillStore:
    def __init__(self, path):
        self.path = path

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def save(self, items):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=1, ensure_ascii=False)
        os.replace(tmp, self.path)

    def add(self, rec):
        with _lock:
            items = self.load()
            if any(i.get("hash") == rec.get("hash") for i in items):
                return False
            items.append(rec)
            self.save(items)
            return True

    def update(self, hash_, **fields):
        with _lock:
            items = self.load()
            for i in items:
                if i.get("hash") == hash_:
                    i.update(fields)
            self.save(items)

    def remove(self, hash_):
        with _lock:
            self.save([i for i in self.load() if i.get("hash") != hash_])

    def due_soon(self, days):
        """Bollette non pagate con scadenza entro 'days' giorni e non ancora segnalate oggi."""
        today = _dt.date.today()
        out = []
        with _lock:
            items = self.load()
            changed = False
            for i in items:
                if i.get("paid") or not i.get("due"):
                    continue
                try:
                    due = _dt.date.fromisoformat(i["due"])
                except ValueError:
                    continue
                left = (due - today).days
                if left <= days and i.get("reminded") != today.isoformat() and left >= -30:
                    out.append((i, left))
                    i["reminded"] = today.isoformat()
                    changed = True
            if changed:
                self.save(items)
        return out


def write_excel(items, path, labels):
    """Crea/aggiorna il foglio Excel. labels: dict di intestazioni tradotte."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = labels.get("sheet", "Bollette")[:31]
    head = [labels["email_date"], labels["sender"], labels["amount"], labels["due"], labels["status"],
            labels["file"], labels["path"]]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F6F8B")
        c.alignment = Alignment(vertical="center")

    def key(i):
        return (i.get("due") or "9999", i.get("email_date") or "")

    today = _dt.date.today()
    for i in sorted(items, key=key):
        due = None
        if i.get("due"):
            try:
                due = _dt.date.fromisoformat(i["due"])
            except ValueError:
                pass
        email_d = None
        if i.get("email_date"):
            try:
                email_d = _dt.date.fromisoformat(i["email_date"])
            except ValueError:
                pass
        if i.get("paid"):
            status = labels["paid"]
        elif due and due < today:
            status = labels["overdue"]
        elif due:
            status = labels["to_pay"]
        else:
            status = labels["unknown"]
        ws.append([email_d, i.get("sender", ""), i.get("amount"), due, status, i.get("file", ""), i.get("path", "")])
        r = ws.max_row
        ws.cell(r, 1).number_format = "DD/MM/YYYY"
        ws.cell(r, 4).number_format = "DD/MM/YYYY"
        ws.cell(r, 3).number_format = '#,##0.00 "€"'
        if status == labels["overdue"]:
            ws.cell(r, 5).font = Font(bold=True, color="C0392B")
        elif status == labels["paid"]:
            ws.cell(r, 5).font = Font(color="2E8B57")
    n = ws.max_row
    ws.auto_filter.ref = "A1:G{}".format(max(1, n))
    if n > 1:
        ws.append([])
        ws.append(["", labels["total_to_pay"],
                   "=SUMIFS(C2:C{n},E2:E{n},\"<>{paid}\")".format(n=n, paid=labels["paid"])])
        ws.cell(ws.max_row, 2).font = Font(bold=True)
        ws.cell(ws.max_row, 3).font = Font(bold=True)
        ws.cell(ws.max_row, 3).number_format = '#,##0.00 "€"'
    widths = [13, 22, 13, 13, 14, 44, 60]
    for idx, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = w
    ws.freeze_panes = "A2"
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp.xlsx"
    wb.save(tmp)
    os.replace(tmp, path)
