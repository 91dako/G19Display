# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 DaKo-Soft
# G19 Einstellungen: Oberflaeche fuer den G19-Helfer (einstellungen.json + tasten.json)
import os, sys, json, time, shutil, subprocess, threading, winreg
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser
import psutil, requests

BASE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(BASE, "einstellungen.json")
KEYS_PATH = os.path.join(BASE, "tasten.json")
KAL_TXT = os.path.join(BASE, "kalender_url.txt")
WA_SCRIPT = os.path.join(BASE, "whatsapp_waechter.py")
WA_STATUS = os.path.join(BASE, "whatsapp_status.json")
WA_EVENT = os.path.join(BASE, "whatsapp_event.json")
WA_PROFILE = os.path.join(BASE, "whatsapp_profil")
HELPER = os.path.join(BASE, "g19_display.py")
PYW = sys.executable.replace("python.exe", "pythonw.exe")
NOWIN = 0x08000000
ALL_VIEWS = ["Uhr", "Musik", "Netzwerk", "System", "Wetter", "Bilder", "Kalender"]
def default_pics():
    home = os.path.expanduser("~")
    for p in (os.path.join(home, "Pictures"), os.path.join(home, "Bilder")):
        if os.path.isdir(p): return p
    return os.path.join(home, "Pictures")

DEFAULTS = {
    "ansichten": [{"name": v, "aktiv": True} for v in ALL_VIEWS],
    "bilder_ordner": default_pics(), "bilder_intervall": 10,
    "wetter": {"ort": "Berlin", "lat": 52.52, "lon": 13.405},
    "kalender_url": "",
    "helligkeit_setzen": False, "helligkeit": 100,
    "tastatur_farbe_setzen": False, "tastatur_farbe": "#FFFFFF",
    "whatsapp": {"aktiv": False, "dauer": 3, "absender_anzeigen": True, "text_anzeigen": False, "fenster_sichtbar": False},
}
WA_TEXT = {"warte_auf_qr": "Warte auf QR-Code-Scan im Browserfenster …", "angemeldet_sync": "Angemeldet – synchronisiere …",
           "angemeldet": "Angemeldet ✓ (Überwachung startet gleich)", "verbunden": "Verbunden ✓ – überwacht neue Nachrichten",
           "nicht_angemeldet": "Nicht angemeldet – bitte neu verbinden", "abgebrochen": "Anmeldung abgebrochen",
           "aus": "Aus", "fehler": "Fehler"}

def merge(d, u):
    for k, v in u.items():
        if isinstance(v, dict) and isinstance(d.get(k), dict): merge(d[k], v)
        else: d[k] = v
    return d

def load_json(p, default):
    try:
        with open(p, encoding="utf-8-sig") as f: return json.load(f)
    except Exception: return default

def write_json(p, obj):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)

