"""
Traduzioni dell'interfaccia. Le frasi sono scritte in italiano nel codice;
T() restituisce la traduzione inglese quando la lingua scelta e' 'en'.
"""
LANG = "it"


def set_language(lang):
    global LANG
    LANG = "en" if str(lang).lower().startswith("en") else "it"


def T(text):
    if LANG == "en":
        return EN.get(text, text)
    return text


EN = {}  # riempito da i18n_en.py

try:
    from i18n_en import EN as _EN
    EN.update(_EN)
except Exception:  # pragma: no cover
    pass
