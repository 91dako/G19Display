# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 DaKo-Soft
# Vier Stream-Deck-Felder. Physisch das obere Drittel der G-Tasten:
#   G1 G7
#   G2 G8

DECK_KEYS = ("G1", "G7", "G2", "G8")
ORT = {"G1": "oben links", "G7": "oben rechts", "G2": "darunter links", "G8": "darunter rechts"}

# id, Anzeigename, Glyphe, Schrift ("mdl2" = Segoe MDL2 Assets, "ui" = Segoe UI)
ICONS = [
    ("leer", "Leer", "", "mdl2"),
    ("kopieren", "Kopieren", "\uE8C8", "mdl2"),
    ("einfuegen", "Einfügen", "\uE77F", "mdl2"),
    ("ausschneiden", "Ausschneiden", "\uE8C6", "mdl2"),
    ("loeschen", "Löschen", "\uE74D", "mdl2"),
    ("rueckgaengig", "Rückgängig", "\uE7A7", "mdl2"),
    ("wiederholen", "Wiederholen", "\uE7A6", "mdl2"),
    ("markieren", "Markieren", "\uE73E", "mdl2"),
    ("speichern", "Speichern", "\uE74E", "mdl2"),
    ("enter", "Enter", "\u21B5", "ui"),
    ("escape", "Escape", "\uE711", "mdl2"),
    ("fenster", "Fenster", "\uE7C4", "mdl2"),
    ("desktop", "Desktop", "\uE7F4", "mdl2"),
    ("task", "Task-Manager", "\uE9D9", "mdl2"),
    ("ordner", "Ordner", "\uED25", "mdl2"),
    ("app", "Programm", "\uECAA", "mdl2"),
    ("web", "Webseite", "\uE774", "mdl2"),
    ("play", "Play", "\uE768", "mdl2"),
    ("next", "Weiter", "\uE893", "mdl2"),
    ("prev", "Zurück", "\uE892", "mdl2"),
    ("volup", "Lauter", "\uE767", "mdl2"),
    ("voldown", "Leiser", "\uE992", "mdl2"),
    ("mute", "Stumm", "\uE74F", "mdl2"),
    ("kamera", "Foto", "\uE722", "mdl2"),
    ("refresh", "Aktualisieren", "\uE895", "mdl2"),
    ("text", "Text", "\uE8D2", "mdl2"),
    ("taste", "Tastatur", "\uE765", "mdl2"),
]

AKTIONEN = [
    ("taste", "Tastenkürzel"),
    ("programm", "Programm öffnen"),
    ("ordner", "Ordner öffnen"),
    ("web", "Webseite öffnen"),
    ("text", "Text einfügen"),
    ("keine", "Keine Aktion"),
]

WERT_LABEL = {
    "taste": "Kürzel", "programm": "Programm", "ordner": "Ordner",
    "web": "Adresse", "text": "Text", "keine": "Ziel",
}

# name, icon, aktion, wert
PRESETS = [
    ("Kopieren", "kopieren", "taste", "CTRL+C"),
    ("Einfügen", "einfuegen", "taste", "CTRL+V"),
    ("Ausschneiden", "ausschneiden", "taste", "CTRL+X"),
    ("Löschen", "loeschen", "taste", "DEL"),
    ("Rückgängig", "rueckgaengig", "taste", "CTRL+Z"),
    ("Wiederholen", "wiederholen", "taste", "CTRL+Y"),
    ("Alles markieren", "markieren", "taste", "CTRL+A"),
    ("Speichern", "speichern", "taste", "CTRL+S"),
    ("Enter", "enter", "taste", "ENTER"),
    ("Escape", "escape", "taste", "ESC"),
    ("Fenster wechseln", "fenster", "taste", "ALT+TAB"),
    ("Desktop anzeigen", "desktop", "taste", "WIN+D"),
    ("Task-Manager", "task", "taste", "CTRL+SHIFT+ESC"),
    ("Explorer", "ordner", "programm", "explorer.exe"),
    ("Play / Pause", "play", "taste", "PLAYPAUSE"),
    ("Nächster Titel", "next", "taste", "NEXT"),
    ("Vorheriger Titel", "prev", "taste", "PREV"),
    ("Lauter", "volup", "taste", "VOLUP"),
    ("Leiser", "voldown", "taste", "VOLDOWN"),
    ("Stumm", "mute", "taste", "MUTE"),
    ("Bildschirmfoto", "kamera", "taste", "PRINT"),
    ("Aktualisieren", "refresh", "taste", "F5"),
    ("Programm öffnen …", "app", "programm", ""),
    ("Ordner öffnen …", "ordner", "ordner", ""),
    ("Webseite öffnen …", "web", "web", ""),
    ("Text einfügen …", "text", "text", ""),
    ("Eigenes Kürzel …", "taste", "taste", ""),
    ("Leeren", "leer", "keine", ""),
]

DEFAULT_SLOTS = [
    {"taste": "G1", "name": "Kopieren", "icon": "kopieren", "bild": "", "aktion": "taste", "wert": "CTRL+C"},
    {"taste": "G7", "name": "Einfügen", "icon": "einfuegen", "bild": "", "aktion": "taste", "wert": "CTRL+V"},
    {"taste": "G2", "name": "Ausschneiden", "icon": "ausschneiden", "bild": "", "aktion": "taste", "wert": "CTRL+X"},
    {"taste": "G8", "name": "Löschen", "icon": "loeschen", "bild": "", "aktion": "taste", "wert": "DEL"},
]

ICON_BY_ID = {i[0]: i for i in ICONS}
ICON_LABEL = {i[0]: i[1] for i in ICONS}
ICON_ID = {i[1]: i[0] for i in ICONS}
AKTION_LABEL = {a[0]: a[1] for a in AKTIONEN}
AKTION_ID = {a[1]: a[0] for a in AKTIONEN}
PRESET_BY_NAME = {p[0]: p for p in PRESETS}
_FIELDS = ("name", "icon", "bild", "aktion", "wert")


def fresh_slots():
    return [dict(s) for s in DEFAULT_SLOTS]


def normalize(raw):
    by = {}
    if isinstance(raw, list):
        for i, item in enumerate(raw[:4]):
            if not isinstance(item, dict):
                continue
            k = item.get("taste") if item.get("taste") in DECK_KEYS else DECK_KEYS[i]
            by[k] = item
    out = []
    for i, taste in enumerate(DECK_KEYS):
        base = dict(DEFAULT_SLOTS[i])
        for field in _FIELDS:
            if field in by.get(taste, {}) and by[taste][field] is not None:
                base[field] = str(by[taste][field])
        base["taste"] = taste
        base["name"] = base["name"].strip()
        base["bild"] = base["bild"].strip()
        base["wert"] = base["wert"].strip()
        if base["aktion"] not in AKTION_LABEL:
            base["aktion"] = "keine"
        if base["icon"] not in ICON_BY_ID:
            base["icon"] = "leer"
        out.append(base)
    return out