def procs(name):
    out = []
    for p in psutil.process_iter(["cmdline"]):
        try:
            if name in " ".join(p.info["cmdline"] or []): out.append(p)
        except Exception: pass
    return out

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("G19 Einstellungen"); self.geometry("620x560"); self.minsize(560, 500)
        ico = os.path.join(BASE, "g19_einstellungen.ico")
        if os.path.exists(ico):
            try: self.iconbitmap(ico)
            except Exception: pass
        st = ttk.Style(self)
        try: st.theme_use("vista")
        except Exception: pass
        self.cfg = merge(json.loads(json.dumps(DEFAULTS)), load_json(CFG_PATH, {}))
        if not self.cfg.get("kalender_url") and os.path.exists(KAL_TXT):
            self.cfg["kalender_url"] = open(KAL_TXT, encoding="utf-8-sig").read().strip()
        self.keys = load_json(KEYS_PATH, {})
        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        for title, fn in (("Ansichten", self.tab_views), ("Bilder", self.tab_pics), ("Wetter", self.tab_weather),
                          ("Kalender", self.tab_cal), ("G-Tasten", self.tab_keys), ("Display", self.tab_display),
                          ("WhatsApp", self.tab_wa)):
            f = ttk.Frame(nb, padding=12); nb.add(f, text=title); fn(f)
        bot = ttk.Frame(self, padding=(8, 4, 8, 8)); bot.pack(fill="x")
        self.helper_lbl = ttk.Label(bot, text=""); self.helper_lbl.pack(side="left")
        ttk.Button(bot, text="Schließen", command=self.close).pack(side="right")
        ttk.Button(bot, text="Speichern", command=self.save).pack(side="right", padx=6)
        ttk.Button(bot, text="Helfer neu starten", command=self.restart_helper).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.saved = self.snapshot()
        self.tick()

    # ---------- Ansichten ----------
    def tab_views(self, f):
        ttk.Label(f, text="Welche Ansichten sollen auf dem Display erscheinen, und in welcher Reihenfolge?\n"
                          "(Wechseln am Display mit den Pfeiltasten)").pack(anchor="w")
        row = ttk.Frame(f); row.pack(fill="both", expand=True, pady=8)
        self.lb = tk.Listbox(row, height=9, font=("Segoe UI", 11), activestyle="none", exportselection=False)
        self.lb.pack(side="left", fill="both", expand=True)
        self.lb.bind("<Double-Button-1>", lambda e: self.toggle_view())
        names = [a["name"] for a in self.cfg["ansichten"] if a.get("name") in ALL_VIEWS]
        self.views = [dict(a) for a in self.cfg["ansichten"] if a.get("name") in ALL_VIEWS]
        self.views += [{"name": v, "aktiv": True} for v in ALL_VIEWS if v not in names]
        side = ttk.Frame(row); side.pack(side="left", fill="y", padx=8)
        ttk.Button(side, text="▲ Nach oben", command=lambda: self.move_view(-1)).pack(fill="x")
        ttk.Button(side, text="▼ Nach unten", command=lambda: self.move_view(1)).pack(fill="x", pady=4)
        ttk.Button(side, text="An / Aus", command=self.toggle_view).pack(fill="x", pady=(12, 0))
        ttk.Button(side, text="Standard", command=self.reset_views).pack(fill="x", pady=(24, 0))
        self.fill_views()
    def fill_views(self, sel=None):
        self.lb.delete(0, "end")
        for a in self.views: self.lb.insert("end", ("  ☑  " if a["aktiv"] else "  ☐  ") + a["name"])
        if sel is not None: self.lb.selection_set(sel); self.lb.see(sel)
    def sel(self):
        s = self.lb.curselection(); return s[0] if s else None
    def move_view(self, d):
        i = self.sel()
        if i is None or not 0 <= i + d < len(self.views): return
        self.views[i], self.views[i + d] = self.views[i + d], self.views[i]; self.fill_views(i + d)
    def toggle_view(self):
        i = self.sel()
        if i is None: return
        if self.views[i]["aktiv"] and sum(a["aktiv"] for a in self.views) == 1:
            messagebox.showinfo("G19", "Mindestens eine Ansicht muss aktiv bleiben."); return
        self.views[i]["aktiv"] = not self.views[i]["aktiv"]; self.fill_views(i)
    def reset_views(self):
        self.views = [{"name": v, "aktiv": True} for v in ALL_VIEWS]; self.fill_views()

    # ---------- Bilder ----------
    def tab_pics(self, f):
        ttk.Label(f, text="Ordner für die Diashow (Unterordner inklusive, nur lokal gespeicherte Bilder):").pack(anchor="w")
        r = ttk.Frame(f); r.pack(fill="x", pady=6)
        self.v_pics = tk.StringVar(value=self.cfg["bilder_ordner"])
        ttk.Entry(r, textvariable=self.v_pics).pack(side="left", fill="x", expand=True)
        ttk.Button(r, text="Durchsuchen …", command=self.pick_dir).pack(side="left", padx=6)
        r = ttk.Frame(f); r.pack(fill="x", pady=10)
        ttk.Label(r, text="Bild wechseln alle").pack(side="left")
        self.v_int = tk.IntVar(value=int(self.cfg["bilder_intervall"]))
        ttk.Spinbox(r, from_=2, to=3600, width=6, textvariable=self.v_int).pack(side="left", padx=6)
        ttk.Label(r, text="Sekunden   (OK-Taste am Display = nächstes Bild)").pack(side="left")
    def pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.v_pics.get() or os.path.expanduser("~"))
        if d: self.v_pics.set(os.path.normpath(d))

    # ---------- Wetter ----------
    def tab_weather(self, f):
        w = self.cfg["wetter"]
        ttk.Label(f, text="Ort für die Wetter-Ansicht (Daten von open-meteo.com):").pack(anchor="w")
        r = ttk.Frame(f); r.pack(fill="x", pady=6)
        self.v_ort = tk.StringVar(value=w["ort"])
        e = ttk.Entry(r, textvariable=self.v_ort); e.pack(side="left", fill="x", expand=True)
        e.bind("<Return>", lambda ev: self.geo())
        ttk.Button(r, text="Ort suchen", command=self.geo).pack(side="left", padx=6)
        self.geo_res = []; self.v_geo = tk.StringVar()
        self.cb_geo = ttk.Combobox(f, textvariable=self.v_geo, state="readonly")
        self.cb_geo.pack(fill="x", pady=4); self.cb_geo.bind("<<ComboboxSelected>>", self.geo_pick)
        r = ttk.Frame(f); r.pack(fill="x", pady=8)
        self.v_lat, self.v_lon = tk.StringVar(value=str(w["lat"])), tk.StringVar(value=str(w["lon"]))
        ttk.Label(r, text="Breite").pack(side="left"); ttk.Entry(r, textvariable=self.v_lat, width=10).pack(side="left", padx=(4, 16))
        ttk.Label(r, text="Länge").pack(side="left"); ttk.Entry(r, textvariable=self.v_lon, width=10).pack(side="left", padx=4)
    def geo(self):
        q = self.v_ort.get().strip()
        if not q: return
        try:
            r = requests.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": q, "count": 8, "language": "de"}, timeout=10).json()
            self.geo_res = r.get("results") or []
        except Exception as ex: messagebox.showerror("Wetter", f"Suche fehlgeschlagen:\n{ex}"); return
        if not self.geo_res: messagebox.showinfo("Wetter", "Kein Ort gefunden."); return
        self.cb_geo["values"] = [f"{g['name']}, {g.get('admin1', '')}, {g.get('country', '')}".replace(", ,", ",") for g in self.geo_res]
        self.cb_geo.current(0); self.geo_pick()
    def geo_pick(self, *_):
        i = self.cb_geo.current()
        if i < 0: return
        g = self.geo_res[i]; self.v_ort.set(g["name"]); self.v_lat.set(f"{g['latitude']:.4f}"); self.v_lon.set(f"{g['longitude']:.4f}")

    # ---------- Kalender ----------
    def tab_cal(self, f):
        ttk.Label(f, text="Google Kalender – „Privatadresse im iCal-Format“\n"
                          "(Google Kalender → Einstellungen → dein Kalender → Kalender integrieren):", justify="left").pack(anchor="w")
        self.v_kal = tk.StringVar(value=self.cfg.get("kalender_url", ""))
        ttk.Entry(f, textvariable=self.v_kal).pack(fill="x", pady=8)
        ttk.Label(f, text="Leer lassen = Kalender-Ansicht zeigt „nicht verbunden“.", foreground="#666").pack(anchor="w")

    # ---------- G-Tasten ----------
    def tab_keys(self, f):
        r = ttk.Frame(f); r.pack(fill="x")
        ttk.Label(r, text="Modus:").pack(side="left")
        self.v_mode = tk.StringVar(value="M1"); self.cur_mode = "M1"
        cb = ttk.Combobox(r, textvariable=self.v_mode, values=["M1", "M2", "M3"], state="readonly", width=5)
        cb.pack(side="left", padx=6); cb.bind("<<ComboboxSelected>>", self.mode_changed)
        ttk.Label(r, text="(umschalten mit M1/M2/M3 auf der Tastatur)", foreground="#666").pack(side="left")
        g = ttk.Frame(f); g.pack(fill="x", pady=8)
        self.key_vars = {}
        for i in range(12):
            n = f"G{i+1}"; v = tk.StringVar(); self.key_vars[n] = v
            ttk.Label(g, text=n, width=4).grid(row=i % 6, column=(i // 6) * 2, sticky="w", pady=2)
            ttk.Entry(g, textvariable=v, width=22).grid(row=i % 6, column=(i // 6) * 2 + 1, sticky="w", padx=(0, 20), pady=2)
        self.load_mode()
        ttk.Label(f, justify="left", foreground="#555", wraplength=560, text=
                  "Beispiele: F13   CTRL+C   CTRL+SHIFT+ESC   ALT+TAB   WIN+D   PLAYPAUSE   VOLUP\n"
                  "Mögliche Tasten: A–Z, 0–9, F1–F24, CTRL, SHIFT, ALT, WIN, ENTER, SPACE, TAB, ESC, BACKSPACE, DEL, INS, "
                  "HOME, END, PGUP, PGDN, LEFT, RIGHT, UP, DOWN, PLAYPAUSE, NEXT, PREV, MUTE, VOLUP, VOLDOWN, PRINT").pack(anchor="w")
    def load_mode(self):
        m = self.keys.get(self.cur_mode, {})
        for n, v in self.key_vars.items(): v.set(m.get(n, ""))
    def store_mode(self):
        self.keys.setdefault(self.cur_mode, {})
        for n, v in self.key_vars.items(): self.keys[self.cur_mode][n] = v.get().strip().upper()
    def mode_changed(self, *_):
        self.store_mode(); self.cur_mode = self.v_mode.get(); self.load_mode()

    # ---------- Display ----------
    def tab_display(self, f):
        self.v_bs = tk.BooleanVar(value=self.cfg["helligkeit_setzen"]); self.v_b = tk.IntVar(value=int(self.cfg["helligkeit"]))
        ttk.Checkbutton(f, text="Display-Helligkeit festlegen", variable=self.v_bs).pack(anchor="w")
        r = ttk.Frame(f); r.pack(fill="x", pady=4)
        self.lbl_b = ttk.Label(r, text="", width=6)
        ttk.Scale(r, from_=0, to=100, variable=self.v_b, command=lambda v: self.lbl_b.config(text=f"{int(float(v))} %")).pack(side="left", fill="x", expand=True)
        self.lbl_b.pack(side="left", padx=6); self.lbl_b.config(text=f"{self.v_b.get()} %")
        ttk.Separator(f).pack(fill="x", pady=14)
        self.v_cs = tk.BooleanVar(value=self.cfg["tastatur_farbe_setzen"]); self.v_c = tk.StringVar(value=self.cfg["tastatur_farbe"])
        ttk.Checkbutton(f, text="Tastatur-Beleuchtungsfarbe festlegen", variable=self.v_cs).pack(anchor="w")
        r = ttk.Frame(f); r.pack(fill="x", pady=4)
        self.swatch = tk.Label(r, width=6, bg=self.v_c.get(), relief="groove"); self.swatch.pack(side="left")
        ttk.Button(r, text="Farbe wählen …", command=self.pick_color).pack(side="left", padx=8)
        ttk.Label(f, foreground="#666", wraplength=560, justify="left", text=
                  "\nHinweis: Helligkeit und Farbe werden direkt an die G19 geschickt. Falls sich am Display nichts ändert, "
                  "unterstützt der Treiber-Ersatz das an dieser Stelle nicht – dann einfach wieder ausschalten.").pack(anchor="w")
    def pick_color(self):
        c = colorchooser.askcolor(color=self.v_c.get(), title="Tastaturfarbe")[1]
        if c: self.v_c.set(c.upper()); self.swatch.config(bg=c)

    # ---------- WhatsApp ----------
    def tab_wa(self, f):
        w = self.cfg["whatsapp"]
        self.v_wa = tk.BooleanVar(value=w["aktiv"]); self.v_wd = tk.DoubleVar(value=float(w["dauer"]))
        self.v_wn = tk.BooleanVar(value=w["absender_anzeigen"]); self.v_wt = tk.BooleanVar(value=w["text_anzeigen"])
        self.v_wf = tk.BooleanVar(value=w.get("fenster_sichtbar", False))
        ttk.Checkbutton(f, text="WhatsApp-Benachrichtigung auf dem G19-Display anzeigen", variable=self.v_wa).pack(anchor="w")
        r = ttk.Frame(f); r.pack(fill="x", pady=6)
        ttk.Label(r, text="Popup anzeigen für").pack(side="left")
        ttk.Spinbox(r, from_=1, to=30, increment=0.5, width=5, textvariable=self.v_wd).pack(side="left", padx=6)
        ttk.Label(r, text="Sekunden").pack(side="left")
        ttk.Checkbutton(f, text="Absender-Name anzeigen", variable=self.v_wn).pack(anchor="w")
        ttk.Checkbutton(f, text="Nachrichtentext anzeigen (nur wenn WhatsApp ihn liefert)", variable=self.v_wt).pack(anchor="w")
        ttk.Checkbutton(f, text="WhatsApp-Browserfenster sichtbar lassen (nur zur Fehlersuche)", variable=self.v_wf).pack(anchor="w")
        box = ttk.LabelFrame(f, text="Verbindung", padding=10); box.pack(fill="x", pady=12)
        self.wa_lbl = ttk.Label(box, text="", font=("Segoe UI", 10, "bold")); self.wa_lbl.pack(anchor="w")
        r = ttk.Frame(box); r.pack(fill="x", pady=(8, 0))
        ttk.Button(r, text="Mit WhatsApp verbinden (QR-Code) …", command=self.wa_login).pack(side="left")
        ttk.Button(r, text="Test-Popup", command=self.wa_test).pack(side="left", padx=6)
        ttk.Button(r, text="Abmelden", command=self.wa_logout).pack(side="right")
        ttk.Label(f, foreground="#555", wraplength=560, justify="left", text=
                  "So geht's: „Mit WhatsApp verbinden“ öffnet ein Chrome-Fenster mit WhatsApp Web. Am Handy WhatsApp → "
                  "Einstellungen → Verknüpfte Geräte → Gerät hinzufügen → QR-Code scannen. Das Fenster schließt sich nach "
                  "ca. 20 Sekunden von selbst. Danach läuft WhatsApp unsichtbar im Hintergrund weiter und das Display zeigt "
                  "bei jeder neuen Nachricht das WhatsApp-Symbol.").pack(anchor="w")

    def wa_login(self):
        if not self.v_wa.get(): self.v_wa.set(True)
        self.save(quiet=True)
        if procs("whatsapp_waechter.py --login"): messagebox.showinfo("WhatsApp", "Das Anmeldefenster ist schon offen."); return
        subprocess.Popen([PYW, WA_SCRIPT, "--login"], cwd=BASE, creationflags=NOWIN)
        self.wa_lbl.config(text="Browserfenster wird geöffnet …")
    def wa_test(self):
        write_json(WA_EVENT, {"t": time.time(), "name": "Test – G19 Einstellungen", "text": "Das ist ein Test-Popup.", "quelle": "test"})
        if not procs("g19_display.py"): messagebox.showwarning("WhatsApp", "Der G19-Helfer läuft gerade nicht – bitte „Helfer neu starten“.")
    def wa_logout(self):
        if not messagebox.askyesno("WhatsApp", "WhatsApp auf diesem PC abmelden und gespeicherte Sitzung löschen?\n"
                                               "(Auf dem Handy unter „Verknüpfte Geräte“ ggf. auch entfernen.)"): return
        self.v_wa.set(False); self.save(quiet=True)
        for p in procs("whatsapp_waechter.py"):
            try: p.terminate(); p.wait(8)
            except Exception: pass
        time.sleep(1)
        shutil.rmtree(WA_PROFILE, ignore_errors=True)
        try: os.remove(WA_STATUS)
        except Exception: pass
        self.wa_lbl.config(text="Abgemeldet")

    # ---------- Speichern / Helfer ----------
    def collect(self):
        c = json.loads(json.dumps(self.cfg))
        c["ansichten"] = [dict(a) for a in self.views]
        c["bilder_ordner"] = self.v_pics.get().strip()
        try: c["bilder_intervall"] = max(2, int(self.v_int.get()))
        except Exception: pass
        try: c["wetter"] = {"ort": self.v_ort.get().strip() or "?", "lat": float(self.v_lat.get().replace(",", ".")), "lon": float(self.v_lon.get().replace(",", "."))}
        except ValueError: raise ValueError("Breite/Länge beim Wetter sind keine Zahlen.")
        c["kalender_url"] = self.v_kal.get().strip()
        c["helligkeit_setzen"], c["helligkeit"] = bool(self.v_bs.get()), int(self.v_b.get())
        c["tastatur_farbe_setzen"], c["tastatur_farbe"] = bool(self.v_cs.get()), self.v_c.get()
        try: dauer = max(0.5, min(60, float(self.v_wd.get())))
        except Exception: dauer = 3
        c["whatsapp"] = {"aktiv": bool(self.v_wa.get()), "dauer": dauer, "absender_anzeigen": bool(self.v_wn.get()),
                         "text_anzeigen": bool(self.v_wt.get()), "fenster_sichtbar": bool(self.v_wf.get())}
        self.store_mode()
        return c
    def snapshot(self):
        try: return json.dumps([self.collect(), self.keys], sort_keys=True)
        except Exception: return None
    def save(self, quiet=False):
        try: c = self.collect()
        except ValueError as ex: messagebox.showerror("G19", str(ex)); return False
        if c["whatsapp"].get("fenster_sichtbar") != self.cfg["whatsapp"].get("fenster_sichtbar"):
            for p in procs("whatsapp_waechter.py"):          # Waechter mit neuer Sichtbarkeit neu starten
                if "--login" not in " ".join(p.cmdline()): p.terminate()
        write_json(CFG_PATH, c); self.cfg = c
        write_json(KEYS_PATH, self.keys)
        if c["kalender_url"]:
            with open(KAL_TXT, "w", encoding="utf-8") as f: f.write(c["kalender_url"])
        self.saved = self.snapshot()
        if not quiet: self.flash("Gespeichert ✓ – das Display übernimmt die Änderungen in ca. 2 Sekunden.")
        return True
    def flash(self, t):
        self.helper_lbl.config(text=t); self.after(4000, lambda: self.helper_lbl.config(text=""))
    def restart_helper(self):
        for p in procs("g19_display.py"):
            try: p.terminate(); p.wait(5)
            except Exception: pass
        cmd = None
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                cmd = winreg.QueryValueEx(k, "G19Helfer")[0]
        except OSError: pass
        time.sleep(1)
        subprocess.Popen(cmd if cmd else [PYW, HELPER], cwd=BASE, creationflags=NOWIN)
        self.flash("G19-Helfer neu gestartet ✓")
    def tick(self):
        st = load_json(WA_STATUS, {})
        s = st.get("status", "")
        txt = WA_TEXT.get(s, "Noch nicht verbunden" if not os.path.isdir(WA_PROFILE) else "Gespeicherte Sitzung vorhanden")
        if s == "verbunden" and "ungelesen" in st: txt += f"  (ungelesen: {st['ungelesen']})"
        if s == "fehler": txt += ": " + st.get("fehler", "")[:80]
        if s in ("verbunden", "warte_auf_qr", "angemeldet_sync") and not psutil.pid_exists(int(st.get("pid", 0) or 0)):
            txt = "Gespeicherte Sitzung vorhanden (Überwachung läuft gerade nicht)" if os.path.isdir(WA_PROFILE) else "Noch nicht verbunden"
        self.wa_lbl.config(text="Status: " + txt)
        self.after(2000, self.tick)
    def close(self):
        if self.snapshot() != self.saved:
            r = messagebox.askyesnocancel("G19", "Änderungen speichern?")
            if r is None: return
            if r and not self.save(quiet=True): return
        self.destroy()

def ctypes_dpi():
    import ctypes; ctypes.windll.shcore.SetProcessDpiAwareness(1)

if __name__ == "__main__":
    import ctypes
    ctypes.windll.kernel32.CreateMutexW(None, False, "G19Einstellungen_einmalig")
    if ctypes.windll.kernel32.GetLastError() == 183: sys.exit(0)
    try: ctypes_dpi()
    except Exception: pass
    App().mainloop()
